# ======================================================================
# BLUEOCEAN — RAJADAS DE VENTO (versão web / Streamlit)
# Adaptado do app desktop Tkinter original, por Mário Henrique.
# ======================================================================
import io
import json
import re
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
from requests.adapters import HTTPAdapter
from streamlit_folium import st_folium
from urllib3.util.retry import Retry

st.set_page_config(page_title="BlueOcean — Rajadas de Vento", layout="wide", page_icon="🌬️")

EMPRESA = "BlueOcean"

# ======================================================================
# CONTATOS POR UNIDADE (igual ao app desktop)
# ======================================================================
CONTATOS_UNIDADES = {'REGAP': {'nome': 'REGAP',
           'numeros': [{'numero': '(31) 3529 4470'},
                       {'numero': '(31) 3529 4405'},
                       {'numero': '(31) 3529 4508'}]},
 'CILEP_CENPES': {'nome': 'CILEP CENPES',
                  'numeros': [{'numero': '(21) 9 9700 6335'}, {'numero': '(21) 9 7968 0027'}]},
 'TMIB COQUEIROS': {'nome': 'TMIB COQUEIROS',
                    'numeros': [{'numero': '(79) 3212 5101'}, {'numero': '(79) 9 9630 8427'}]},
 'ARM RIO': {'nome': 'ARM RIO',
             'numeros': [{'numero': '(21) 9 6576-0066'},
                         {'numero': '(21) 9 6576-0142'},
                         {'numero': '(21) 9 9649 4019'}]},
 'UTE_Canoas': {'nome': 'UTE Canoas',
                'numeros': [{'numero': '(51) 3415-3939'}, {'numero': '(51) 99866-6449'}]},
 'Guamaré': {'nome': 'Guamaré',
             'numeros': [{'numero': '(85) 98830.3729'},
                         {'numero': '(84) 99984.7020'},
                         {'numero': '85) 99207.7804'}]},
 'REFAP': {'nome': 'REFAP',
           'numeros': [{'numero': '(51) 3415-2080'},
                       {'numero': '(51) 99982-0520'},
                       {'numero': '(51) 99617-3964'}]},
 'REPAR': {'nome': 'REPAR',
           'numeros': [{'numero': '(41) 3641-2987'},
                       {'numero': '(41) 99157-6902'},
                       {'numero': '(41) 99241-5443'}]},
 'UTC_Nova_Piratininga': {'nome': 'UTE Nova Piratininga',
                          'numeros': [{'numero': '(11) 3523-5856'},
                                      {'numero': '(11) 3523 5876'},
                                      {'numero': '(11) 98393-0913'}]},
 'RPBC': {'nome': 'RPBC',
          'numeros': [{'numero': '(13) 3328-4074'},
                      {'numero': '(13) 99712-4788'},
                      {'numero': '(13) 3328-4253'}]},
 'RECAP': {'nome': 'RECAP',
           'numeros': [{'numero': '(11) 3795-9314'},
                       {'numero': '(11) 96183-2809'},
                       {'numero': '(11) 3795-9130'}]},
 'UTG_Caraguatatuba': {'nome': 'UTGCA - Caraguatatuba',
                       'numeros': [{'numero': '(12) 3886-5050', 'descricao': 'Opção 1'},
                                   {'numero': '(12) 3886-5117', 'descricao': 'Opção 2'},
                                   {'numero': '(12) 3886-5066', 'descricao': 'Opção 3'}]},
 'REVAP': {'nome': 'REVAP',
           'numeros': [{'numero': '(12) 3928-6304'},
                       {'numero': '(12) 3928-6499'},
                       {'numero': '(12) 9 9130-6608'}]},
 'REPLAN': {'nome': 'REPLAN',
            'numeros': [{'numero': '(19) 2116-6892 e (19) 99772-1201',
                         'descricao': 'celular melhor'},
                        {'numero': '(19) 2116-6542 e (19) 99602-8522'},
                        {'numero': '(19) 2116--6183'}]},
 'UTE_Tres_lagoas': {'nome': 'UTE Três Lagoas',
                     'numeros': [{'numero': '(67) 3509-3275',
                                  'descricao': 'Opção 1 - Sala de Controle'},
                                 {'numero': '(67) 3509 - 3234',
                                  'descricao': 'Opção 2 - Supervisor de Turno'},
                                 {'numero': '(67) 9 - 9847 - 3567',
                                  'descricao': 'Opção 3 - Celular da Operação'}]},
 'UTE_Seropedica': {'nome': 'UTE Seropédica',
                    'numeros': [{'numero': '(21) 2665-9221', 'descricao': 'supervisao op'},
                                {'numero': '(21) 2665-9234'},
                                {'numero': '(21) 98330 0979.'}]},
 'UTE_Termorio': {'nome': 'UTE Termorio',
                  'numeros': [{'numero': '(21) 3227-5746'},
                              {'numero': '(21) 98055-0569'},
                              {'numero': '(21) 9 6720 8088'}]},
 'REDUC': {'nome': 'REDUC',
           'numeros': [{'numero': '(21) 2677-2232', 'descricao': 'Opção 1'},
                       {'numero': '(21) 2677-2975', 'descricao': 'Opção 2'},
                       {'numero': '(21) 9 - 9872 - 4188',
                        'descricao': 'Fernanda Neves (Gerente do Setor)'}]},
 'UTG_Itaborai': {'nome': 'UTG Itaboraí',
                  'numeros': [{'numero': '(21) 2133-4199', 'descricao': 'ligar neste'},
                              {'numero': '(21) 2133-4202'},
                              {'numero': '(21) 99700-6571'}]},
 'Arm Macaé': {'nome': 'Arm Macaé',
               'numeros': [{'numero': '(22) 9 9824-6085'}, {'numero': '(22) 9 9940-2957'}]},
 'UTE Juiz de Fora': {'nome': 'UTE Juiz de Fora',
                      'numeros': [{'numero': '(32) 3239-8431', 'descricao': 'sala op'},
                                  {'numero': '(32) 3239-8423', 'descricao': 'sala op'},
                                  {'numero': '(32) 99804-4943'}]},
 'UTE_Termomacae': {'nome': 'UTE Termomacaé',
                    'numeros': [{'numero': '(22) 3379-6134'},
                                {'numero': '(22) 3379-6135'},
                                {'numero': '(22) 98817-2571'}]},
 'UTG_Cabiunas': {'nome': 'UTG Cabiunas',
                  'numeros': [{'numero': '(22) 9 - 9981-1678 / Ramal: 2759 - 5280',
                               'descricao': 'Opção 1'},
                              {'numero': '(22) 9 - 9778-7616 / Ramal: 2797 - 5248 / 2797 - 5249',
                               'descricao': 'Opção 2'}]},
 'UTE_Ibirite': {'nome': 'UTE Ibirité',
                 'numeros': [{'numero': '(31) 3472-2230'},
                             {'numero': '(31) 99704-5869'},
                             {'numero': '(11) 96857-9818'}]},
 'UTG Sul_Capixaba': {'nome': 'UTG Sul Capixaba',
                      'numeros': [{'numero': '(28) 3360-6065', 'descricao': 'CISP'},
                                  {'numero': '(27) 99297-9464', 'descricao': 'CISP'}]},
 'UTG_Cacimbas': {'nome': 'UTG C - Cacimbas',
                  'numeros': [{'numero': '(27) 3048-9107 / 9903',
                               'descricao': 'Supervisão da Operação (K-45)'},
                              {'numero': '(27) 3048-9300 / 9909'},
                              {'numero': '(27)3048-9152',
                               'descricao': 'Coordenador de Turno da Operação (K-45)'},
                              {'numero': '(27) 3048-9131', 'descricao': 'SMS (k-32)'},
                              {'numero': '(27)3048-9140',
                               'descricao': 'Controle de CFTV - 24h (k-04)'}]},
 'RNEST': {'nome': 'RNEST',
           'numeros': [{'numero': '(81) 3879 - 4530'},
                       {'numero': '(81) 3879 - 3220'},
                       {'numero': '(81) 3879 - 4525'}]},
 'UTE_Termobahia': {'nome': 'UTE Termobahia',
                    'numeros': [{'numero': '(71) 3348-5006', 'descricao': 'Opção 1'},
                                {'numero': '(71) 9 - 9988-5704', 'descricao': 'Opção 2'},
                                {'numero': '(71) 9 - 9918 - 3933 / 9 -9672 - 4400',
                                 'descricao': 'Opção 3'}]},
 'Porto Belém': {'nome': 'PORTO BELÉM',
                 'numeros': [{'numero': '(91) 99150.0369'},
                             {'numero': '(79) 99163.0089'},
                             {'numero': '(85) 99207.7804'}]},
 'Mucuripe_Paracuru': {'nome': 'Mucuripe Paracuru',
                       'numeros': [{'numero': '(85) 98147.6460'},
                                   {'numero': '(85) 98829.9818'},
                                   {'numero': '(85) 98126.3018'},
                                   {'numero': '85) 99207.7804'}]},
 'UTE_Vale_ACU': {'nome': 'UTE Vale do Açu',
                  'numeros': [{'numero': '(84) 3235-6033', 'descricao': 'Opção 1'},
                              {'numero': '(84) 3235-6034', 'descricao': 'Opção 2'},
                              {'numero': '(84)  9 9609 - 9675', 'descricao': 'Opção 3'}]},
 'UTE_Termoceara': {'nome': 'UTE Termoceara',
                    'numeros': [{'numero': '(85) 3411 - 4420 / 4440',
                                 'descricao': 'Sala de Controle da Unidade'},
                                {'numero': '(85) 9 9957-4422',
                                 'descricao': 'Cristiano Freire - Gerente de Operação'},
                                {'numero': '(85) 998490019',
                                 'descricao': 'Thiago Gerente de SMS'}]},
 'Porto Aratu': {'nome': 'Porto Aratu', 'numeros': [{'numero': '(71) 9 9649 4961'}]},
 'Porto Macaé': {'nome': 'UTE Porto Macaé',
                 'numeros': [{'numero': '(22) 9 8113-0416'},
                             {'numero': '(22) 9 8183-0096'},
                             {'numero': '(22) 9 9736-9161'}]},
 'Porto Valença': {'nome': 'UTE Porto VALENÇA', 'numeros': [{'numero': '(71) 9 9649 4961'}]},
 'Porto Açu': {'nome': 'UTE Porto AÇU',
               'numeros': [{'numero': '(22) 9 9944 9292'}, {'numero': '(22) 9 9962 7159'}]},
 'Porto B Guanabara': {'nome': 'UTE PORTO BAIA DE  GUANABARA',
                       'numeros': [{'numero': '(21) 9 9519 4346'},
                                   {'numero': '(21) 2144 0051'},
                                   {'numero': '(21) 9 8145 4321'}]}}


