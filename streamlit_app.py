# ======================================================================
# BLUEOCEAN — RAJADAS DE VENTO (versão web / Streamlit)
# Adaptado do app desktop Tkinter original, por Mário Henrique.
# ======================================================================
import io
import json
import math
import os
import re
import shutil
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import folium
import numpy as np
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="BlueOcean — Rajadas de Vento", layout="wide", page_icon="🌬️")

EMPRESA = "BlueOcean"

# ======================================================================
# ARQUIVOS ESTÁTICOS (necessário pro mapa ler os raios via JS sem
# precisar recarregar a página inteira — ver seção "RAIOS AO VIVO")
# ======================================================================
APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

SOM_ALERTA_NOME = "alerta_raio.wav"
_som_origem = os.path.join(APP_DIR, "data", SOM_ALERTA_NOME)
_som_destino = os.path.join(STATIC_DIR, SOM_ALERTA_NOME)
if os.path.exists(_som_origem) and not os.path.exists(_som_destino):
    try:
        shutil.copyfile(_som_origem, _som_destino)
    except Exception:
        pass

RAIOS_JSON_PATH = os.path.join(STATIC_DIR, "raios_live.json")


def _escrever_raios_json(raios_df, celulas_com_trajetoria, atualizado_em_utc, alertas_unidade=None, erro=None, intervalo_raios_seg=30):
    """Grava o estado atual dos raios num JSON estático que o JS do mapa
    fica lendo periodicamente. É isso que permite atualizar só os raios
    sem re-renderizar o mapa (e sem perder zoom / popups abertos)."""
    agora = datetime.now(timezone.utc)
    raios_out = []
    if raios_df is not None and not raios_df.empty:
        for _, r in raios_df.iterrows():
            idade_min = max((agora - r["time"]).total_seconds() / 60, 0) if pd.notna(r["time"]) else 0
            raios_out.append({
                "lat": float(r["lat"]), "lon": float(r["lon"]),
                "idade_min": round(idade_min, 1),
                "hora": utc_para_brasilia(r["time"]).strftime("%H:%M:%S") if pd.notna(r["time"]) else "?",
            })
    celulas_out = []
    for cel in celulas_com_trajetoria:
        traj = cel["trajetoria"]
        celulas_out.append({
            "id": cel["id"],
            "historico": [{"lat": p["lat"], "lon": p["lon"]} for p in cel["historico"]],
            "checkpoints": traj["checkpoints"],
            "vel_kmh": round(traj["vel_kmh"], 1),
            "rumo_texto": traj["rumo_texto"],
        })
    alertas_out = []
    agora_ts = time.time()
    # "novo" fica True só por uma janela curtinha (pouco mais que um ciclo
    # de atualização) logo depois do Python decidir notificar. Isso é o
    # que o JS usa pra saber se deve tocar som/abrir pop-up agora — como a
    # decisão de verdade mora aqui (sobrevive à reconstrução do mapa), o
    # som não repete toda vez que a página é recarregada por outro motivo.
    janela_novo_seg = max(intervalo_raios_seg * 1.5, 20)
    for nome, a in (alertas_unidade or {}).items():
        if a["expira_ts"] <= agora_ts: continue
        alertas_out.append({
            "estacao": nome,
            "nivel": a["nivel"],
            "notificado_ts": a["notificado_ts"],
            "novo": (agora_ts - a["notificado_ts"]) < janela_novo_seg,
            "expira_brasilia": utc_para_brasilia(datetime.fromtimestamp(a["expira_ts"], tz=timezone.utc)).strftime("%H:%M:%S"),
        })
    payload = {
        "raios": raios_out,
        "celulas": celulas_out,
        "alertas": alertas_out,
        "atualizado_em_utc": atualizado_em_utc.isoformat() if atualizado_em_utc else None,
        "atualizado_em_brasilia": utc_para_brasilia(atualizado_em_utc).strftime("%H:%M:%S") if atualizado_em_utc else None,
        "erro": erro,
    }
    try:
        with open(RAIOS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass

# ======================================================================
# CONTATOS POR UNIDADE
# ======================================================================
CONTATOS_UNIDADES = {'REGAP': {'nome': 'REGAP', 'numeros': [{'numero': '(31) 3529 4470'}, {'numero': '(31) 3529 4405'}, {'numero': '(31) 3529 4508'}]}, 'CILEP_CENPES': {'nome': 'CILEP CENPES', 'numeros': [{'numero': '(21) 9 9700 6335'}, {'numero': '(21) 9 7968 0027'}]}, 'TMIB COQUEIROS': {'nome': 'TMIB COQUEIROS', 'numeros': [{'numero': '(79) 3212 5101'}, {'numero': '(79) 9 9630 8427'}]}, 'ARM RIO': {'nome': 'ARM RIO', 'numeros': [{'numero': '(21) 9 6576-0066'}, {'numero': '(21) 9 6576-0142'}, {'numero': '(21) 9 9649 4019'}]}, 'UTE_Canoas': {'nome': 'UTE Canoas', 'numeros': [{'numero': '(51) 3415-3939'}, {'numero': '(51) 99866-6449'}]}, 'Guamaré': {'nome': 'Guamaré', 'numeros': [{'numero': '(85) 98830.3729'}, {'numero': '(84) 99984.7020'}, {'numero': '85) 99207.7804'}]}, 'REFAP': {'nome': 'REFAP', 'numeros': [{'numero': '(51) 3415-2080'}, {'numero': '(51) 99982-0520'}, {'numero': '(51) 99617-3964'}]}, 'REPAR': {'nome': 'REPAR', 'numeros': [{'numero': '(41) 3641-2987'}, {'numero': '(41) 99157-6902'}, {'numero': '(41) 99241-5443'}]}, 'UTC_Nova_Piratininga': {'nome': 'UTE Nova Piratininga', 'numeros': [{'numero': '(11) 3523-5856'}, {'numero': '(11) 3523 5876'}, {'numero': '(11) 98393-0913'}]}, 'RPBC': {'nome': 'RPBC', 'numeros': [{'numero': '(13) 3328-4074'}, {'numero': '(13) 99712-4788'}, {'numero': '(13) 3328-4253'}]}, 'RECAP': {'nome': 'RECAP', 'numeros': [{'numero': '(11) 3795-9314'}, {'numero': '(11) 96183-2809'}, {'numero': '(11) 3795-9130'}]}, 'UTG_Caraguatatuba': {'nome': 'UTGCA - Caraguatatuba', 'numeros': [{'numero': '(12) 3886-5050', 'descricao': 'Opção 1'}, {'numero': '(12) 3886-5117', 'descricao': 'Opção 2'}, {'numero': '(12) 3886-5066', 'descricao': 'Opção 3'}]}, 'REVAP': {'nome': 'REVAP', 'numeros': [{'numero': '(12) 3928-6304'}, {'numero': '(12) 3928-6499'}, {'numero': '(12) 9 9130-6608'}]}, 'REPLAN': {'nome': 'REPLAN', 'numeros': [{'numero': '(19) 2116-6892 e (19) 99772-1201', 'descricao': 'celular melhor'}, {'numero': '(19) 2116-6542 e (19) 99602-8522'}, {'numero': '(19) 2116--6183'}]}, 'UTE_Tres_lagoas': {'nome': 'UTE Três Lagoas', 'numeros': [{'numero': '(67) 3509-3275', 'descricao': 'Opção 1 - Sala de Controle'}, {'numero': '(67) 3509 - 3234', 'descricao': 'Opção 2 - Supervisor de Turno'}, {'numero': '(67) 9 - 9847 - 3567', 'descricao': 'Opção 3 - Celular da Operação'}]}, 'UTE_Seropedica': {'nome': 'UTE Seropédica', 'numeros': [{'numero': '(21) 2665-9221', 'descricao': 'supervisao op'}, {'numero': '(21) 2665-9234'}, {'numero': '(21) 98330 0979.'}]}, 'UTE_Termorio': {'nome': 'UTE Termorio', 'numeros': [{'numero': '(21) 3227-5746'}, {'numero': '(21) 98055-0569'}, {'numero': '(21) 9 6720 8088'}]}, 'REDUC': {'nome': 'REDUC', 'numeros': [{'numero': '(21) 2677-2232', 'descricao': 'Opção 1'}, {'numero': '(21) 2677-2975', 'descricao': 'Opção 2'}, {'numero': '(21) 9 - 9872 - 4188', 'descricao': 'Fernanda Neves (Gerente do Setor)'}]}, 'UTG_Itaborai': {'nome': 'UTG Itaboraí', 'numeros': [{'numero': '(21) 2133-4199', 'descricao': 'ligar neste'}, {'numero': '(21) 2133-4202'}, {'numero': '(21) 99700-6571'}]}, 'Arm Macaé': {'nome': 'Arm Macaé', 'numeros': [{'numero': '(22) 9 9824-6085'}, {'numero': '(22) 9 9940-2957'}]}, 'UTE Juiz de Fora': {'nome': 'UTE Juiz de Fora', 'numeros': [{'numero': '(32) 3239-8431', 'descricao': 'sala op'}, {'numero': '(32) 3239-8423', 'descricao': 'sala op'}, {'numero': '(32) 99804-4943'}]}, 'UTE_Termomacae': {'nome': 'UTE Termomacaé', 'numeros': [{'numero': '(22) 3379-6134'}, {'numero': '(22) 3379-6135'}, {'numero': '(22) 98817-2571'}]}, 'UTG_Cabiunas': {'nome': 'UTG Cabiunas', 'numeros': [{'numero': '(22) 9 - 9981-1678 / Ramal: 2759 - 5280', 'descricao': 'Opção 1'}, {'numero': '(22) 9 - 9778-7616 / Ramal: 2797 - 5248 / 2797 - 5249', 'descricao': 'Opção 2'}]}, 'UTE_Ibirite': {'nome': 'UTE Ibirité', 'numeros': [{'numero': '(31) 3472-2230'}, {'numero': '(31) 99704-5869'}, {'numero': '(11) 96857-9818'}]}, 'UTG Sul_Capixaba': {'nome': 'UTG Sul Capixaba', 'numeros': [{'numero': '(28) 3360-6065', 'descricao': 'CISP'}, {'numero': '(27) 99297-9464', 'descricao': 'CISP'}]}, 'UTG_Cacimbas': {'nome': 'UTG C - Cacimbas', 'numeros': [{'numero': '(27) 3048-9107 / 9903', 'descricao': 'Supervisão da Operação (K-45)'}, {'numero': '(27) 3048-9300 / 9909'}, {'numero': '(27)3048-9152', 'descricao': 'Coordenador de Turno da Operação (K-45)'}, {'numero': '(27) 3048-9131', 'descricao': 'SMS (k-32)'}, {'numero': '(27)3048-9140', 'descricao': 'Controle de CFTV - 24h (k-04)'}]}, 'RNEST': {'nome': 'RNEST', 'numeros': [{'numero': '(81) 3879 - 4530'}, {'numero': '(81) 3879 - 3220'}, {'numero': '(81) 3879 - 4525'}]}, 'UTE_Termobahia': {'nome': 'UTE Termobahia', 'numeros': [{'numero': '(71) 3348-5006', 'descricao': 'Opção 1'}, {'numero': '(71) 9 - 9988-5704', 'descricao': 'Opção 2'}, {'numero': '(71) 9 - 9918 - 3933 / 9 -9672 - 4400', 'descricao': 'Opção 3'}]}, 'Porto Belém': {'nome': 'PORTO BELÉM', 'numeros': [{'numero': '(91) 99150.0369'}, {'numero': '(79) 99163.0089'}, {'numero': '(85) 99207.7804'}]}, 'Mucuripe_Paracuru': {'nome': 'Mucuripe Paracuru', 'numeros': [{'numero': '(85) 98147.6460'}, {'numero': '(85) 98829.9818'}, {'numero': '(85) 98126.3018'}, {'numero': '85) 99207.7804'}]}, 'UTE_Vale_ACU': {'nome': 'UTE Vale do Açu', 'numeros': [{'numero': '(84) 3235-6033', 'descricao': 'Opção 1'}, {'numero': '(84) 3235-6034', 'descricao': 'Opção 2'}, {'numero': '(84)  9 9609 - 9675', 'descricao': 'Opção 3'}]}, 'UTE_Termoceara': {'nome': 'UTE Termoceara', 'numeros': [{'numero': '(85) 3411 - 4420 / 4440', 'descricao': 'Sala de Controle da Unidade'}, {'numero': '(85) 9 9957-4422', 'descricao': 'Cristiano Freire - Gerente de Operação'}, {'numero': '(85) 998490019', 'descricao': 'Thiago Gerente de SMS'}]}, 'Porto Aratu': {'nome': 'Porto Aratu', 'numeros': [{'numero': '(71) 9 9649 4961'}]}, 'Porto Macaé': {'nome': 'UTE Porto Macaé', 'numeros': [{'numero': '(22) 9 8113-0416'}, {'numero': '(22) 9 8183-0096'}, {'numero': '(22) 9 9736-9161'}]}, 'Porto Valença': {'nome': 'UTE Porto VALENÇA', 'numeros': [{'numero': '(71) 9 9649 4961'}]}, 'Porto Açu': {'nome': 'UTE Porto AÇU', 'numeros': [{'numero': '(22) 9 9944 9292'}, {'numero': '(22) 9 9962 7159'}]}, 'Porto B Guanabara': {'nome': 'UTE PORTO BAIA DE  GUANABARA', 'numeros': [{'numero': '(21) 9 9519 4346'}, {'numero': '(21) 2144 0051'}, {'numero': '(21) 9 8145 4321'}]}}

def _normalizar_nome(texto):
    if not texto: return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", " ", texto).strip().upper()

ALIASES_UNIDADES = {
    "REGAP": ["Refinaria Gabriel Passos"], "REVAP": ["Refinaria Henrique Lage", "Refinaria do Vale do Paraiba"],
    "REPLAN": ["Refinaria de Paulinia", "Refinaria Paulinia"],
    "RPBC": ["Refinaria Presidente Bernardes", "Refinaria de Presidente Bernardes", "Refinaria de Cubatao"],
    "RECAP": ["Refinaria de Capuava", "Refinaria Capuava"], "REDUC": ["Refinaria Duque de Caxias", "Refinaria de Duque de Caxias"],
    "REFAP": ["Refinaria Alberto Pasqualini"],
    "REPAR": ["Refinaria Presidente Getulio Vargas", "Refinaria de Araucaria", "Refinaria Araucaria"],
    "RNEST": ["Refinaria Abreu e Lima", "Refinaria de Abreu e Lima"],
    "CILEP_CENPES": ["CENPES", "Centro de Pesquisas Leopoldo Americo Miguez de Mello"],
    "UTG_Itaborai": ["Boaventura"], "UTG_Cabiunas": ["UTGCAB", "UTG CAB", "UTG-CAB"],
    "UTG Sul_Capixaba": ["UTGSUL", "UTGSC", "UTG-SUL", "UTG SUL"], "UTG_Cacimbas": ["UTGC"],
    "UTG_Caraguatatuba": ["UTGCA"], "TMIB COQUEIROS": ["TMIB"], "Mucuripe_Paracuru": ["Mucuripe", "Paracuru"],
    "ARM RIO": ["Armazem Rio de Janeiro", "Armazem do Rio de Janeiro"],
}
_PALAVRAS_GENERICAS_UNIDADE = {"REFINARIA", "USINA", "UNIDADE", "TERMELETRICA", "TERMOELETRICA", "TERMICA", "COMPLEXO", "INDUSTRIAL", "TRATAMENTO", "GAS", "PORTO", "TERMINAL", "ARMAZENAMENTO", "DE", "DO", "DA", "DOS", "DAS", "E"}

def _palavras_significativas(t):
    return {p for p in t.split() if p not in _PALAVRAS_GENERICAS_UNIDADE and len(p) > 2}

def buscar_contatos_por_estacao(nome_estacao):
    alvo = _normalizar_nome(str(nome_estacao))
    if not alvo: return None
    palavras_alvo = _palavras_significativas(alvo)
    melhor_substring, melhor_tam, melhor_palavras, melhor_qtd = None, 0, None, 0
    for chave, info in CONTATOS_UNIDADES.items():
        candidatos = [chave, info["nome"]] + ALIASES_UNIDADES.get(chave, [])
        for bruto in candidatos:
            candidato = _normalizar_nome(bruto)
            if not candidato: continue
            if candidato == alvo: return info
            if len(candidato) >= 4 and (candidato in alvo or alvo in candidato):
                if len(candidato) > melhor_tam:
                    melhor_substring, melhor_tam = info, len(candidato)
            pc = _palavras_significativas(candidato)
            if len(pc) >= 2 and pc and pc <= palavras_alvo:
                if len(pc) > melhor_qtd:
                    melhor_palavras, melhor_qtd = info, len(pc)
    return melhor_substring or melhor_palavras

# ======================================================================
# ESTAÇÕES
# ======================================================================
ESTACOES_PADRAO = [
    {"estacao": "UTE Termocamaçari - UTE TCA", "lat": -12.66687, "lon": -38.31469},
    {"estacao": "UTE Termobahia - UTE TBA", "lat": -12.70324, "lon": -38.5649},
    {"estacao": "UTE Termoceará - UTE TCE", "lat": -3.69246, "lon": -38.87061},
    {"estacao": "UTE Vale do Açu - UTE VLA", "lat": -5.38169, "lon": -36.81975},
    {"estacao": "Refinaria Abreu e Lima - RNEST", "lat": -8.37966, "lon": -35.0102},
    {"estacao": "Unidade de Tratamento de Gás Sul Capixaba - UTGSUL", "lat": -20.79446, "lon": -40.62091},
    {"estacao": "Unidade de Tratamento de Gás de Cacimbas - UTGC", "lat": -19.4631, "lon": -39.7606},
    {"estacao": "Refinaria Duque de Caxias - REDUC", "lat": -22.7151, "lon": -43.28401},
    {"estacao": "UTE Termorio - UTE TRI", "lat": -22.71488, "lon": -43.25435},
    {"estacao": "BOAVENTURA, Itaboraí-RJ", "lat": -22.66071, "lon": -42.85363},
    {"estacao": "Unidade de Tratamento de Gás de Cabiúnas - UTGCAB", "lat": -22.28533, "lon": -41.71791},
    {"estacao": "UTE Termomacaé - UTE TMA", "lat": -22.30616, "lon": -41.8767},
    {"estacao": "UTE Seropédica/Baixada Fluminense - UTE SRP/BF", "lat": -22.72329, "lon": -43.64772},
    {"estacao": "Refinaria Gabriel Passos - REGAP", "lat": -19.96428, "lon": -44.09514},
    {"estacao": "UTE Ibirité - UTE IBT", "lat": -19.98858, "lon": -44.09821},
    {"estacao": "UTE Juiz de Fora - UTE JF", "lat": -21.69062, "lon": -43.45672},
    {"estacao": "UTE Três Lagoas - UTE TLG", "lat": -20.7455, "lon": -51.66459},
    {"estacao": "Unidade de Tratamento de Gás de Caraguatatuba - UTGCA", "lat": -23.65419, "lon": -45.50121},
    {"estacao": "Refinaria Presidente Bernardes - RPBC", "lat": -23.87333, "lon": -46.42757},
    {"estacao": "UTE Cubatão - UTE CBT", "lat": -23.87573, "lon": -46.43139},
    {"estacao": "Refinaria Henrique Lage - REVAP", "lat": -23.1848, "lon": -45.81581},
    {"estacao": "Refinaria de Capuava - RECAP", "lat": -23.65668, "lon": -46.48088},
    {"estacao": "Refinaria de Paulínia - REPLAN", "lat": -22.72959, "lon": -47.14771},
    {"estacao": "UTE Nova Piratininga - UTE NPI", "lat": -23.69941, "lon": -46.67388},
    {"estacao": "Refinaria Presidente Getúlio Vargas - REPAR", "lat": -25.56614, "lon": -49.36942},
    {"estacao": "Refinaria Alberto Pasqualini - REFAP", "lat": -29.8699, "lon": -51.17819},
    {"estacao": "UTE Canoas - UTE CAN", "lat": -29.87507, "lon": -51.14544},
    {"estacao": "Armazém Rio de Janeiro", "lat": -22.81097, "lon": -43.28188},
    {"estacao": "CILEP - CENPES", "lat": -22.8542, "lon": -43.23383},
    {"estacao": "Porto Baia de Guanabara", "lat": -22.87894, "lon": -43.20933},
    {"estacao": "ARM Macaé - Armazém Macaé", "lat": -22.41532, "lon": -41.86135},
    {"estacao": "Porto de Imbetiba - Macaé", "lat": -22.38683, "lon": -41.76874},
    {"estacao": "Porto Açu", "lat": -21.86474, "lon": -41.01644},
    {"estacao": "Porto Aratu", "lat": -12.78013, "lon": -38.49676},
    {"estacao": "Porto TMIB", "lat": -10.82413, "lon": -36.9463},
    {"estacao": "Porto Belém", "lat": -1.4399, "lon": -48.49492},
    {"estacao": "Porto Valença", "lat": -13.36937, "lon": -39.07125},
    {"estacao": "Porto Guamaré", "lat": -5.10669, "lon": -36.31959},
    {"estacao": "Porto Mucuripe", "lat": -3.71312, "lon": -38.47404},
    {"estacao": "Porto Paracuru", "lat": -3.40115, "lon": -39.0109},
]

RAIOS_ALERTA_KM = [(30, "#3b82f6"), (50, "#22c55e"), (100, "#f97316"), (150, "#ef4444"), (200, "#991b1b")]
GUST_THRESHOLDS = [1.8, 6, 11, 20, 30, 40, 50, 61, 74, 87, 102]
GUST_COLORS = ["#4ade80", "#34d399", "#22c55e", "#16a34a", "#15803d", "#166534", "#eab308", "#ca8a04", "#f87171", "#ef4444", "#dc2626", "#991b1b"]
GUST_LABELS = ["Calmaria", "Aragem, Vento Quase Calmo", "Brisa leve", "Vento fresco ou leve", "Vento Moderado", "Vento Regular", "Vento muito fresco ou meio forte", "Vento Forte", "Ventania", "Ventania Forte", "Vendaval ou Tempestade", "Ciclone Extratropical"]
RAIN_THRESHOLDS = [2.5, 10, 25, 50]
RAIN_COLORS = ["#a8d8ff", "#4fa8f0", "#2166d6", "#7c3aed", "#5b0fae"]
RAIN_LABELS = ["Previsão de chuvisco a chuva fraca", "Previsão de chuva fraca a moderada", "Previsão de chuva moderada a forte", "Previsão de chuva forte", "Previsão de chuva extrema"]
CAPE_THRESHOLDS = [300, 1000, 2500, 4000]
CAPE_COLORS = ["#a8d8ff", "#eab308", "#f97316", "#ef4444", "#7c1d1d"]
CAPE_LABELS = ["Instabilidade fraca", "Instabilidade moderada", "Instabilidade forte", "Instabilidade muito forte", "Instabilidade extrema"]

ALERTA_CAPE_MIN_JKG_PADRAO = 2500
TIMEZONE_OFFSET_HOURS = 0
GLM_BUCKET = "noaa-goes19"
GLM_BASE_URL = f"https://{GLM_BUCKET}.s3.amazonaws.com"
SOUTH_AMERICA_BOUNDS = {"lat_min": -58.0, "lat_max": 13.5, "lon_min": -82.0, "lon_max": -33.0}
BRAZIL_BOUNDS = {"lat_min": -34.0, "lat_max": 5.5, "lon_min": -74.5, "lon_max": -32.0}

def classify_index(v, thresholds):
    if v is None or pd.isna(v): v = 0.0
    v = float(v)
    for i, lim in enumerate(thresholds):
        if v <= lim: return i
    return len(thresholds)

def gust_color_hex(v): return GUST_COLORS[classify_index(v, GUST_THRESHOLDS)]
def rain_color_hex(v): return RAIN_COLORS[classify_index(v, RAIN_THRESHOLDS)]
def cape_color_hex(v): return CAPE_COLORS[classify_index(v, CAPE_THRESHOLDS)]

def _hora_local(t): return int((t.hour + TIMEZONE_OFFSET_HOURS) % 24)

def utc_para_brasilia(dt_utc):
    return dt_utc - timedelta(hours=3)

def classificar_periodo(h):
    if 0 <= h < 6: return "madrugada"
    if 6 <= h < 12: return "manhã"
    if 12 <= h < 18: return "tarde"
    return "noite"

def periodos_acima_limiar(valid_times, valores, limiar):
    ordem = ["madrugada", "manhã", "tarde", "noite"]
    encontrados = set()
    for t, v in zip(valid_times, valores):
        if v is None or pd.isna(v): continue
        if float(v) > limiar:
            encontrados.add(classificar_periodo(_hora_local(t)))
    return [p for p in ordem if p in encontrados]

def formatar_periodos_texto(periodos):
    prep = {"madrugada": "de madrugada", "manhã": "pela manhã", "tarde": "à tarde", "noite": "à noite"}
    if not periodos: return "ao longo do dia"
    if len(periodos) >= 4: return "ao longo de todo o dia"
    textos = [prep[p] for p in periodos]
    if len(textos) == 1: return textos[0]
    return ", ".join(textos[:-1]) + f" e {textos[-1]}"

def montar_mensagem_alerta_vento(nome, limiar_kmh, periodos_texto):
    icone = "🔴" if limiar_kmh >= 61 else "⚠️"
    texto_limiar = "61 km/h" if limiar_kmh >= 61 else "40 km/h"
    return (f"{icone} Atenção: A unidade {nome} não se encontra em alerta neste momento. Contudo, há "
            f"previsão de rajadas de vento superiores a {texto_limiar} {periodos_texto}. As condições "
            f"seguem em monitoramento contínuo pela Blue Ocean Meteorologia.")

def montar_mensagem_alerta_chuva(nome, label):
    return (f"⚠️ Atenção: A unidade {nome} não se encontra em alerta neste momento. Contudo, há "
            f"{label.lower()} entre a madrugada e o decorrer do dia de amanhã. As condições seguem em "
            f"monitoramento contínuo pela Blue Ocean Meteorologia.")

def montar_mensagem_alerta_cape(nome, periodos_texto, cape_max):
    return (f"⚡ Atenção: A unidade {nome} não se encontra em alerta neste momento. Contudo, há previsão "
            f"de forte instabilidade atmosférica (CAPE de até {cape_max:.0f} J/kg) com potencial para "
            f"formação de raios/tempestades {periodos_texto}. Recomenda-se acompanhar a camada de raios "
            f"ao vivo (GLM/GOES-19) pra confirmação. As condições seguem em monitoramento contínuo pela "
            f"Blue Ocean Meteorologia.")

def montar_mensagem_proximidade_raio(nivel_km, nome_estacao, meteorologista, renovacao=False):
    agora = utc_para_brasilia(datetime.now(timezone.utc))
    validade = agora + timedelta(hours=1)
    janela = "-15 min até o momento" if nivel_km == 30 else "-30 min até o momento"
    emoji = "🔴" if nivel_km == 30 else "🟡"
    nivel_nome = "VERMELHO (raio a menos de 30 km)" if nivel_km == 30 else "AMARELO (raio a menos de 50 km)"
    prefixo = "🔁 Alerta renovado após 1h — segue ativo" if renovacao else "Novo alerta"
    return (f"{emoji} {agora.strftime('%d/%m/%Y')} - {agora.strftime('%H:%M')}\n"
            f"* {prefixo}\n"
            f"* Local: {nome_estacao}\n"
            f"* Nível de alerta: {nivel_nome}\n"
            f"* Meteorologista: {meteorologista or '(não informado)'}\n"
            f"* Raios próximos de sua região ({janela})\n"
            f"Válido até as {validade.strftime('%H:%M')}")

RISCO_NIVEIS = [
    {"label": "Baixo", "emoji": "🟢", "color": "#22c55e"},
    {"label": "Médio", "emoji": "🟡", "color": "#eab308"},
    {"label": "Alto", "emoji": "🔴", "color": "#ef4444"},
]

def classificar_risco_combinado(max_gust, soma_precip, max_cape, alerta_gust_min=40, alerta_cape_min=ALERTA_CAPE_MIN_JKG_PADRAO):
    def _g():
        if max_gust is None or pd.isna(max_gust): return 0
        v = float(max_gust)
        if v > 61: return 2
        if v > alerta_gust_min: return 1
        return 0

    def _c():
        idx = classify_index(soma_precip, RAIN_THRESHOLDS)
        if idx >= 3: return 2
        if idx == 2: return 1
        return 0

    def _cp():
        if max_cape is None or pd.isna(max_cape): return 0
        v = float(max_cape)
        if v > max(alerta_cape_min * 1.6, alerta_cape_min + 1000): return 2
        if v > alerta_cape_min: return 1
        return 0

    score = max(_g(), _c(), _cp())
    nivel = RISCO_NIVEIS[score]
    return score, nivel["label"], nivel["emoji"], nivel["color"]

# ======================================================================
# BUSCA OPEN-METEO
# ======================================================================
MODEL_LABELS = {"gfs_seamless": "GFS", "icon_seamless": "ICON", "ecmwf_ifs025": "ECMWF", "ensemble": "ENSEMBLE (GFS+ICON+ECMWF)"}
ENSEMBLE_MODELOS = ["gfs_seamless", "icon_seamless", "ecmwf_ifs025"]

def build_session():
    s = requests.Session()
    retries = Retry(total=8, backoff_factor=4, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"], respect_retry_after_header=True)
    a = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("https://", a); s.mount("http://", a)
    s.headers.update({"User-Agent": "BlueOceanApp/1.0 (uso pessoal/operacional - contato via Streamlit)"})
    return s

def _openmeteo_base_url():
    try: chave = st.secrets.get("OPENMETEO_API_KEY", None)
    except Exception: chave = None
    if chave: return "https://customer-api.open-meteo.com/v1/forecast", chave
    return "https://api.open-meteo.com/v1/forecast", None

@st.cache_data(show_spinner=False, ttl=1800)
def fetch_openmeteo_full_hourly(df_json, model, target_date, batch_size=40):
    df = pd.read_json(io.StringIO(df_json))
    session = build_session()
    url, api_key = _openmeteo_base_url()
    # "hoje" tem que ser calculado no fuso de Brasília, não em UTC — perto
    # da virada do dia (21h-00h em Brasília = já é "amanhã" em UTC) isso
    # fazia o cálculo de past_days/forecast_days errar por 1 dia e a busca
    # pro dia seguinte podia vir vazia.
    today = utc_para_brasilia(datetime.now(timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    today = pd.Timestamp(today).tz_localize(None).normalize()
    target = pd.Timestamp(target_date).normalize()
    diff_days = (today - target).days
    if diff_days >= 0:
        past_days, forecast_days = max(diff_days, 0) + 1, 1
    else:
        past_days, forecast_days = 0, abs(diff_days) + 1
    past_days, forecast_days = min(past_days, 92), min(forecast_days, 16)

    results = []
    n = len(df)
    n_batches = int(np.ceil(n / batch_size))
    for b in range(n_batches):
        start, end = b * batch_size, min((b + 1) * batch_size, n)
        batch = df.iloc[start:end]
        params = {
            "latitude": ",".join(f"{v:.5f}" for v in batch["lat"]),
            "longitude": ",".join(f"{v:.5f}" for v in batch["lon"]),
            "hourly": "wind_gusts_10m,wind_speed_10m,wind_direction_10m,precipitation,cape",
            "models": model, "timezone": "America/Sao_Paulo", "past_days": past_days, "forecast_days": forecast_days,
        }
        if api_key: params["apikey"] = api_key
        r = session.get(url, params=params, timeout=90)
        r.raise_for_status()
        data = r.json()
        points = data if isinstance(data, list) else [data]
        for (_, row), point in zip(batch.iterrows(), points):
            n_horas = len(point["hourly"]["time"])
            precip_list = point["hourly"].get("precipitation", [None] * n_horas)
            cape_list = point["hourly"].get("cape", [None] * n_horas)
            for t, g, s_, dr, p, cp in zip(point["hourly"]["time"], point["hourly"]["wind_gusts_10m"], point["hourly"]["wind_speed_10m"], point["hourly"]["wind_direction_10m"], precip_list, cape_list):
                results.append({"estacao": row["estacao"], "lat": row["lat"], "lon": row["lon"], "modelo": model, "valid_time": t, "wind_gust_kmh": g, "wind_speed_kmh": s_, "wind_dir_deg": dr, "precip_mm": p, "cape_jkg": cp})
        time.sleep(1.0)
    out = pd.DataFrame(results)
    out["valid_time"] = pd.to_datetime(out["valid_time"])
    return out

def compute_ensemble(dfs):
    dfs_validos = [d for d in dfs if d is not None and not d.empty]
    if not dfs_validos: return pd.DataFrame(columns=["estacao", "lat", "lon", "valid_time", "wind_gust_kmh", "wind_speed_kmh", "wind_dir_deg", "precip_mm", "cape_jkg", "modelo"])
    base = dfs_validos[0][["estacao", "lat", "lon", "valid_time"]].drop_duplicates()
    soma_gust = np.zeros(len(base)); soma_precip = np.zeros(len(base)); soma_cape = np.zeros(len(base))
    soma_sin = np.zeros(len(base)); soma_cos = np.zeros(len(base))
    for d in dfs_validos:
        merged = base.merge(d[["estacao", "lat", "lon", "valid_time", "wind_gust_kmh", "wind_dir_deg", "precip_mm", "cape_jkg"]], on=["estacao", "lat", "lon", "valid_time"], how="left")
        soma_gust += merged["wind_gust_kmh"].fillna(0).values
        soma_precip += merged["precip_mm"].fillna(0).values
        soma_cape += merged["cape_jkg"].fillna(0).values
        rad = np.deg2rad(merged["wind_dir_deg"].fillna(0).values)
        soma_sin += np.sin(rad); soma_cos += np.cos(rad)
    n_modelos = len(dfs_validos)
    ens = base.copy()
    ens["wind_gust_kmh"] = soma_gust / n_modelos
    ens["precip_mm"] = soma_precip / n_modelos
    ens["cape_jkg"] = soma_cape / n_modelos
    ens["wind_dir_deg"] = (np.degrees(np.arctan2(soma_sin, soma_cos)) + 360) % 360
    ens["modelo"] = "ensemble"
    return ens

# ======================================================================
# GLM — RAIOS
# ======================================================================
def _parse_glm_timestamp(nome):
    m = re.search(r"_s(\d{13})", nome)
    if not m: return None
    b = m.group(1)
    ano, doy = int(b[0:4]), int(b[4:7])
    hh, mm, ss = int(b[7:9]), int(b[9:11]), int(b[11:13])
    return datetime(ano, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)

def _listar_arquivos_glm_hora(session, ano, doy, hora):
    prefixo = f"GLM-L2-LCFA/{ano}/{doy:03d}/{hora:02d}/"
    url = f"{GLM_BASE_URL}/?list-type=2&prefix={prefixo}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    root = ET.fromstring(r.content)
    return [el.text for el in root.findall(".//s3:Key", ns)]

@st.cache_data(show_spinner=False, ttl=90)
def fetch_glm_flashes_recent(minutos=15):
    import netCDF4
    session = build_session()
    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(minutes=minutos)
    horas = {(agora.year, agora.timetuple().tm_yday, agora.hour)}
    if inicio.hour != agora.hour or inicio.timetuple().tm_yday != agora.timetuple().tm_yday:
        horas.add((inicio.year, inicio.timetuple().tm_yday, inicio.hour))

    chaves = []
    falhas = 0
    for ano, doy, hora in horas:
        try: chaves.extend(_listar_arquivos_glm_hora(session, ano, doy, hora))
        except Exception: falhas += 1
    if falhas == len(horas): raise RuntimeError("não foi possível conectar ao bucket GLM na AWS")

    arquivos = sorted(c for c in chaves if (ts := _parse_glm_timestamp(c)) is not None and ts >= inicio)
    if not arquivos: return pd.DataFrame(columns=["lat", "lon", "energy_j", "time"])

    linhas = []
    for chave in arquivos:
        try:
            r = session.get(f"{GLM_BASE_URL}/{chave}", timeout=30)
            r.raise_for_status()
            with netCDF4.Dataset("inmemory.nc", memory=r.content) as ds:
                lats = np.asarray(ds.variables["flash_lat"][:])
                lons = np.asarray(ds.variables["flash_lon"][:])
                energias = np.asarray(ds.variables["flash_energy"][:])
                ts_arquivo = _parse_glm_timestamp(chave)
                for lat, lon, en in zip(lats, lons, energias):
                    linhas.append({"lat": float(lat), "lon": float(lon), "energy_j": float(en), "time": ts_arquivo})
        except Exception: continue
    df = pd.DataFrame(linhas)
    if not df.empty:
        b = SOUTH_AMERICA_BOUNDS
        df = df[(df["lat"] >= b["lat_min"]) & (df["lat"] <= b["lat_max"]) &
                (df["lon"] >= b["lon_min"]) & (df["lon"] <= b["lon_max"])]
    return df

def _dist_km(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111
    latm = (lat1 + lat2) / 2
    dlon = (lon1 - lon2) * 111 * math.cos(math.radians(latm))
    return math.hypot(dlat, dlon)

def _bearing_graus(lat1, lon1, lat2, lon2):
    lat1r, lon1r, lat2r, lon2r = map(math.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2r - lon1r
    y = math.sin(dlon) * math.cos(lat2r)
    x = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def _bearing_para_rumo(deg):
    rumos = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return rumos[round(deg / 45) % 8]

def _destino_ponto(lat, lon, bearing_deg, dist_km):
    R = 6371
    lat1, lon1, brng = math.radians(lat), math.radians(lon), math.radians(bearing_deg)
    lat2 = math.asin(math.sin(lat1) * math.cos(dist_km / R) + math.cos(lat1) * math.sin(dist_km / R) * math.cos(brng))
    lon2 = lon1 + math.atan2(math.sin(brng) * math.sin(dist_km / R) * math.cos(lat1), math.cos(dist_km / R) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)

def clusterizar_raios(raios_df, dist_km=18, min_pts=3):
    if raios_df.empty: return []
    pontos = raios_df[["lat", "lon"]].to_dict("records")
    n = len(pontos)
    tamanho_grade = dist_km / 111
    buckets = defaultdict(list)
    for i, p in enumerate(pontos):
        buckets[(int(p["lat"] // tamanho_grade), int(p["lon"] // tamanho_grade))].append(i)

    pai = list(range(n))
    def _find(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    def _uniao(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb: pai[ra] = rb

    dist2_lim = dist_km ** 2
    for (gx, gy), idxs in buckets.items():
        vizinhos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vizinhos.extend(buckets.get((gx + dx, gy + dy), []))
        for i in idxs:
            for j in vizinhos:
                if j <= i: continue
                dlat = (pontos[i]["lat"] - pontos[j]["lat"]) * 111
                latm = (pontos[i]["lat"] + pontos[j]["lat"]) / 2
                dlon = (pontos[i]["lon"] - pontos[j]["lon"]) * 111 * math.cos(math.radians(latm))
                if dlat * dlat + dlon * dlon <= dist2_lim:
                    _uniao(i, j)
    grupos_map = defaultdict(list)
    for i in range(n): grupos_map[_find(i)].append(pontos[i])
    return [g for g in grupos_map.values() if len(g) >= min_pts]

def atualizar_celulas_raio(grupos, agora_ts):
    celulas = st.session_state.get("celulas_raio", [])
    usadas = set()
    for grupo in grupos:
        lat = sum(p["lat"] for p in grupo) / len(grupo)
        lon = sum(p["lon"] for p in grupo) / len(grupo)
        melhor, menor_dist = None, float("inf")
        for cel in celulas:
            if cel["id"] in usadas: continue
            ult = cel["historico"][-1]
            d = _dist_km(lat, lon, ult["lat"], ult["lon"])
            if d < menor_dist:
                menor_dist, melhor = d, cel
        if melhor is not None and menor_dist <= 60:
            alvo = melhor
        else:
            novo_id = st.session_state.get("proximo_id_celula", 1)
            alvo = {"id": novo_id, "historico": []}
            st.session_state.proximo_id_celula = novo_id + 1
            celulas.append(alvo)
        alvo["historico"].append({"lat": lat, "lon": lon, "t": agora_ts, "n": len(grupo)})
        if len(alvo["historico"]) > 6: alvo["historico"] = alvo["historico"][-6:]
        alvo["ultima_atualizacao"] = agora_ts
        usadas.add(alvo["id"])
    celulas = [c for c in celulas if agora_ts - c["ultima_atualizacao"] <= 600]
    st.session_state.celulas_raio = celulas
    return celulas

def calcular_trajetoria_celula(celula):
    hist = celula["historico"]
    if len(hist) < 2: return None
    referencia, atual = hist[0], hist[-1]
    dist_km = _dist_km(referencia["lat"], referencia["lon"], atual["lat"], atual["lon"])
    horas = max((atual["t"] - referencia["t"]) / 3600, 1 / 3600)
    vel_kmh = dist_km / horas
    rumo_graus = _bearing_graus(referencia["lat"], referencia["lon"], atual["lat"], atual["lon"])
    rumo_texto = _bearing_para_rumo(rumo_graus)
    checkpoints = []
    if len(hist) >= 3 and 2 <= vel_kmh <= 120:
        b = SOUTH_AMERICA_BOUNDS
        for passo in range(1, 4):
            minutos_futuro = passo * 30
            dist_proj = vel_kmh * (minutos_futuro / 60)
            lat2, lon2 = _destino_ponto(atual["lat"], atual["lon"], rumo_graus, dist_proj)
            if not (b["lat_min"] <= lat2 <= b["lat_max"] and b["lon_min"] <= lon2 <= b["lon_max"]): break
            checkpoints.append({"lat": lat2, "lon": lon2, "min": minutos_futuro})
    return {"vel_kmh": vel_kmh, "rumo_texto": rumo_texto, "checkpoints": checkpoints}

def calcular_resumo_estacoes(df_full, target_date, safety_margin_pct, horas_filtro=None, alerta_gust_min=40, alerta_cape_min=ALERTA_CAPE_MIN_JKG_PADRAO):
    d = df_full[df_full["valid_time"].dt.date == pd.Timestamp(target_date).date()].copy()
    if horas_filtro: d = d[d["valid_time"].dt.strftime("%H").isin(horas_filtro)]
    if d.empty: return pd.DataFrame(), []
    d["gust_ajustado"] = d["wind_gust_kmh"] * (1 + safety_margin_pct / 100)
    for c in ("precip_mm", "cape_jkg"):
        if c not in d.columns: d[c] = np.nan
    d = d.sort_values("valid_time")
    linhas, alertas, prox_id = [], [], 1
    for estacao, g in d.groupby("estacao", sort=False):
        g = g.sort_values("valid_time")
        nome = estacao.split(" - ")[0]
        gusts = [float(v) for v in g["gust_ajustado"] if pd.notna(v)]
        precs = [float(v) for v in g["precip_mm"] if pd.notna(v)]
        capes = [float(v) for v in g["cape_jkg"] if pd.notna(v)]
        max_gust = max(gusts) if gusts else 0.0
        soma_precip = sum(precs) if precs else 0.0
        max_cape = max(capes) if capes else 0.0
        score, label, emoji, color = classificar_risco_combinado(max_gust, soma_precip, max_cape, alerta_gust_min, alerta_cape_min)
        contatos = buscar_contatos_por_estacao(estacao)
        linhas.append({"estacao": estacao, "nome": nome, "lat": float(g["lat"].iloc[0]), "lon": float(g["lon"].iloc[0]),
                        "max_gust": max_gust, "soma_precip": soma_precip, "max_cape": max_cape,
                        "risco_score": score, "risco_label": label, "risco_emoji": emoji, "risco_color": color,
                        "contatos": contatos, "horas": [t.strftime("%H:%M") for t in g["valid_time"]],
                        "gusts": [round(float(v), 1) if pd.notna(v) else None for v in g["gust_ajustado"]],
                        "precip": [round(float(v), 2) if pd.notna(v) else None for v in g["precip_mm"]],
                        "capes": [round(float(v), 0) if pd.notna(v) else None for v in g["cape_jkg"]]})
        if max_gust > 61:
            per = periodos_acima_limiar(g["valid_time"], g["gust_ajustado"], 61)
            alertas.append({"id": prox_id, "tipo": "vento", "estacao": nome, "texto": montar_mensagem_alerta_vento(nome, 61, formatar_periodos_texto(per))}); prox_id += 1
        elif max_gust > alerta_gust_min:
            per = periodos_acima_limiar(g["valid_time"], g["gust_ajustado"], alerta_gust_min)
            alertas.append({"id": prox_id, "tipo": "vento", "estacao": nome, "texto": montar_mensagem_alerta_vento(nome, 40, formatar_periodos_texto(per))}); prox_id += 1
        precip_max_hora = max(precs) if precs else 0.0
        idx_chuva = classify_index(precip_max_hora, RAIN_THRESHOLDS)
        if idx_chuva >= 2:
            alertas.append({"id": prox_id, "tipo": "chuva", "estacao": nome, "texto": montar_mensagem_alerta_chuva(nome, RAIN_LABELS[idx_chuva])}); prox_id += 1
        if max_cape > alerta_cape_min:
            per_c = periodos_acima_limiar(g["valid_time"], g["cape_jkg"], alerta_cape_min)
            alertas.append({"id": prox_id, "tipo": "cape", "estacao": nome, "texto": montar_mensagem_alerta_cape(nome, formatar_periodos_texto(per_c), max_cape)}); prox_id += 1
    return pd.DataFrame(linhas), alertas

def gerar_boletim_pdf_bytes(df_estacoes, alertas, target_date, modelo_label, margin_pct, horas_filtro, alerta_gust_min, alerta_cape_min, meteorologista_nome=""):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("T", parent=styles["Title"], textColor=colors.HexColor("#0d1117"))
    estilo_secao = ParagraphStyle("S", parent=styles["Heading2"], textColor=colors.HexColor("#0f5c5c"), spaceBefore=14, spaceAfter=6)
    estilo_normal = styles["Normal"]
    estilo_alerta = ParagraphStyle("A", parent=styles["Normal"], fontSize=9.5, backColor=colors.HexColor("#f5f5f5"), borderPadding=6, spaceAfter=8)

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    story = []
    data_fmt = pd.Timestamp(target_date).strftime("%d/%m/%Y")
    horas_txt = "todas as 24h" if not horas_filtro or len(horas_filtro) == 24 else ", ".join(f"{h}h" for h in sorted(horas_filtro))

    story.append(Paragraph(f"Boletim Meteorológico Diário — {EMPRESA}", estilo_titulo))
    story.append(Paragraph(f"Data da previsão: <b>{data_fmt}</b> · Modelo(s): <b>{modelo_label}</b> · Margem: <b>+{margin_pct}%</b><br/>Horários: {horas_txt}<br/>Limiares: rajada &gt;{alerta_gust_min} km/h (alto acima de 61) · CAPE &gt;{alerta_cape_min:.0f} J/kg<br/>Meteorologista: <b>{meteorologista_nome or '(não informado)'}</b><br/>Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", estilo_normal))
    story.append(Spacer(1, 10))

    if df_estacoes.empty:
        story.append(Paragraph("Nenhum dado horário disponível pra essa combinação.", estilo_normal))
        doc.build(story)
        return buf.getvalue()

    def _ranking(titulo, ordenado, unidade, chave):
        story.append(Paragraph(titulo, estilo_secao))
        linhas = [["#", "Estação", f"Valor ({unidade})"]]
        for i, (_, e) in enumerate(ordenado.head(6).iterrows(), start=1):
            linhas.append([str(i), e["nome"], f"{e[chave]:.1f}"])
        t = Table(linhas, colWidths=[1.2 * cm, 9 * cm, 4 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5c5c")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccc")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")])]))
        story.append(t); story.append(Spacer(1, 8))

    _ranking("Top 6 — Rajada de vento", df_estacoes.sort_values("max_gust", ascending=False), "km/h", "max_gust")
    _ranking("Top 6 — Precipitação acumulada", df_estacoes.sort_values("soma_precip", ascending=False), "mm", "soma_precip")
    _ranking("Top 6 — CAPE", df_estacoes.sort_values("max_cape", ascending=False), "J/kg", "max_cape")

    story.append(Paragraph("Estações em risco (combinado)", estilo_secao))
    em_risco = df_estacoes[df_estacoes["risco_score"] > 0].sort_values("risco_score", ascending=False)
    if not em_risco.empty:
        linhas = [["Risco", "Estação", "Rajada", "Chuva", "CAPE"]]
        for _, e in em_risco.iterrows():
            linhas.append([e["risco_label"].upper(), e["nome"], f"{e['max_gust']:.0f}", f"{e['soma_precip']:.1f}", f"{e['max_cape']:.0f}"])
        t = Table(linhas, colWidths=[2.6 * cm, 6 * cm, 2.6 * cm, 2.4 * cm, 2.6 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ef4444")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccc")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")])]))
        story.append(t)
    else:
        story.append(Paragraph("Nenhuma estação em risco médio/alto.", estilo_normal))

    story.append(PageBreak())
    story.append(Paragraph("Alertas de previsão gerados", estilo_secao))
    emoji_pat = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF\u2190-\u21FF\uFE0F\u200d]+")
    if alertas:
        for a in alertas: story.append(Paragraph(emoji_pat.sub("", a["texto"]).strip(), estilo_alerta))
    else:
        story.append(Paragraph("Nenhum alerta gerado.", estilo_normal))
    doc.build(story)
    return buf.getvalue()

# ======================================================================
# INTERFACE STREAMLIT
# ======================================================================
st.markdown("""
<style>
    .stApp { background-color: #0d1117; }
    section[data-testid="stSidebar"] { background-color: #161b22; }
</style>
""", unsafe_allow_html=True)

st.title("🌬️ BlueOcean — Rajadas de Vento, Precipitação e CAPE")
st.caption("Versão web do painel de monitoramento — by Mário Henrique")

if "alertas_raio_ativos" not in st.session_state: st.session_state.alertas_raio_ativos = []
if "alertas_unidade" not in st.session_state: st.session_state.alertas_unidade = {}
if "log_alertas" not in st.session_state: st.session_state.log_alertas = []

with st.sidebar:
    st.header("⚙ Configuração")
    meteorologista = st.text_input("Meteorologista responsável", value="")

    st.subheader("📁 Estações")
    df_stations = pd.DataFrame(ESTACOES_PADRAO)
    st.caption(f"{len(df_stations)} unidades já cadastradas no app.")
    with st.expander("Usar outra planilha (opcional)"):
        arquivo_estacoes = st.file_uploader("Envie um .xlsx (colunas: estacao, lat, lon)", type=["xlsx"])
        if arquivo_estacoes is not None:
            df_custom = pd.read_excel(arquivo_estacoes)
            if df_custom.shape[1] != 3: st.error(f"Esperava 3 colunas (estação/lat/lon), encontrei {df_custom.shape[1]}.")
            else:
                df_custom.columns = ["estacao", "lat", "lon"]
                df_stations = df_custom
                st.success(f"Usando {len(df_stations)} estações da planilha enviada.")

    st.subheader("📅 Data e horários")
    hoje_brasilia = utc_para_brasilia(datetime.now(timezone.utc)).date()
    target_date = st.date_input(
        "Data da previsão", value=hoje_brasilia,
        min_value=hoje_brasilia - timedelta(days=90), max_value=hoje_brasilia + timedelta(days=15),
        help="O Open-Meteo cobre até 90 dias no passado (histórico) e 15 dias de previsão pra frente.",
    )
    todas_horas = [f"{h:02d}" for h in range(24)]
    horas_selecionadas = st.multiselect("Horários a incluir", todas_horas, default=todas_horas)

    st.subheader("🌬 Modelos")
    modelos_valores = ["gfs_seamless", "icon_seamless", "ecmwf_ifs025", "ensemble"]
    modelo_vento = st.selectbox("Modelo — Rajada de vento", modelos_valores, index=0)
    modelo_chuva = st.selectbox("Modelo — Precipitação", modelos_valores, index=0)
    modelo_cape = st.selectbox("Modelo — CAPE", modelos_valores, index=0)
    margin_pct = st.slider("Margem de segurança da rajada (%)", 0, 50, 15)
    alerta_gust_min = st.number_input("Limiar de alerta de rajada (km/h)", 20, 60, 40)
    alerta_cape_min = st.number_input("Limiar de alerta de CAPE (J/kg)", 500, 6000, ALERTA_CAPE_MIN_JKG_PADRAO, step=100)

    st.subheader("⚡ Raios ao vivo (GLM/GOES-19)")
    incluir_raios = st.checkbox("Mostrar raios ao vivo no mapa", value=True)
    raios_minutos = st.slider("Janela de tempo (min)", 5, 60, 15, step=5, disabled=not incluir_raios)
    intervalo_raios_seg = st.slider("Intervalo de atualização dos raios (segundos)", 10, 120, 30, step=10, disabled=not incluir_raios)
    tocar_som = True
    st.caption("🔊 O som e o pop-up automático de alerta ficam sempre ativos quando os raios estão ligados.")
    arquivo_som = st.file_uploader("Trocar o som de alerta (opcional)", type=["mp3", "wav", "ogg", "m4a"], disabled=not incluir_raios)
    mostrar_deslocamento = st.checkbox("Mostrar deslocamento das células de tempestade", value=True, disabled=not incluir_raios)
    st.caption("🔄 Só os raios (pontos, células e alertas) atualizam sozinhos — o mapa em si (zoom, posição, pop-ups abertos) não é recarregado.")

    st.subheader("📏 Raios de alerta ao redor das unidades")
    mostrar_aneis = st.checkbox("Mostrar anéis de distância no mapa", value=True)
    distancias_aneis = st.multiselect("Distâncias (km)", [30, 50, 100, 150, 200], default=[30, 50, 100, 150, 200], disabled=not mostrar_aneis)

    st.subheader("🗺️ Variável e horário no mapa")
    variavel_mapa = st.radio("Variável exibida", ["Rajada de vento", "Precipitação", "CAPE"], horizontal=False)
    modo_horario = st.radio("Modo de exibição", ["Resumo do dia (acumulado)", "Hora específica"], horizontal=False)
    hora_especifica = None
    if modo_horario == "Hora específica" and horas_selecionadas:
        hora_especifica = st.select_slider("Horário", options=sorted(horas_selecionadas), value=sorted(horas_selecionadas)[0])

    gerar = st.button("🌍 Gerar / Atualizar mapa", type="primary", use_container_width=True)

# --------------------------------------------------------------
# Som de alerta personalizado: se a pessoa subiu um arquivo, salva ele
# no static/ (pra poder ser tocado pelo JS do mapa) e passa a usar esse
# em vez do padrão. Fica valendo enquanto durar a sessão.
# --------------------------------------------------------------
som_alerta_nome_ativo = SOM_ALERTA_NOME
if arquivo_som is not None:
    ext = os.path.splitext(arquivo_som.name)[1].lower() or ".mp3"
    conteudo = arquivo_som.getvalue()
    # nome baseado no hash do conteúdo: evita um usuário sobrescrever o
    # som de outro se o app estiver sendo usado por mais de uma pessoa
    # ao mesmo tempo (o static/ é compartilhado entre sessões).
    hash_conteudo = abs(hash(conteudo)) % (10**10)
    nome_custom = f"alerta_custom_{hash_conteudo}{ext}"
    caminho_custom = os.path.join(STATIC_DIR, nome_custom)
    if not os.path.exists(caminho_custom):
        with open(caminho_custom, "wb") as f:
            f.write(conteudo)
    som_alerta_nome_ativo = nome_custom
    st.sidebar.audio(arquivo_som, format=f"audio/{ext.lstrip('.')}")

margin = 1.5
bbox = {"lon_min": df_stations["lon"].min() - margin, "lon_max": df_stations["lon"].max() + margin, "lat_min": df_stations["lat"].min() - margin, "lat_max": df_stations["lat"].max() + margin}

if gerar:
    try:
        with st.spinner("Buscando dados no Open-Meteo..."):
            modelos_necessarios = set(ENSEMBLE_MODELOS) | {m for m in (modelo_vento, modelo_chuva, modelo_cape) if m != "ensemble"}
            df_json = df_stations.to_json()
            dfs_base = {}
            for i, m in enumerate(sorted(modelos_necessarios)):
                if i > 0: time.sleep(2.0)
                dfs_base[m] = fetch_openmeteo_full_hourly(df_json, m, str(target_date))

            def obter(modelo_id): return compute_ensemble([dfs_base[m] for m in ENSEMBLE_MODELOS]) if modelo_id == "ensemble" else dfs_base[modelo_id]

            df_vento_src, df_chuva_src, df_cape_src = obter(modelo_vento), obter(modelo_chuva), obter(modelo_cape)
            chave = ["estacao", "lat", "lon", "valid_time"]
            df_final = df_vento_src[chave + ["wind_gust_kmh", "wind_speed_kmh", "wind_dir_deg"]].copy()
            df_final = df_final.merge(df_chuva_src[chave + ["precip_mm"]], on=chave, how="left")
            df_final = df_final.merge(df_cape_src[chave + ["cape_jkg"]], on=chave, how="left")

            if df_final.empty or df_final["valid_time"].dt.date.eq(target_date).sum() == 0:
                st.warning(
                    f"O Open-Meteo respondeu, mas não veio nenhum horário pra **{target_date.strftime('%d/%m/%Y')}** "
                    "nos dados recebidos. Isso pode acontecer se a data escolhida estiver fora da janela de "
                    "cobertura do modelo — tente uma data mais próxima de hoje."
                )

            label_v, label_c, label_cp = MODEL_LABELS[modelo_vento], MODEL_LABELS[modelo_chuva], MODEL_LABELS[modelo_cape]
            modelo_label = label_v if modelo_vento == modelo_chuva == modelo_cape else f"{label_v} (vento)/{label_c} (chuva)/{label_cp} (CAPE)"

            st.session_state.df_full = df_final
            st.session_state.modelo_label = modelo_label
            st.session_state.dfs_base = {m: dfs_base[m] for m in ENSEMBLE_MODELOS if m in dfs_base}
            st.session_state.params = dict(target_date=str(target_date), horas=horas_selecionadas, margin_pct=margin_pct, alerta_gust_min=alerta_gust_min, alerta_cape_min=alerta_cape_min, meteorologista=meteorologista)
    except Exception as e:
        st.error(f"Não consegui buscar os dados do Open-Meteo pra **{target_date.strftime('%d/%m/%Y')}**: {e}")
        st.stop()

if "df_full" not in st.session_state:
    st.info("Configure os parâmetros na barra lateral e clique em **Gerar / Atualizar mapa**.")
    st.stop()

df_full = st.session_state.df_full
params = st.session_state.params
df_estacoes, alertas = calcular_resumo_estacoes(df_full, params["target_date"], params["margin_pct"], horas_filtro=params["horas"], alerta_gust_min=params["alerta_gust_min"], alerta_cape_min=params["alerta_cape_min"])

if df_estacoes.empty:
    st.warning("Nenhum dado horário disponível pra essa combinação de data/horários.")
    st.stop()

col_mapa, col_lado = st.columns([2.4, 1])

var_map = {"Rajada de vento": ("max_gust", gust_color_hex, "km/h"), "Precipitação": ("soma_precip", rain_color_hex, "mm"), "CAPE": ("max_cape", cape_color_hex, "J/kg")}
chave_var, color_fn, unidade_var = var_map[variavel_mapa]
chave_dado_hora = {"Rajada de vento": "gusts", "Precipitação": "precip", "CAPE": "capes"}[variavel_mapa]

@st.dialog("⚡ Raio próximo de uma unidade!")
def _dialog_alerta_raio():
    texto = st.session_state.get("dialog_raio_texto")
    if not texto: return
    st.warning("Foi detectado um raio próximo de uma unidade monitorada. Copie a mensagem abaixo:")
    st.code(texto, language=None)

def _atualizar_dados_raios():
    """Só busca os raios, agrupa em células, checa proximidade de perigo
    e grava tudo em static/raios_live.json. NÃO mexe no mapa — é por isso
    que agora só os raios atualizam sozinhos, o mapa fica parado."""
    raios_df = pd.DataFrame()
    celulas_com_trajetoria = []
    erro = None
    if incluir_raios:
        try:
            raios_df = fetch_glm_flashes_recent(minutos=raios_minutos)
            st.session_state.ultima_atualizacao_raios = datetime.now(timezone.utc)
            st.session_state.ultimo_erro_raios = None
        except Exception as e:
            erro = str(e)
            st.session_state.ultimo_erro_raios = erro

        if mostrar_deslocamento and not raios_df.empty:
            grupos = clusterizar_raios(raios_df)
            agora_ts = time.time()
            celulas = atualizar_celulas_raio(grupos, agora_ts)
            for cel in celulas:
                traj = calcular_trajetoria_celula(cel)
                if traj is not None: celulas_com_trajetoria.append({**cel, "trajetoria": traj})

        if not raios_df.empty:
            for _, est in df_estacoes.iterrows():
                # menor distância até qualquer raio ativo no momento
                dists = ((raios_df["lat"] - est["lat"]) ** 2 + (raios_df["lon"] - est["lon"]) ** 2) ** 0.5 * 111
                dist_min = float(dists.min())

                if dist_min <= 30: nivel_atual, nivel_km = "vermelho", 30
                elif dist_min <= 50: nivel_atual, nivel_km = "amarelo", 50
                else: nivel_atual, nivel_km = None, None
                if nivel_atual is None: continue

                agora_ts = time.time()
                existente = st.session_state.alertas_unidade.get(est["nome"])
                deve_notificar, renovacao = False, False
                if existente is None:
                    deve_notificar = True
                elif nivel_atual == "vermelho" and existente["nivel"] == "amarelo":
                    # escalou de amarelo pra vermelho: avisa de novo, mais grave
                    deve_notificar = True
                elif agora_ts >= existente["expira_ts"]:
                    # já passou 1h e o perigo continua: renotifica
                    deve_notificar, renovacao = True, True

                if deve_notificar:
                    st.session_state.alertas_unidade[est["nome"]] = {
                        "nivel": nivel_atual, "notificado_ts": agora_ts, "expira_ts": agora_ts + 3600,
                    }
                    texto = montar_mensagem_proximidade_raio(nivel_km, est["nome"], params["meteorologista"], renovacao=renovacao)
                    st.session_state.alertas_raio_ativos.insert(0, {"id": f"{est['nome']}_{agora_ts}", "texto": texto, "estacao": est["nome"], "expira": agora_ts + 3600})
                    st.session_state.dialog_raio_texto = texto
                    st.session_state.dialog_raio_ts = agora_ts

    st.session_state.alertas_raio_ativos = [a for a in st.session_state.alertas_raio_ativos if a["expira"] > time.time()]
    st.session_state["_fragment_raios_df"] = raios_df
    st.session_state["_fragment_celulas"] = celulas_com_trajetoria

    _escrever_raios_json(raios_df, celulas_com_trajetoria, st.session_state.get("ultima_atualizacao_raios"), st.session_state.alertas_unidade, erro, intervalo_raios_seg)

    # Só chama o diálogo numa janela curtinha logo após um alerta NOVO —
    # senão ele reabriria sozinho a cada atualização de raios, mesmo
    # depois de já ter sido fechado no X.
    dialog_ts = st.session_state.get("dialog_raio_ts")
    janela_dialog_seg = max(intervalo_raios_seg * 1.5, 20)
    if dialog_ts and (time.time() - dialog_ts) < janela_dialog_seg and st.session_state.get("dialog_raio_texto"):
        _dialog_alerta_raio()

    if incluir_raios:
        ultima_att = st.session_state.get("ultima_atualizacao_raios")
        if ultima_att is not None:
            hora_brasilia = utc_para_brasilia(ultima_att).strftime("%H:%M:%S")
            st.caption(f"⚡ Raios (GLM/GOES-19) atualizados às **{hora_brasilia}** · a cada {intervalo_raios_seg}s, sem recarregar o mapa")
        erro_raios = st.session_state.get("ultimo_erro_raios")
        if erro_raios: st.warning(f"GLM indisponível no momento: {erro_raios}")

def _construir_mapa():
    if hora_especifica: st.caption(f"🕐 Mostrando previsão pontual das **{hora_especifica}:00** — {variavel_mapa}")
    else: st.caption(f"📊 Mostrando o **resumo acumulado do dia** — {variavel_mapa}")

    bb = BRAZIL_BOUNDS
    center_lat = (bb["lat_min"] + bb["lat_max"]) / 2
    center_lon = (bb["lon_min"] + bb["lon_max"]) / 2
    m = folium.Map(location=[center_lat, center_lon], tiles="CartoDB dark_matter", control_scale=True, min_lat=bb["lat_min"], max_lat=bb["lat_max"], min_lon=bb["lon_min"], max_lon=bb["lon_max"], max_bounds=True, min_zoom=4, max_zoom=14, maxBoundsViscosity=1.0)
    m.fit_bounds([[bb["lat_min"], bb["lon_min"]], [bb["lat_max"], bb["lon_max"]]])

    aneis_fg = folium.FeatureGroup(name="📏 Raios de alerta ao redor das unidades", show=mostrar_aneis)
    marcadores_js = {}
    estacoes_para_js = []
    dados_estacoes = {}
    marcadores_bind_js = []

    for _, e in df_estacoes.iterrows():
        if hora_especifica and e["horas"]:
            try:
                idx_hora = e["horas"].index(f"{hora_especifica}:00")
                valor_hora = e[chave_dado_hora][idx_hora]
            except ValueError:
                valor_hora = None
            valor_exibido = valor_hora if valor_hora is not None else 0.0
            cor_valor = color_fn(valor_exibido)
            texto_valor = f"{valor_exibido:.1f} {unidade_var}" if valor_hora is not None else "sem dado nessa hora"
        else:
            valor_exibido = e[chave_var]
            cor_valor = color_fn(valor_exibido)
            texto_valor = f"{valor_exibido:.1f} {unidade_var}"

        marcador_estacao = folium.CircleMarker(location=[e["lat"], e["lon"]], radius=8, color=e["risco_color"], weight=3, fill=True, fill_color=cor_valor, fill_opacity=0.9, tooltip=f"{e['risco_emoji']} {e['nome']} — {texto_valor}")
        marcador_estacao.add_to(m)
        marcadores_js[e["nome"]] = marcador_estacao.get_name()
        estacoes_para_js.append({"nome": e["nome"], "lat": e["lat"], "lon": e["lon"]})

        # dados completos da estação pro painel que abre no clique — 100%
        # client-side, sem precisar de nenhuma "ponte" com o Streamlit
        dados_estacoes[e["estacao"]] = {
            "nome": e["nome"], "horas": e["horas"], "gusts": e["gusts"], "precip": e["precip"], "capes": e["capes"],
            "max_gust": e["max_gust"], "soma_precip": e["soma_precip"], "max_cape": e["max_cape"],
            "risco_emoji": e["risco_emoji"], "risco_label": e["risco_label"], "risco_color": e["risco_color"],
            "cor_gust": gust_color_hex(e["max_gust"]), "cor_precip": rain_color_hex(e["soma_precip"]), "cor_cape": cape_color_hex(e["max_cape"]),
            "contatos": e["contatos"],
        }
        marcadores_bind_js.append(f"{marcador_estacao.get_name()}.on('click', function() {{ window.blueoceanAbrirPainel({json.dumps(e['estacao'])}); }});")

        if mostrar_aneis:
            for raio_km, cor_raio in RAIOS_ALERTA_KM:
                if raio_km not in distancias_aneis: continue
                folium.Circle(location=[e["lat"], e["lon"]], radius=raio_km * 1000, color=cor_raio, weight=1.5, fill=False, dash_array="6, 6", opacity=0.85, tooltip=f"{e['nome']} — raio de {raio_km} km").add_to(aneis_fg)
    aneis_fg.add_to(m)

    raios_fg = folium.FeatureGroup(name="⚡ Raios ao vivo", show=True)
    raios_fg.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    # --------------------------------------------------------------
    # Painel de previsão horária — abre ao clicar numa unidade, igual
    # no app desktop: 100% desenhado em JS (Chart.js), sem precisar
    # mandar nada de volta pro Python. Os dados de todas as unidades já
    # vão embutidos no mapa, então abrir o painel é instantâneo.
    # --------------------------------------------------------------
    painel_estacao_html = """
<div id="painel_estacao" style="display:none; position:absolute; top:44px; left:50px; z-index:1000; width:300px;
     max-height:calc(100% - 90px); overflow-y:auto; background:#12161ff2; color:#f0f2f5; padding:12px 14px;
     border:1px solid #3fc2c2; border-radius:8px; font-family:'Segoe UI', Arial, sans-serif; box-shadow:0 4px 14px rgba(0,0,0,0.5);">
  <div style="display:flex; justify-content:space-between; align-items:flex-start;">
    <div id="painel_estacao_nome" style="font-size:14px; font-weight:bold; color:#3fc2c2; padding-right:8px;">—</div>
    <span onclick="document.getElementById('painel_estacao').style.display='none';"
          style="cursor:pointer; color:#ff6b5e; font-weight:bold; flex-shrink:0;">✕</span>
  </div>
  <div id="painel_estacao_resumo" style="font-size:11px; color:#8b93a3; margin:8px 0;">—</div>
  <canvas id="painel_estacao_canvas" width="270" height="150"></canvas>
  <div id="painel_estacao_contatos" style="font-size:11.5px; margin-top:10px;"></div>
</div>
"""
    m.get_root().html.add_child(folium.Element(painel_estacao_html))

    dados_estacoes_json = json.dumps(dados_estacoes, ensure_ascii=False).replace("</", "<\\/")
    marcadores_bind_str = "\n".join(marcadores_bind_js)
    painel_estacao_script = f"""
<script>
(function() {{
    var dadosEstacoes = {dados_estacoes_json};
    var painelChart = null;

    function renderizarContatos(contatos) {{
        var corpo = document.getElementById("painel_estacao_contatos");
        if (!contatos || !contatos.numeros || !contatos.numeros.length) {{
            corpo.innerHTML = "";
            return;
        }}
        var html = "<hr style='border-color:#2a2f3a;'/><b style='color:#3fc2c2;'>📞 " + contatos.nome + "</b><br/>";
        contatos.numeros.slice(0, 3).forEach(function(item) {{
            html += item.numero;
            if (item.descricao) html += " <i style='color:#8b93a3;'>(" + item.descricao + ")</i>";
            html += "<br/>";
        }});
        corpo.innerHTML = html;
    }}

    function montarGrafico(d) {{
        var ctx = document.getElementById("painel_estacao_canvas").getContext("2d");
        if (painelChart) {{ painelChart.destroy(); }}
        painelChart = new Chart(ctx, {{
            type: "line",
            data: {{
                labels: d.horas,
                datasets: [
                    {{ label: "Rajada (km/h)", data: d.gusts, borderColor: d.cor_gust, backgroundColor: d.cor_gust + "33",
                       yAxisID: "y", fill: true, tension: 0.3, borderWidth: 2, spanGaps: false, pointRadius: 2 }},
                    {{ label: "Chuva (mm)", data: d.precip, type: "bar", backgroundColor: (d.cor_precip || "#4fa8f0") + "99",
                       yAxisID: "y1", spanGaps: false }},
                    {{ label: "CAPE (J/kg)", data: d.capes, borderColor: (d.cor_cape || "#f97316"), backgroundColor: "transparent",
                       yAxisID: "y2", fill: false, tension: 0.3, borderWidth: 1.6, borderDash: [4, 3], pointRadius: 1.5, spanGaps: false }},
                ]
            }},
            options: {{
                responsive: false, animation: false,
                plugins: {{ legend: {{ display: true, labels: {{ color: "#8b93a3", font: {{ size: 9 }}, boxWidth: 10 }} }} }},
                scales: {{
                    x: {{ ticks: {{ color: "#8b93a3", font: {{ size: 8 }}, maxTicksLimit: 8 }}, grid: {{ color: "#2a2f3a" }} }},
                    y: {{ position: "left", min: 0, beginAtZero: true, ticks: {{ color: "#8b93a3", font: {{ size: 9 }} }}, grid: {{ color: "#2a2f3a" }} }},
                    y1: {{ position: "right", min: 0, beginAtZero: true, ticks: {{ color: "#8b93a3", font: {{ size: 9 }} }}, grid: {{ display: false }} }},
                    y2: {{ display: false, min: 0, beginAtZero: true }},
                }}
            }}
        }});
    }}

    window.blueoceanAbrirPainel = function(chave) {{
        var d = dadosEstacoes[chave];
        if (!d) return;

        document.getElementById("painel_estacao").style.display = "block";
        document.getElementById("painel_estacao_nome").textContent = (d.risco_emoji || "") + " " + d.nome;
        document.getElementById("painel_estacao_resumo").innerHTML =
            "Risco combinado: <b style='color:" + d.risco_color + ";'>" + d.risco_label + "</b><br/>" +
            "Rajada máx.: <b style='color:" + d.cor_gust + ";'>" + d.max_gust.toFixed(0) + " km/h</b>" +
            " · Chuva acum.: <b style='color:" + d.cor_precip + ";'>" + d.soma_precip.toFixed(1) + " mm</b>" +
            " · CAPE máx.: <b style='color:" + d.cor_cape + ";'>" + d.max_cape.toFixed(0) + " J/kg</b>";
        renderizarContatos(d.contatos);

        if (window.Chart) {{
            montarGrafico(d);
        }} else {{
            var s = document.createElement("script");
            s.src = "https://cdn.jsdelivr.net/npm/chart.js";
            s.onload = function() {{ montarGrafico(d); }};
            document.head.appendChild(s);
        }}
    }};

    function ligarMarcadores() {{
        {marcadores_bind_str}
    }}
    if (document.readyState === "complete") {{ ligarMarcadores(); }}
    else {{ window.addEventListener("load", ligarMarcadores); }}
}})();
</script>
"""
    m.get_root().html.add_child(folium.Element(painel_estacao_script))

    # --------------------------------------------------------------
    # Busca de unidade 100% em JS: digitar/escolher aqui só dá zoom +
    # abre o pop-up da unidade no mapa já carregado. Não passa pelo
    # Streamlit, então não recarrega nem reconstrói nada — é só zoom.
    # --------------------------------------------------------------
    map_var_busca = m.get_name()
    estacoes_busca_json = json.dumps(estacoes_para_js, ensure_ascii=False).replace("</", "<\\/")
    marcadores_busca_json = json.dumps(marcadores_js, ensure_ascii=False).replace("</", "<\\/")
    options_html = "".join(f'<option value="{e["nome"]}">' for e in estacoes_para_js)
    busca_html = f"""
<div id="busca-unidade-bar" style="position:absolute; z-index:1000; top:8px; right:50px; background:rgba(15,15,20,0.75); padding:4px 8px; border-radius:6px;">
  <input id="busca-unidade-input" list="busca-unidade-lista" placeholder="🔎 Buscar unidade…" autocomplete="off"
    style="width:180px; font:12px sans-serif; padding:3px 6px; border-radius:4px; border:1px solid #374151; background:#111827; color:#e5e7eb;">
  <datalist id="busca-unidade-lista">{options_html}</datalist>
</div>
<script>
window.addEventListener("load", function() {{
    var mapaBusca = window["{map_var_busca}"];
    var estacoesBusca = {estacoes_busca_json};
    var marcadoresBusca = {marcadores_busca_json};
    var inputBusca = document.getElementById("busca-unidade-input");
    if (!inputBusca) return;

    function irParaUnidade(nome) {{
        var est = estacoesBusca.find(function(e) {{ return e.nome === nome; }});
        if (!est || !mapaBusca) return;
        mapaBusca.flyTo([est.lat, est.lon], 10, {{animate: true, duration: 0.8}});
        var nomeVar = marcadoresBusca[nome];
        var marcador = nomeVar ? window[nomeVar] : null;
        if (marcador && marcador.openPopup) {{
            setTimeout(function() {{ marcador.openPopup(); }}, 400);
        }}
    }}

    inputBusca.addEventListener("change", function() {{ irParaUnidade(inputBusca.value); }});
    inputBusca.addEventListener("keydown", function(ev) {{
        if (ev.key === "Enter") irParaUnidade(inputBusca.value);
    }});
}});
</script>
"""
    m.get_root().html.add_child(folium.Element(busca_html))

    # JS que atualiza SÓ os raios (pontos + células de deslocamento),
    # lendo periodicamente static/raios_live.json — o resto do mapa
    # (tiles, estações, anéis, zoom, pop-ups abertos) fica intocado.
    # Quando um raio cai no range de perigo (30/50 km) de uma unidade,
    # abre o pop-up daquela unidade no mapa e toca o som de alerta.
    # --------------------------------------------------------------
    if incluir_raios:
        map_var = m.get_name()
        raios_fg_var = raios_fg.get_name()
        js_payload = {
            "estacoes": estacoes_para_js,
            "marcadores": marcadores_js,
            "intervaloMs": int(intervalo_raios_seg) * 1000,
            "janelaMin": raios_minutos,
            "somUrl": f"app/static/{som_alerta_nome_ativo}",
            "jsonUrl": "app/static/raios_live.json",
            "mostrarDeslocamento": bool(mostrar_deslocamento),
            "tocarSom": bool(tocar_som),
        }
        js_payload_str = json.dumps(js_payload, ensure_ascii=False).replace("</", "<\\/")
        script_html = f"""
<div id="raios-status-bar" style="position:absolute; z-index:1000; top:8px; left:50px; background:rgba(15,15,20,0.75); color:#e5e7eb; padding:4px 10px; border-radius:6px; font:12px sans-serif;">
  ⚡ carregando raios…
  <button id="raios-som-btn" style="margin-left:8px; font:11px sans-serif; cursor:pointer; background:#1f2937; color:#e5e7eb; border:1px solid #374151; border-radius:4px; padding:1px 6px;">🔊 ativar som</button>
</div>
<style>
.raio-celula-icon {{ background: transparent !important; border: none !important; }}
</style>
<script>
// "load" garante que isso só roda DEPOIS do script principal do Folium
// (que cria o mapa e os marcadores), não importa a ordem no HTML.
window.addEventListener("load", function() {{
    var cfg = {js_payload_str};
    var map = window["{map_var}"];
    var raiosLayer = window["{raios_fg_var}"];
    var celulasLayer = L.layerGroup().addTo(map);
    var audio = new Audio(cfg.somUrl);
    audio.preload = "auto";
    var somLiberado = false;
    var vistosNotificacao = {{}};
    var statusEl = document.getElementById("raios-status-bar");
    var btnSom = document.getElementById("raios-som-btn");
    if (btnSom) {{
        btnSom.onclick = function() {{
            audio.play().then(function() {{ audio.pause(); audio.currentTime = 0; somLiberado = true; btnSom.innerText = "🔊 som ativado"; }}).catch(function() {{}});
        }};
    }}

    function corPorIdade(idadeMin) {{
        var fracao = Math.min(idadeMin / Math.max(cfg.janelaMin, 1), 1);
        if (fracao < 0.33) return "#ff2828";
        if (fracao < 0.66) return "#f97316";
        return "#eab308";
    }}

    function checarPerigo(alertas) {{
        // O Python é quem decide de verdade se uma notificação é NOVA
        // (campo "novo", só fica true por uma janela curtinha logo após
        // decidir notificar) — essa decisão sobrevive à reconstrução do
        // mapa, que é quando a memória local (vistosNotificacao) se perde.
        // vistosNotificacao aqui serve só pra não tocar o som 2x caso o
        // JS dê poll mais de uma vez dentro dessa mesma janela curta.
        (alertas || []).forEach(function(a) {{
            if (!a.novo) return;
            var jaVisto = vistosNotificacao[a.estacao];
            if (jaVisto === a.notificado_ts) return;
            vistosNotificacao[a.estacao] = a.notificado_ts;

            if (cfg.tocarSom) {{
                var nomeVar = cfg.marcadores[a.estacao];
                var marcador = nomeVar ? window[nomeVar] : null;
                if (marcador && marcador.openPopup) {{
                    marcador.openPopup();
                    if (map.panTo) map.panTo(marcador.getLatLng());
                }}
                audio.currentTime = 0;
                audio.play().catch(function() {{}});
            }}
        }});
    }}

    function desenharRaios(data) {{
        raiosLayer.clearLayers();
        (data.raios || []).forEach(function(r) {{
            var cor = corPorIdade(r.idade_min);
            L.circleMarker([r.lat, r.lon], {{radius: 3, color: cor, weight: 1, fill: true, fillColor: cor, fillOpacity: 0.8}})
                .bindTooltip("⚡ " + r.hora + " · ~" + Math.round(r.idade_min) + " min atrás")
                .addTo(raiosLayer);
        }});

        celulasLayer.clearLayers();
        if (cfg.mostrarDeslocamento) {{
            (data.celulas || []).forEach(function(cel) {{
                var hist = cel.historico || [];
                var pts = hist.map(function(p) {{ return [p.lat, p.lon]; }})
                    .concat((cel.checkpoints || []).map(function(c) {{ return [c.lat, c.lon]; }}));
                if (pts.length > 1) {{
                    L.polyline(pts, {{color: "#e5e7eb", weight: 1.5, opacity: 0.55, dashArray: "6, 5"}}).addTo(celulasLayer);
                }}
                hist.forEach(function(p, i) {{
                    var atual = (i === hist.length - 1);
                    var tam = atual ? 18 : 13;
                    var icone = L.divIcon({{
                        className: "raio-celula-icon",
                        html: '<div style="font-weight:900; font-size:' + tam + 'px; color:' + (atual ? "#ef4444" : "#eab308") + '; text-shadow:0 0 4px #000,0 0 7px #000; line-height:1;">✕</div>',
                        iconSize: [tam + 6, tam + 6], iconAnchor: [(tam + 6) / 2, (tam + 6) / 2]
                    }});
                    var marc = L.marker([p.lat, p.lon], {{icon: icone}});
                    if (atual) marc.bindTooltip("Célula #" + cel.id + " · ~" + Math.round(cel.vel_kmh) + " km/h para " + cel.rumo_texto);
                    marc.addTo(celulasLayer);
                }});
                (cel.checkpoints || []).forEach(function(c, idx) {{
                    var op = Math.max(0.75 - idx * 0.18, 0.2);
                    L.circleMarker([c.lat, c.lon], {{radius: 3.5, color: "#e5e7eb", weight: 1, fill: true, fillColor: "#e5e7eb", fillOpacity: op, opacity: op}})
                        .bindTooltip("Célula #" + cel.id + " — alcance estimado em +" + c.min + " min")
                        .addTo(celulasLayer);
                }});
            }});
        }}
    }}

    function atualizar() {{
        fetch(cfg.jsonUrl + "?t=" + Date.now())
            .then(function(r) {{ return r.json(); }})
            .then(function(data) {{
                desenharRaios(data);
                checarPerigo(data.alertas || []);
                if (statusEl) {{
                    var txt = data.erro ? ("⚠️ GLM indisponível: " + data.erro) : ("⚡ raios atualizados às " + (data.atualizado_em_brasilia || "—"));
                    statusEl.childNodes[0].nodeValue = txt + " ";
                }}
            }})
            .catch(function(e) {{ if (statusEl) statusEl.childNodes[0].nodeValue = "⚠️ não foi possível ler os raios "; }});
    }}

    atualizar();
    setInterval(atualizar, cfg.intervaloMs);
}});
</script>
"""
        m.get_root().html.add_child(folium.Element(script_html))

    components.html(m._repr_html_(), height=650)


with col_mapa:
    if incluir_raios:
        st.fragment(run_every=intervalo_raios_seg)(_atualizar_dados_raios)()
    else:
        _atualizar_dados_raios()

    raios_df = st.session_state.get("_fragment_raios_df", pd.DataFrame())
    celulas_com_trajetoria = st.session_state.get("_fragment_celulas", [])

    _construir_mapa()

with col_lado:
    with st.container(key="painel_lateral"):
        tab_risco, tab_rank, tab_alertas, tab_raio = st.tabs(["🚨 Risco", "🏆 Ranking", "📋 Alertas", "⚡ Raios"])

        with tab_risco:
            em_risco = df_estacoes[df_estacoes["risco_score"] > 0].sort_values("risco_score", ascending=False)
            if em_risco.empty: st.success("Nenhuma estação em risco médio/alto no momento.")
            else:
                for _, e in em_risco.iterrows(): st.markdown(f"{e['risco_emoji']} **{e['nome']}** — <span style='color:{e['risco_color']}'>{e['risco_label']}</span>", unsafe_allow_html=True)

        with tab_rank:
            st.markdown(f"**Top 6 — {variavel_mapa}**")
            top6 = df_estacoes.sort_values(chave_var, ascending=False).head(6)[["nome", chave_var]]
            top6.columns = ["Estação", unidade_var]
            st.dataframe(top6, hide_index=True, use_container_width=True)

        with tab_alertas:
            if not alertas: st.success("Nenhum alerta de previsão ativo.")
            else:
                for a in alertas:
                    with st.container(border=True):
                        st.text(a["texto"])
                        st.code(a["texto"], language=None)

        with tab_raio:
            def _corpo_tab_raio():
                if incluir_raios:
                    ultima_att = st.session_state.get("ultima_atualizacao_raios")
                    if ultima_att is not None: st.caption(f"🕐 Última atualização: **{utc_para_brasilia(ultima_att).strftime('%H:%M:%S')}** · janela de {raios_minutos} min · atualiza a cada {intervalo_raios_seg}s")
                else: st.caption("Raios desativados na barra lateral.")

                if st.session_state.alertas_raio_ativos:
                    if st.button("🗑️ Limpar todos os alertas", key="limpar_todos_alertas", use_container_width=True):
                        st.session_state.alertas_raio_ativos = []
                    for a in st.session_state.alertas_raio_ativos:
                        with st.container(border=True):
                            col_txt, col_del = st.columns([6, 1])
                            with col_txt:
                                st.text(a["texto"])
                                st.code(a["texto"], language=None)
                            with col_del:
                                if st.button("✕", key=f"excluir_alerta_{a.get('id', a['texto'])}", help="Excluir este alerta"):
                                    st.session_state.alertas_raio_ativos = [x for x in st.session_state.alertas_raio_ativos if x.get("id") != a.get("id")]
                else:
                    st.info("Nenhum alerta de raio próximo ativo.")

            # Fragmento próprio, no mesmo intervalo dos raios — assim essa
            # lista atualiza junto (no mesmo instante) que o pop-up de
            # alerta aparece, sem precisar de uma interação manual pra
            # a aba "Raios" refletir o alerta mais recente.
            if incluir_raios:
                st.fragment(run_every=intervalo_raios_seg)(_corpo_tab_raio)()
            else:
                _corpo_tab_raio()

st.divider()
col_pdf, _ = st.columns([1, 3])
with col_pdf:
    pdf_bytes = gerar_boletim_pdf_bytes(df_estacoes, alertas, params["target_date"], st.session_state.modelo_label, params["margin_pct"], params["horas"], params["alerta_gust_min"], params["alerta_cape_min"], meteorologista_nome=params["meteorologista"])
    st.download_button("📄 Baixar boletim em PDF", data=pdf_bytes, file_name=f"boletim_{params['target_date']}.pdf", mime="application/pdf", use_container_width=True)