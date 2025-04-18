import streamlit as st
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import openai
import gspread
import re

# ======= CONFIGURAÇÕES =======
st.set_page_config(page_title="Bem‑vindo ao SIMULAMAX - Simulador Médico IA", page_icon="🩺", layout="wide")

openai.api_key = st.secrets["openai"]["api_key"]
ASSISTANT_ID             = st.secrets["assistants"]["default"]
ASSISTANT_PEDIATRIA_ID   = st.secrets["assistants"]["pediatria"]
ASSISTANT_EMERGENCIAS_ID = st.secrets["assistants"]["emergencias"]

scope        = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = dict(st.secrets["google_credentials"])
creds        = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client_gspread = gspread.authorize(creds)

# ======= GARANTIR ESTADO INICIAL =======
REQUIRED_KEYS = [
    "logado",
    "thread_id",
    "historico",
    "consulta_finalizada",
    "prompt_inicial",
    "media_usuario",
    "run_em_andamento",
    "especialidade",
]
for key in REQUIRED_KEYS:
    if key not in st.session_state:
        # bool para logado, None para outros
        st.session_state[key] = False if key == "logado" else None

# ======= FUNÇÕES UTILITÁRIAS =======

def remover_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_chave(chave: str) -> str:
    return remover_acentos(chave.strip().lower())


def normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").lower().strip()


def validar_credenciais(usuario: str, senha: str) -> bool:
    try:
        sheet = client_gspread.open("LoginSimulador").sheet1
        for linha in sheet.get_all_records():
            ln = {normalizar_chave(k): v.strip() for k, v in linha.items() if isinstance(v, str)}
            if ln.get("usuario") == usuario and ln.get("senha") == senha:
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao validar login: {e}")
        return False


def contar_casos_usuario(usuario: str) -> int:
    try:
        sheet = client_gspread.open("LogsSimulador").worksheet("Pagina1")
        return sum(1 for l in sheet.get_all_records() if str(l.get("usuario", "")).strip().lower() == usuario.lower())
    except:
        return 0


def calcular_media_usuario(usuario: str) -> float:
    try:
        sheet = client_gspread.open("notasSimulador").sheet1
        notas = [float(l["nota"]) for l in sheet.get_all_records() if str(l.get("usuario", "")) .strip().lower() == usuario.lower()]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0


def registrar_caso(usuario: str, texto: str):
    sheet      = client_gspread.open("LogsSimulador").worksheet("Pagina1")
    datahora   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resumo     = texto[:300].replace("\n", " ").strip()
    assistente = st.session_state.get("especialidade", "desconhecido")
    sheet.append_row([usuario, datahora, resumo, assistente], value_input_option="USER_ENTERED")


def salvar_nota_usuario(usuario: str, nota: float):
    sheet    = client_gspread.open("notasSimulador").sheet1
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([usuario, str(nota), datahora], value_input_option="USER_ENTERED")