def _normalizar_nome(texto):
    if not texto:
        return ""
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
_PALAVRAS_GENERICAS_UNIDADE = {
    "REFINARIA", "USINA", "UNIDADE", "TERMELETRICA", "TERMOELETRICA", "TERMICA", "COMPLEXO",
    "INDUSTRIAL", "TRATAMENTO", "GAS", "PORTO", "TERMINAL", "ARMAZENAMENTO", "DE", "DO", "DA", "DOS", "DAS", "E",
}


def _palavras_significativas(t):
    return {p for p in t.split() if p not in _PALAVRAS_GENERICAS_UNIDADE and len(p) > 2}


def buscar_contatos_por_estacao(nome_estacao):
    alvo = _normalizar_nome(str(nome_estacao))
    if not alvo:
        return None
    palavras_alvo = _palavras_significativas(alvo)
    melhor_substring, melhor_tam = None, 0
    melhor_palavras, melhor_qtd = None, 0
    for chave, info in CONTATOS_UNIDADES.items():
        candidatos = [chave, info["nome"]] + ALIASES_UNIDADES.get(chave, [])
        for bruto in candidatos:
            candidato = _normalizar_nome(bruto)
            if not candidato:
                continue
            if candidato == alvo:
                return info
            if len(candidato) >= 4 and (candidato in alvo or alvo in candidato):
                if len(candidato) > melhor_tam:
                    melhor_substring, melhor_tam = info, len(candidato)
            pc = _palavras_significativas(candidato)
            if len(pc) >= 2 and pc and pc <= palavras_alvo:
                if len(pc) > melhor_qtd:
                    melhor_palavras, melhor_qtd = info, len(pc)
    return melhor_substring or melhor_palavras


