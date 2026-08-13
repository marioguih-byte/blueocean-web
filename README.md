# BlueOcean — Rajadas de Vento (versão web)

Versão do painel de monitoramento adaptada para rodar num navegador, hospedada
de graça no **Streamlit Community Cloud**.

## O que mudou em relação ao app desktop (Tkinter)

- A janela Tkinter virou uma página web (`streamlit_app.py`).
- A planilha de estações agora é enviada por upload na barra lateral, em vez
  de ser lida de uma pasta fixa do seu PC.
- O som de alerta de raio próximo toca um beep genérico embutido
  (`data/alerta_raio.wav`) — não dá pra "tocar prévia de um arquivo do seu PC"
  como no app desktop, porque o servidor não tem acesso ao seu computador.
- O histórico de alertas copiados/excluídos (auditoria) agora vale só pra
  sessão aberta no navegador — não fica salvo permanentemente, porque o
  Streamlit Cloud gratuito não mantém disco entre reinicializações do app
  (ele "dorme" depois de um tempo sem uso e reinicia do zero). Se um dia você
  quiser esse histórico permanente, dá pra plugar um banco gratuito (ex.:
  Supabase) — é um passo futuro, não obrigatório agora.
- A trajetória animada das células de tempestade (as marcas "✕" se movendo) e
  o campo de vento animado de fundo foram simplificados: os raios aparecem
  como pontos coloridos por idade (vermelho → laranja → amarelo), sem a
  projeção de deslocamento.

Tudo o resto (rajada/chuva/CAPE por estação, ranking, risco combinado 🟢🟡🔴,
alertas estilo WhatsApp, contatos por unidade e exportação de boletim em PDF)
funciona igual.

## Passo a passo pra colocar no ar (grátis)

### 1. Suba esta pasta pro GitHub

```bash
cd blueocean_web
git init
git add .
git commit -m "BlueOcean web"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/blueocean-web.git
git push -u origin main
```

Se preferir sem terminal: crie um repositório novo em github.com → "Add file"
→ "Upload files" → arraste todos os arquivos desta pasta (mantendo a
subpasta `.streamlit/` e `data/`).

**Importante:** o repositório pode ser público ou privado — os dois funcionam
no plano gratuito do Streamlit Cloud.

### 2. Crie a conta no Streamlit Cloud

Acesse **share.streamlit.io**, entre com sua conta do GitHub (é o mesmo
login, não precisa criar senha nova) e autorize o acesso aos seus
repositórios.

### 3. Publique o app

- Clique em **"New app"**.
- Escolha o repositório `blueocean-web`, branch `main`.
- Em "Main file path", coloque: `streamlit_app.py`
- Clique em **Deploy**.

A primeira publicação demora uns 3–5 minutos (instalando as dependências,
inclusive o netCDF4 que precisa compilar). Depois disso o link fica fixo,
tipo `https://seu-usuario-blueocean-web.streamlit.app`, e você acessa de
qualquer lugar — celular, outro computador, onde for.

### 4. Uso no dia a dia

- Toda vez que alguém abrir o link, o app carrega.
- Envie a planilha de estações (.xlsx) na barra lateral.
- Se o app ficar muito tempo sem acesso, o Streamlit Cloud "hiberna" ele
  (economia de recursos do plano grátis); o próximo acesso demora uns 30s
  pra "acordar" — é normal, não é erro.

## Rodando localmente (pra testar antes de subir)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Limite conhecido do plano gratuito

O Streamlit Community Cloud gratuito tem um limite de recursos (RAM/CPU)
compartilhado por app — pra uma planilha com até algumas centenas de
estações e uso por 1-2 pessoas ao mesmo tempo, funciona bem. Se um dia a
planilha crescer muito (milhares de estações) ou precisar de várias pessoas
acessando ao mesmo tempo com alta frequência, aí vale considerar um plano
pago ou outro provedor (Render, Railway).
