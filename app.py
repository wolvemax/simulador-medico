import streamlit as st
import openai
import gspread
import time
import re
import unicodedata
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# ======= CSS =======
st.markdown("""
<style>
textarea {
    border: 2px solid #003366 !important;
    border-radius: 8px !important;
    box-shadow: 0 0 5px rgba(0, 51, 102, 0.4);
}
.modal-container {
    position: fixed;
    top: 30%;
    left: 50%;
    transform: translate(-50%, -50%);
    background-color: #ffffff;
    padding: 30px;
    border-radius: 12px;
    box-shadow: 0 0 20px rgba(0, 0, 0, 0.2);
    z-index: 9999;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ======= CHAVES =======
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_credentials"]), scope)
gs = gspread.authorize(creds)

# ======= FUNÇÕES AUXILIARES =======
def normalizar(txt):
    return ''.join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn").lower().strip()

def validar(usuario, senha):
    sheet = gs.open("LoginSimulador").sheet1
    for l in sheet.get_all_records():
        if "usuario" in l and "senha" in l:
            if normalizar(l["usuario"]) == normalizar(usuario) and str(l["senha"]).strip() == senha:
                return True
    return False

def contar_casos(usuario):
    dados = gs.open("LogsSimulador").sheet1.get_all_records()
    return sum(1 for l in dados if normalizar(l.get("usuario", "")) == normalizar(usuario))

def media_global(usuario):
    try:
        dados = gs.open("notasSimulador").sheet1.get_all_records()
        notas = [float(l["nota"]) for l in dados if normalizar(l.get("usuario", "")) == normalizar(usuario)]
        return round(sum(notas)/len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar(usuario, texto):
    gs.open("LogsSimulador").sheet1.append_row([usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto, "IA"])

def salvar_nota(usuario, nota):
    gs.open("notasSimulador").sheet1.append_row([usuario, nota, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def extrair_nota(texto):
    m = re.search(r"Nota:\s*(\d+(?:[.,]\d+)?)", texto)
    return float(m.group(1).replace(",", ".")) if m else None

# ======= SESSION STATE =======
for var in ["logado", "usuario", "thread_id", "historico", "consulta_finalizada", "anotacoes", "modal_aberto"]:
    if var not in st.session_state:
        st.session_state[var] = "" if var in ["usuario", "historico", "anotacoes"] else None if var == "thread_id" else False

# ======= LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Login")
    with st.form("login_form"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar(u, p):
                st.session_state.usuario = u
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= LAYOUT =======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")
col1, col2 = st.columns(2)
col1.metric("Casos finalizados", contar_casos(st.session_state.usuario))
col2.metric("Média global", media_global(st.session_state.usuario))

# ======= ESPECIALIDADE =======
especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"])
aid = ASSISTANT_ID if especialidade == "PSF" else ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_EMERGENCIAS_ID

# ======= NOVA SIMULAÇÃO =======
if st.button("➕ Nova Simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        st.session_state.modal_aberto = True
    else:
        st.session_state.thread_id = openai.beta.threads.create().id
        st.session_state.consulta_finalizada = False
        prompt = "Iniciar simulação clínica pediátrica." if especialidade == "Pediatria" else "Iniciar nova simulação clínica." if especialidade == "PSF" else ""
        if prompt:
            openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
        with st.spinner("🧠 Gerando paciente..."):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.5)
        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        st.session_state.historico = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")

if st.session_state.modal_aberto:
    st.markdown("""<div class="modal-container">
        <h4>⚠️ Simulação em andamento</h4>
        <p>Deseja iniciar uma nova simulação e perder o progresso atual?</p></div>""", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("❌ Cancelar"):
        st.session_state.modal_aberto = False
        st.rerun()
    if c2.button("✅ Confirmar"):
        st.session_state.modal_aberto = False
        st.session_state.thread_id = None
        st.session_state.consulta_finalizada = False
        st.session_state.historico = ""
        st.rerun()

# ======= CONSULTA ATIVA =======
if st.session_state.historico:
    st.markdown("### 👤 Paciente")
    st.info(st.session_state.historico)

if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    a1, a2 = st.columns([2, 1])
    with a1:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
                with st.spinner("💬 Respondendo..."):
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                        time.sleep(0.5)
                mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                resposta = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")
                st.markdown(f"**Resposta do paciente:** {resposta}")
    with a2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)", value=st.session_state.anotacoes, height=300)

if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=(
                "Finalizar consulta. A partir do histórico da consulta, gere:
"
                "1. O prontuário completo do paciente (título: ### Prontuário Completo do Paciente).
"
                "2. Um feedback educacional completo para o médico.
"
                "3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10."
            )
        )
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
        with st.spinner("📄 Gerando relatório da consulta..."):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.5)
        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        resposta = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")
        st.markdown("### 📄 Resultado Final")
        st.markdown(resposta)
        st.session_state.consulta_finalizada = True
        registrar(st.session_state.usuario, resposta)
        nota = extrair_nota(resposta)
        if nota:
            salvar_nota(st.session_state.usuario, nota)
            st.rerun()