# ======================================================================
# ESCALAS OPERACIONAIS
# ======================================================================
GUST_THRESHOLDS = [1.8, 6, 11, 20, 30, 40, 50, 61, 74, 87, 102]
GUST_COLORS = ["#4ade80", "#34d399", "#22c55e", "#16a34a", "#15803d", "#166534", "#eab308",
               "#ca8a04", "#f87171", "#ef4444", "#dc2626", "#991b1b"]
GUST_LABELS = ["Calmaria", "Aragem, Vento Quase Calmo", "Brisa leve", "Vento fresco ou leve",
               "Vento Moderado", "Vento Regular", "Vento muito fresco ou meio forte", "Vento Forte",
               "Ventania", "Ventania Forte", "Vendaval ou Tempestade", "Ciclone Extratropical"]

RAIN_THRESHOLDS = [2.5, 10, 25, 50]
RAIN_COLORS = ["#a8d8ff", "#4fa8f0", "#2166d6", "#7c3aed", "#5b0fae"]
RAIN_LABELS = ["Previsão de chuvisco a chuva fraca", "Previsão de chuva fraca a moderada",
               "Previsão de chuva moderada a forte", "Previsão de chuva forte", "Previsão de chuva extrema"]

CAPE_THRESHOLDS = [300, 1000, 2500, 4000]
CAPE_COLORS = ["#a8d8ff", "#eab308", "#f97316", "#ef4444", "#7c1d1d"]
CAPE_LABELS = ["Instabilidade fraca", "Instabilidade moderada", "Instabilidade forte",
               "Instabilidade muito forte", "Instabilidade extrema"]

