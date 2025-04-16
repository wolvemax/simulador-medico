import streamlit as st
import unicodedata
import openai
import gspread
import re
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ========= CONFIGURAÇÕES =========
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# ========= CSS =========
st.markdown("""
    <style>
    textarea {
        border: 2px solid #003366 !important;
        border-radius: 8px !important;
        box-shadow: 0px 0px 5px rgba(0, 51, 102, 0.4);
        padding: 0.5rem;
    }
    </style>
""", unsafe_allow_html=True)

# ========= OPENAI & SHEETS =========
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_credentials"]), scope)
gs = gspread.authorize(creds)

# ========= FUNÇÕES =========
def _normalize(txt):
    return ''.join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn").lower().strip()

def validate_credentials(user, pwd):
    sheet = gs.open("LoginSimulador").sheet1
    for row in sheet.get_all_records():
        u = _normalize(row.get("usuario", ""))
        p = str(row.get("senha", "")).strip()
        if u == _normalize(user) and p == pwd:
            return True
    return False

def count_cases(user):
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(1 for r in sheet.get_all_records() if _normalize(r.get("usuario")) == _normalize(user))
    except:
        return 0

def calculate_average(user):
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [float(r["nota"]) for r in sheet.get_all_records() if _normalize(r.get("usuario")) == _normalize(user)]
        return round(sum(notas)/len(notas), 2) if notas else 0.0
    except:
        return 0.0

def register_case(user, texto):
    gs.open("LogsSimulador").sheet1.append_row([user, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto, "IA"])

def save_user_score(user, nota):
    gs.open("notasSimulador").sheet1.append_row([user, nota, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def extract_score(texto):
    m = re.search(r"Nota:\s*(\d+(?:[.,]\d+)?)", texto)
    return float(m.group(1).replace(",", ".")) if m else None

def gerar_nova_simulacao():
    st.session_state.consulta_finalizada = False
    st.session_state.anotacoes = ""
    st.session_state.prompt_inicial = ""
    st.session_state.thread_id = openai.beta.threads.create().id

    if st.session_state.especialidade == "Pediatria":
        st.session_state.prompt_inicial = "Iniciar clínica pediátrica..."
    elif st.session_state.especialidade == "PSF":
        st.session_state.prompt_inicial = "Iniciar nova simulação clínica com paciente simulado."

    if st.session_state.prompt_inicial:
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=st.session_state.prompt_inicial
        )

    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=st.session_state.assistant_usado)

    with st.spinner("🧠 Gerando paciente... aguarde"):
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
            time.sleep(0.5)

    mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    st.session_state.history = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")

# ========= SESSION =========
for var in ["logged_in", "user", "thread_id", "history", "consulta_finalizada", "anotacoes", "escolheu_nova", "especialidade", "assistant_usado"]:
    if var not in st.session_state:
        st.session_state[var] = False if "log" in var or "finalizada" in var else ""

# ========= LOGIN =========
if not st.session_state.logged_in:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login_form"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validate_credentials(u, p):
                st.session_state.user = u
                st.session_state.logged_in = True
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ========= LAYOUT =========
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.user}**")

col1, col2 = st.columns(2)
col1.metric("Casos finalizados", count_cases(st.session_state.user))
col2.metric("Média global", calculate_average(st.session_state.user))

# ========= SELEÇÃO DE ESPECIALIDADE =========
st.session_state.especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"])
st.session_state.assistant_usado = (
    ASSISTANT_ID if st.session_state.especialidade == "PSF" else
    ASSISTANT_PEDIATRIA_ID if st.session_state.especialidade == "Pediatria" else
    ASSISTANT_EMERGENCIAS_ID
)

# ========= BOTÃO NOVA SIMULAÇÃO =========
if st.button("➕ Nova Simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        st.session_state.escolheu_nova = True
    else:
        gerar_nova_simulacao()

if st.session_state.escolheu_nova:
    st.markdown("""
    <div style='
        position: fixed;
        top: 30%;
        left: 50%;
        transform: translate(-50%, -50%);
        background-color: #fff;
        padding: 30px;
        border-radius: 10px;
        box-shadow: 0 0 15px rgba(0,0,0,0.2);
        z-index: 9999;
        text-align: center;
    '>
        <h4>⚠️ Simulação em andamento</h4>
        <p>Deseja iniciar uma nova simulação e perder o progresso atual?</p>
    """, unsafe_allow_html=True)
    colx1, colx2 = st.columns(2)
    with colx1:
        if st.button("❌ Cancelar"):
            st.session_state.escolheu_nova = False
    with colx2:
        if st.button("✅ Confirmar"):
            st.session_state.thread_id = None
            st.session_state.history = ""
            st.session_state.escolheu_nova = False
            gerar_nova_simulacao()
    st.markdown("</div>", unsafe_allow_html=True)

# ========= PACIENTE =========
if st.session_state.history:
    st.subheader("👤 Paciente")
    st.info(st.session_state.history)

# ========= INTERAÇÃO =========
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    col1, col2 = st.columns([2, 1])
    with col1:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=st.session_state.assistant_usado)
                with st.spinner("💬 Pensando..."):
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                        time.sleep(0.5)
                mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                resposta = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")
                st.markdown(f"**Resposta do paciente:**\n\n{resposta}")
            else:
                st.warning("Digite algo antes de enviar.")
    with col2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese):", st.session_state.anotacoes, height=260)

# ========= FINALIZAR =========
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        prompt = (
            "Finalizar consulta. "
            "1) Gere o prontuário completo (### Prontuário Completo do Paciente). "
            "2) Gere um feedback educacional. "
            "3) Gere a nota no formato: Nota: X/10."
        )
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=st.session_state.assistant_usado)
        with st.spinner("📄 Gerando relatório da consulta... aguarde"):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.5)
        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        resposta = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")
        st.subheader("📄 Resultado Final")
        st.markdown(resposta)
        st.session_state.consulta_finalizada = True
        register_case(st.session_state.user, resposta)
        nota = extract_score(resposta)
        if nota is not None:
            save_user_score(st.session_state.user, nota)
