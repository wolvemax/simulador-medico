import streamlit as st
import unicodedata
import time
import re
import openai
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ====== CONFIGURAÇÃO DA PÁGINA ======
st.set_page_config(
    page_title="Simulador Médico IA",
    page_icon="🩺",
    layout="wide"
)

# ====== CSS PARA TEXTAREA ======
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
    unsafe_allow_html=True
)

# ====== CREDENCIAIS ======
openai.api_key               = st.secrets["openai"]["api_key"]
ASSISTANT_ID                 = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID       = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID     = st.secrets["assistants"]["emergencias"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    dict(st.secrets["google_credentials"]),
    scope
)
gs = gspread.authorize(creds)

# ====== FUNÇÕES AUXILIARES ======
def _normalize(txt):
    if txt is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(txt))
                   if unicodedata.category(c) != "Mn").lower().strip()

def validate_credentials(user_input, pass_input):
    sheet = gs.open("LoginSimulador").sheet1
    for row in sheet.get_all_records():
        # identifica coluna 'usuario' e 'senha'
        user_row = _normalize(row.get("usuario",""))
        pass_row = str(row.get("senha","")).strip()
        if user_row == _normalize(user_input) and pass_row == pass_input.strip():
            return True
    return False

def count_cases(user):
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(1 for r in sheet.get_all_records()
                   if _normalize(r.get("usuario")) == _normalize(user))
    except:
        return 0

def calculate_average(user):
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [float(r["nota"]) for r in sheet.get_all_records()
                 if _normalize(r.get("usuario")) == _normalize(user)]
        return round(sum(notas)/len(notas),2) if notas else 0.0
    except:
        return 0.0

def register_case(user, text):
    gs.open("LogsSimulador").sheet1.append_row([
        user,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        text,
        "IA"
    ])

def save_user_score(user, score):
    gs.open("notasSimulador").sheet1.append_row([
        user,
        score,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ], value_input_option="USER_ENTERED")

def extract_score(text):
    m = re.search(r"Nota:\s*(\d+(?:[.,]\d+)?)", text)
    return float(m.group(1).replace(",", ".")) if m else None

# ====== SESSION STATE DEFAULTS ======
st.session_state.setdefault("logged_in", False)
st.session_state.setdefault("user", "")
st.session_state.setdefault("thread_id", None)
st.session_state.setdefault("history", "")
st.session_state.setdefault("finished", False)
st.session_state.setdefault("notes", "")

# ====== LOGIN ======
if not st.session_state.logged_in:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login_form"):
        user_input = st.text_input("Usuário")
        pass_input = st.text_input("Senha", type="password")
        submitted  = st.form_submit_button("Entrar")
        if submitted:
            if validate_credentials(user_input, pass_input):
                st.session_state.user = user_input
                st.session_state.logged_in = True
                st.success("Login realizado com sucesso!")
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ====== ÁREA PRINCIPAL (após login) ======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.user}**")

col1, col2 = st.columns(2)
col1.metric("Casos finalizados", count_cases(st.session_state.user))
col2.metric("Média global",      calculate_average(st.session_state.user))

# ====== SELEÇÃO DE ESPECIALIDADE ======
speciality = st.radio(
    "Especialidade:",
    ["PSF", "Pediatria", "Emergências"],
    horizontal=True
)
assistant_used = (
    ASSISTANT_ID if speciality == "PSF"
    else ASSISTANT_PEDIATRIA_ID if speciality == "Pediatria"
    else ASSISTANT_EMERGENCIAS_ID
)

# ====== NOVA SIMULAÇÃO ======
if st.button("➕ Nova Simulação"):
    # confirmação se já há simulação ativa e não finalizada
    if st.session_state.thread_id and not st.session_state.finished:
        confirm = st.checkbox(
            "⚠️ Simulação em andamento. Confirmar nova e perder progresso atual."
        )
        if not confirm:
            st.warning("Aguardando confirmação para iniciar nova simulação.")
            st.stop()

    # inicia thread e gera paciente
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.finished    = False

    placeholder = st.empty()
    placeholder.markdown(
        "<h3 style='text-align:center'>🧠 Gerando paciente... aguarde</h3>",
        unsafe_allow_html=True
    )
    run = openai.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=assistant_used
    )
    while openai.beta.threads.runs.retrieve(
        thread_id=st.session_state.thread_id,
        run_id=run.id
    ).status != "completed":
        time.sleep(0.5)
    placeholder.empty()

    msgs = openai.beta.threads.messages.list(
        thread_id=st.session_state.thread_id
    ).data
    st.session_state.history = next(
        (m.content[0].text.value for m in msgs if m.role=="assistant"),
        ""
    )

# ====== EXIBIR PACIENTE ======
if st.session_state.history:
    st.subheader("👤 Paciente")
    st.info(st.session_state.history)

# ====== INTERAÇÃO & ANOTAÇÕES ======
if st.session_state.thread_id and not st.session_state.finished:
    col_q, col_n = st.columns([2, 1])
    with col_q:
        question = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if question.strip():
                ph2 = st.empty()
                ph2.markdown(
                    "<h3 style='text-align:center'>💬 Processando... aguarde</h3>",
                    unsafe_allow_html=True
                )
                openai.beta.threads.messages.create(
                    thread_id=st.session_state.thread_id,
                    role="user",
                    content=question
                )
                run2 = openai.beta.threads.runs.create(
                    thread_id=st.session_state.thread_id,
                    assistant_id=assistant_used
                )
                while openai.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id,
                    run_id=run2.id
                ).status != "completed":
                    time.sleep(0.5)
                ph2.empty()

                msgs2 = openai.beta.threads.messages.list(
                    thread_id=st.session_state.thread_id
                ).data
                resp = next(
                    (m.content[0].text.value for m in msgs2 if m.role=="assistant"),
                    ""
                )
                st.markdown(f"**Resposta do paciente:**\n\n{resp}")
            else:
                st.warning("Digite algo primeiro.")
    with col_n:
        st.session_state.notes = st.text_area(
            "📝 Anotações (anamnese):",
            st.session_state.notes,
            height=260
        )

# ====== FINALIZAR CONSULTA ======
if st.session_state.thread_id and not st.session_state.finished:
    if st.button("✅ Finalizar Consulta"):
        ph3 = st.empty()
        ph3.markdown(
            "<h3 style='text-align:center'>📄 Gerando relatório da consulta... aguarde</h3>",
            unsafe_allow_html=True
        )
        openai.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=(
                "Finalizar consulta. "
                "1) Prontuário completo (### Prontuário Completo do Paciente). "
                "2) Feedback educacional. "
                "3) Nota: X/10."
            )
        )
        run3 = openai.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=assistant_used
        )
        while openai.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread_id,
            run_id=run3.id
        ).status != "completed":
            time.sleep(0.5)
        ph3.empty()

        msgs3 = openai.beta.threads.messages.list(
            thread_id=st.session_state.thread_id
        ).data
        final_resp = next(
            (m.content[0].text.value for m in msgs3 if m.role=="assistant"),
            ""
        )
        st.subheader("📄 Resultado Final")
        st.markdown(final_resp)

        st.session_state.finished = True
        register_case(st.session_state.user, final_resp)
        score = extract_score(final_resp)
        if score is not None:
            save_user_score(st.session_state.user, score)
