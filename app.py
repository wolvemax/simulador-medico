
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

# CSS para estilização
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

# ======= CREDENCIAIS =======
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

# ======= FUNÇÕES =======
def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def normalizar_chave(chave):
    return remover_acentos(chave.strip().lower())

def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn').lower().strip()

def validar_credenciais(usuario, senha):
    sheet = client_gspread.open("LoginSimulador").sheet1
    for linha in sheet.get_all_records():
        if normalizar(linha.get("usuario","")) == normalizar(usuario) and linha.get("senha","").strip() == senha:
            return True
    return False

def contar_casos_usuario(usuario):
    try:
        sheet = client_gspread.open("LogsSimulador").sheet1
        return sum(1 for l in sheet.get_all_records() if normalizar(l.get("usuario","")) == normalizar(usuario))
    except:
        return 0

def calcular_media_usuario(usuario):
    try:
        sheet = client_gspread.open("notasSimulador").sheet1
        notas = [float(l["nota"]) for l in sheet.get_all_records() if normalizar(l.get("usuario","")) == normalizar(usuario)]
        return round(sum(notas)/len(notas),2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario, texto):
    sheet = client_gspread.open("LogsSimulador").sheet1
    sheet.append_row([usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto, "IA"])

def salvar_nota_usuario(usuario, nota):
    sheet = client_gspread.open("notasSimulador").sheet1
    sheet.append_row([usuario, nota, datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option="USER_ENTERED")

def extrair_nota(texto):
    import re
    m = re.search(r"Nota:\s*(\d+(?:[\.,]\d+)?)", texto)
    return float(m.group(1).replace(",", ".")) if m else None

# ======= SESSION STATE =======
for var in ["logado","thread_id","historico","consulta_finalizada","prompt_inicial","anotacoes","confirm_new"]:
    if var not in st.session_state:
        st.session_state[var] = False if var in ["logado","consulta_finalizada","confirm_new"] else "" if var in ["historico","prompt_inicial","anotacoes"] else None

# ======= LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        s = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(u,s):
                st.session_state.usuario = u
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= LAYOUT PRINCIPAL =======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("Casos Finalizados", contar_casos_usuario(st.session_state.usuario))
col2.metric("Média Global", calcular_media_usuario(st.session_state.usuario))

# ======= SELEÇÃO DE ESPECIALIDADE =======
especialidade = st.radio("Especialidade:", ["PSF","Pediatria","Emergências"])
if especialidade=="PSF": aid=ASSISTANT_ID
elif especialidade=="Pediatria": aid=ASSISTANT_PEDIATRIA_ID
else: aid=ASSISTANT_EMERGENCIAS_ID

# ======= NOVA SIMULAÇÃO =======
if st.button("➕ Nova Simulação"):
    # checa progresso
    if st.session_state.thread_id and not st.session_state.consulta_finalizada and not st.session_state.confirm_new:
        st.warning("⚠️ Simulação em andamento. Iniciar nova e perder progresso?")
        if st.button("Confirmar"):
            st.session_state.confirm_new = True
            st.rerun()
        st.stop()
    # reset confirmação
    st.session_state.confirm_new=False
    # iniciar thread
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada=False
    # prompt condicional
    if especialidade=="Pediatria":
        st.session_state.prompt_inicial = "Iniciar clínica pediátrica..."
    else:
        st.session_state.prompt_inicial = ""
    # envia prompt inicial se existir
    if st.session_state.prompt_inicial:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,role="user",content=st.session_state.prompt_inicial)
    # gera paciente
    run=openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,assistant_id=aid)
    placeholder=st.empty()
    placeholder.markdown("<h3 style='text-align:center'>🧠 Gerando paciente... aguarde</h3>",unsafe_allow_html=True)
    while True:
        status=openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,run_id=run.id)
        time.sleep(0.5)
        if status.status=="completed": break
    placeholder.empty()
    msgs=openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    st.session_state.historico = next((m.content[0].text.value for m in msgs if m.role=="assistant"),"")

# ======= INTERAÇÃO =======
if st.session_state.historico:
    st.markdown("### Paciente")
    st.info(st.session_state.historico)

# input e anotações lado a lado
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    c1, c2 = st.columns([2,1])
    with c1:
        q=st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if q:
                run=openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,assistant_id=aid)
                p=st.empty(); p.markdown("<h3 style='text-align:center'>💬 Processando... aguarde</h3>",unsafe_allow_html=True)
                while True:
                    status=openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,run_id=run.id)
                    time.sleep(0.5)
                    if status.status=="completed": break
                p.empty()
                msgs=openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                st.markdown(f"**Resposta do paciente:** {next((m.content[0].text.value for m in msgs if m.role=='assistant'), '')}")
    with c2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)", value=st.session_state.anotacoes, height=300)

# ======= FINALIZAR CONSULTA =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        run=openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,assistant_id=aid)
        placeholder=st.empty()
        placeholder.markdown("<h3 style='text-align:center'>📄 Gerando relatório da consulta... aguarde</h3>",unsafe_allow_html=True)
        while True:
            status=openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,run_id=run.id)
            time.sleep(0.5)
            if status.status=="completed": break
        placeholder.empty()
        msgs=openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        resp=next((m.content[0].text.value for m in msgs if m.role=="assistant"), "")
        st.markdown("### Resultado Final")
        st.markdown(resp)
        st.session_state.consulta_finalizada=True
        registrar_caso(st.session_state.usuario, resp)
        nota=extrair_nota(resp)
        if nota is not None:
            salvar_nota_usuario(st.session_state.usuario, nota)
            st.rerun()