ALERTA_CAPE_MIN_JKG_PADRAO = 2500
TIMEZONE_OFFSET_HOURS = -3
GLM_BUCKET = "noaa-goes19"
GLM_BASE_URL = f"https://{GLM_BUCKET}.s3.amazonaws.com"
SOUTH_AMERICA_BOUNDS = {"lat_min": -58.0, "lat_max": 13.5, "lon_min": -82.0, "lon_max": -33.0}


def classify_index(v, thresholds):
    if v is None or pd.isna(v):
        v = 0.0
    v = float(v)
    for i, lim in enumerate(thresholds):
        if v <= lim:
            return i
    return len(thresholds)


def gust_color_hex(v):
    return GUST_COLORS[classify_index(v, GUST_THRESHOLDS)]


def rain_color_hex(v):
    return RAIN_COLORS[classify_index(v, RAIN_THRESHOLDS)]


def cape_color_hex(v):
    return CAPE_COLORS[classify_index(v, CAPE_THRESHOLDS)]


def _hora_local(t):
    return int((t.hour + TIMEZONE_OFFSET_HOURS) % 24)


def classificar_periodo(h):
    if 0 <= h < 6: return "madrugada"
    if 6 <= h < 12: return "manhã"
    if 12 <= h < 18: return "tarde"
    return "noite"


def periodos_acima_limiar(valid_times, valores, limiar):
    ordem = ["madrugada", "manhã", "tarde", "noite"]
    encontrados = set()
    for t, v in zip(valid_times, valores):
        if v is None or pd.isna(v):
            continue
        if float(v) > limiar:
            encontrados.add(classificar_periodo(_hora_local(t)))
    return [p for p in ordem if p in encontrados]


def formatar_periodos_texto(periodos):
    prep = {"madrugada": "de madrugada", "manhã": "pela manhã", "tarde": "à tarde", "noite": "à noite"}
    if not periodos:
        return "ao longo do dia"
    if len(periodos) >= 4:
        return "ao longo de todo o dia"
    textos = [prep[p] for p in periodos]
    if len(textos) == 1:
        return textos[0]
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


def montar_mensagem_proximidade_raio(nivel, nome_estacao, meteorologista):
    agora = datetime.now()
    validade = agora + timedelta(hours=1)
    janela = "-15 min até o momento" if nivel == 30 else "-30 min até o momento"
    emoji = "🔴" if nivel == 30 else "🟡"
    return (f"{emoji} {agora.strftime('%d/%m/%Y')} - {agora.strftime('%H:%M')}\n"
            f"* Local: {nome_estacao}\n"
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
    retries = Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    a = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    s.mount("https://", a); s.mount("http://", a)
    return s


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_openmeteo_full_hourly(df_json, model, target_date, batch_size=40):
    df = pd.read_json(io.StringIO(df_json))
    session = build_session()
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
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
            "models": model, "timezone": "UTC", "past_days": past_days, "forecast_days": forecast_days,
        }
        r = session.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=90)
        r.raise_for_status()
        data = r.json()
        points = data if isinstance(data, list) else [data]
        for (_, row), point in zip(batch.iterrows(), points):
            n_horas = len(point["hourly"]["time"])
            precip_list = point["hourly"].get("precipitation", [None] * n_horas)
            cape_list = point["hourly"].get("cape", [None] * n_horas)
            for t, g, s_, dr, p, cp in zip(point["hourly"]["time"], point["hourly"]["wind_gusts_10m"],
                                            point["hourly"]["wind_speed_10m"], point["hourly"]["wind_direction_10m"],
                                            precip_list, cape_list):
                results.append({"estacao": row["estacao"], "lat": row["lat"], "lon": row["lon"], "modelo": model,
                                 "valid_time": t, "wind_gust_kmh": g, "wind_speed_kmh": s_, "wind_dir_deg": dr,
                                 "precip_mm": p, "cape_jkg": cp})
    out = pd.DataFrame(results)
    out["valid_time"] = pd.to_datetime(out["valid_time"])
    return out


