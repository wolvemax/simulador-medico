import sys
import time
import os
import re
import json
import gspread
import unicodedata
import sounddevice as sd
import numpy as np
import scipy.io.wavfile
import io
import wave
import qdarkstyle
from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.QtWidgets import QListWidgetItem, QDialog, QVBoxLayout, QLabel, QListWidget, QMessageBox
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime
from PyQt5.QtCore import QTimer
from openai import OpenAI
import streamlit as st
from audio_recorder_streamlit import audio_recorder

client = OpenAI(api_key="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")
ASSISTANT_ID = "asst_3B1VTDFwJhCaOOdYaymPcMg0"
ASSISTANT_PEDIATRIA_ID = "asst_T8Vtb86SlVd6jKnm7A6d8adL"

st.title("Gravador de Áudio")

audio_bytes = audio_recorder()
if audio_bytes:
    st.audio(audio_bytes, format="audio/wav")

def remover_acentos(texto):
    return ''.join((c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn'))

def normalizar_chave(chave):
    return remover_acentos(chave.strip().lower())

def contar_casos_usuario(usuario):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("LogsSimulador").worksheets()[0]
        dados = sheet.get_all_records()
        count = sum(1 for linha in dados if normalizar_chave(str(linha.get("usuario", ""))) == normalizar_chave(usuario))
        return count
    except Exception as e:
        print(f"Erro ao contar casos: {e}")
        return 0

def calcular_media_usuario(usuario):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("notasSimulador").sheet1  # pega a primeira aba automaticamente
        dados = sheet.get_all_records()
        notas = [float(l["nota"]) for l in dados if normalizar_chave(str(l.get("usuario", ""))) == normalizar_chave(usuario)]
        return round(sum(notas) / len(notas), 2) if notas else 0.0
    except Exception as e:
        print(f"Erro ao calcular média: {e}")
        return 0.0

def salvar_nota_usuario(usuario, nota):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("notasSimulador").sheet1

        # Validação do cabeçalho
        headers = [normalizar_chave(h) for h in sheet.row_values(1)]
        if not {"usuario", "nota", "datahora"}.issubset(set(headers)):
            raise Exception("Cabeçalhos incorretos. Esperado: usuario | nota | datahora")

        # Monta linha e insere
        datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = [usuario, str(nota), datahora]
        sheet.append_row(linha, value_input_option="USER_ENTERED")
        print(f"✅ Nota {nota} salva com sucesso para {usuario}")
    except Exception as e:
        print(f"❌ Erro ao salvar nota: {type(e).__name__} - {e}")

def registrar_caso(usuario, texto):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("LogsSimulador").worksheets()[0]
        datahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linha = [usuario, datahora, texto, "IA"]
        sheet.append_row(linha)
        print(f"✅ Caso registrado no Google Sheets para {usuario}")
    except Exception as e:
        print(f"❌ Erro ao registrar no Google Sheets: {e}")

def gerar_prompt_novo_caso(usuario):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("LogsSimulador").worksheets()[0]
        dados = sheet.get_all_records()
        dados_normalizados = [
            {normalizar_chave(k): v for k, v in linha.items()} for linha in dados
        ]
        ultimos_resumos = [linha["resumo"] for linha in dados_normalizados if linha["usuario"] == usuario][-20:]
        prompt = "🧝Paciente Simulado — Simulação Médica Interativa\n"
        prompt += "Os casos abaixo são registros de simulações anteriores deste usuário. NÃO OS REPITA.\n\n"
        prompt += "📁 Casos anteriores:\n"
        for i, caso in enumerate(ultimos_resumos, 1):
            prompt += f"{i}. {caso[:300]}\n"
        prompt += "\n�ힺ Tarefa:\n"
        prompt += "Gere apenas o INÍCIO de uma nova consulta simulada com um paciente fictício.\n"
        prompt += "⚠️ A Queixa Principal (QP) deve ser completamente diferente em contexto, sintoma, ou órgão afetado.\n\n"
        prompt += "🩺 Cardiologia, Pneumologia, Gastroenterologia, Endocrinologia, Psiquiatria, Neurologia, Infectologia, Reumatologia, Geriatria, Dermatologia, Ginecologia/Obstetrícia, Ortopedia.\n\n"
        prompt += "Inclua:\n"
        prompt += "- Identificação: Nome, idade, sexo, profissão, escolaridade, estado civil, situação socioeconômica, personalidade e atitude durante a consulta\n"
        prompt += "- Queixa Principal (QP): uma queixa vaga ou inicial\n"
        prompt += "- Primeira fala do paciente (em primeira pessoa), como se estivesse na UBS/PSF\n\n"
        prompt += "❗ Aguarde as perguntas do médico antes de fornecer mais informações. NÃO continue com HDA, exames, diagnóstico ou conduta por enquanto.\n"
        return prompt
    except Exception as e:
        print(f"❌ Erro ao gerar prompt com logs: {e}")
        return "Iniciar nova simulação clínica com paciente simulado."
    


def formatar_html(mensagem): 
    mensagem = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', mensagem)
    linhas = mensagem.split("\n")
    return "<br>".join(linhas)

class WorkerThread(QtCore.QThread):
    resultado_signal = QtCore.pyqtSignal(str)

    def __init__(self, prompt, thread_id, assistant_id, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.thread_id = thread_id
        self.assistant_id = assistant_id

    def run(self):
        client.beta.threads.messages.create(thread_id=self.thread_id, role="user", content=self.prompt)
        run = client.beta.threads.runs.create(thread_id=self.thread_id, assistant_id=self.assistant_id)
        while True:
            status = client.beta.threads.runs.retrieve(thread_id=self.thread_id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)
        mensagens = client.beta.threads.messages.list(thread_id=self.thread_id).data
        for msg in mensagens:
            if msg.role == "assistant" and msg.content:
                resposta = msg.content[0].text.value
                self.resultado_signal.emit(resposta)
                return
        self.resultado_signal.emit("⚠️ A IA não retornou resposta válida.")

class Login(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(os.path.dirname(__file__), "login.ui")
        uic.loadUi(ui_path, self)
        self.pushButton_login.clicked.connect(self.fazer_login)
        self.usuario_logado = None

    def fazer_login(self):
        usuario = self.lineEdit_usuario.text().strip()
        senha = self.lineEdit_senha.text().strip()
        if validar_credenciais(usuario, senha):
            self.usuario_logado = usuario
            QMessageBox.information(
                self,
                "Bem-vindo ao Simulamax",
                "Seja bem-vindo Dr. ao Simulamax, obrigado por adquirir a ideia e fazer parte deste projeto.\n\n"
                "Este simulador de atendimento médico tem a funcionalidade de treinar o usuário e melhorar sua conduta clínica, raciocinio, escrita médica.\n\n"
                "⚠️ Ele está em fase de testes ainda.\n\n"
                "Ao usar o programa, você concorda em não divulgar, copiar ou vender qualquer parte deste programa.\n\n"
                "Obrigado e bom treinamento, Dr. \n\n"
                "© 2025 Simulamax - Todos os direitos reservados."
            )
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Erro", "Usuário ou senha inválidos.")

class Simulador(QtWidgets.QDialog):
    def __init__(self, usuario_logado):
        super().__init__()
        self.simulacao_em_andamento = False
        self.consulta_finalizada = False
        self.usuario_logado = usuario_logado
        ui_path = os.path.join(os.path.dirname(__file__), "simulador.ui")
        uic.loadUi(ui_path, self)
        self.checkBox_pediatria = self.findChild(QtWidgets.QCheckBox, "checkBox_pediatria")
        self.CheckBox_psf = self.findChild(QtWidgets.QCheckBox, "CheckBox_psf")
        print("🧪 checkBox_pediatria encontrado:", self.checkBox_pediatria is not None)
        print("🧪 CheckBox_psf encontrado:", self.CheckBox_psf is not None)
        self.pushButton_novaSimulacao.clicked.connect(self.confirmar_nova_simulacao)
        self.pushButton_finalizarConsulta.clicked.connect(self.finalizar_consulta)
        self.pushButton_enviar.clicked.connect(self.enviar_mensagem)
        self.pushButton_salvarAnamnese.clicked.connect(self.salvar_anamnese)
        self.pushButton_sairlogin.clicked.connect(self.confirmar_sair)
        self.pushButton_meuhistorico.clicked.connect(self.abrir_historico)
        self.pushButton_microfone = self.findChild(QtWidgets.QPushButton, "pushButton_microfone")
        self.label_status_microfone = self.findChild(QtWidgets.QLabel, "label_status_microfone")
        if self.label_status_microfone:
            self.label_status_microfone.setText("🛑 Não Gravando")
        if self.pushButton_microfone:
            self.gravando_audio = False
            self.pushButton_microfone.clicked.connect(self.gravar_e_transcrever_whisper)
        self.lineEdit_mensagem.setEnabled(False)
        self.pushButton_enviar.setEnabled(False)

 

        QTimer.singleShot(0, self.verificar_widget_status)

    def gravar_e_transcrever_whisper(self):
        if self.gravando_audio:
            return

        self.gravando_audio = True
        self.label_status_microfone.setText("🎙 Gravando...")

        self.fs = 16000
        self.duracao_limite = 6000 # segundos
        self.audio_buffer = []

        def callback(indata, frames, time, status):
            if self.gravando_audio:
                self.audio_buffer.append(indata.copy())

        try:
            self.stream = sd.InputStream(samplerate=self.fs, channels=1, callback=callback)
            self.stream.start()
            print("🎙️ Gravação iniciada...")
        # ⏱ Chama o stop automático após 6 segundos
            QtCore.QTimer.singleShot(self.duracao_limite, self.parar_gravacao_e_transcrever)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao iniciar gravação: {e}")        
        
    def parar_gravacao_e_transcrever(self):
        if not self.gravando_audio:
            return
        print("🛑 Parando gravação automaticamente após 6s...")
        self.gravando_audio = False
        self.stream.stop()
        self.stream.close()
        self.label_status_microfone.setText("🛑 Parado")

        audio_data = np.concatenate(self.audio_buffer, axis=0)
        audio_data = (audio_data * 32767).astype(np.int16)
        audio_wav = io.BytesIO()

        with wave.open(audio_wav, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.fs)
            wf.writeframes(audio_data.tobytes())
        audio_wav.seek(0)

        print("📤 Enviando para Whisper API...")
        try:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", audio_wav, "audio/wav"),
                language="pt"
            )
            texto = response.text.strip()
            print(f"✅ Transcrição automática: {texto}")
            self.lineEdit_mensagem.setText(texto)
        except Exception as e:
            print(f"❌ Erro na transcrição automática:\n{e}")
            self.lineEdit_mensagem.setText("[Erro na transcrição]")

    def confirmar_sair(self):
        if self.confirmar_saida():
            self.close()
            self.hide()
            login = Login()
            if login.exec_() == QtWidgets.QDialog.Accepted:
                self.__init__(login.usuario_logado)
                self.show()

    def closeEvent(self, event):
        if not self.confirmar_saida():
            event.ignore()

    def verificar_widget_status(self):
        if hasattr(self, "listWidget_status"):
            self.atualizar_status_usuario()
        else:
            print("❌ listWidget_status não encontrado na interface.")
    
    def confirmar_saida(self):
        if self.simulacao_em_andamento and not self.consulta_finalizada:
            reply = QMessageBox.question(
                self,
                "Simulação em andamento",
                "Você iniciou uma nova simulação e ainda não finalizou. Deseja sair mesmo assim?\n\n⚠️ Seu progresso será perdido.",
                QMessageBox.Yes | QMessageBox.No
        )
            return reply == QMessageBox.Yes
        return True

    def atualizar_status_usuario(self):
        try:
            self.listWidget_status.clear()
            total = contar_casos_usuario(self.usuario_logado)
            media = calcular_media_usuario(self.usuario_logado)
            self.listWidget_status.addItem(f"Usuário logado: {self.usuario_logado}")
            self.listWidget_status.addItem(f"Casos realizados: {total}")
            self.listWidget_status.addItem(f"Média global: {media}/10")
        except Exception as e:
            print(f"Erro ao atualizar status do usuário: {e}")
    
    def atualizar_status_usuario(self):
        try:
            self.listWidget_status.clear()

            total = contar_casos_usuario(self.usuario_logado)
            media = calcular_media_usuario(self.usuario_logado)

            self.listWidget_status.addItem(f"Usuário logado: {self.usuario_logado}")
            self.listWidget_status.addItem(f"Casos realizados: {total}")
            self.listWidget_status.addItem(f"Média global: {media}/10")
        except Exception as e:
            print(f"Erro ao atualizar status do usuário: {e}")
    
    def confirmar_nova_simulacao(self):
        if self.simulacao_em_andamento and not self.consulta_finalizada:
            reply = QMessageBox.question(self, "Simulação em andamento", "Deseja realmente iniciar uma nova simulação?", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.nova_simulacao()

    def nova_simulacao(self):
        # Verificação de especialidade
        if not self.checkBox_pediatria.isChecked() and not self.CheckBox_psf.isChecked():
            QMessageBox.warning(
                self,
                "Especialidade não selecionada",
                "⚠️ Por favor, selecione uma especialidade antes de iniciar a simulação."
            )
            print("❌ Nenhuma checkbox de especialidade selecionada.")
            return

    # Seleção do assistant_id com print para debug
        if self.checkBox_pediatria.isChecked():
            assistant_id_usado = ASSISTANT_PEDIATRIA_ID
            print("🩺 Checkbox PEDIATRIA selecionada. Usando ASSISTANT_PEDIATRIA_ID:", assistant_id_usado)
        elif self.CheckBox_psf.isChecked():
            assistant_id_usado = ASSISTANT_ID
            print("👨‍⚕️ Checkbox PSF selecionada. Usando ASSISTANT_ID:", assistant_id_usado)
        else:
            print("❌ Erro inesperado: nenhuma checkbox validada.")
            return

    # Inicializa a simulação normalmente
        self.thread = client.beta.threads.create()
        self.textEdit_chat.clear()
        self.simulacao_em_andamento = True
        self.consulta_finalizada = False

        self.lineEdit_mensagem.setEnabled(True)
        self.pushButton_enviar.setEnabled(True)

        prompt = gerar_prompt_novo_caso(self.usuario_logado)
        self.adicionar_mensagem("Paciente", "⏳ Pensando...")
        self.worker = WorkerThread(prompt, thread_id=self.thread.id, assistant_id=assistant_id_usado)
        self.worker.resultado_signal.connect(lambda resposta: self.adicionar_resposta_formatada("Paciente", resposta))
        self.worker.start()


    def enviar_mensagem(self):
        texto = self.lineEdit_mensagem.text().strip()
        if not texto:
            return
        
        self.adicionar_mensagem("Você", texto)
        self.lineEdit_mensagem.clear()
        self.adicionar_mensagem("Paciente", "⏳ Pensando...")
        assistant_id_usado = ASSISTANT_PEDIATRIA_ID if self.checkBox_pediatria.isChecked() else ASSISTANT_ID
        self.worker = WorkerThread(texto, thread_id=self.thread.id, assistant_id=assistant_id_usado)
        self.worker.resultado_signal.connect(lambda resposta: self.adicionar_resposta_formatada("Paciente", resposta))
        self.worker.start()

    def finalizar_consulta(self):
        if not self.thread:
            QMessageBox.information(
                self,
                "Nenhuma simulação ativa",
                "Você ainda não iniciou uma simulação.\nClique em 'Nova Simulação' antes de finalizar."
            )
            return

        if not self.simulacao_em_andamento:
            QMessageBox.information(
                self,
                "Consulta não iniciada",
                "Nenhuma simulação está em andamento para ser finalizada."
            )
            return

        if self.consulta_finalizada:
            QMessageBox.information(self, "Consulta já finalizada", "Você já finalizou esta consulta.")
            return

        self.adicionar_mensagem("Paciente", "⏳ Pensando...")
    
        assistant_id_usado = ASSISTANT_PEDIATRIA_ID if self.checkBox_pediatria.isChecked() else ASSISTANT_ID
        mensagem_final = (
            "Finalizar consulta. A partir do histórico da consulta, gere: \\n"
            "Se clicar em finalizar consulta sem ter coletado nenhum dado, dar 0.\\n"
            "1. O resumo do prontuário completo do paciente (título: ### resumo Prontuário do Paciente).\\n"
            "2. Um feedback educacional completo para o médico. Inclua:\\n"
            "  - O que o médico fez corretamente;\\n"
            "  - O que poderia ter feito melhor;\\n"
            "  - O que era esperado e não foi perguntado;\\n"
            "  - Quais seriam as perguntas ou condutas ideais para o caso;\\n"
            "  - Avaliação do raciocínio clínico, anamnese, exame físico e conduta;\\n"
            "3. Gere uma nota objetiva de 0 a 10 com base na performance do médico. Escreva obrigatoriamente no formato exato: Nota: X/10.\\n"
        )
        self.worker = WorkerThread(mensagem_final, thread_id=self.thread.id, assistant_id=assistant_id_usado)
        self.worker.resultado_signal.connect(self.processar_finalizacao)
        self.worker.start()
        self.lineEdit_mensagem.setEnabled(False)
        self.pushButton_enviar.setEnabled(False)

    def adicionar_mensagem(self, autor, mensagem):
        cor = "#007bff" if autor.lower() in ["você", "voce"] else "#dc3545"
        self.textEdit_chat.append(f"<span style='color:{cor};'><b>{autor}:</b></span><br>{mensagem}<br>")

    def adicionar_resposta_formatada(self, autor, resposta):
        self.textEdit_chat.undo()
        resposta_formatada = formatar_html(resposta)
        self.adicionar_mensagem(autor, resposta_formatada)

    def processar_finalizacao(self, resposta):
        self.textEdit_chat.undo()
        resposta_formatada = formatar_html(resposta)
        self.adicionar_mensagem("Paciente", resposta_formatada)
        prontuario = self.extrair_prontuario(resposta)
        nota = self.extrair_nota(resposta)
        self.simulacao_em_andamento = False  # ✅ Marcar como finalizada
        self.consulta_finalizada = True

        if prontuario:
            registrar_caso(self.usuario_logado, prontuario)
        else:
            registrar_caso(self.usuario_logado, resposta)

        if nota is not None and isinstance(nota, (int, float)):
            salvar_nota_usuario(self.usuario_logado, nota)
            media = calcular_media_usuario(self.usuario_logado)
            self.textEdit_chat.append(
            f"<span style='color:green;'><b>📝 Avaliação Final:</b></span><br>"
            f"Sua nota nesta consulta foi <b>{nota}/10</b>.<br>"
            f"Média geral das suas simulações até agora: <b>{media}/10</b><br><br>"
        )
        else:
            self.textEdit_chat.append(
                "<span style='color:red;'><b>⚠️ Não foi possível extrair a nota da resposta da IA.</b></span><br>"
        )

        self.atualizar_status_usuario()

    def extrair_prontuario(self, texto):
        match = re.search(r"### Prontuário Completo do Paciente:(.*?)### Feedback Educacional", texto, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def extrair_nota(self, texto):
        try:
        # Primeiro tenta extrair "Nota: X/10" ou "Nota - X"
            match = re.search(r"nota\s*[:\-]?\s*(\d+(?:[\.,]\d+)?)(?:\s*/?\s*10)?", texto, re.IGNORECASE)
            if not match:
                # Se não encontrar "nota", tenta pegar apenas número com /10 (ex: "6.5/10")
                match = re.search(r"(\d+(?:[\.,]\d+)?)\s*/\s*10", texto)
            if match:
                nota_str = match.group(1).replace(",", ".")
                return float(nota_str)
        except Exception as e:
            print(f"Erro ao extrair nota: {e}")
        return None

    def abrir_historico(self):
        self.hist_win = HistoricoWindow(self.usuario_logado)
        self.hist_win.exec_()

    def salvar_anamnese(self):
        texto = self.textEdit_anamnese.toPlainText().strip()
        if not texto:
            QMessageBox.information(self, "Aviso", "Anamnese vazia. Escreva algo antes de salvar.")
            return

        try:
            nome_arquivo = f"logs/anamnese_{self.usuario_logado}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            os.makedirs("logs", exist_ok=True)
            with open(nome_arquivo, "w", encoding="utf-8") as f:
                f.write(texto)
            QMessageBox.information(self, "Sucesso", f"Anamnese salva em {nome_arquivo}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao salvar anamnese: {e}")    

class HistoricoWindow(QDialog):
    def __init__(self, usuario):
        super().__init__()
        self.setWindowTitle("Histórico de Casos")
        self.resize(600, 400)
        layout = QVBoxLayout()
        self.label = QLabel(f"Histórico do usuário: {usuario}")
        layout.addWidget(self.label)
        self.lista = QListWidget()
        layout.addWidget(self.lista)
        self.setLayout(layout)
        self.carregar_historico(usuario)

    def carregar_historico(self, usuario):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
            creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
            client = gspread.authorize(creds)
            sheet = client.open("LogsSimulador").worksheets()[0]
            dados = sheet.get_all_records()
            for linha in dados:
                if normalizar_chave(str(linha.get("usuario", ""))) == normalizar_chave(usuario):
                    resumo = linha.get("resumo", "[Sem resumo]")
                    data = linha.get("datahora", "")
                    item = QListWidgetItem(f"{data} - {resumo[:120]}...")
                    self.lista.addItem(item)
        except Exception as e:
            self.lista.addItem(f"Erro ao carregar histórico: {e}")

def validar_credenciais(usuario, senha):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    cred_path = os.path.join(os.path.dirname(__file__), "credenciais.json")
    creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scope)
    client = gspread.authorize(creds)
    sheet = client.open("LoginSimulador").sheet1
    dados = sheet.get_all_records()
    for linha in dados:
        linha_normalizada = {normalizar_chave(k): v.strip() for k, v in linha.items()}
        if linha_normalizada.get("usuario") == usuario and linha_normalizada.get("senha") == senha:
            return True
    return False

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    login = Login()
    if login.exec_() == QtWidgets.QDialog.Accepted:
        window = Simulador(login.usuario_logado)
        window.show()
        sys.exit(app.exec_())
