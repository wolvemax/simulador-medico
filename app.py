import streamlit as st
import unicodedata
import time
import re
import openai
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# Estilo para textarea
st.markdown("""<style>
textarea{border:2px solid #003366!important;border-radius:8px!important;
box-shadow:0 0 5px rgba(0,51,102,.4);padding:.5rem}
</style>""", unsafe_allow_html=True)

# ======= CREDENCIAIS =======
openai.api_key       = st.secrets["openai"]["api_key"]
ASSISTANT_ID         = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA  = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIA = st.secrets["assistants"]["emergencias"]

scope  = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds  = ServiceAccountCredentials.from_json_keyfile_dict(
    dict(st.secrets["google_credentials"]), scope
)
gs     = gspread.authorize(creds)

# ======= UTILITÁRIOS =======
def normalizar_texto(texto: str) -> str:
    if texto is None:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()

def validar_credenciais(usuario_input: str, senha_input: str) -> bool:
    usuario_input_norm = normalizar_texto(usuario_input)
    senha_input_norm   = str(senha_input).strip()
    sheet = gs.open("LoginSimulador").sheet1
    for linha in sheet.get_all_records():
        usuario_plan = normalizar_texto(linha.get("usuario", ""))
        senha_plan   = str(linha.get("senha", "")).strip()
        if usuario_plan == usuario_input_norm and senha_plan == senha_input_norm:
            return True
    return False

def contar_casos_usuario(usuario: str) -> int:
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(
            1
            for l in sheet.get_all_records()
            if normalizar_texto(l.get("usuario", "")) == normalizar_texto(usuario)
        )
    except:
        return 0

def calcular_media_usuario(usuario: str) -> float:
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [
            float(l["nota"])
            for l in sheet.get_all_records()
            if normalizar_texto(l.get("usuario", "")) == normalizar_texto(usuario)
        ]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario: str, texto: str):
    sheet = gs.open("LogsSimulador").sheet1
    sheet.append_row([usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto, "IA"])

def salvar_nota_usuario(usuario: str, nota: float):
    sheet = gs.open("notasSimulador").sheet1
    sheet.append_row([usuario, nota, datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option="USER_ENTERED")

def extrair_nota(texto: str) -> float | None:
    match = re.search(r"Nota:\s*(\d+(?:[\.,]\d+)?)", texto)
    if match:
        return float(match.group(1).replace(",", "."))
    return None

# ======= SESSION STATE =======
if "logado" not in st.session_state:
    st.session_state.logado = False

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
                st.success("Login realizado com sucesso!")
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= ÁREA LOGADA =======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
col2.metric("📊 Média global", calcular_media_usuario(st.session_state.usuario))

# ─────────── ESPECIALIDADE ───────────
esp = st.radio("Especialidade", ["PSF","Pediatria","Emergências"], horizontal=True)
AID = {"PSF":ASSISTANT_ID,"Pediatria":ASSISTANT_PEDIATRIA,"Emergências":ASSISTANT_EMERGENCIA}[esp]

# ─────────── BOTÃO NOVA SIMULAÇÃO ───────────
if st.button("➕ Nova simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        # modal de confirmação
        with st.modal("Simulação não finalizada"):
            st.warning("Há uma simulação em andamento. Continuar apagará o progresso.")
            if st.button("Iniciar nova"):
                st.session_state.thread_id=None
                st.session_state.historico=""
                st.session_state.consulta_finalizada=False
            else:
                st.stop()

    # cria thread
    st.session_state.thread_id = openai.beta.threads.create().id
    prompt = "Iniciar clínica pediátrica..." if esp=="Pediatria" else ""
    if prompt:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,
                                            role="user", content=prompt)
    # run
    with st.modal("Gerando paciente…"):
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                              assistant_id=AID)
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                run_id=run.id).status!="completed":
            time.sleep(0.4)
    msg = next((m.content[0].text.value for m in
                openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                if m.role=="assistant"), "")
    st.session_state.historico = msg
    st.session_state.consulta_finalizada=False
    st.rerun()

# ─────────── EXPÕE PACIENTE ───────────
if st.session_state.historico:
    st.subheader("👤 Paciente")
    st.info(st.session_state.historico)

# ─────────── PERGUNTA & ANOTAÇÕES ───────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    col_p,col_a = st.columns([2,1])
    with col_p:
        q = st.text_area("Digite pergunta / conduta:")
        if st.button("Enviar"):
            if q.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,
                                                    role="user", content=q)
                with st.modal("Processando resposta…"):
                    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                                          assistant_id=AID)
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                            run_id=run.id).status!="completed":
                        time.sleep(0.4)
                resp = next((m.content[0].text.value for m in
                             openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                             if m.role=="assistant"), "")
                st.markdown(f"**Resposta do paciente:**\n\n{resp}")
            else:
                st.warning("Digite algo primeiro.")
    with col_a:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)",
                                                  st.session_state.anotacoes,
                                                  height=260)

# ─────────── FINALIZAR CONSULTA ───────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar consulta"):
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=("Finalizar consulta. 1) Prontuário completo "
                     "2) Feedback. 3) Nota: X/10.")
        )
        with st.modal("Gerando relatório da consulta…"):
            run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                                  assistant_id=AID)
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                    run_id=run.id).status!="completed":
                time.sleep(0.5)
        resp = next((m.content[0].text.value for m in
                     openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                     if m.role=="assistant"), "")
        st.subheader("📄 Resultado final")
        st.markdown(resp)
        st.session_state.consulta_finalizada=True
        registrar(st.session_state.usuario, resp)
        n = extrair_nota(resp)
        if n is not None: salvar_nota(st.session_state.usuario, n)
        st.rerun()