def compute_ensemble(dfs):
    dfs_validos = [d for d in dfs if d is not None and not d.empty]
    if not dfs_validos:
        return pd.DataFrame(columns=["estacao", "lat", "lon", "valid_time", "wind_gust_kmh", "wind_speed_kmh",
                                      "wind_dir_deg", "precip_mm", "cape_jkg", "modelo"])
    base = dfs_validos[0][["estacao", "lat", "lon", "valid_time"]].drop_duplicates()
    soma_gust = np.zeros(len(base)); soma_precip = np.zeros(len(base)); soma_cape = np.zeros(len(base))
    soma_sin = np.zeros(len(base)); soma_cos = np.zeros(len(base))
    for d in dfs_validos:
        merged = base.merge(d[["estacao", "lat", "lon", "valid_time", "wind_gust_kmh", "wind_dir_deg",
                                "precip_mm", "cape_jkg"]], on=["estacao", "lat", "lon", "valid_time"], how="left")
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
# GLM — RAIOS (GOES-19, AWS S3 público)
# ======================================================================
def _parse_glm_timestamp(nome):
    m = re.search(r"_s(\d{13})", nome)
    if not m:
        return None
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
        try:
            chaves.extend(_listar_arquivos_glm_hora(session, ano, doy, hora))
        except Exception:
            falhas += 1
    if falhas == len(horas):
        raise RuntimeError("não foi possível conectar ao bucket GLM na AWS")

    arquivos = sorted(c for c in chaves if (ts := _parse_glm_timestamp(c)) is not None and ts >= inicio)
    if not arquivos:
        return pd.DataFrame(columns=["lat", "lon", "energy_j", "time"])

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
        except Exception:
            continue
    df = pd.DataFrame(linhas)
    if not df.empty:
        b = SOUTH_AMERICA_BOUNDS
        df = df[(df["lat"] >= b["lat_min"]) & (df["lat"] <= b["lat_max"]) &
                (df["lon"] >= b["lon_min"]) & (df["lon"] <= b["lon_max"])]
    return df


# ======================================================================
# RESUMO POR ESTAÇÃO
# ======================================================================
def calcular_resumo_estacoes(df_full, target_date, safety_margin_pct, horas_filtro=None,
                              alerta_gust_min=40, alerta_cape_min=ALERTA_CAPE_MIN_JKG_PADRAO):
    d = df_full[df_full["valid_time"].dt.date == pd.Timestamp(target_date).date()].copy()
    if horas_filtro:
        d = d[d["valid_time"].dt.strftime("%H").isin(horas_filtro)]
    if d.empty:
        return pd.DataFrame(), []
    d["gust_ajustado"] = d["wind_gust_kmh"] * (1 + safety_margin_pct / 100)
    for c in ("precip_mm", "cape_jkg"):
        if c not in d.columns:
            d[c] = np.nan
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
            alertas.append({"id": prox_id, "tipo": "vento", "estacao": nome,
                             "texto": montar_mensagem_alerta_vento(nome, 61, formatar_periodos_texto(per))}); prox_id += 1
        elif max_gust > alerta_gust_min:
            per = periodos_acima_limiar(g["valid_time"], g["gust_ajustado"], alerta_gust_min)
            alertas.append({"id": prox_id, "tipo": "vento", "estacao": nome,
                             "texto": montar_mensagem_alerta_vento(nome, 40, formatar_periodos_texto(per))}); prox_id += 1
        precip_max_hora = max(precs) if precs else 0.0
        idx_chuva = classify_index(precip_max_hora, RAIN_THRESHOLDS)
        if idx_chuva >= 2:
            alertas.append({"id": prox_id, "tipo": "chuva", "estacao": nome,
                             "texto": montar_mensagem_alerta_chuva(nome, RAIN_LABELS[idx_chuva])}); prox_id += 1
        if max_cape > alerta_cape_min:
            per_c = periodos_acima_limiar(g["valid_time"], g["cape_jkg"], alerta_cape_min)
            alertas.append({"id": prox_id, "tipo": "cape", "estacao": nome,
                             "texto": montar_mensagem_alerta_cape(nome, formatar_periodos_texto(per_c), max_cape)}); prox_id += 1
    return pd.DataFrame(linhas), alertas


