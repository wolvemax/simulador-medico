# ======= VISUAL E ESTILO PERSONALIZADO PARA O SIMULADOR MÉDICO =======
import streamlit as st
import base64

# ⚙️ Configuração da Página
st.set_page_config(
    page_title="Simulador Médico IA",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get Help": "https://github.com/seu-repo",
        "Report a bug": "https://github.com/seu-repo/issues",
        "About": "Simulador de Atendimento Médico com IA treinado em diretrizes clínicas brasileiras."
    }
)

# 🎨 CSS Customizado
st.markdown(
    """
    <style>
    .main-title {
        font-size: 38px;
        font-weight: bold;
        color: #003366;
        margin-bottom: 1rem;
    }
    .stButton > button {
        background-color: #003366;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        padding: 0.5em 1em;
    }
    .stTextInput > div > input, .stTextArea > div > textarea {
        border-radius: 6px;
        border: 1px solid #ccc;
    }
    .metric-box {
        background-color: #f7f9fc;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
    .sidebar-img {
        width: 100%;
        border-radius: 20px;
        margin-bottom: 1.5rem;
        box-shadow: 0 0 10px rgba(0, 102, 204, 0.4);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 🔧 Função utilitária para carregar imagem e converter em base64
def img_to_base64(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception as e:
        return None

# 🧠 Exibição da imagem no sidebar (avatar do sistema ou logo institucional)
avatar_path = "imgs/simulador_avatar.png"  # substitua por caminho real
img_base64 = img_to_base64(avatar_path)
if img_base64:
    st.sidebar.markdown(
        f'<img src="data:image/png;base64,{img_base64}" class="sidebar-img">',
        unsafe_allow_html=True
    )

# 📑 Instruções ou Modo
modo = st.sidebar.radio("Modo de operação:", ["Simulação Clínica", "Histórico", "Sobre o Projeto"])

if modo == "Sobre o Projeto":
    st.sidebar.info("""
        Este simulador é voltado ao treinamento médico em ambiente virtual interativo, com apoio de IA generativa.

        Criado por: [Seu Nome]
    """)

# ✅ Título Estilizado
st.markdown('<div class="main-title">🩺 Simulador Médico Interativo com IA</div>', unsafe_allow_html=True)

# 🧾 Caixa de texto explicativa
st.markdown("""
Desenvolvido para simular atendimentos clínicos em tempo real. Inclui pontuação automática, prontuário e feedback ao final de cada simulação.

- Baseado em guidelines médicas.
- Funciona com **modelos da OpenAI (GPT Assistants)**.
- Armazena desempenho e histórico do usuário via **Google Sheets**.
""")

# Exemplo de layout dividido
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
    st.metric("Casos Finalizados", "🔄 Aguarde")
    st.markdown("</div>", unsafe_allow_html=True)
with col2:
    st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
    st.metric("Média Global", "📊 Calculando")
    st.markdown("</div>", unsafe_allow_html=True)
with col3:
    st.markdown("<div class='metric-box'>", unsafe_allow_html=True)
    st.metric("Simulações Hoje", "🕒 Atualizando")
    st.markdown("</div>", unsafe_allow_html=True)

# 🔄 Aviso condicional para login ou ações
if "logado" not in st.session_state or not st.session_state.logado:
    st.warning("Faça login para iniciar uma nova simulação médica.")