def extrair_nota(texto: str):
    match = re.search(r"nota\s*[:\-]?\s*(\d+(?:[.,]\d+)?)(?:\s*/?\s*10)?", texto, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*10", texto)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except:
            return None
    return None


def obter_ultimos_resumos(usuario: str, especialidade: str, n: int = 10):
    try:
        sheet   = client_gspread.open("LogsSimulador").worksheet("Pagina1")
        dados   = sheet.get_all_records()
        hist    = [l for l in dados if str(l.get("usuario", "")).strip().lower() == usuario.lower() and str(l.get("assistente", "")).lower() == especialidade.lower()]
        ultimos = hist[-n:]
        return [l.get("resumo", "")[:250] for l in ultimos if l.get("resumo", "")]  # primeiros 250 caracteres
    except Exception as e:
        st.warning(f"Erro ao obter resumos de casos anteriores: {e}")
        return []


def aguardar_fim_do_run(thread_id):
    while True:
        runs = openai.beta.threads.runs.list(thread_id=thread_id).data
        if runs and runs[0].status != "in_progress":
            break
        time.sleep(1)


def renderizar_historico():
    if not st.session_state.thread_id:
        return
    mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    for msg in sorted(mensagens, key=lambda x: x.created_at):
        conteudo = msg.content[0].text.value
        if "Iniciar nova simulação clínica" in conteudo:
            continue  # pula prompt inicial
        hora   = datetime.fromtimestamp(msg.created_at).strftime("%H:%M")
        avatar = "👨‍⚕️" if msg.role == "user" else "🧑‍⚕️"
        with st.chat_message(msg.role, avatar=avatar):
            st.markdown(conteudo)
            st.caption(f"⏰ {hora}")

# ======= TELA DE LOGIN =======
if not st.session_state.logado:
    st.title("🔐 Simulador Médico - Login")
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha   = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado  = True
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha inválidos.")
    st.stop()

# ======= ÁREA LOGADA =======
st.title("🩺 Simulador Médico Interativo com IA")
st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

col1, col2 = st.columns(2)
col1.metric("📋 Casos finalizados", contar_casos_usuario(st.session_state.usuario))
if st.session_state.media_usuario is None:
    st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
col2.metric("📊 Média global", st.session_state.media_usuario)

# --- selecionar especialidade ---
especialidade = st.radio("Especialidade:", ["PSF", "Pediatria", "Emergências"], index=0)
st.session_state["especialidade"] = especialidade  # <<< GARANTE QUE SERÁ SALVA

# mapear id do assistant
if especialidade == "Pediatria":
    assistant_id_usado = ASSISTANT_PEDIATRIA_ID
elif especialidade == "Emergências":
    assistant_id_usado = ASSISTANT_EMERGENCIAS_ID
else:
    assistant_id_usado = ASSISTANT_ID

# ======= NOVA SIMULAÇÃO =======
if st.button("➕ Nova Simulação"):
    st.session_state.historico            = ""
    st.session_state.consulta_finalizada  = False
    st.session_state.thread_id            = openai.beta.threads.create().id

    # montar prompt inicial evitando repetições
    resumos_anteriores = obter_ultimos_resumos(st.session_state.usuario, especialidade)
    contexto_resumos   = "\n\n".join(resumos_anteriores) if resumos_anteriores else "Nenhum caso anterior registrado."

    prompt_inicial_base = {
        "PSF": "Iniciar nova simulação clínica com paciente simulado em contexto de atenção primária. Forneça apenas identificação e queixa principal.",
        "Pediatria": "Iniciar nova simulação clínica pediátrica com identificação e queixa principal.",
        "Emergências": "Iniciar nova simulação de emergência clínica. Apenas identificação e queixa principal do paciente."
    }
    prompt = f"""
Considere os seguintes resumos de casos previamente utilizados pelo estudante nesta especialidade (apenas para evitar repetições):
{contexto_resumos}

{prompt_inicial_base[especialidade]}
"""

    openai.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=prompt
    )

    run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
    aguardar_fim_do_run(st.session_state.thread_id)

    mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
    for m in mensagens:
        if m.role == "assistant":
            st.session_state.historico = m.content[0].text.value
            break
    st.experimental_rerun()

# ======= CHAT / ANAMNESE =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    renderizar_historico()
    pergunta = st.chat_input("Digite sua pergunta ou conduta:")
    if pergunta:
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
        aguardar_fim_do_run(st.session_state.thread_id)
        st.experimental_rerun()

# ======= FINALIZAR CONSULTA =======
if st.session_state.thread_id and not st.session_state.consulta_finalizada:
    if st.button("✅ Finalizar Consulta"):
        mensagem_final = ("Finalizar consulta. Gere prontuário completo, feedback educacional detalhado e Nota: X/10, além das notas de etapas e justificativas.")
        openai.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=mensagem_final)
        run = openai.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id_usado)
        aguardar_fim_do_run(st.session_state.thread_id)

        mensagens = openai.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        for m in mensagens:
            if m.role == "assistant":
                resposta = m.content[0].text.value
                with st.chat_message("assistant", avatar="🧑‍⚕️"):
                    st.markdown("### 📄 Resultado Final")
                    st.markdown(resposta)
                st.session_state.consulta_finalizada = True
                registrar_caso(st.session_state.usuario, resposta)
                nota = extrair_nota(resposta)
                if nota is not None:
                    salvar_nota_usuario(st.session_state.usuario, nota)
                    st.session_state.media_usuario = calcular_media_usuario(st.session_state.usuario)
                    st.success("✅ Nota salva com sucesso!")
                break