# ======================================================================
# PDF (boletim)
# ======================================================================
def gerar_boletim_pdf_bytes(df_estacoes, alertas, target_date, modelo_label, margin_pct, horas_filtro,
                             alerta_gust_min, alerta_cape_min, meteorologista_nome=""):
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
    estilo_alerta = ParagraphStyle("A", parent=styles["Normal"], fontSize=9.5,
                                    backColor=colors.HexColor("#f5f5f5"), borderPadding=6, spaceAfter=8)

    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    story = []
    data_fmt = pd.Timestamp(target_date).strftime("%d/%m/%Y")
    horas_txt = "todas as 24h" if not horas_filtro or len(horas_filtro) == 24 else ", ".join(f"{h}h" for h in sorted(horas_filtro))

    story.append(Paragraph(f"Boletim Meteorológico Diário — {EMPRESA}", estilo_titulo))
    story.append(Paragraph(
        f"Data da previsão: <b>{data_fmt}</b> · Modelo(s): <b>{modelo_label}</b> · Margem: <b>+{margin_pct}%</b><br/>"
        f"Horários: {horas_txt}<br/>Limiares: rajada &gt;{alerta_gust_min} km/h (alto acima de 61) · CAPE &gt;{alerta_cape_min:.0f} J/kg<br/>"
        f"Meteorologista: <b>{meteorologista_nome or '(não informado)'}</b><br/>Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        estilo_normal))
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
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5c5c")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccc")),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")])]))
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
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ef4444")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ccc")),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")])]))
        story.append(t)
    else:
        story.append(Paragraph("Nenhuma estação em risco médio/alto.", estilo_normal))

    story.append(PageBreak())
    story.append(Paragraph("Alertas de previsão gerados", estilo_secao))
    emoji_pat = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF\u2190-\u21FF\uFE0F\u200d]+")
    if alertas:
        for a in alertas:
            story.append(Paragraph(emoji_pat.sub("", a["texto"]).strip(), estilo_alerta))
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

if "alertas_raio_ativos" not in st.session_state:
    st.session_state.alertas_raio_ativos = []
if "alertas_raio_disparados" not in st.session_state:
    st.session_state.alertas_raio_disparados = {}
if "log_alertas" not in st.session_state:
    st.session_state.log_alertas = []  # auditoria só desta sessão (não persiste no servidor gratuito)

with st.sidebar:
    st.header("⚙ Configuração")
    meteorologista = st.text_input("Meteorologista responsável", value="")

    st.subheader("📁 Planilha de estações")
    arquivo_estacoes = st.file_uploader("Envie o .xlsx (colunas: estacao, lat, lon)", type=["xlsx"])
    df_stations = None
    if arquivo_estacoes is not None:
        df_stations = pd.read_excel(arquivo_estacoes)
        if df_stations.shape[1] != 3:
            st.error(f"Esperava 3 colunas (estação/lat/lon), encontrei {df_stations.shape[1]}.")
            df_stations = None
        else:
            df_stations.columns = ["estacao", "lat", "lon"]
            st.success(f"{len(df_stations)} estações carregadas.")

    st.subheader("📅 Data e horários")
    target_date = st.date_input("Data da previsão", value=datetime.now().date())
    todas_horas = [f"{h:02d}" for h in range(24)]
    horas_selecionadas = st.multiselect("Horários (UTC) a incluir", todas_horas, default=todas_horas)

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
    tocar_som = st.checkbox("Tocar som quando raio cair perto de uma unidade", value=True, disabled=not incluir_raios)

    variavel_mapa = st.radio("Variável exibida no mapa", ["Rajada de vento", "Precipitação", "CAPE"], horizontal=False)

    gerar = st.button("🌍 Gerar / Atualizar mapa", type="primary", use_container_width=True)

if df_stations is None:
    st.info("⬅️ Envie a planilha de estações (.xlsx com colunas estação/lat/lon) na barra lateral pra começar.")
    st.stop()

margin = 1.5
bbox = {"lon_min": df_stations["lon"].min() - margin, "lon_max": df_stations["lon"].max() + margin,
        "lat_min": df_stations["lat"].min() - margin, "lat_max": df_stations["lat"].max() + margin}

