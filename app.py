import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import openai
import gspread
import base64
import sounddevice as sd
import scipy.io.wavfile as wav
import tempfile
import os

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]

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
    try:
        sheet = client_gspread.open("LoginSimulador").sheet1
        dados = sheet.get_all_records()
        for linha in dados:
            linha_normalizada = {normalizar_chave(k): v.strip() for k, v in linha.items() if isinstance(v, str)}
            if linha_normalizada.get("usuario") == usuario and linha_normalizada.get("senha") == senha:
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao validar login: {e}")
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
        match = re.search(r"nota[:\\-]?\\s*(\\d+(?:[.,]\\d+)?)", texto, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", "."))
    except:
        pass
    return None

def renderizar_historico():
    mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    mensagens_ordenadas = sorted(mensagens, key=lambda x: x.created_at)
    st.markdown("<div style='height:400px; overflow-y:auto; border:1px solid #ccc; padding:10px; border-radius:8px;'>", unsafe_allow_html=True)
    for msg in mensagens_ordenadas:
        hora = datetime.fromtimestamp(msg.created_at).strftime("%H:%M")
        if msg.role == "user":
            with st.chat_message("user", avatar="👨‍⚕️"):
                st.markdown(msg.content[0].text.value)
                st.caption(f"⏰ {hora}")
        elif msg.role == "assistant":
            with st.chat_message("assistant", avatar="🧑‍⚕️"):
                st.markdown(msg.content[0].text.value)
                st.caption(f"⏰ {hora}")
    st.markdown("</div>", unsafe_allow_html=True)

# ======= ÁUDIO + WHISPER =======
def gravar_audio(nome_arquivo, duracao=5, taxa=44100):
    gravacao = sd.rec(int(duracao * taxa), samplerate=taxa, channels=1, dtype='int16')
    sd.wait()
    wav.write(nome_arquivo, taxa, gravacao)

def transcrever_audio(caminho_arquivo):
    with open(caminho_arquivo, "rb") as audio_file:
        transcript = openai.Audio.transcribe("whisper-1", audio_file, language="pt")
        return transcript["text"]

# ======= ESTADO INICIAL =======
if "logado" not in st.session_state:
    st.session_state.logado = False
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "consulta_finalizada" not in st.session_state:
    st.session_state.consulta_finalizada = False
if "media_usuario" not in st.session_state:
    st.session_state.media_usuario = 0.0

# ======= LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= DASHBOARD =======
st.title("🩺 Simulador Médico Interativo com IA")
st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")
col1, col2 = st.columns(2)
col1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
col2.metric("📊 Média global", st.session_state.media_usuario)

# ======= SIMULAÇÃO =======
if st.button("➕ Nova Simulação"):
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False
    openai.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content="Iniciar nova simulação clínica com identificação e queixa principal."
    )
    run = openai.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=ASSISTANT_ID
    )
    with st.spinner("Gerando paciente..."):
        while True:
            status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)
    st.rerun()

# ======= CHAT & INPUT =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    renderizar_historico()

    col1, col2 = st.columns([6, 1])
    with col1:
        pergunta = st.chat_input("Digite sua pergunta ou conduta:")
    with col2:
        if st.button("🎙️ Gravar áudio"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                gravar_audio(tmpfile.name)
                texto = transcrever_audio(tmpfile.name)
                st.session_state.input_temp = texto
                os.unlink(tmpfile.name)
                st.experimental_rerun()

    if pergunta:
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=pergunta
        )
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=ASSISTANT_ID)
        with st.spinner("Pensando..."):
            while True:
                status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                if status.status == "completed":
                    break
                time.sleep(1)
        st.rerun()

# ======= FINALIZAR CONSULTA =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content="Finalizar consulta. A partir do histórico da consulta, gere:\n1. O prontuário completo do paciente (título: ### Prontuário Completo do Paciente).\n2. Um feedback educacional completo para o médico.\n3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10."
        )
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=ASSISTANT_ID)
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
                    st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
                    st.success("✅ Nota salva com sucesso!")
                else:
                    st.warning("⚠️ Não foi possível extrair a nota.")
                break
