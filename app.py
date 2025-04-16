import streamlit as st
import gspread
import unicodedata
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from openai import OpenAI
import os
import time

# ======= CONFIG =======
client = OpenAI(api_key="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")
ASSISTANT_ID = "asst_3B1VTDFwJhCaOOdYaymPcMg0"
ASSISTANT_PEDIATRIA_ID = "asst_T8Vtb86SlVd6jKnm7A6d8adL"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
gclient = gspread.authorize(creds)

def normalizar_chave(chave):
    return ''.join((c for c in unicodedata.normalize('NFD', str(chave)) if unicodedata.category(c) != 'Mn')).lower().strip()

def validar_credenciais(usuario_input, senha_input):
    sheet = gclient.open("LoginSimulador").sheet1
    dados = sheet.get_all_records()
    for linha in dados:
        usuario = str(linha.get("usuario", "")).strip()
        senha = str(linha.get("senha", "")).strip()
        if normalizar_chave(usuario) == normalizar_chave(usuario_input) and senha == senha_input:
            return True
    return False

def contar_casos_usuario(usuario):
    try:
        sheet = gclient.open("LogsSimulador").worksheets()[0]
        dados = sheet.get_all_records()
        return sum(1 for linha in dados if normalizar_chave(str(linha.get("usuario", ""))) == normalizar_chave(usuario))
    except Exception:
        return 0

def calcular_media_usuario(usuario):
    try:
        sheet = gclient.open("notasSimulador").sheet1
        dados = sheet.get_all_records()
        notas = [float(l["nota"]) for l in dados if normalizar_chave(str(l.get("usuario", ""))) == normalizar_chave(usuario)]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except:
        return 0.0

def registrar_caso(usuario, texto):
    sheet = gclient.open("LogsSimulador").worksheets()[0]
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = [usuario, datahora, texto, "IA"]
    sheet.append_row(linha)

def salvar_nota_usuario(usuario, nota):
    sheet = gclient.open("notasSimulador").sheet1
    datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = [usuario, str(nota), datahora]
    sheet.append_row(linha, value_input_option="USER_ENTERED")

def extrair_nota(texto):
    import re
    try:
        match = re.search(r"nota\s*[:\-]?\s*(\d+(?:[\.,]\d+)?)(?:\s*/?\s*10)?", texto, re.IGNORECASE)
        if not match:
            match = re.search(r"(\d+(?:[\.,]\d+)?)\s*/\s*10", texto)
        if match:
            return float(match.group(1).replace(",", "."))
    except:
        return None

# ======= STREAMLIT =======
st.set_page_config(page_title="Simulador Médico", layout="centered")

if "logado" not in st.session_state:
    st.session_state.logado = False
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "historico" not in st.session_state:
    st.session_state.historico = ""
if "consulta_finalizada" not in st.session_state:
    st.session_state.consulta_finalizada = False

st.title("🩺 Simulador Médico Interativo")

if not st.session_state.logado:
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if validar_credenciais(usuario, senha):
                st.session_state.usuario = usuario
                st.session_state.logado = True
                st.success("✅ Login realizado com sucesso.")
            else:
                st.error("❌ Usuário ou senha inválido.")

if st.session_state.logado:
    st.markdown(f"👨‍⚕️ **Usuário:** {st.session_state.usuario}")
    col1, col2 = st.columns(2)
    col1.metric("📁 Casos Finalizados", contar_casos_usuario(st.session_state.usuario))
    col2.metric("📊 Média Global", calcular_media_usuario(st.session_state.usuario))

    especialidade = st.radio("Especialidade:", ["PSF", "Pediatria"])

    if st.button("➕ Nova Simulação"):
        assistant_id = ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID
        st.session_state.thread_id = client.beta.threads.create().id
        st.session_state.consulta_finalizada = False
        prompt_inicial = "Iniciar nova simulação clínica com paciente simulado. Apenas início da consulta com identificação e queixa principal."
        client.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt_inicial)
        run = client.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id)

        with st.spinner("Gerando paciente..."):
            while True:
                status = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                if status.status == "completed":
                    break
                time.sleep(1)

        mensagens = client.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
        for msg in mensagens:
            if msg.role == "assistant":
                st.session_state.historico = msg.content[0].text.value
                break

    if st.session_state.historico:
        st.markdown("### 👤 Paciente:")
        st.info(st.session_state.historico)

    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        pergunta = st.text_area("Digite sua pergunta ou conduta:")
        if st.button("Enviar"):
            if pergunta.strip() != "":
                client.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=pergunta)
                assistant_id = ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID
                run = client.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id)
                with st.spinner("Pensando..."):
                    while True:
                        status = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                        if status.status == "completed":
                            break
                        time.sleep(1)
                mensagens = client.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
                for msg in mensagens:
                    if msg.role == "assistant":
                        st.markdown("**Resposta do paciente:**")
                        st.success(msg.content[0].text.value)
                        break

    if st.session_state.thread_id and not st.session_state.consulta_finalizada:
        if st.button("✅ Finalizar Consulta"):
            prompt_final = (
                "Finalizar consulta. A partir do histórico da consulta, gere:\n"
                "1. O prontuário completo do paciente (título: ### Prontuário Completo do Paciente).\n"
                "2. Um feedback educacional completo para o médico.\n"
                "3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10.\n"
            )
            client.beta.threads.messages.create(thread_id=st.session_state.thread_id, role="user", content=prompt_final)
            assistant_id = ASSISTANT_PEDIATRIA_ID if especialidade == "Pediatria" else ASSISTANT_ID
            run = client.beta.threads.runs.create(thread_id=st.session_state.thread_id, assistant_id=assistant_id)

            with st.spinner("Gerando relatório..."):
                while True:
                    status = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread_id, run_id=run.id)
                    if status.status == "completed":
                        break
                    time.sleep(1)

            mensagens = client.beta.threads.messages.list(thread_id=st.session_state.thread_id).data
            for msg in mensagens:
                if msg.role == "assistant":
                    resposta = msg.content[0].text.value
                    st.markdown("### 📋 Relatório Final")
                    st.markdown(resposta)
                    registrar_caso(st.session_state.usuario, resposta)
                    nota = extrair_nota(resposta)
                    if nota is not None:
                        salvar_nota_usuario(st.session_state.usuario, nota)
                    st.session_state.consulta_finalizada = True
                    break
