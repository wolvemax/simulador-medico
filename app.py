import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import time
import openai
import gspread

# ======= ESTILO PERSONALIZADO =======
st.markdown("""
    <style>
    .title {
        font-size: 36px;
        font-weight: bold;
        color: #005b96;
        margin-bottom: 10px;
    }
    .stButton > button {
        background-color: #005b96;
        color: white;
        border-radius: 8px;
        padding: 0.5em 1em;
        font-weight: 600;
    }
    .stTextInput > div > input {
        border-radius: 6px;
        border: 1px solid #ccc;
    }
    .stRadio > div {
        background-color: #f0f2f6;
        padding: 1em;
        border-radius: 10px;
    }
    .metric-container {
        background-color: #f9f9f9;
        padding: 10px;
        border-radius: 10px;
        box-shadow: 0px 1px 4px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# ======= CONFIG =======
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

# ======= FUNÇÕES =======
def remover_acentos(texto):
    return ''.join((c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn'))

def normalizar_chave(chave):
    return remover_acentos(chave.strip().lower())

def normalizar(texto):
    return ''.join((c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')).lower().strip()

def validar_credenciais(usuario, senha):
    sheet = client_gspread.open("LoginSimulador").sheet1
    dados = sheet.get_all_records()
    for linha in dados:
        linha_normalizada = {normalizar_chave(k): v.strip() for k, v in linha.items()}
        if linha_normalizada.get("usuario") == usuario and linha_normalizada.get("senha") == senha:
            return True
    return False

def contar_casos_usuario(usuario):
    try:
        sheet = client_gspread.open("LogsSimulador").worksheets()[0]
        dados = sheet.get_all_records()
        return sum(1 for linha in dados if str(linha.get("usuario", "")).strip().lower() == usuario.lower())
    except:
        return 0

def calcular_media_usuario(usuario):
    try:
        sheet = client_gspread.open("notasSimulador").sheet1
        dados = sheet.get_all_records()
        notas = [float(l["nota"]) for l in dados if str(l.get("usuario", "")).strip().lower() == usuario.lower()]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario, texto):
    sheet = client_gspread.open("LogsSimulador").worksheets()[0]
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([usuario, datahora, texto, "IA"])

def salvar_nota_usuario(usuario, nota):
    sheet = client_gspread.open("notasSimulador").sheet1
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([usuario, str(nota), datahora], value_input_option="USER_ENTERED")

def extrair_nota(texto):
    import re
    match = re.search(r"nota\s*[:\-]?\s*(\d+(?:[\.,]\d+)?)(?:\s*/?\s*10)?", texto, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+(?:[\.,]\d+)?)\s*/\s*10", texto)
    if match:
        return float(match.group(1).replace(",", "."))
    return None

# ======= INTERFACE =======
st.set_page_config(page_title="Simulador Médico", layout="centered")

if "logado" not in st.session_state:
    st.session_state.logado = False
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "historico" not in st.session_state:
    st.session_state.historico = ""
if "consulta_finalizada" not in st.session_state:
    st.session_state.consulta_finalizada = False
if "prompt_inicial" not in st.session_state:
    st.session_state.prompt_inicial = ""

st.markdown('<div class="title">🩺 Simulador Médico Interativo</div>', unsafe_allow_html=True)

if not st.session_state.logado:
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado = True
                st.success("Login realizado com sucesso.")
            else:
                st.error("Usuário ou senha inválido.")

if st.session_state.logado:
    st.markdown(f"👤 **Usuário:** `{st.session_state.usuario}`")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<div class='metric-container'>", unsafe_allow_html=True)
        st.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='metric-container'>", unsafe_allow_html=True)
        st.metric("📊 Média global", calcular_media_usuario(st.session_state.usuario))
        st.markdown("</div>", unsafe_allow_html=True)

    especialidade = st.radio("Especialidade:", ["PSF", "Pediatria"])

    if st.button("➕ Nova Simulação"):
        assistant_id_usado = ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID
        st.session_state.thread_id = openai.beta.threads.create().id
        st.session_state.consulta_finalizada = False
        st.session_state.prompt_inicial = "Iniciar nova simulação clínica com paciente simulado. Apenas início da consulta com identificação e queixa principal."
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=st.session_state.prompt_inicial)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
        with st.spinner("Gerando paciente..."):
            while True:
                status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                if status.status == "completed":
                    break
                time.sleep(1)
        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        for msg in mensagens:
            if msg.role == "assistant":
                st.session_state.historico = msg.content[0].text.value
                st.session_state.consulta_finalizada = False
                break

    if st.session_state.historico:
        st.markdown("### 👤 Paciente")
        st.info(st.session_state.historico)

    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID)
                with st.spinner("Pensando..."):
                    while True:
                        status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                        if status.status == "completed":
                            break
                        time.sleep(1)
                mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                for msg in mensagens:
                    if msg.role == "assistant":
                        st.markdown(f"**Resposta do paciente:** {msg.content[0].text.value}")
                        break
            else:
                st.warning("Digite uma pergunta antes de enviar.")

    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        if st.button("✅ Finalizar Consulta"):
            mensagem_final = (
                "Finalizar consulta. A partir do histórico da consulta, gere:\n"
                "1. O prontuário completo do paciente (título: ### Prontuário Completo do Paciente).\n"
                "2. Um feedback educacional completo para o médico.\n"
                "3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10.\n"
            )
            openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=mensagem_final)
            run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID)
            with st.spinner("Gerando relatório da consulta..."):
                while True:
                    status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                    if status.status == "completed":
                        break
                    time.sleep(1)
            mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
            for msg in mensagens:
                if msg.role == "assistant":
                    resposta = msg.content[0].text.value
                    st.session_state.consulta_finalizada = True
                    st.markdown("### 📄 Resultado Final")
                    st.markdown(resposta)
                    registrar_caso(st.session_state.usuario, resposta)
                    nota = extrair_nota(resposta)
                    if nota is not None:
                        salvar_nota_usuario(st.session_state.usuario, nota)
                    break
