import streamlit as st
import unicodedata, time, re, openai, gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ─────────────────── Configuração visual ───────────────────
st.set_page_config("Simulador Médico IA", "🩺", layout="wide")

st.markdown(
    """
    <style>
    textarea{border:2px solid #003366!important;border-radius:8px!important;
             box-shadow:0 0 5px rgba(0,51,102,.4);padding:.5rem}
    div[data-testid="stSpinner"]>div{
        display:flex;justify-content:center;align-items:center;
        height:160px;font-size:1.1rem;font-weight:bold;color:#003366}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────── Credenciais ───────────────────
openai.api_key   = st.secrets["openai"]["api_key"]
ASSISTANT_ID     = st.secrets["assistants"]["default"]
ASSISTANT_PED_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EME_ID = st.secrets["assistants"]["emergencias"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds  = ServiceAccountCredentials.from_json_keyfile_dict(
    dict(st.secrets["google_credentials"]), scope
)
gs = gspread.authorize(creds)

# ─────────────────── Funções auxiliares ───────────────────
def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()

def validar(u, p):
    sh = gs.open("LoginSimulador").sheet1
    for l in sh.get_all_records():
        if _norm(l["usuario"]) == _norm(u) and l["senha"].strip() == p:
            return True
    return False

def casos(u):
    try:
        return sum(1 for l in gs.open("LogsSimulador").sheet1.get_all_records() if _norm(l["usuario"]) == _norm(u))
    except:
        return 0

def media(u):
    try:
        notas = [
            float(l["nota"])
            for l in gs.open("notasSimulador").sheet1.get_all_records()
            if _norm(l["usuario"]) == _norm(u)
        ]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar(u, txt):
    gs.open("LogsSimulador").sheet1.append_row([u, datetime.now().isoformat(" ", "seconds"), txt, "IA"])

def salvar_nota(u, n):
    gs.open("notasSimulador").sheet1.append_row([u, n, datetime.now().isoformat(" ", "seconds")])

def extrair_nota(txt):
    m = re.search(r"Nota:\s*([\d.,]+)", txt)
    return float(m.group(1).replace(",", ".")) if m else None

# ─────────────────── Session State defaults ───────────────────
st.session_state.setdefault("logado", False)
st.session_state.setdefault("thread_id", None)
st.session_state.setdefault("historico", "")
st.session_state.setdefault("consulta_finalizada", False)
st.session_state.setdefault("anotacoes", "")
st.session_state.setdefault("confirm_nova", False)   # estado da confirmação

# ─────────────────── Login ───────────────────
if not st.session_state.logado:
    st.title("🔐 Simulador Médico – login")
    with st.form("f_login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar(u, p):
                st.session_state.usuario = u
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Credenciais inválidas")
    st.stop()

# ─────────────────── Cabeçalho do app ───────────────────
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

c1, c2 = st.columns(2)
c1.metric("Casos finalizados", casos(st.session_state.usuario))
c2.metric("Média global", media(st.session_state.usuario))

# ─────────────────── Escolha de especialidade ───────────────────
esp = st.radio("Especialidade", ["PSF", "Pediatria", "Emergências"], horizontal=True)
aid = {"PSF": ASSISTANT_ID, "Pediatria": ASSISTANT_PED_ID, "Emergências": ASSISTANT_EME_ID}[esp]

# ─────────  botão Nova simulação com confirmação  ─────────
if st.button("➕ Nova simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        # Já existe consulta em progresso
        with st.modal("Encerrar simulação atual?"):
            st.warning("Há uma simulação não finalizada. Iniciar nova apagará o progresso.")
            if st.button("Iniciar nova"):
                st.session_state.confirm_nova = True
            if st.button("Cancelar"):
                st.session_state.confirm_nova = False
        st.stop()

    # Se caiu aqui, pode iniciar
    st.session_state.confirm_nova = False
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False

    prompt = "Iniciar clínica pediátrica..." if esp == "Pediatria" else ""
    if prompt:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)

    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
    with st.spinner("🧠 Gerando paciente…"):
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
            time.sleep(0.4)

    msg = next(
        (m.content[0].text.value for m in openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data if m.role == "assistant"),
        ""
    )
    st.session_state.historico = msg
    st.rerun()

# ─────────  Exibe paciente  ─────────
if st.session_state.historico:
    st.subheader("👤 Paciente")
    st.info(st.session_state.historico)

# ─────────  Interação e anotações  ─────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    c1, c2 = st.columns([2, 1])
    with c1:
        pergunta = st.text_area("Digite pergunta / conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
                with st.spinner("💬 Processando…"):
                    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                        time.sleep(0.4)
                resposta = next(
                    (m.content[0].text.value for m in openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data if m.role == "assistant"),
                    ""
                )
                st.markdown(f"**Resposta do paciente:**\n\n{resposta}")
            else:
                st.warning("Digite algo primeiro.")

    with c2:
        st.session_state.anotacoes = st.text_area("📝 Anotações (anamnese)", st.session_state.anotacoes, height=260)

# ─────────  Finalizar consulta  ─────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar consulta"):
        mensagem_final = (
            "Finalizar consulta. "
            "1) Gere prontuário completo (### Prontuário Completo do Paciente). "
            "2) Feedback educativo. "
            "3) Nota objetiva de 0 a 10 no formato: Nota: X/10."
        )
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=mensagem_final)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
        with st.spinner("📄 Gerando relatório…"):
            while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != "completed":
                time.sleep(0.5)
        resp = next(
            (m.content[0].text.value for m in openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data if m.role == "assistant"),
            ""
        )
        st.subheader("📄 Resultado final")
        st.markdown(resp)
        st.session_state.consulta_finalizada = True

        # salva log e nota
        registrar_caso(st.session_state.usuario, resp)
        n = extrair_nota(resp)
        if n is not None:
            salvar_nota_usuario(st.session_state.usuario, n)

        # força recálculo das métricas
        st.rerun()