if gerar:
    with st.spinner("Buscando dados no Open-Meteo..."):
        modelos_necessarios = set(ENSEMBLE_MODELOS) | {m for m in (modelo_vento, modelo_chuva, modelo_cape) if m != "ensemble"}
        df_json = df_stations.to_json()
        dfs_base = {m: fetch_openmeteo_full_hourly(df_json, m, str(target_date)) for m in sorted(modelos_necessarios)}

        def obter(modelo_id):
            return compute_ensemble([dfs_base[m] for m in ENSEMBLE_MODELOS]) if modelo_id == "ensemble" else dfs_base[modelo_id]

        df_vento_src, df_chuva_src, df_cape_src = obter(modelo_vento), obter(modelo_chuva), obter(modelo_cape)
        chave = ["estacao", "lat", "lon", "valid_time"]
        df_final = df_vento_src[chave + ["wind_gust_kmh", "wind_speed_kmh", "wind_dir_deg"]].copy()
        df_final = df_final.merge(df_chuva_src[chave + ["precip_mm"]], on=chave, how="left")
        df_final = df_final.merge(df_cape_src[chave + ["cape_jkg"]], on=chave, how="left")

        label_v, label_c, label_cp = MODEL_LABELS[modelo_vento], MODEL_LABELS[modelo_chuva], MODEL_LABELS[modelo_cape]
        modelo_label = label_v if modelo_vento == modelo_chuva == modelo_cape else f"{label_v} (vento)/{label_c} (chuva)/{label_cp} (CAPE)"

        st.session_state.df_full = df_final
        st.session_state.modelo_label = modelo_label
        st.session_state.params = dict(target_date=str(target_date), horas=horas_selecionadas, margin_pct=margin_pct,
                                        alerta_gust_min=alerta_gust_min, alerta_cape_min=alerta_cape_min, meteorologista=meteorologista)

if "df_full" not in st.session_state:
    st.info("Configure os parâmetros na barra lateral e clique em **Gerar / Atualizar mapa**.")
    st.stop()

df_full = st.session_state.df_full
params = st.session_state.params
df_estacoes, alertas = calcular_resumo_estacoes(df_full, params["target_date"], params["margin_pct"],
                                                 horas_filtro=params["horas"], alerta_gust_min=params["alerta_gust_min"],
                                                 alerta_cape_min=params["alerta_cape_min"])

if df_estacoes.empty:
    st.warning("Nenhum dado horário disponível pra essa combinação de data/horários.")
    st.stop()

# --------- raios (opcional) ---------
raios_df = pd.DataFrame()
if incluir_raios:
    try:
        raios_df = fetch_glm_flashes_recent(minutos=raios_minutos)
    except Exception as e:
        st.sidebar.warning(f"GLM indisponível: {e}")

    if not raios_df.empty:
        for _, raio in raios_df.iterrows():
            for _, est in df_estacoes.iterrows():
                dist = ((raio["lat"] - est["lat"]) ** 2 + (raio["lon"] - est["lon"]) ** 2) ** 0.5 * 111
                for nivel in (30, 50):
                    if dist > nivel:
                        continue
                    chave_alerta = f"{est['nome']}_{nivel}"
                    ultimo = st.session_state.alertas_raio_disparados.get(chave_alerta, 0)
                    if time.time() - ultimo < 3600:
                        continue
                    st.session_state.alertas_raio_disparados[chave_alerta] = time.time()
                    texto = montar_mensagem_proximidade_raio(nivel, est["nome"], params["meteorologista"])
                    st.session_state.alertas_raio_ativos.insert(0, {"texto": texto, "estacao": est["nome"], "expira": time.time() + 3600})
                    if tocar_som:
                        st.session_state["_tocar_beep"] = True

st.session_state.alertas_raio_ativos = [a for a in st.session_state.alertas_raio_ativos if a["expira"] > time.time()]

if st.session_state.get("_tocar_beep"):
    st.audio("data/alerta_raio.wav", autoplay=True)
    st.session_state["_tocar_beep"] = False

# ======================================================================
# LAYOUT — mapa + painéis
# ======================================================================
col_mapa, col_lado = st.columns([2.4, 1])

var_map = {"Rajada de vento": ("max_gust", gust_color_hex, "km/h"), "Precipitação": ("soma_precip", rain_color_hex, "mm"),
           "CAPE": ("max_cape", cape_color_hex, "J/kg")}
chave_var, color_fn, unidade_var = var_map[variavel_mapa]

