import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import openai
import gspread

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Bem vindo ao SIMULAMAX - Simulador Médico IA", page_icon="🩺", layout="wide")

openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

# ======= GARANTIR ESTADO INICIAL =======
REQUIRED_KEYS = ["logado", "thread_id", "historico", "consulta_finalizada", "prompt_inicial", "media_usuario", "run_em_andamento"]
for key in REQUIRED_KEYS:
    if key not in st.session_state:
        st.session_state[key] = False if key == "logado" else None

# ======= FUNÇÕES UTILITÁRIAS =======
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
        match = re.search(r"nota\s*[:\-]?\s*(\d+(?:[.,]\d+)?)(?:\s*/?\s*10)?", texto, re.IGNORECASE)
        if not match:
            match = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*10", texto)
        if match:
            return float(match.group(1).replace(",", "."))
    except:
        pass
    return None

def renderizar_historico():
    if not st.session_state.thread_id:
        return
    mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    mensagens_ordenadas = sorted(mensagens, key=lambda x: x.created_at)
    for msg in mensagens_ordenadas:
        conteudo = msg.content[0].text.value
        if "Iniciar nova simulação clínica" in conteudo:
            continue
        hora = datetime.fromtimestamp(msg.created_at).strftime("%H:%M")
        if msg.role == "user":
            with st.chat_message("user", avatar="👨‍⚕️"):
                st.markdown(conteudo)
                st.caption(f"⏰ {hora}")
        elif msg.role == "assistant":
            with st.chat_message("assistant", avatar="🧑‍⚕️"):
                st.markdown(conteudo)
                st.caption(f"⏰ {hora}")

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
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= INTERFACE LOGADA =======
st.title("🩺 Simulador Médico Interativo com IA")
st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
if not st.session_state.media_usuario:
    st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
col2.metric("📊 Média global", st.session_state.media_usuario)

especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"])
assistant_id_usado = ASSISTANT_ID if especialidade == "PSF" else ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_EMERGENCIAS_ID

if st.button("➕ Nova Simulação"):
    st.session_state.historico = ""
    st.session_state.thread_id = openai.beta.threads.create().id
    st.session_state.consulta_finalizada = False
    prompt = ""
    if especialidade == "Pediatria":
        prompt = "Iniciar nova simulação clínica pediátrica com identificação e queixa principal."
    elif especialidade == "PSF":
        prompt = "Iniciar nova simulação clínica com paciente simulado. Apenas início da consulta com identificação e queixa principal."
    if prompt:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
        with st.spinner("Gerando paciente..."):
            while True:
                status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                if status.status == "completed":
                    break
                time.sleep(1)
        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        for msg in mensagens:
            if msg.role == "assistant":
                st.session_state.historico = msg.content[0].text.value
                break
        st.rerun()

# ======= CONTEÚDO PRINCIPAL =======
if st.session_state.historico:
    st.markdown("### 👤 Identificação do Paciente")
    st.info(st.session_state.historico)

if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    renderizar_historico()
    pergunta = st.chat_input("Digite sua pergunta ou conduta:")
    if pergunta:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
        with st.spinner("Pensando..."):
            while True:
                status = openai.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                if status.status == "completed":
                    break
                time.sleep(1)
        st.rerun()

# ======= FINALIZAR CONSULTA COM PROMPT EXPLICATIVO =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        mensagem_final = (
            "Avalie a simulação médica considerando os seguintes critérios:\n"
            "1. Identificação e anamnese (nota de 0 a 10 com justificativa);\n"
            "2. Hipóteses diagnósticas sugeridas (nota de 0 a 10 com justificativa);\n"
            "3. Conduta médica (nota de 0 a 10 com justificativa);\n"
            "4. Qualidade geral do raciocínio clínico (nota de 0 a 10 com justificativa);\n"
            "5. Participação ativa e número de interações (nota de 0 a 10 com justificativa).\n\n"
            "Depois, forneça a média ponderada com os seguintes pesos:\n"
            "- Identificação e anamnese: 20%\n"
            "- Hipóteses diagnósticas: 20%\n"
            "- Conduta médica: 25%\n"
            "- Raciocínio clínico: 25%\n"
            "- Participação: 10%\n\n"
            "Resultado final:\n"
            "1. Prontuário clínico do paciente (título: ### Prontuário Completo do Paciente)\n"
            "2. Feedback educacional com análise das falhas e sugestões de melhoria\n"
            "3. Nota final no formato exato: Nota: X/10"
        )

        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=mensagem_final)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
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
                with st.chat_message("assistant", avatar="🧑‍⚕️"):
                    st.markdown("### 📄 Resultado Final")
                    st.markdown(resposta)
                    st.info("""
**Notas por etapa:**
- Identificação e anamnese: _nota atribuída pela IA_
- Hipóteses diagnósticas: _nota atribuída pela IA_
- Conduta: _nota atribuída pela IA_
- Raciocínio clínico: _nota atribuída pela IA_
- Participação: _nota atribuída pela IA_
""")
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
