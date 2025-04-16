
import streamlit as st
import unicodedata
import time
import re
import openai
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ======= CONFIGURAÇÃO DA PÁGINA =======
st.set_page_config(page_title="Simulador Médico IA", page_icon="🩺", layout="wide")

# ======= CSS PARA TEXTAREA =======
st.markdown("
<style>
textarea {
    border: 2px solid #003366 !important;
    border-radius: 8px !important;
    box-shadow: 0 0 5px rgba(0,51,102,0.4);
    padding: .5rem;
}
</style>
", unsafe_allow_html=True)

# ======= CREDENCIAIS =======
openai.api_key             = st.secrets["openai"]["api_key"]
ASSISTANT_ID               = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID     = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID   = st.secrets["assistants"]["emergencias"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds_dict = dict(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs = gspread.authorize(creds)

# ======= FUNÇÕES AUXILIARES =======
def _norm(txt):
    if txt is None:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(txt)) if unicodedata.category(c) != 'Mn').lower().strip()

def validate_credentials(user_input, pass_input):
    sheet = gs.open("LoginSimulador").sheet1
    for row in sheet.get_all_records():
        if _norm(row.get("usuario")) == _norm(user_input) and str(row.get("senha","")).strip() == pass_input:
            return True
    return False

def count_cases(user):
    try:
        sheet = gs.open("LogsSimulador").sheet1
        return sum(1 for r in sheet.get_all_records() if _norm(r.get("usuario")) == _norm(user))
    except:
        return 0

def calculate_average(user):
    try:
        sheet = gs.open("notasSimulador").sheet1
        notas = [float(r['nota']) for r in sheet.get_all_records() if _norm(r.get('usuario')) == _norm(user)]
        return round(sum(notas) / len(notas),2) if notas else 0.0
    except:
        return 0.0

def register_case(user, text):
    gs.open("LogsSimulador").sheet1.append_row([user, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text, "IA"])

def save_user_score(user, score):
    gs.open("notasSimulador").sheet1.append_row([user, score, datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option="USER_ENTERED")

def extract_score(text):
    m = re.search(r"Nota:\s*(\d+(?:[\.,]\d+)?)", text)
    return float(m.group(1).replace(",",".")) if m else None

# ======= STATE PADRÕES =======
st.session_state.setdefault('logged_in', False)
st.session_state.setdefault('thread_id', None)
st.session_state.setdefault('history', "")
st.session_state.setdefault('finished', False)
st.session_state.setdefault('notes', "")

# ======= TELA DE LOGIN =======
if not st.session_state.logged_in:
    st.title("🔐 Simulador Médico - Login")
    with st.form('login_form'):
        user = st.text_input('Usuário')
        pwd = st.text_input('Senha', type='password')
        if st.form_submit_button('Entrar'):
            if validate_credentials(user, pwd):
                st.session_state.user = user
                st.session_state.logged_in = True
                st.experimental_rerun()
            else:
                st.error('Usuário ou senha inválidos.')
    st.stop()

# ======= PÓS LOGIN =======
st.title("🩺 Simulador Médico Interativo")
st.markdown(f"👤 **{st.session_state.user}**")

c1, c2 = st.columns(2)
c1.metric('📋 Casos finalizados', count_cases(st.session_state.user))
c2.metric('📊 Média global', calculate_average(st.session_state.user))

# ======= ESPECIALIDADE =======
esp = st.radio('Especialidade:', ['PSF','Pediatria','Emergências'], horizontal=True)
aid = ASSISTANT_ID if esp=='PSF' else ASSISTANT_PEDIATRIA_ID if esp=='Pediatria' else ASSISTANT_EMERGENCIAS_ID

# ======= NOVA SIMULAÇÃO =======
if st.button('➕ Nova Simulação'):
    # confirmação se em andamento
    if st.session_state.thread_id and not st.session_state.finished:
        st.warning('⚠️ Simulação em andamento. Confirmar nova e perder progresso.')
        if not st.checkbox('Confirmar nova simulação'):
            st.stop()
    # inicia nova
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.finished = False
    # gera paciente
    ph = st.empty()
    ph.markdown("<h3 style='text-align:center'>🧠 Gerando paciente... aguarde</h3>", unsafe_allow_html=True)
    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
    while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id).status != 'completed':
        time.sleep(0.5)
    ph.empty()
    msgs = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    st.session_state.history = next((m.content[0].text.value for m in msgs if m.role=='assistant'), '')
    st.experimental_rerun()

# ======= EXIBE PACIENTE =======
if st.session_state.history:
    st.subheader('👤 Paciente')
    st.info(st.session_state.history)

# ======= INTERAÇÃO E ANOTAÇÕES =======
if st.session_state.thread_id and not st.session_state.finished:
    col_q, col_n = st.columns([2,1])
    with col_q:
        q = st.text_area('Digite sua pergunta ou conduta:')
        if st.button('Enviar'):
            if q.strip():
                ph2 = st.empty()
                ph2.markdown("<h3 style='text-align:center'>💬 Processando... aguarde</h3>", unsafe_allow_html=True)
                openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role='user', content=q)
                run2 = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
                while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run2.id).status != 'completed':
                    time.sleep(0.5)
                ph2.empty()
                msgs2 = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                resp = next((m.content[0].text.value for m in msgs2 if m.role=='assistant'), '')
                st.markdown(f"**Resposta do paciente:**\n\n{resp}")
    with col_n:
        st.session_state.notes = st.text_area('📝 Suas anotações de anamnese:', value=st.session_state.notes, height=250)

# ======= FINALIZAR CONSULTA =======
if st.session_state.thread_id and not st.session_state.finished:
    if st.button('✅ Finalizar Consulta'):
        ph3 = st.empty()
        ph3.markdown("<h3 style='text-align:center'>📄 Gerando relatório da consulta... aguarde</h3>", unsafe_allow_html=True)
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role='user', content=(
            'Finalizar consulta. '
            '1) Prontuário completo (### Prontuário Completo do Paciente). '
            '2) Feedback educacional. '
            '3) Nota: X/10.'
        ))
        run3 = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=aid)
        while openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run3.id).status != 'completed':
            time.sleep(0.5)
        ph3.empty()
        msgs3 = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        final_resp = next((m.content[0].text.value for m in msgs3 if m.role=='assistant'), '')
        st.subheader('📄 Resultado Final')
        st.markdown(final_resp)
        st.session_state.finished = True
        register = register_case(st.session_state.user, final_resp)
        score = extract_score(final_resp)
        if score is not None:
            save_user_score(st.session_state.user, score)
        st.experimental_rerun()
