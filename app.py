
import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import openai
import gspread
import base64

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# 💅 CSS para destacar text_area
st.markdown(\"\"\"
<style>
textarea {
    border: 2px solid #003366 !important;
    border-radius: 8px !important;
    box-shadow: 0px 0px 5px rgba(0, 51, 102, 0.4);
    padding: 0.5rem;
}
</style>
\"\"\", unsafe_allow_html=True)

openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

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
    try:
        match = re.search(r"nota\\s*[:\\-]?\\s*(\\d+(?:[\\.,]\\d+)?)(?:\\s*/?\\s*10)?", texto, re.IGNORECASE)
        if not match:
            match = re.search(r"(\\d+(?:[\\.,]\\d+)?)\\s*/\\s*10", texto)
        if match:
            return float(match.group(1).replace(",", "."))
    except:
        return None

# ======= ESTADO INICIAL =======
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

# ======= LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= ÁREA LOGADA =======
st.title("🩺 Simulador Médico Interativo com IA")
st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
col2.metric("📊 Média global", calcular_media_usuario(st.session_state.usuario))

especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"])

if especialidade == "Pediatria":
    assistant_id_usado = ASSISTANT_PEDIATRIA_ID
elif especialidade == "Emergências":
    assistant_id_usado = ASSISTANT_EMERGENCIAS_ID
else:
    assistant_id_usado = ASSISTANT_ID

if st.button("➕ Nova Simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        st.warning("⚠️ Uma simulação está em andamento e não foi finalizada. Deseja realmente iniciar uma nova e perder o progresso atual?")
        if not st.button("Confirmar Nova Simulação"):
            st.stop()

    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False

    if especialidade == "Emergências":
        st.session_state.prompt_inicial = ""
    elif especialidade == "Pediatria":
        st.session_state.prompt_inicial = "Iniciar nova simulação clínica pediátrica com identificação e queixa principal."
    else:
        st.session_state.prompt_inicial = "Iniciar nova simulação clínica com paciente simulado. Apenas início da consulta com identificação e queixa principal."

    if st.session_state.prompt_inicial:
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=st.session_state.prompt_inicial
        )

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
            break

if st.session_state.historico:
    st.markdown("### 👤 Paciente")
    st.info(st.session_state.historico)

if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    pergunta = st.text_area("Digite sua pergunta ou conduta:")
    if st.button("Enviar"):
        if pergunta.strip():
            openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
            run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
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
            "Finalizar consulta. A partir do histórico da consulta, gere:\\n"
            "1. O prontuário completo do paciente (título: ### Prontuário Completo do Paciente).\\n"
            "2. Um feedback educacional completo para o médico.\\n"
            "3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10.\\n"
        )
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=mensagem_final)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
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
                st.markdown("### 📄 Resultado Final")
                st.markdown(resposta)
                st.session_state.consulta_finalizada = True
                registrar_caso(st.session_state.usuario, resposta)
                nota = extrair_nota(resposta)
                if nota is not None:
                    salvar_nota_usuario(st.session_state.usuario, nota)
                break
"""

# Salvar o arquivo no diretório acessível
final_path = Path("/mnt/data/app_simulador_melhorias.py")
final_path.write_text(app_code_updated)
final_path