with col_mapa:
    center_lat = (bbox["lat_min"] + bbox["lat_max"]) / 2
    center_lon = (bbox["lon_min"] + bbox["lon_max"]) / 2
    m = folium.Map(location=[center_lat, center_lon], tiles="CartoDB dark_matter", control_scale=True)
    m.fit_bounds([[bbox["lat_min"], bbox["lon_min"]], [bbox["lat_max"], bbox["lon_max"]]])

    for _, e in df_estacoes.iterrows():
        cor_valor = color_fn(e[chave_var])
        popup_html = (f"<b>{e['risco_emoji']} {e['nome']}</b><br/>"
                      f"Risco combinado: <b style='color:{e['risco_color']}'>{e['risco_label']}</b><br/>"
                      f"Rajada máx.: {e['max_gust']:.0f} km/h<br/>"
                      f"Chuva acum.: {e['soma_precip']:.1f} mm<br/>"
                      f"CAPE máx.: {e['max_cape']:.0f} J/kg")
        if e["contatos"]:
            popup_html += f"<hr/><b>📞 {e['contatos']['nome']}</b><br/>"
            for item in e["contatos"]["numeros"][:3]:
                popup_html += f"{item['numero']}"
                if item.get("descricao"):
                    popup_html += f" <i>({item['descricao']})</i>"
                popup_html += "<br/>"
        folium.CircleMarker(
            location=[e["lat"], e["lon"]], radius=8, color=e["risco_color"], weight=3,
            fill=True, fill_color=cor_valor, fill_opacity=0.9,
            tooltip=f"{e['risco_emoji']} {e['nome']} — {e[chave_var]:.1f} {unidade_var}",
            popup=folium.Popup(popup_html, max_width=260),
        ).add_to(m)

    if incluir_raios and not raios_df.empty:
        agora = datetime.now(timezone.utc)
        for _, raio in raios_df.iterrows():
            idade_min = max((agora - raio["time"]).total_seconds() / 60, 0) if pd.notna(raio["time"]) else 0
            fracao = min(idade_min / max(raios_minutos, 1), 1)
            cor = "#ff2828" if fracao < 0.33 else ("#f97316" if fracao < 0.66 else "#eab308")
            folium.CircleMarker(location=[raio["lat"], raio["lon"]], radius=3, color=cor, weight=1,
                                 fill=True, fill_color=cor, fill_opacity=0.8,
                                 tooltip=f"⚡ ~{idade_min:.0f} min atrás").add_to(m)

    st_folium(m, height=620, use_container_width=True, returned_objects=[])

with col_lado:
    tab_risco, tab_rank, tab_alertas, tab_raio, tab_contatos = st.tabs(["🚨 Risco", "🏆 Ranking", "📋 Alertas", "⚡ Raios", "📞 Contatos"])

    with tab_risco:
        em_risco = df_estacoes[df_estacoes["risco_score"] > 0].sort_values("risco_score", ascending=False)
        if em_risco.empty:
            st.success("Nenhuma estação em risco médio/alto no momento.")
        else:
            for _, e in em_risco.iterrows():
                st.markdown(f"{e['risco_emoji']} **{e['nome']}** — <span style='color:{e['risco_color']}'>{e['risco_label']}</span>", unsafe_allow_html=True)

    with tab_rank:
        st.markdown(f"**Top 6 — {variavel_mapa}**")
        top6 = df_estacoes.sort_values(chave_var, ascending=False).head(6)[["nome", chave_var]]
        top6.columns = ["Estação", unidade_var]
        st.dataframe(top6, hide_index=True, use_container_width=True)

    with tab_alertas:
        if not alertas:
            st.success("Nenhum alerta de previsão ativo.")
        else:
            for a in alertas:
                with st.container(border=True):
                    st.text(a["texto"])
                    st.code(a["texto"], language=None)

    with tab_raio:
        st.caption(f"Monitorando raios (GLM/GOES-19) — janela de {raios_minutos} min." if incluir_raios else "Raios desativados na barra lateral.")
        if st.session_state.alertas_raio_ativos:
            for a in st.session_state.alertas_raio_ativos:
                with st.container(border=True):
                    st.text(a["texto"])
                    st.code(a["texto"], language=None)
        else:
            st.info("Nenhum alerta de raio próximo ativo.")

    with tab_contatos:
        nomes_unidades = sorted(CONTATOS_UNIDADES.keys(), key=lambda k: CONTATOS_UNIDADES[k]["nome"].lower())
        escolha = st.selectbox("Unidade", nomes_unidades, format_func=lambda k: CONTATOS_UNIDADES[k]["nome"])
        info = CONTATOS_UNIDADES[escolha]
        st.markdown(f"**📞 {info['nome']}**")
        for i, item in enumerate(info["numeros"], start=1):
            linha = f"{i}. {item['numero']}"
            if item.get("descricao"):
                linha += f"  _{item['descricao']}_"
            st.markdown(linha)

st.divider()
col_pdf, _ = st.columns([1, 3])
with col_pdf:
    pdf_bytes = gerar_boletim_pdf_bytes(df_estacoes, alertas, params["target_date"], st.session_state.modelo_label,
                                         params["margin_pct"], params["horas"], params["alerta_gust_min"],
                                         params["alerta_cape_min"], meteorologista_nome=params["meteorologista"])
    st.download_button("📄 Baixar boletim em PDF", data=pdf_bytes,
                        file_name=f"boletim_{params['target_date']}.pdf", mime="application/pdf",
                        use_container_width=True)
