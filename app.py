import streamlit as st
import openai
import gspread
import time
import re
import unicodedata
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ================== CONFIGURAÇÕES ==================
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# ================== CSS PERSONALIZADO ==================
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

# ================== CREDENCIAIS ==================
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_credentials"]), scope)
gs = gspread.authorize(creds)

# ================== FUNÇÕES ==================
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

# ================== SESSION STATE ==================
for var in ["logado", "usuario", "thread_id", "historico", "consulta_finalizada", "anotacoes", "popup_novo", "especialidade", "assistant_usado"]:
    if var not in st.session_state:
        st.session_state[var] = "" if var in ["usuario", "historico", "anotacoes", "especialidade", "assistant_usado"] else False

# ================== LOGIN ==================
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

# ================== INTERFACE LOGADA ==================
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("Casos finalizados", contar_casos(st.session_state.usuario))
col2.metric("Média global", media_global(st.session_state.usuario))

st.session_state.especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"])

if st.session_state.especialidade == "PSF":
    st.session_state.assistant_usado = ASSISTANT_ID
elif st.session_state.especialidade == "Pediatria":
    st.session_state.assistant_usado = ASSISTANT_PEDIATRIA_ID
else:
    st.session_state.assistant_usado = ASSISTANT_EMERGENCIAS_ID

# ================== BOTÃO NOVA SIMULAÇÃO ==================
if st.button("➕ Nova Simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        st.session_state.popup_novo = True
    else:
        st.session_state.thread_id = openai.beta.threads.create().id
        st.session_state.consulta_finalizada = False

        if st.session_state.especialidade == "Pediatria":
            prompt = "Iniciar simulação clínica pediátrica com identificação e QP."
        elif st.session_state.especialidade == "PSF":
            prompt = "Iniciar nova simulação clínica com paciente simulado."
        else:
            prompt = ""

        if prompt:
            openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)

        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=st.session_state.assistant_usado)

        with st.spinner("🧠 Gerando paciente..."):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.5)

        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        st.session_state.historico = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")

# ================== MODAL DE CONFIRMAÇÃO ==================
if st.session_state.popup_novo:
    st.markdown("""
    <div class="modal-container">
        <h4>⚠️ Simulação em andamento</h4>
        <p>Deseja iniciar uma nova simulação e perder o progresso atual?</p>
    </div>
    """, unsafe_allow_html=True)

    colx1, colx2 = st.columns(2)
    with colx1:
        if st.button("❌ Cancelar"):
            st.session_state.popup_novo = False
            st.rerun()
    with colx2:
        if st.button("✅ Confirmar"):
            st.session_state.popup_novo = False
            st.session_state.thread_id = None
            st.session_state.historico = ""
            st.session_state.consulta_finalizada = False
            st.rerun()

# ================== HISTÓRICO ==================
if st.session_state.historico:
    st.markdown("### 👤 Paciente")
    st.info(st.session_state.historico)

# ================== INTERAÇÃO ==================
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    col1, col2 = st.columns([2, 1])
    with col1:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=st.session_state.assistant_usado)
                with st.spinner("💬 Respondendo..."):
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                        time.sleep(0.5)
                mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                resposta = next((m.content[0].text.value for m in mensagens if m.role == "assistant"), "")
                st.markdown(f"**Resposta do paciente:**\n\n{resposta}")
            else:
                st.warning("Digite algo para enviar.")
    with col2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)", st.session_state.anotacoes, height=260)

# ================== FINALIZAR CONSULTA ==================
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
        st.markdown("### 📄 Resultado Final")
        st.markdown(resposta)
        st.session_state.consulta_finalizada = True
        registrar(st.session_state.usuario, resposta)
        nota = extrair_nota(resposta)
        if nota is not None:
            salvar_nota(st.session_state.usuario, nota)
            st.rerun()
