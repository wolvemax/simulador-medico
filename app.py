import streamlit as st
import unicodedata, time, re, openai, gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ─────────── CONFIG. VISUAL ───────────
st.set_page_config("Simulador Médico IA", "🩺", layout="wide")

st.markdown(
    """
    <style>
    textarea{
        border:2px solid #003366!important;border-radius:8px!important;
        box-shadow:0 0 5px rgba(0,51,102,.4);padding:.5rem}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────── CREDENCIAIS ───────────
openai.api_key       = st.secrets["openai"]["api_key"]
ASSISTANT_ID         = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA  = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIA = st.secrets["assistants"]["emergencias"]

scope  = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]
creds  = ServiceAccountCredentials.from_json_keyfile_dict(
            dict(st.secrets["google_credentials"]), scope)
gs     = gspread.authorize(creds)

# ─────────── FUNÇÕES ───────────
_norm = lambda s: "".join(c for c in unicodedata.normalize("NFD", str(s))
                          if unicodedata.category(c) != "Mn").lower().strip()

def validar(u, p):
    for l in gs.open("LoginSimulador").sheet1.get_all_records():
        if _norm(l.get("usuario","")) == _norm(u) and str(l.get("senha","")).strip() == p:
            return True
    return False

def casos(u):
    try:
        return sum(1 for l in gs.open("LogsSimulador").sheet1.get_all_records()
                   if _norm(l.get("usuario","")) == _norm(u))
    except: return 0

def media(u):
    try:
        notas=[float(l["nota"]) for l in gs.open("notasSimulador").sheet1.get_all_records()
               if _norm(l.get("usuario","")) == _norm(u)]
        return round(sum(notas)/len(notas),2) if notas else 0
    except: return 0

def registrar(u,txt):
    gs.open("LogsSimulador").sheet1.append_row(
        [u, datetime.now().isoformat(" ","seconds"), txt, "IA"])

def salvar_nota(u,n):
    gs.open("notasSimulador").sheet1.append_row(
        [u, n, datetime.now().isoformat(" ","seconds")])

def extrair_nota(txt):
    m=re.search(r"Nota:\s*([\d.,]+)",txt)
    return float(m.group(1).replace(",",".")) if m else None

# ─────────── SESSION DEFAULTS ───────────
defaults = {
    "logado":False,"thread_id":None,"historico":"","consulta_finalizada":False,
    "anotacoes":"","confirm_nova":False
}
for k,v in defaults.items(): st.session_state.setdefault(k,v)

# ─────────── LOGIN ───────────
if not st.session_state.logado:
    st.title("🔐 Simulador Médico – Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar(u,p):
                st.session_state.usuario=u
                st.session_state.logado=True
                st.rerun()
            else:
                st.error("Credenciais inválidas")
    st.stop()

# ─────────── CABEÇALHO ───────────
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

c1,c2 = st.columns(2)
c1.metric("Casos finalizados", casos(st.session_state.usuario))
c2.metric("Média global",      media(st.session_state.usuario))

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
