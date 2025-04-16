import streamlit as st
import unicodedata, time, re, openai, gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ───────── Config visual ─────────
st.set_page_config("Simulador Médico IA", "🩺", layout="wide")
st.markdown("""
<style>
textarea{border:2px solid #003366!important;border-radius:8px!important;
         box-shadow:0 0 5px rgba(0,51,102,.4);padding:.5rem}
div[data-testid="stSpinner"]>div{
    display:flex;justify-content:center;align-items:center;
    height:160px;font-size:1.1rem;font-weight:bold;color:#003366}
</style>""", unsafe_allow_html=True)

# ───────── Credenciais ─────────
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID, ASSISTANT_PED_ID, ASSISTANT_EME_ID = (
    st.secrets["assistants"]["default"],
    st.secrets["assistants"]["pediatria"],
    st.secrets["assistants"]["emergencias"],
)
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    dict(st.secrets["google_credentials"]),
    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"],
)
gs = gspread.authorize(creds)

# ───────── Funções ─────────
_norm = lambda s: "".join(c for c in unicodedata.normalize("NFD", str(s))
                          if unicodedata.category(c) != "Mn").lower().strip()

def validar(u, p):
    for l in gs.open("LoginSimulador").sheet1.get_all_records():
        if _norm(l.get("usuario")) == _norm(u) and str(l.get("senha","")).strip() == p:
            return True
    return False

def casos(u):
    try:
        return sum(1 for r in gs.open("LogsSimulador").sheet1.get_all_records()
                   if _norm(r.get("usuario")) == _norm(u))
    except: return 0

def media(u):
    try:
        notas = [float(r["nota"]) for r in gs.open("notasSimulador").sheet1.get_all_records()
                 if _norm(r.get("usuario")) == _norm(u)]
        return round(sum(notas)/len(notas),2) if notas else 0.0
    except: return 0.0

def registrar(u, txt):
    gs.open("LogsSimulador").sheet1.append_row(
        [u, datetime.now().isoformat(" ", "seconds"), txt, "IA"])

def salvar_nota(u, n):
    gs.open("notasSimulador").sheet1.append_row(
        [u, n, datetime.now().isoformat(" ", "seconds")])

def extrair_nota(txt):
    m = re.search(r"Nota:\s*([\d.,]+)", txt)
    return float(m.group(1).replace(",", ".")) if m else None

# ───────── Estado default ─────────
st.session_state.setdefault("logado", False)
st.session_state.setdefault("thread_id", None)
st.session_state.setdefault("historico", "")
st.session_state.setdefault("consulta_finalizada", False)
st.session_state.setdefault("anotacoes", "")

# ───────── Login ─────────
if not st.session_state.logado:
    st.title("🔐 Simulador Médico – Login")
    with st.form("f_login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar") and validar(u, p):
            st.session_state.update({"usuario": u, "logado": True})
            st.rerun()
    st.stop()

# ───────── Cabeçalho ─────────
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")
c1, c2 = st.columns(2)
c1.metric("Casos finalizados", casos(st.session_state.usuario))
c2.metric("Média global",     media(st.session_state.usuario))

# ───────── Especialidade ─────────
esp = st.radio("Especialidade", ["PSF", "Pediatria", "Emergências"], horizontal=True)
aid = {"PSF": ASSISTANT_ID, "Pediatria": ASSISTANT_PED_ID, "Emergências": ASSISTANT_EME_ID}[esp]

# ───────── Nova simulação ─────────
if st.button("➕ Nova simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        # modal de confirmação
        with st.modal("Simulação não finalizada"):
            st.warning("Há uma simulação em andamento. Iniciar nova apagará o progresso.")
            if st.button("Iniciar nova"):
                st.session_state.thread_id = None
            else:
                st.stop()

    # cria nova thread
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False
    msg_inicial = "Iniciar clínica pediátrica..." if esp == "Pediatria" else ""
    if msg_inicial:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,
                                            role="user", content=msg_inicial)

    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                          assistant_id=aid)
    with st.spinner("🧠 Gerando paciente…"):
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                run_id=run.id).status != "completed":
            time.sleep(0.4)
    msg = next((m.content[0].text.value for m in
                openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                if m.role == "assistant"), "")
    st.session_state.historico = msg
    st.rerun()

# ───────── Exibe paciente ─────────
if st.session_state.historico:
    st.subheader("👤 Paciente"); st.info(st.session_state.historico)

# ───────── Perguntas e notas ─────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    c1, c2 = st.columns([2,1])
    with c1:
        q = st.text_area("Digite pergunta / conduta:")
        if st.button("Enviar"):
            if q.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,
                                                    role="user", content=q)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                                      assistant_id=aid)
                with st.spinner("💬 Processando…"):
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                            run_id=run.id).status != "completed":
                        time.sleep(0.4)
                r = next((m.content[0].text.value for m in
                          openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                          if m.role == "assistant"), "")
                st.markdown(f"**Resposta do paciente:**\n\n{r}")
            else:
                st.warning("Digite algo primeiro.")
    with c2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)",
                                                  st.session_state.anotacoes, height=260)

# ───────── Finalizar consulta ─────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar consulta"):
        instrucao = ("Finalizar consulta. 1) Prontuário completo (### Prontuário Completo do Paciente). "
                     "2) Feedback. 3) Nota objetiva no formato: Nota: X/10.")
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id,
                                            role="user", content=instrucao)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id,
                                              assistant_id=aid)
        with st.spinner("📄 Gerando relatório…"):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id,
                                                    run_id=run.id).status != "completed":
                time.sleep(0.5)
        resultado = next((m.content[0].text.value for m in
                          openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                          if m.role == "assistant"), "")
        st.subheader("📄 Resultado final"); st.markdown(resultado)
        st.session_state.consulta_finalizada = True
        registrar(st.session_state.usuario, resultado)
        n = extrair_nota(resultado)
        if n is not None:
            salvar_nota(st.session_state.usuario, n)
        st.rerun()
