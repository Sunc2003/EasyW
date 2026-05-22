import streamlit as st
import requests
import json
import pandas as pd
import pdfplumber
import io
from datetime import datetime

# --- CONFIGURACIÓN DE INFRAESTRUCTURA ---
IA_SERVER_URL = "http://192.168.1.18:1234/v1/chat/completions"
API_SAP_URL = "http://192.168.0.26:3000"
MODEL_ID = "nemotron-3-nano-omni-30b-a3b-reasoning"

# Credenciales SAP
USER_SAP = "Marsella"
PASS_SAP = "marsella.2026"

st.set_page_config(
    page_title="Marsella IA - Gestión & Extracción",
    page_icon="🤖",
    layout="wide"
)

class SapAgent:
    def __init__(self):
        if "token" not in st.session_state:
            st.session_state.token = None

    def login(self):
        try:
            base_url = API_SAP_URL.rstrip('/')
            response = requests.post(
                f"{base_url}/token",
                data={"username": USER_SAP, "password": PASS_SAP},
                timeout=15
            )
            if response.status_code == 200:
                st.session_state.token = response.json()["access_token"]
                return True
            return False
        except Exception as e:
            st.error(f"⚠️ Error de conexión SAP: {e}")
            return False

    def consultar_sap(self, endpoint):
        if not st.session_state.token:
            if not self.login(): return {"error": "Autenticación fallida"}
        
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        try:
            url = f"{API_SAP_URL.rstrip('/')}{endpoint}"
            res = requests.get(url, headers=headers, timeout=45)
            if res.status_code == 401:
                if self.login():
                    headers = {"Authorization": f"Bearer {st.session_state.token}"}
                    res = requests.get(url, headers=headers, timeout=45)
            return res.json()
        except Exception as e:
            return {"error": f"Fallo en consulta: {str(e)}"}

# --- FUNCIONES DE DOCUMENTOS ---
def extraer_texto_pdf(uploaded_file):
    """Extrae texto manteniendo una estructura legible para la IA"""
    texto_acumulado = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for i, pagina in enumerate(pdf.pages):
            texto_acumulado += f"\n--- PÁGINA {i+1} ---\n"
            texto_acumulado += pagina.extract_text()
    return texto_acumulado

# --- INTERFAZ ---
st.sidebar.title("🏢 Ferretería Marsella")
st.sidebar.info("Panel de Control IA conectado a SAP HANA")

# Sección de Carga de Archivos
st.sidebar.markdown("---")
st.sidebar.subheader("📂 Extracción de Documentos")
archivo_pdf = st.sidebar.file_uploader("Subir Factura/Proforma (PDF)", type=["pdf"])

if st.sidebar.button("🧹 Limpiar Historial"):
    st.session_state.messages = []
    st.rerun()

st.title("🦾 Asistente de Operaciones Senior")
st.caption(f"Inteligencia Artificial Nemotron 30B | Chile, {datetime.now().strftime('%d/%m/%Y')}")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ej: Extrae los items de la factura en formato Excel"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("🧠 Procesando requerimiento..."):
        # LÓGICA DE DETECCIÓN: ¿Es una extracción de PDF o una consulta a SAP?
        if archivo_pdf:
            # CASO A: EXTRACCIÓN DE DATOS DE PDF
            texto_pdf = extraer_texto_pdf(archivo_pdf)
            
            prompt_extraccion = f"""
            Eres el Analista de Datos de Ferretería Marsella. Tu objetivo es extraer información precisa de documentos PDF.
            
            CONTENIDO DEL DOCUMENTO:
            {texto_pdf}
            
            SOLICITUD DEL USUARIO:
            {prompt}
            
            REGLAS DE FORMATO (ESTRICTAS):
            1. Si el usuario pide datos para Excel, responde ÚNICAMENTE con un bloque de código en formato TSV (Tab-Separated Values).
            2. Las columnas deben estar separadas por TABULACIONES, no comas. Esto permite pegar directo en Excel.
            3. Usa coma (,) para los decimales en precios y puntos (.) para miles si es necesario.
            4. No añadas introducciones ni conclusiones. Solo el bloque de código con los datos.
            """
            
            try:
                res_ia = requests.post(IA_SERVER_URL, json={
                    "model": MODEL_ID,
                    "messages": [{"role": "system", "content": prompt_extraccion}],
                    "temperature": 0
                }, timeout=1000).json()
                
                respuesta = res_ia['choices'][0]['message']['content']
                
                with st.chat_message("assistant"):
                    st.markdown("### 📋 Datos Extraídos (Listos para copiar y pegar en Excel)")
                    st.code(respuesta, language="text")
                    st.info("💡 Tip: Haz clic en el icono de copiar del bloque de arriba y pégalo directamente en una celda de Excel.")
                    st.session_state.messages.append({"role": "assistant", "content": f"Datos extraídos del PDF:\n\n{respuesta}"})
            except Exception as e:
                st.error(f"Error procesando el PDF: {e}")

        else:
            # CASO B: CONSULTA SAP (Tu lógica original mejorada)
            agent = SapAgent()
            # ... (Aquí va tu bloque de routing_prompt y herramientas que ya tenías) ...
            # [Se mantiene tu lógica de routing y consulta de endpoints]
            # ...
            st.warning("No has subido un PDF. Si deseas extraer datos, cárgalo en la barra lateral.")