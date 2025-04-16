
import streamlit as st
import unicodedata, time, re, openai, gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ====== CONFIGURAÇÃO DA PÁGINA ======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# ====== CSS PARA TEXTAREA ======
st.markdown("""
<style>
textarea {
    border: 2px solid #003366 !important;
    border-radius: 8px !important;
    box-shadow: 0 0 5px rgba(0,51,102,0.4);
    padding: .5rem;
}
</style>
""", unsafe_allow_html=True)

# ====== CREDENCIAIS ======
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["google_credentials"]), scope)
gs = gspread.authorize(creds)

# ====== AUXILIARES ======
def normalizar_texto(texto):
    if texto is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").lower().strip()

def validar_credenciais(usuario_input, senha_input):
    sheet = gs.open("LoginSimulador").sheet1
    for row in sheet.get_all_records():
        # normalizar chaves e valores
        row_norm = { normalizar_texto(k): row[k] for k in row }
        u = normalizar_texto(row_norm.get("usuario",""))
        p = str(row_norm.get("senha","")).strip()
        if u == normalizar_texto(usuario_input) and p == senha_input:
            return True
    return False

def contar_casos_usuario(usuario):
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(1 for r in sheet.get_all_records() if normalizar_texto(r.get("usuario","")) == normalizar_texto(usuario))
    except:
        return 0

def calcular_media_usuario(usuario):
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [float(r["nota"]) for r in sheet.get_all_records() if normalizar_texto(r.get("usuario","")) == normalizar_texto(usuario)]
        return round(sum(notas)/len(notas),2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario, texto):
    gs.open("LogsSimulador").sheet1.append_row([usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), texto, "IA"])

def salvar_nota_usuario(usuario, nota):
    gs.open("notasSimulador").sheet1.append_row([usuario, nota, datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option="USER_ENTERED")

def extrair_nota(texto):
    m = re.search(r"Nota:\s*(\d+(?:[\.,]\d+)?)", texto)
    if m:
        return float(m.group(1).replace(",","."))
    return None

# ====== SESSION STATE ======
if "logado" not in st.session_state:
    st.session_state.logado = False
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "historico" not in st.session_state:
    st.session_state.historico = ""
if "consulta_finalizada" not in st.session_state:
    st.session_state.consulta_finalizada = False

# ====== LOGIN ======
if not st.session_state.logado:
    st.title("🔐 Login")
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado = True
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ====== APÓS LOGIN ======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("Casos finalizados", contar_casos_usuario(st.session_state.usuario))
col2.metric("Média global", calcular_media_usuario(st.session_state.usuario))

especialidade = st.radio("Especialidade:", ["PSF","Pediatria","Emergências"])
assist_id = ASSISTANT_ID if especialidade=="PSF" else ASSISTANT_PEDIATRIA_ID if especialidade=="Pediatria" else ASSISTANT_EMERGENCIAS_ID

# ====== NOVA SIMULAÇÃO ======
if st.button("➕ Nova Simulação"):
    # se existe simulação ativa
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        with st.modal("Confirmar reinício"):
            st.warning("Consulta em andamento. Iniciar nova apagará todo o progresso.")
            if st.button("Iniciar nova"):
                st.session_state.thread_id = None
                st.session_state.historico = ""
                st.session_state.consulta_finalizada = False
            else:
                st.stop()

    st.session_state.thread_id = openai.beta.threads.create().id
    # prompt inicial vazio (configurado no assistant)
    with st.modal("Gerando paciente…"):
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assist_id)
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
            time.sleep(0.4)
    msgs = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    st.session_state.historico = next((m.content[0].text.value for m in msgs if m.role=="assistant"), "")
    st.session_state.consulta_finalizada = False
    st.rerun()

# ====== EXIBIR PACIENTE ======
if st.session_state.historico:
    st.subheader("👤 Paciente")
    st.info(st.session_state.historico)

# ====== INTERAÇÃO E ANOTAÇÕES ======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    c1, c2 = st.columns([2,1])
    with c1:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                with st.modal("Processando…"):
                    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assist_id)
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                        time.sleep(0.4)
                msgs = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                resposta = next((m.content[0].text.value for m in msgs if m.role=="assistant"), "")
                st.markdown(f"**Resposta do paciente:**\n\n{resposta}")
            else:
                st.warning("Digite algo primeiro.")
    with c2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)", st.session_state.get("anotacoes",""), height=260)

# ====== FINALIZAR CONSULTA ======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar consulta"):
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content="Finalizar consulta.")
        with st.modal("Gerando relatório…"):
            run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assist_id)
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.4)
        msgs = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        resp = next((m.content[0].text.value for m in msgs if m.role=="assistant"), "")
        st.subheader("📄 Resultado Final")
        st.markdown(resp)
        st.session_state.consulta_finalizada = True
        registrar_caso(st.session_state.usuario, resp)
        nota_val = extrair_nota(resp)
        if nota_val is not None:
            salvar_nota_usuario(st.session_state.usuario, nota_val)
        st.rerun()
