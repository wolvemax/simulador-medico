import streamlit as st
import unicodedata
import time
import re
import openai
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ─────────── Configuração da Página ───────────
st.set_page_config(
    page_title="Simulador Médico IA",
    page_icon="🩺",
    layout="wide",
)

st.markdown(
    """
    <style>
    textarea {
        border: 2px solid #003366 !important;
        border-radius: 8px !important;
        box-shadow: 0 0 5px rgba(0,51,102,0.4);
        padding: .5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────── Credenciais OpenAI & Google ───────────
openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID         = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA  = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIA = st.secrets["assistants"]["emergencias"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    dict(st.secrets["google_credentials"]), scope
)
gs = gspread.authorize(creds)

# ─────────── Funções Auxiliares ───────────
def _norm(txt: str) -> str:
    if txt is None: return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(txt))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()

def validar_credenciais(user, pwd) -> bool:
    sheet = gs.open("LoginSimulador").sheet1
    for row in sheet.get_all_records():
        if _norm(row.get("usuario")) == _norm(user) and str(row.get("senha","")).strip() == pwd:
            return True
    return False

def contar_casos(usuario) -> int:
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(
            1 for r in sheet.get_all_records()
            if _norm(r.get("usuario")) == _norm(usuario)
        )
    except:
        return 0

def calcular_media(usuario) -> float:
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [
            float(r["nota"])
            for r in sheet.get_all_records()
            if _norm(r.get("usuario")) == _norm(usuario)
        ]
        return round(sum(notas)/len(notas),2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario, texto):
    gs.open("LogsSimulador").sheet1.append_row([
        usuario,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        texto,
        "IA"
    ])

def salvar_nota(usuario, nota):
    gs.open("notasSimulador").sheet1.append_row([
        usuario,
        nota,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ], value_input_option="USER_ENTERED")

def extrair_nota(texto) -> float | None:
    m = re.search(r"Nota:\s*([\d.,]+)", texto)
    if not m: return None
    return float(m.group(1).replace(",", "."))

# ─────────── Session State Defaults ───────────
st.session_state.setdefault("logado", False)
st.session_state.setdefault("thread_id", None)
st.session_state.setdefault("historico", "")
st.session_state.setdefault("consulta_finalizada", False)
st.session_state.setdefault("anotacoes", "")

# ─────────── Tela de Login ───────────
if not st.session_state.logado:
    st.title("🔐 Simulador Médico – Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        s = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(u, s):
                st.session_state.usuario = u
                st.session_state.logado = True
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ─────────── Cabeçalho Pós‑Login ───────────
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.usuario}**")

c1, c2 = st.columns(2)
c1.metric("Casos finalizados", contar_casos(st.session_state.usuario))
c2.metric("Média global",      calcular_media(st.session_state.usuario))

# ─────────── Seleção de Especialidade ───────────
esp = st.radio(
    "Especialidade:",
    ["PSF", "Pediatria", "Emergências"],
    horizontal=True
)
ASSIST_ID = {
    "PSF": ASSISTANT_ID,
    "Pediatria": ASSISTANT_PEDIATRIA,
    "Emergências": ASSISTANT_EMERGENCIA
}[esp]

# ─────────── Iniciar Nova Simulação ───────────
if st.button("➕ Nova Simulação"):
    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        with st.modal("Simulação não finalizada"):
            st.warning("⚠️ Há uma simulação em andamento. Iniciar nova apagará o progresso atual.")
            if st.button("Iniciar nova"):
                st.session_state.thread_id = None
                st.session_state.historico = ""
                st.session_state.consulta_finalizada = False
            else:
                st.stop()

    # Cria nova thread e gera paciente
    st.session_state.thread_id = openai.beta.threads.create().id
    with st.modal("🧠 Gerando paciente…"):
        run = openai.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=ASSIST_ID
        )
        while openai.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread_id,
            run_id=run.id
        ).status != "completed":
            time.sleep(0.4)

    msgs = openai.beta.threads.messages.list(
        thread_id=st.session_state.thread_id
    ).data
    st.session_state.historico = next(
        (m.content[0].text.value for m in msgs if m.role=="assistant"),
        ""
    )
    st.session_state.consulta_finalizada = False
    st.rerun()

# ─────────── Exibir Paciente ───────────
if st.session_state.historico:
    st.subheader("👤 Paciente")
    st.info(st.session_state.historico)

# ─────────── Pergunta & Anotações ───────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    col_p, col_a = st.columns([2,1])
    with col_p:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip():
                openai.beta.threads.messages.create(
                    thread_id=st.session_state.thread_id,
                    role="user",
                    content=pergunta
                )
                with st.modal("💬 Processando…"):
                    run = openai.beta.threads.runs.create(
                        thread_id=st.session_state.thread_id,
                        assistant_id=ASSIST_ID
                    )
                    while openai.beta.threads.runs.retrieve(
                        thread_id=st.session_state.thread_id,
                        run_id=run.id
                    ).status != "completed":
                        time.sleep(0.4)

                msgs = openai.beta.threads.messages.list(
                    thread_id=st.session_state.thread_id
                ).data
                resposta = next(
                    (m.content[0].text.value for m in msgs if m.role=="assistant"),
                    ""
                )
                st.markdown(f"**Resposta do paciente:**\n\n{resposta}")
            else:
                st.warning("Digite algo primeiro.")

    with col_a:
        st.session_state.anotacoes = st.text_area(
            "📝 Anotações (anamnese)",
            st.session_state.anotacoes,
            height=260
        )

# ─────────── Finalizar Consulta ───────────
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar consulta"):
        # Envia instrução para relatório
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=(
                "Finalizar consulta. "
                "1) Prontuário completo (### Prontuário Completo do Paciente). "
                "2) Feedback educacional. "
                "3) Nota objetiva de 0 a 10 no formato: Nota: X/10."
            )
        )
        with st.modal("📄 Gerando relatório da consulta…"):
            run = openai.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=ASSIST_ID
            )
            while openai.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread_id,
                run_id=run.id
            ).status != "completed":
                time.sleep(0.5)

        msgs = openai.beta.threads.messages.list(
            thread_id=st.session_state.thread_id
        ).data
        resp = next(
            (m.content[0].text.value for m in msgs if m.role=="assistant"),
            ""
        )
        st.subheader("📄 Resultado final")
        st.markdown(resp)

        st.session_state.consulta_finalizada = True
        registrar_caso(st.session_state.usuario, resp)
        nota = extrair_nota(resp)
        if nota is not None:
            salvar_nota(st.session_state.usuario, nota)
        st.rerun()
