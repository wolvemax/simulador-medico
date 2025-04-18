import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import openai
import gspread
import re

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Bem‑vindo ao SIMULAMAX - Simulador Médico IA", page_icon="🩺", layout="wide")

openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID             = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID   = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope        = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds        = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

# ======= GARANTIR ESTADO INICIAL =======
DEFAULTS = {
    "logado": False,
    "thread_id": None,
    "historico": "",
    "consulta_finalizada": False,
    "prompt_inicial": "",
    "media_usuario": None,
    "especialidade": "PSF",
    "run_em_andamento": False,
    "especialidade_atual": None,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

# ======= FUNÇÕES UTILITÁRIAS =======

def remover_acentos(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")

def normalizar_chave(ch: str) -> str:
    return remover_acentos(ch.strip().lower())

def normalizar(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn").lower().strip()

def validar_credenciais(usuario: str, senha: str) -> bool:
    try:
        sheet = client_gspread.open("LoginSimulador").sheet1
        for linha in sheet.get_all_records():
            ln = {normalizar_chave(k): v.strip() for k, v in linha.items() if isinstance(v, str)}
            if ln.get("usuario") == usuario and ln.get("senha") == senha:
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao validar login: {e}")
        return False

def contar_casos_usuario(user: str) -> int:
    try:
        dados = client_gspread.open("LogsSimulador").worksheet("Pagina1").get_all_records()
        return sum(1 for l in dados if str(l.get("usuario", "")).strip().lower() == user.lower())
    except:
        return 0

def calcular_media_usuario(user: str) -> float:
    try:
        dados = client_gspread.open("notasSimulador").sheet1.get_all_records()
        notas = [float(l["nota"]) for l in dados if str(l.get("usuario", "")).strip().lower() == user.lower()]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario: str, texto: str, assistente: str):
    sheet    = client_gspread.open("LogsSimulador").worksheet("Pagina1")
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resumo   = texto[:300].replace("\n", " ").strip()
    sheet.append_row([usuario, datahora, resumo, assistente], value_input_option="USER_ENTERED")

def salvar_nota_usuario(user: str, nota: float):
    sh = client_gspread.open("notasSimulador").sheet1
    sh.append_row([user, str(nota), datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option="USER_ENTERED")

def extrair_nota(txt: str):
    m = re.search(r"nota\s*[:\-]?\s*(\d+(?:[.,]\d+)?)(?:\s*/?\s*10)?", txt, re.I)
    if not m:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*10", txt)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except:
            return None
    return None

def obter_ultimos_resumos(user: str, esp: str, n: int = 10):
    try:
        dados = client_gspread.open("LogsSimulador").worksheet("Pagina1").get_all_records()
        hist  = [l for l in dados if str(l.get("usuario", "")).lower()==user.lower() and str(l.get("assistente", "")).lower()==esp.lower()]
        ult   = hist[-n:]
        return [l.get("resumo", "")[:250] for l in ult if l.get("resumo", "")]
    except Exception as e:
        st.warning(f"Erro ao obter resumos: {e}")
        return []

def aguardar_run(thread_id: str):
    while True:
        runs = openai.beta.threads.runs.list(thread_id=thread_id).data
        if runs and runs[0].status != "in_progress":
            break
        time.sleep(1)

def renderizar_historico():
    if not st.session_state.thread_id:
        return
    msgs = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    for m in sorted(msgs, key=lambda x: x.created_at):
        if "Iniciar nova simulação clínica" in m.content[0].text.value:
            continue
        hora = datetime.fromtimestamp(m.created_at).strftime("%H:%M")
        avatar = "👨‍⚕️" if m.role == "user" else "🧑‍⚕️"
        with st.chat_message(m.role, avatar=avatar):
            st.markdown(m.content[0].text.value)
            st.caption(f"⏰ {hora}")

# ======= LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login"):
        usr = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(usr, pwd):
                st.session_state.usuario = usr
                st.session_state.logado  = True
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= INTERFACE PRINCIPAL =======
st.title("🩺 Simulador Médico Interativo com IA")
st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

c1, c2 = st.columns(2)
c1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
if st.session_state.media_usuario is None:
    st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
c2.metric("📊 Média global", st.session_state.media_usuario)

# ---- especialidade ----
esp = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"], index=["PSF", "Pediatria", "Emergências"].index(st.session_state.especialidade))
st.session_state.especialidade = esp

assistant_id = {
    "PSF": ASSISTANT_ID,
    "Pediatria": ASSISTANT_PEDIATRIA_ID,
    "Emergências": ASSISTANT_EMERGENCIAS_ID,
}[esp]

# ======= NOVA SIMULAÇÃO =======
if st.button("➕ Nova Simulação"):
    st.session_state.thread_id           = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False
    st.session_state.historico           = ""
    st.session_state.especialidade_atual = esp  # <‑ fixa!

    # anti‑repetição
    res_ant = obter_ultimos_resumos(st.session_state.usuario, esp)
    contexto = "\n\n".join(res_ant) if res_ant else "Nenhum caso anterior registrado."

    intro = {
        "PSF": "Iniciar nova simulação clínica em atenção primária (identificação + QP).",
        "Pediatria": "Iniciar nova simulação clínica pediátrica (identificação + QP).",
        "Emergências": "Iniciar nova simulação de emergência (identificação + QP).",
    }[esp]

    prompt = f"""Considere os resumos abaixo apenas para não repetir casos prévios:
{contexto}

{intro}"""

    openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)
    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id)
    aguardar_run(st.session_state.thread_id)

    for m in openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data:
        if m.role == "assistant":
            st.session_state.historico = m.content[0].text.value
            break
    st.experimental_rerun()

# ======= CHAT =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    renderizar_historico()
    pergunta = st.chat_input("Digite sua pergunta ou conduta:")
    if pergunta:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
        run = openai.beta.threads.runs
