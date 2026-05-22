import streamlit as st
import pandas as pd
import tempfile
import streamlit.components.v1 as components
import uuid
import os
import time
import requests
import zipfile
import json
from io import BytesIO
import re
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import quote
from generador import generar_ficha, generar_documento
from utils_pdf import procesar_pdf_a_imagenes, unir_imagenes_verticalmente

# =========================================================
# 1. CONFIGURACIÓN INICIAL Y BASE DE DATOS LOCAL
# =========================================================
st.set_page_config(page_title="Herramientas Marsella", layout="wide")

CARPETA_LOGOS = "Logos"
os.makedirs(CARPETA_LOGOS, exist_ok=True)
DB_FILE = "base_productos.json"
CARPETA_FOTOS = "imagenes_productos"
os.makedirs("salidas", exist_ok=True)
os.makedirs(CARPETA_FOTOS, exist_ok=True)

def cargar_base_datos():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def guardar_en_base_datos(lista):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=4)

# --- INICIALIZACIÓN DE ESTADOS DE SESIÓN (Solución a AttributeError) ---
if 'lista_productos' not in st.session_state:
    st.session_state.lista_productos = cargar_base_datos()

if 'df_central' not in st.session_state:
    st.session_state.df_central = pd.DataFrame({"Código": [""] * 15, "URL Encontrada": [""] * 15})

if "logo_auto_path" not in st.session_state:
    st.session_state.logo_auto_path = None
    
if 'df_ohiggins' not in st.session_state:
    st.session_state.df_ohiggins = pd.DataFrame({"SKU": [""] * 15, "BÚSQUEDA": [""] * 15})

if "preview_image" not in st.session_state:
    st.session_state.preview_image = None

if "foto_local_path" not in st.session_state:
    st.session_state.foto_local_path = None

if 'idx_creacion' not in st.session_state:
    st.session_state.idx_creacion = 0

# =========================================================
# 2. FUNCIONES LÓGICAS Y CALLBACKS
# =========================================================
def buscar_y_rellenar():
    sku_b = st.session_state.sku_input_manual.strip()
    if "logo_auto_path" not in st.session_state:
        st.session_state.logo_auto_path = None
    if sku_b and st.session_state.lista_productos:
        encontrado = next((p for p in st.session_state.lista_productos if p.get('sku') == sku_b), None)
        if encontrado:
            st.session_state.nombre_auto_field = encontrado.get('nombre', "")
            st.session_state.specs_auto_field = encontrado.get('specs_solo', "")
            marca = encontrado.get('marca', "")
            
            # --- BÚSQUEDA DE LOGO AUTOMÁTICO ---
            logo_encontrado = None
            if marca:
                extensiones = [".png", ".jpg", ".jpeg", ".webp", ".PNG", ".JPG", ".JPEG"]
                for ext in extensiones:
                    ruta_logo = os.path.join(CARPETA_LOGOS, f"{marca}{ext}")
                    if os.path.isfile(ruta_logo):
                        logo_encontrado = ruta_logo
                        break
                # Si no exacto, buscar sin distinguir mayúsculas
                if not logo_encontrado:
                    for f in os.listdir(CARPETA_LOGOS):
                        nombre_sin_ext = os.path.splitext(f)[0]
                        if nombre_sin_ext.lower() == marca.lower():
                            logo_encontrado = os.path.join(CARPETA_LOGOS, f)
                            break
            st.session_state.logo_auto_path = logo_encontrado
            
            # --- BÚSQUEDA DE FOTO DEL PRODUCTO (existente) ---
            # (código actual de búsqueda en CARPETA_FOTOS)
            foto_encontrada = None
            extensiones_img = [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]
            nombres_a_buscar = [sku_b, f"{sku_b}_A", f"{sku_b}_1"]
            for root, dirs, files in os.walk(CARPETA_FOTOS):
                for nombre_base in nombres_a_buscar:
                    for ext in extensiones_img:
                        archivo_objetivo = f"{nombre_base}{ext}"
                        if archivo_objetivo in files:
                            foto_encontrada = os.path.join(root, archivo_objetivo)
                            break
                    if foto_encontrada: break
                if foto_encontrada: break
            if not foto_encontrada:
                for root, dirs, files in os.walk(CARPETA_FOTOS):
                    for f in files:
                        if f.startswith(sku_b) and f.lower().endswith(tuple(extensiones_img)):
                            foto_encontrada = os.path.join(root, f)
                            break
                    if foto_encontrada: break
            
            st.session_state.foto_local_path = foto_encontrada
            
            if logo_encontrado:
                st.toast(f"✅ Datos cargados. Logo: {os.path.basename(logo_encontrado)}")
            else:
                st.toast(f"✨ Datos cargados (Logo no encontrado para marca '{marca}')")

# =========================================================
# FUNCIONES DE INTERFAZ (Definir fuera de los tabs)
# =========================================================
def cuadro_copiado_vtex(titulo, contenido, height=350, font_size="16px"):
    if contenido:
        st.subheader(titulo)
        id_unico = f"copy-{uuid.uuid4().hex}"
        html_code = f"""
        <div id="{id_unico}" style="background-color:#f0f2f6; padding:15px; border-radius:10px; border:1px solid #d1d5db; cursor:pointer; font-family:Arial; font-size:{font_size}; white-space:pre-wrap; color:#31333F; line-height:1.5;" 
           onclick="copyToVtex('{id_unico}')">
{contenido}
        </div>
        <script>
        function copyToVtex(elementId) {{
            const text = document.getElementById(elementId).innerText.trim();
            const htmlFormat = `<span style="font-size: 16px; font-family: Arial;">${{text.replace(/\\n/g, '<br>')}}</span>`;
            const blobHtml = new Blob([htmlFormat], {{ type: 'text/html' }});
            const blobText = new Blob([text], {{ type: 'text/plain' }});
            const data = [new ClipboardItem({{ 'text/html': blobHtml, 'text/plain': blobText }})];
            navigator.clipboard.write(data).then(() => {{
                const el = document.getElementById(elementId);
                el.style.backgroundColor = "#c6f6d5"; 
                setTimeout(() => {{ el.style.backgroundColor = "#f0f2f6"; }}, 500);
            }});
        }}
        </script>
        """
        components.html(html_code, height=height, scrolling=True)
        
        
        
def boton_copiar_texto(texto: str, label="📋 Copiar nombre"):
    btn_id = f"btn-{uuid.uuid4().hex}"
    html = f"""
    <button id="{btn_id}" style="padding:8px 14px; background:#f04; color:white; border:none; border-radius:6px; cursor:pointer;">{label}</button>
    <script>
        document.getElementById("{btn_id}").addEventListener("click", () => {{
            navigator.clipboard.writeText("{texto}");
            document.getElementById("{btn_id}").innerText = "✅ Copiado";
            setTimeout(() => document.getElementById("{btn_id}").innerText = "{label}", 1500);
        }});
    </script>
    """
    components.html(html, height=50)

def parse_specs(raw_text):
    lineas = [l.strip() for l in raw_text.strip().split('\n') if l.strip()]
    if not lineas: return {}
    if lineas[0].count(':') > 1: return [linea.split(':') for linea in lineas]
    specs_dict = {}
    for linea in lineas:
        if ':' in linea:
            clave, valor = linea.split(':', 1)
            specs_dict[clave.strip()] = valor.strip()
    return specs_dict

def obtener_urls_v18(lista_codigos):
    total_filas = len(lista_codigos)
    urls_finales = [""] * total_filas
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.page_load_strategy = 'eager' 
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except: return ["ERROR DRIVER"] * total_filas
    barra = st.progress(0)
    estado = st.empty()
    try:
        for i, codigo in enumerate(lista_codigos):
            codigo_str = str(codigo).strip()
            barra.progress((i + 1) / total_filas)
            if not codigo_str or codigo_str.lower() in ["nan", "none"]: continue
            estado.text(f"🔎 Buscando: {codigo_str}")
            try:
                driver.get(f"https://www.ferreteriamarsella.cl/{codigo_str}")
                time.sleep(2)
                current_url = driver.current_url
                if "/p" in current_url: urls_finales[i] = current_url
                else: urls_finales[i] = "NO ENCONTRADO"
            except: urls_finales[i] = "ERROR TÉCNICO"
    finally:
        driver.quit()
        barra.empty()
        estado.empty()
    return urls_finales


import numpy as np
from PIL import Image

def ajustar_imagen_producto(ruta_o_bytes, threshold=10):
    """
    Realiza un recorte automático (Auto-Trim) de la imagen eliminando 
    espacios en blanco o transparentes innecesarios.
    """
    # Cargar imagen y asegurar modo RGBA
    img = Image.open(ruta_o_bytes).convert("RGBA")
    data = np.array(img)
    
    # Extraer canales
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    
    # Detectar el color de fondo (esquina superior izquierda)
    bg_r, bg_g, bg_b = r[0,0], g[0,0], b[0,0]
    
    # Calcular diferencia de color respecto al fondo
    diff = np.abs(r - bg_r) + np.abs(g - bg_g) + np.abs(b - bg_b)
    
    # Definir qué es 'fondo' (Transparencia baja O color similar al fondo)
    # Equivalente a la lógica de tu JS
    is_background = (a < 50) | (diff < threshold)
    
    # Invertir para encontrar el contenido
    is_content = ~is_background
    
    # Encontrar las coordenadas del contenido
    if not np.any(is_content):
        return img # No se detectó contenido, devolver original
        
    coords = np.argwhere(is_content)
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    
    # Recortar (añadiendo un margen de seguridad de 1px como en tu JS)
    img_res = img.crop((
        max(0, x0 - 1), 
        max(0, y0 - 1), 
        min(img.width, x1 + 1), 
        min(img.height, y1 + 1)
    ))
    
    return img_res


st.title("🛠️ Herramientas")

tab_fichas, tab_creacion, tab_CatalogoVtex, tab_masivo, tab_cms, tab_creacionvtex, tab_robot, tab_ohiggins, tab_pdf, tab_marsellitta, tab_ohiggins2, tab_ohiggins20= st.tabs([
    "Fichas Tecnicas", 
    "Productos",
    "Buscador Vtex",
    "Generacion masiva",
    "Carga de fichas tecnicas",
    "Sincronizacion con Vtex",
    "Descarga Imagen ohiggins",
    "URL Web Marsella", 
    "PDF a JPG", 
    "Imagen Producto Marsella",
    "Fichas Tecnicas O'Higgins",
    "Fichas Tecnicas O'Higgins Mitutoyo "
])

# =========================================================
# 3. Funcion auxiliar

# =========================================================

from PIL import Image, ImageOps

def procesar_imagen_estilo_illustrator(contenido_imagen, target_height=597, canvas_size=(800, 800)):
    """
    Toma los bytes de una imagen, la redimensiona a 597px de alto 
    manteniendo proporción y la centra en un lienzo blanco.
    """
    img = Image.open(BytesIO(contenido_imagen))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # 1. Calcular redimensión (Height = 597)
    w_percent = (target_height / float(img.size[1]))
    target_width = int((float(img.size[0]) * float(w_percent)))
    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    # 2. Crear lienzo blanco (como la mesa de trabajo)
    # Puedes ajustar (800, 800) al tamaño de tus mesas de trabajo habituales
    canvas = Image.new('RGB', canvas_size, (255, 255, 255))
    
    # 3. Calcular posición para centrar
    offset = ((canvas_size[0] - target_width) // 2, (canvas_size[1] - target_height) // 2)
    canvas.paste(img_resized, offset)
    
    # 4. Devolver bytes
    buf = BytesIO()
    canvas.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

# ---------------------------------------------------------
# PESTAÑA 1: GENERADOR DE FICHAS TÉCNICAS
# ---------------------------------------------------------

with tab_fichas:
    col_f1, col_f2 = st.columns([1.2, 1.8])
    
    with col_f1:
        st.subheader("Datos del Producto")
        sku_f = st.text_input("Ingresa SKU y presiona Enter:", key="sku_input_manual", on_change=buscar_y_rellenar)
        st.divider()
        
        nombre_f = st.text_input("Nombre del producto *", key="nombre_auto_field")
        
        # --- SECCIÓN DE FOTO ---
        foto_f = st.file_uploader("📸 Subir foto manualmente", type=["jpg", "png", "webp"], key="foto_f")
        ruta_auto = st.session_state.get("foto_local_path")
        
        if ruta_auto and not foto_f:
            st.success(f"🖼️ Foto detectada: `{os.path.basename(ruta_auto)}`")
            st.image(ruta_auto, width=150)
        
        # --- SECCIÓN DE LOGO ---
        logo_f = st.file_uploader("🏷 Logo marca *", type=["jpg", "png"], key="logo_f")
        ruta_logo_auto_mostrar = st.session_state.get("logo_auto_path")
        
        if ruta_logo_auto_mostrar and not logo_f:
            st.success(f"🏷️ Logo detectado para la marca: `{os.path.basename(ruta_logo_auto_mostrar)}`")
            st.image(ruta_logo_auto_mostrar, width=100)
            
        specs_f = st.text_area("Especificaciones *", height=250, key="specs_auto_field")
        
        # --- BOTÓN DE ACCIÓN ---
        if st.button("📄 Generar Ficha Técnica", use_container_width=True, type="primary"):
            sku_actual = st.session_state.get("sku_input_manual", "").strip()
            
            # 1. Definir la ruta de la foto original (manual o automática)
            foto_final_path = None
            if foto_f:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    tf.write(foto_f.read())
                    foto_final_path = tf.name
            elif ruta_auto:
                foto_final_path = ruta_auto
            
            # 2. Definir ruta del logo
            ruta_logo_auto = st.session_state.get("logo_auto_path")
            logo_path = None
            if logo_f:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tl:
                    tl.write(logo_f.read())
                    logo_path = tl.name
            elif ruta_logo_auto:
                logo_path = ruta_logo_auto
            
            # 3. Validación y Procesamiento
            if nombre_f and sku_actual and foto_final_path and logo_path and specs_f:
                try:
                    # --- MEJORA: AJUSTE INTELIGENTE DE IMAGEN (AUTO-TRIM) ---
                    with st.spinner("Ajustando imagen del producto..."):
                        # Aplicamos la lógica de recorte de píxeles antes de generar
                        imagen_procesada = ajustar_imagen_producto(foto_final_path, threshold=10)
                        
                        # Guardamos la imagen recortada en un temporal para enviarla al generador
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                            imagen_procesada.save(tmp_img.name, format="PNG")
                            foto_para_ficha = tmp_img.name
                    
                    # --- GENERACIÓN DEL DOCUMENTO ---
                    specs_parsed = parse_specs(specs_f)
                    out = generar_documento(
                        nombre=nombre_f,
                        datos=specs_parsed,
                        sku=sku_actual,
                        foto_producto=foto_para_ficha, # <--- Usamos la foto ya ajustada
                        logo_marca=logo_path,
                        skus_matriz=sku_actual
                    )
                    
                    # Guardar y actualizar vista previa
                    ruta_salida = os.path.join("salidas", f"FT-{sku_actual}.jpg")
                    os.replace(out, ruta_salida)
                    st.session_state.preview_image = ruta_salida
                    st.success("✅ Ficha Técnica generada y ajustada con éxito")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error durante el proceso: {str(e)}")
            else:
                st.error("Faltan datos obligatorios (nombre, SKU, foto, logo, especificaciones).")
    
    with col_f2:
        st.subheader("Vista Previa")
        if st.session_state.get("preview_image") and os.path.exists(st.session_state.preview_image):
            st.image(st.session_state.preview_image, use_container_width=True)
            
            nombre_archivo_ft = os.path.basename(st.session_state.preview_image)
            
            # Utilidad de copia y descarga
            c1, c2 = st.columns(2)
            with c1:
                boton_copiar_texto(nombre_archivo_ft, label=f"📋 Copiar nombre")
            with c2:
                with open(st.session_state.preview_image, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Ficha", 
                        f, 
                        file_name=nombre_archivo_ft, 
                        mime="image/jpeg",
                        use_container_width=True
                    )
        else:
            st.info("Ingresa un SKU y genera la ficha para ver la vista previa aquí.")
# ---------------------------------------------------------
# PESTAÑA 2: UTILIDADES PDF (Optimizado)
# ---------------------------------------------------------
with tab_pdf: 
    st.header("Convertidor de PDF")
    
    uploaded_file = st.file_uploader("Sube tu archivo PDF", type=["pdf"], key="pdf_main")

    if uploaded_file:
        # 1. PROCESAMIENTO Y CACHE
        @st.cache_data
        def obtener_imagenes(file_bytes):
            # Aquí va tu función original: procesar_pdf_a_imagenes(file_bytes)
            # Retorna lista de objetos PIL.Image
            return procesar_pdf_a_imagenes(file_bytes) 

        with st.spinner("Leyendo PDF..."):
            # Nota: Asegúrate de que procesar_pdf_a_imagenes esté definida en tu script
            imagenes = obtener_imagenes(uploaded_file.getvalue())

        # 2. LÓGICA DE SELECCIÓN (Checkboxes)
        st.subheader("Selección de Páginas")
        
        # Botones de selección masiva
        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
        if col_btn1.button("✅ Seleccionar Todo"):
            for i in range(len(imagenes)):
                st.session_state[f"sel_{i}"] = True
            st.rerun()
        
        if col_btn2.button("❌ Desmarcar Todo"):
            for i in range(len(imagenes)):
                st.session_state[f"sel_{i}"] = False
            st.rerun()

        # Grid de visualización
        paginas_seleccionadas = []
        with st.expander(f"👀 Vista previa ({len(imagenes)} páginas)", expanded=True):
            cols = st.columns(5)
            for i, img in enumerate(imagenes):
                with cols[i % 5]:
                    st.image(img, caption=f"Pág {i+1}", use_container_width=True)
                    # El estado se guarda en session_state para persistencia
                    if st.checkbox("Incluir", key=f"sel_{i}", value=True):
                        paginas_seleccionadas.append(i)

        st.divider()

        # 3. CONFIGURACIÓN DE DESCARGA
        c_datos, c_accion = st.columns([1, 2], gap="large")

        with c_datos:
            st.subheader("1. Identificación")
            sku_pdf = st.text_input("Ingresa SKU:", placeholder="Ej: 340635").strip()
            nombre_base = f"FT-{sku_pdf}" if sku_pdf else "FT-SinSKU"
            
            modo = st.radio("Formato de salida:", ["Hoja Única", "Imagen Larga"], horizontal=False)

        with c_accion:
            st.subheader("2. Procesar y Descargar")
            
            if not sku_pdf:
                st.warning("Escribe el SKU para habilitar la descarga.")
            
            elif modo == "Hoja Única":
                c_sel, c_btn = st.columns([1, 2])
                num = c_sel.number_input("Pág:", min_value=1, max_value=len(imagenes), value=1)
                
                buf = BytesIO()
                imagenes[num-1].convert("RGB").save(buf, format="JPEG", quality=95)
                
                c_btn.write("###")
                c_btn.download_button(
                    label=f"⬇️ Descargar Página {num}",
                    data=buf.getvalue(),
                    file_name=f"{nombre_base}_p{num}.jpg",
                    mime="image/jpeg",
                    type="primary",
                    use_container_width=True
                )

            elif modo == "Imagen Larga":
                if not paginas_seleccionadas:
                    st.error("⚠️ No has seleccionado ninguna página arriba.")
                else:
                    with st.spinner("Uniendo imágenes..."):
                        # Filtrar solo las seleccionadas en el orden original
                        img_final = unir_imagenes_verticalmente([imagenes[idx] for idx in paginas_seleccionadas])
                        
                        buf = BytesIO()
                        img_final.convert("RGB").save(buf, format="JPEG", quality=85)
                        
                        st.download_button(
                            label=f"⬇️ Descargar Imagen Larga ({len(paginas_seleccionadas)} págs)",
                            data=buf.getvalue(),
                            file_name=f"{nombre_base}.jpg",
                            mime="image/jpeg",
                            type="primary",
                            use_container_width=True
                        )



# ---------------------------------------------------------
# PESTAÑA 3: ROBOT URL
# ---------------------------------------------------------
with tab_robot:
    st.header("Extractor de URL")
    st.markdown("Pega los códigos y buscará los enlaces en ferreteriamarsella.cl")

    cambios_usuario = st.data_editor(
        st.session_state.df_central,
        num_rows="dynamic",
        height=400,
        use_container_width=True,
        key="editor_principal",
        column_config={
            "Código": st.column_config.TextColumn("Código (Pegar aquí)", required=True),
            "URL Encontrada": st.column_config.LinkColumn("Resultado", max_chars=100)
        }
    )

    col1, col2 = st.columns([1, 4])

    with col1:
        if st.button("INICIAR", type="primary", use_container_width=True):
            df_trabajo = cambios_usuario.copy()
            lista_completa = df_trabajo["Código"].tolist()
            codigos_reales = [c for c in lista_completa if str(c).strip() != ""]
            
            if len(codigos_reales) > 0:
                st.toast(f"Detectados {len(codigos_reales)} códigos. Iniciando...")
                urls_obtenidas = obtener_urls_v18(lista_completa)
                df_trabajo["URL Encontrada"] = urls_obtenidas
                st.session_state.df_central = df_trabajo
                st.rerun()
            else:
                st.warning("La tabla parece vacía.")

    with col2:
        if st.button("Limpiar Tabla", key="limpiar_tab3"):
            st.session_state.df_central = pd.DataFrame({"Código": [""] * 15, "URL Encontrada": [""] * 15})
            st.rerun()

# ---------------------------------------------------------
# PESTAÑA 4: ROBOT O'HIGGINS (Para descargar fichas tecnicas de ohiggins)
# ---------------------------------------------------------
with tab_ohiggins:
    st.header("Descarga Masiva de Fichas (O'Higgins)")
    st.markdown("""
    1. Pega tu lista de SKUs.
    2. Descarga **todas las hojas del PDF unidas** en una imagen vertical.
    """)

    # --- INICIALIZAR ESTADO DE TABLA ---
    if 'df_ohiggins_sku' not in st.session_state:
        st.session_state.df_ohiggins_sku = pd.DataFrame({"SKU": [""] * 15})

    # --- TABLA EDITABLE ---
    editor_ohiggins = st.data_editor(
        st.session_state.df_ohiggins_sku,
        num_rows="dynamic",
        height=400,
        use_container_width=True,
        key="editor_ohiggins_sku_widget",
        column_config={
            "SKU": st.column_config.TextColumn("Listado de SKUs", required=True)
        }
    )

    c_btn1, c_btn2 = st.columns([1, 4])

    with c_btn1:
        if st.button("INICIAR POR SKU", type="primary", use_container_width=True):
            
            # Filtramos filas vacías
            df_trabajo = editor_ohiggins.copy()
            df_trabajo = df_trabajo[df_trabajo["SKU"].astype(str).str.strip() != ""]

            if len(df_trabajo) == 0:
                st.warning("La tabla está vacía.")
            else:
                resultados_zip = BytesIO()
                log_errores = []
                
                progreso = st.progress(0)
                status = st.empty()
                total = len(df_trabajo)
                st.toast(f"Iniciando {total} SKUs...")

                # Configuración Selenium
                options = webdriver.ChromeOptions()
                options.add_argument("--start-maximized")
                
                try:
                    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                except:
                    st.error("Error al iniciar Chrome Driver.")
                    st.stop()

                # --- PROCESO ---
                with zipfile.ZipFile(resultados_zip, 'w') as zf:
                    
                    for i, (index, row) in enumerate(df_trabajo.iterrows()):
                        sku_objetivo = str(row["SKU"]).strip()
                        
                        progreso.progress((i + 1) / total)
                        status.text(f"⏳ ({i+1}/{total}) Procesando SKU: {sku_objetivo}")

                        try:
                            # 1. BÚSQUEDA
                            url_busqueda = f"https://www.ohigginsherramientas.cl/catalogsearch/result/?q={sku_objetivo}"
                            driver.get(url_busqueda)
                            time.sleep(2.5) 

                            # 2. DETECCIÓN UBICACIÓN (Ficha vs Lista)
                            ya_en_ficha = False
                            try:
                                driver.find_element(By.CLASS_NAME, "product-info-main")
                                ya_en_ficha = True
                            except:
                                ya_en_ficha = False

                            if not ya_en_ficha:
                                try:
                                    producto = driver.find_element(By.CSS_SELECTOR, ".product-item-link") 
                                    link_producto = producto.get_attribute("href")
                                    driver.get(link_producto)
                                    time.sleep(2)
                                except:
                                    try:
                                        producto = driver.find_element(By.CSS_SELECTOR, "a.product-image")
                                        link_producto = producto.get_attribute("href")
                                        driver.get(link_producto)
                                        time.sleep(2)
                                    except:
                                        log_errores.append(f"{sku_objetivo}: No se encontró el producto")
                                        continue

                            # 3. BUSCAR LINK DE DESCARGA
                            link_pdf = ""
                            try:
                                # A. Botón smart-download
                                boton = driver.find_element(By.CLASS_NAME, "smart-download")
                                onclick_txt = boton.get_attribute("onclick") 
                                
                                if onclick_txt and "http" in onclick_txt:
                                    start = onclick_txt.find("'") + 1
                                    end = onclick_txt.find("'", start)
                                    link_pdf = onclick_txt[start:end]
                                else:
                                    raise Exception("Botón sin JS")

                            except:
                                # B. Fallback texto
                                try:
                                    elementos = driver.find_elements(By.XPATH, "//*[contains(text(), 'Descargar Ficha')]")
                                    for elem in elementos:
                                        onclick_txt = elem.get_attribute("onclick")
                                        href_txt = elem.get_attribute("href")
                                        
                                        if onclick_txt and "http" in onclick_txt:
                                            start = onclick_txt.find("'") + 1
                                            end = onclick_txt.find("'", start)
                                            link_pdf = onclick_txt[start:end]
                                            break
                                        elif href_txt and ".pdf" in href_txt:
                                            link_pdf = href_txt
                                            break
                                except:
                                    pass

                            if not link_pdf:
                                raise Exception("No encontré botón de descarga")

                            # 4. DESCARGAR Y PROCESAR (IMAGEN LARGA)
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                "Referer": driver.current_url 
                            }
                            response = requests.get(link_pdf, headers=headers)
                            
                            if response.status_code == 200:
                                if b"%PDF" in response.content[:20]:
                                    # Convertimos PDF a lista de imágenes
                                    paginas = procesar_pdf_a_imagenes(response.content) 
                                    
                                    if paginas:
                                        # === CAMBIO CLAVE AQUÍ ===
                                        # Unimos todas las páginas verticalmente
                                        img_final = unir_imagenes_verticalmente(paginas)
                                        
                                        img_buffer = BytesIO()
                                        
                                        # Intentamos guardar como JPG
                                        try:
                                            img_final.save(img_buffer, format="JPEG", quality=90)
                                            ext = "jpg"
                                        except Exception:
                                            # Si falla (ej. imagen muy alta), usamos PNG
                                            img_buffer = BytesIO()
                                            img_final.save(img_buffer, format="PNG")
                                            ext = "png"
                                        
                                        # Guardamos en ZIP
                                        zf.writestr(f"FT-{sku_objetivo}.{ext}", img_buffer.getvalue())
                                    else:
                                        log_errores.append(f"{sku_objetivo}: PDF vacío")
                                else:
                                    log_errores.append(f"{sku_objetivo}: Archivo inválido")
                            else:
                                log_errores.append(f"{sku_objetivo}: Error descarga {response.status_code}")

                        except Exception as e:
                            log_errores.append(f"{sku_objetivo}: Error - {str(e)}")

                driver.quit()
                status.success("¡Proceso terminado!")
                progreso.empty()

                st.download_button(
                    label="Descargar ZIP con Fichas",
                    data=resultados_zip.getvalue(),
                    file_name="Fichas_Por_SKU.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )

                if log_errores:
                    st.warning(f"Hubo problemas con {len(log_errores)} productos.")
                    with st.expander("Ver reporte de errores"):
                        st.write(log_errores)

    with c_btn2:
        if st.button("Limpiar Tabla", key="limpiar_tab4_sku"):
            st.session_state.df_ohiggins_sku = pd.DataFrame({"SKU": [""] * 15})
            st.rerun()
            
            



# ---------------------------------------------------------
# PESTAÑA 7: ROBOT O'HIGGINS PARA DESCARGAR IMAGEN DE PRODUCTO
# ---------------------------------------------------------
with tab_ohiggins2:
    st.header("📸 Descargador de Imágenes (O'Higgins)")
    st.markdown("""
    **Modo Imágenes (Optimizado):**
    1. Pega tu lista de SKUs.
    2. Se extrae la **URL de Alta Calidad** directamente del código fuente.
    3. Convierte todo a **.JPG** y genera un ZIP.
    """)

    # --- CAMBIO 1: Estado independiente para imágenes ---
    if 'df_ohiggins_img' not in st.session_state:
        st.session_state.df_ohiggins_img = pd.DataFrame({"SKU": [""] * 15})

    # --- TABLA EDITABLE ---
    # CAMBIO 2: key única "editor_ohiggins_img_widget"
    editor_ohiggins_img = st.data_editor(
        st.session_state.df_ohiggins_img,
        num_rows="dynamic",
        height=400,
        use_container_width=True,
        key="editor_ohiggins_img_widget", 
        column_config={
            "SKU": st.column_config.TextColumn("Listado de SKUs", required=True)
        }
    )

    c_btn1, c_btn2 = st.columns([1, 4])

    with c_btn1:
        if st.button("DESCARGAR IMÁGENES", type="primary", use_container_width=True, key="btn_descargar_img"):
            
            df_trabajo = editor_ohiggins_img.copy()
            df_trabajo = df_trabajo[df_trabajo["SKU"].astype(str).str.strip() != ""]

            if len(df_trabajo) == 0:
                st.warning("La tabla está vacía.")
            else:
                resultados_zip = BytesIO()
                log_errores = []
                
                progreso = st.progress(0)
                status = st.empty()
                total = len(df_trabajo)
                st.toast(f"Iniciando descarga de {total} imágenes...")

                options = webdriver.ChromeOptions()
                options.add_argument("--start-maximized")
                options.add_argument("--log-level=3")
                
                # --- BLOQUE DE INICIO ROBUSTO ---
                try:
                    # 1. Agregamos esta importación que faltaba
                    from selenium.webdriver.support.ui import WebDriverWait
                    
                    # Opciones extra para evitar errores
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--disable-gpu")
                    
                    # Instalación limpia del driver
                    ruta_driver = ChromeDriverManager().install()
                    service = Service(ruta_driver)
                    
                    driver = webdriver.Chrome(service=service, options=options)
                    
                    # 2. CORRECCIÓN AQUÍ: Usamos WebDriverWait directamente
                    wait = WebDriverWait(driver, 5)

                except Exception as e:
                    st.error(f"Error crítico al iniciar el Driver: {str(e)}")
                    st.stop()

                # --- PROCESO ---
                with zipfile.ZipFile(resultados_zip, 'w') as zf:
                    from PIL import Image
                    from selenium.webdriver.support import expected_conditions as EC

                    for i, (index, row) in enumerate(df_trabajo.iterrows()):
                        sku_objetivo = str(row["SKU"]).strip()
                        progreso.progress((i + 1) / total)
                        status.text(f"📷 ({i+1}/{total}) Procesando SKU: {sku_objetivo}")

                        try:
                            # 1. BÚSQUEDA
                            url_busqueda = f"https://www.ohigginsherramientas.cl/catalogsearch/result/?q={sku_objetivo}"
                            driver.get(url_busqueda)
                            
                            # 2. ENTRAR AL PRODUCTO (Lógica Inteligente)
                            # ---------------------------------------------------------
                            ya_en_ficha = False
                            
                            # A. Revisar si la web nos redirigió automáticamente a la ficha
                            try:
                                # Buscamos un elemento que solo existe dentro de la ficha (ej. columna de info)
                                driver.find_element(By.CSS_SELECTOR, ".product-info-main")
                                ya_en_ficha = True
                            except:
                                ya_en_ficha = False

                            # B. Si NO estamos en la ficha, entonces buscamos en la lista de resultados
                            if not ya_en_ficha:
                                try:
                                    # Esperamos el click en el listado
                                    link_producto = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.product-item-link")))
                                    link_producto.click()
                                except:
                                    # Si no estamos en ficha y no hay lista -> Entonces sí que no existe
                                    log_errores.append(f"{sku_objetivo}: Producto no encontrado (Ni directo ni en lista)")
                                    continue
                            # --------------------------------------------------------
                            # 3. EXTRAER IMAGEN (Lógica optimizada)
                            image_src = None
                            
                            # A. INTENTO 1: Buscar <link itemprop="image">
                            try:
                                link_tag = driver.find_element(By.CSS_SELECTOR, "link[itemprop='image']")
                                image_src = link_tag.get_attribute("href")
                            except:
                                pass

                            # B. INTENTO 2: Buscar data-amsrc
                            if not image_src:
                                try:
                                    img_placeholder = driver.find_element(By.CSS_SELECTOR, ".gallery-placeholder__image")
                                    image_src = img_placeholder.get_attribute("data-amsrc")
                                    if not image_src:
                                        image_src = img_placeholder.get_attribute("src")
                                except:
                                    pass
                            
                            # C. INTENTO 3: Fallback visual
                            if not image_src or "base64" in image_src:
                                try:
                                    img_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "img.fotorama__img")))
                                    image_src = img_element.get_attribute("src")
                                except:
                                    pass

                            if not image_src:
                                log_errores.append(f"{sku_objetivo}: URL de imagen no encontrada")
                                continue

                            # 4. DESCARGAR Y GUARDAR
                            headers = {"User-Agent": "Mozilla/5.0"}
                            response = requests.get(image_src, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                try:
                                    img = Image.open(BytesIO(response.content))
                                    if img.mode in ("RGBA", "P"):
                                        img = img.convert("RGB")
                                    
                                    img_buffer = BytesIO()
                                    img.save(img_buffer, format="JPEG", quality=95)
                                    zf.writestr(f"{sku_objetivo}.jpg", img_buffer.getvalue())
                                except:
                                    log_errores.append(f"{sku_objetivo}: Error al procesar imagen")
                            else:
                                log_errores.append(f"{sku_objetivo}: Error descarga HTTP")

                        except Exception as e:
                            log_errores.append(f"{sku_objetivo}: Error {str(e)}")

                driver.quit()
                status.success("¡Proceso terminado!")
                progreso.empty()

                st.download_button(
                    label="Descargar ZIP con Imágenes",
                    data=resultados_zip.getvalue(),
                    file_name="Imagenes_Ohiggins_SKU.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )

                if log_errores:
                    with st.expander(f"Ver {len(log_errores)} errores"):
                        st.write(log_errores)

    with c_btn2:
        # CAMBIO 3: key única para limpiar
        if st.button("🗑️ Limpiar Tabla", key="limpiar_tab7_img"):
            st.session_state.df_ohiggins_img = pd.DataFrame({"SKU": [""] * 15})
            st.rerun()


        
        
# ==============================================================================
# PESTAÑA 10: ROBOT O'HIGGINS (V11 - DESCARGA HD + FILTRO INTELIGENTE)
# ==============================================================================


with tab_ohiggins20:
    st.header("🇨🇱 Robot O'Higgins (V11 - Calidad HD)")
    st.markdown("""
    **Mejoras V11:**
    1. **Descarga Real:** Extrae los archivos originales (JPG/PNG) del código fuente.
    2. **Filtro de Calidad:** Elimina automáticamente logos, iconos y basura pequeña.
    3. **Diseño Limpio:** Muestra el producto y las tablas técnicas con su traducción abajo.
    """)

    # --- AUTO-CORRECTOR DE MEMORIA ---
    reset_needed = False
    if 'df_ohiggins' not in st.session_state: reset_needed = True
    elif 'DESCRIPCION' not in st.session_state.df_ohiggins.columns: reset_needed = True
    elif 'SKU' not in st.session_state.df_ohiggins.columns: reset_needed = True
        
    if reset_needed:
        st.session_state.df_ohiggins = pd.DataFrame({
            "SKU": [""] * 5,
            "DESCRIPCION": [""] * 5
        })

    editor_ohiggins = st.data_editor(
        st.session_state.df_ohiggins,
        num_rows="dynamic",
        key="editor_ohiggins_widget_v11",
        column_config={
            "SKU": st.column_config.TextColumn("SKU (Código)", required=True),
            "DESCRIPCION": st.column_config.TextColumn("Nombre del Producto", required=True)
        }
    )

    if st.button("🚀 EJECUTAR ROBOT V11", type="primary", key="btn_ohiggins_start_v11"):
        
        try: import fitz, requests
        except ImportError: 
            st.error("⚠️ Faltan librerías. Instala: pip install pymupdf requests")
            st.stop()

        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from urllib.parse import quote 
        import base64
        import time
        import re # Para buscar patrones de texto
        
        # User Agent (Disfraz de navegador)
        USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        HEADERS = {"User-Agent": USER_AGENT}

        df_work = editor_ohiggins.copy()
        if "SKU" in df_work.columns:
            df_work = df_work[df_work["SKU"].astype(str).str.strip() != ""] 
        else:
            st.error("⚠️ Error en la tabla. Recarga la página.")
            st.stop()

        if len(df_work) == 0:
            st.warning("⚠️ La tabla está vacía.")
        else:
            resultados_zip = BytesIO()
            log_errores = []
            
            progreso = st.progress(0)
            status = st.empty()
            total = len(df_work)
            
            options = webdriver.ChromeOptions()
            options.add_argument("--log-level=3")
            options.add_argument("--headless") 
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"user-agent={USER_AGENT}")
            options.add_argument("--window-size=1920,1080")
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 20)
            except Exception as e:
                st.error(f"Error crítico al iniciar Chrome: {e}")
                st.stop()

            with zipfile.ZipFile(resultados_zip, 'w') as zf:
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    sku_producto = str(row.get("SKU", "")).strip()
                    nombre_producto = str(row.get("DESCRIPCION", "")).strip()
                    
                    progreso.progress((i + 1) / total)
                    status.text(f"📥 ({i+1}/{total}) Procesando: {sku_producto}...")

                    try:
                        # 1. BÚSQUEDA
                        url_busqueda = f"https://www.ohigginsherramientas.cl/catalogsearch/result/?q={quote(sku_producto)}"
                        try: driver.get(url_busqueda)
                        except: 
                            time.sleep(2)
                            driver.get(url_busqueda)

                        # Navegar al producto si es lista
                        try:
                            # Esperar a que cargue el body
                            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                            links = driver.find_elements(By.CSS_SELECTOR, "a.product-item-link")
                            if len(links) > 0:
                                driver.get(links[0].get_attribute("href"))
                        except: pass 
                        
                        time.sleep(3) # Esperar carga básica

                        # 2. EXTRACCIÓN DE DATOS
                        datos = {"sku": sku_producto, "titulo": "", "imgs_b64": []}

                        try: 
                            datos["titulo"] = driver.find_element(By.CSS_SELECTOR, "h1.page-title").text.strip()
                        except: datos["titulo"] = nombre_producto

                        # --- MOTOR DE EXTRACCIÓN DE IMÁGENES HD ---
                        urls_candidatas = []
                        
                        try:
                            # A. Búsqueda en el JSON de Magento (Donde están las fotos originales)
                            # Buscamos en el código fuente scripts que contengan datos de imagen
                            page_source = driver.page_source
                            # Patrón regex para encontrar URLs de imágenes grandes en JSON
                            # Busca: "full": "https://..." o "img": "https://..."
                            found_urls = re.findall(r'"full":\s*"([^"]+)"', page_source)
                            if not found_urls:
                                found_urls = re.findall(r'"img":\s*"([^"]+)"', page_source)
                            
                            for url in found_urls:
                                clean_url = url.replace("\\/", "/") # Arreglar barras escapadas
                                if clean_url not in urls_candidatas:
                                    urls_candidatas.append(clean_url)

                            # B. Búsqueda en el DOM (Si falla el JSON)
                            if not urls_candidatas:
                                elements = driver.find_elements(By.CSS_SELECTOR, ".fotorama__img")
                                for el in elements:
                                    src = el.get_attribute("src")
                                    if src and src not in urls_candidatas:
                                        urls_candidatas.append(src)

                            # C. DESCARGA Y FILTRADO (EL SECRETO)
                            # Aquí filtramos la "basura" (logos pequeños, iconos)
                            count_validas = 0
                            for url in urls_candidatas:
                                if count_validas >= 3: break # Solo queremos las 3 mejores (Producto + Tablas)
                                
                                try:
                                    # Descargar la imagen
                                    resp = requests.get(url, headers=HEADERS, timeout=10)
                                    if resp.status_code == 200:
                                        # FILTRO DE TAMAÑO: Si pesa menos de 25KB, es basura (logo/icono)
                                        tamanio_bytes = len(resp.content)
                                        if tamanio_bytes > 25000: 
                                            b64 = base64.b64encode(resp.content).decode('utf-8')
                                            datos["imgs_b64"].append(f"data:image/jpeg;base64,{b64}")
                                            count_validas += 1
                                except: pass

                        except Exception as e:
                            print(f"Error extracción: {e}")

                        # 3. CONSTRUCCIÓN HTML
                        imgs_html = ""
                        if not datos["imgs_b64"]:
                            imgs_html = '<div class="img-box">⚠️ No se encontraron imágenes grandes válidas.</div>'
                        else:
                            for idx, img_b64 in enumerate(datos["imgs_b64"]):
                                label = "Producto" if idx == 0 else "Especificaciones Técnicas (Ver traducción abajo)"
                                imgs_html += f"""
                                <div class="img-box">
                                    <div class="img-label">{label}</div>
                                    <img src="{img_b64}">
                                </div>
                                """

                        # GLOSARIO DE TRADUCCIÓN (Indispensable para las tablas en portugués)
                        glosario_html = """
                        <div class="translation-legend">
                            <h3>🇪🇸 Guía de Traducción (Portugués » Español)</h3>
                            <div class="legend-grid">
                                <div class="term"><strong>Código No.</strong> <br> <span>Código</span></div>
                                <div class="term"><strong>Capacidade</strong> <br> <span>Capacidad</span></div>
                                <div class="term"><strong>Exatidão</strong> <br> <span>Precisión</span></div>
                                <div class="term"><strong>Graduação</strong> <br> <span>Graduación</span></div>
                                <div class="term"><strong>Polegada</strong> <br> <span>Pulgadas (")</span></div>
                                <div class="term"><strong>Métrico</strong> <br> <span>Métrico (mm)</span></div>
                                <div class="term"><strong>Características</strong> <br> <span>Características</span></div>
                                <div class="term"><strong>Faces de metal duro</strong> <br> <span>Caras de carburo</span></div>
                                <div class="term"><strong>Sem Revestimento</strong> <br> <span>Sin Revestimiento</span></div>
                                <div class="term"><strong>Dimensões</strong> <br> <span>Dimensiones</span></div>
                                <div class="term"><strong>Espessura</strong> <br> <span>Espesor</span></div>
                                <div class="term"><strong>Bicos</strong> <br> <span>Puntas/Mandíbulas</span></div>
                            </div>
                        </div>
                        """

                        html_template = f"""
                        <!DOCTYPE html>
                        <html lang="es">
                        <head>
                            <meta charset="UTF-8">
                            <style>
                                body {{ font-family: 'Helvetica', 'Arial', sans-serif; padding: 40px; color: #333; background: #fff; }}
                                .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #d32f2f; padding-bottom: 15px; margin-bottom: 25px; }}
                                .logo {{ color: #d32f2f; font-size: 24px; font-weight: 800; font-style: italic; }}
                                .sku-tag {{ background: #222; color: white; padding: 6px 15px; font-weight: bold; border-radius: 4px; font-size: 14px; }}
                                h1 {{ font-size: 26px; margin-bottom: 5px; color: #000; }}
                                .subtitle {{ color:#666; font-size: 14px; margin-bottom:30px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                                
                                /* Grid Vertical para máxima legibilidad de tablas */
                                .grid {{ display: flex; flex-direction: column; gap: 40px; align-items: center; }}
                                
                                .img-box {{ 
                                    text-align: center; 
                                    border: 1px solid #e0e0e0; 
                                    padding: 20px; 
                                    border-radius: 8px; 
                                    background: #fff; 
                                    width: 95%; /* Ancho completo */
                                    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
                                    page-break-inside: avoid;
                                }}
                                .img-box img {{ 
                                    width: 100%; 
                                    height: auto; 
                                    object-fit: contain; 
                                    /* Sin límite de altura para que la tabla se vea completa */
                                }}
                                .img-label {{ text-align: left; font-size: 12px; font-weight: bold; color: #d32f2f; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                                
                                .translation-legend {{ background: #f8f9fa; border: 1px solid #e9ecef; border-left: 5px solid #0056b3; padding: 20px; margin-top: 50px; page-break-inside: avoid; }}
                                .translation-legend h3 {{ margin: 0 0 15px 0; color: #0056b3; font-size: 16px; border-bottom: 1px solid #dee2e6; padding-bottom: 5px; }}
                                .legend-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); font-size: 12px; gap: 10px; }}
                                .term {{ background: white; padding: 8px; border-radius: 4px; border: 1px solid #dee2e6; line-height: 1.4; }}
                                .term strong {{ color: #495057; display: block; margin-bottom: 2px; }}
                                .term span {{ color: #0056b3; font-weight: bold; }}
                                
                                .footer {{ margin-top: 50px; font-size: 10px; color: #aaa; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }}
                            </style>
                        </head>
                        <body>
                            <div class="header">
                                <div class="logo">Mitutoyo / O'Higgins</div>
                                <div class="sku-tag">SKU: {datos['sku']}</div>
                            </div>
                            <h1>{datos['titulo']}</h1>
                            <div class="subtitle">Ficha Técnica Generada Automáticamente</div>
                            
                            <div class="grid">{imgs_html}</div>
                            
                            {glosario_html}
                            
                            <div class="footer">Documento informativo | Fuente: Ohiggins Herramientas</div>
                        </body>
                        </html>
                        """

                        # 4. RENDERIZAR
                        driver.get("data:text/html;charset=utf-8," + quote(html_template))
                        time.sleep(1.5)

                        pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
                            "printBackground": True,
                            "paperWidth": 8.27, "paperHeight": 11.69, # A4
                            "marginTop": 0.3, "marginBottom": 0.3, "marginLeft": 0.3, "marginRight": 0.3,
                            "pageRanges": "1-2", 
                        })

                        pdf_bytes = base64.b64decode(pdf_data['data'])
                        if pdf_bytes:
                            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(3.0, 3.0)) # Alta calidad
                            zf.writestr(f"FT-{sku_producto}.jpg", pix.tobytes("jpg"))
                        else:
                            log_errores.append(f"{sku_producto}: Falló generación")

                    except Exception as e:
                        log_errores.append(f"{sku_producto}: Error general - {str(e)}")

            driver.quit()
            status.success("✅ ¡Fichas (HD) Terminadas!")
            progreso.empty()

            st.download_button(
                label="📦 Descargar Fichas (ZIP)",
                data=resultados_zip.getvalue(),
                file_name="Fichas_Ohiggins_V11_HD.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

            if log_errores:
                with st.expander(f"⚠️ Errores ({len(log_errores)})"):
                    st.write(log_errores)

    if st.button("🗑️ Limpiar Tabla", key="clean_ohiggins"):
        st.session_state.df_ohiggins = pd.DataFrame({"SKU": [""] * 5, "DESCRIPCION": [""] * 5})
        st.rerun()
        



# ==============================================================================
# PESTAÑA 11: ROBOT MARSELLA (ESPECIALISTA VTEX)
# ==============================================================================


with tab_marsellitta:
    st.header("🔵 Robot Marsella")
    st.markdown("""
    **Descarga imagen Marsella**
    1. **Navegación:** Entra automáticamente al producto si la búsqueda arroja una lista.
    2. **Descarga:** Extrae la imagen original en alta calidad y la guarda como `{SKU}.jpg`.
    """)

    if 'df_marsella' not in st.session_state:
        st.session_state.df_marsella = pd.DataFrame({
            "SKU": [""] * 5
        })

    editor_marsella = st.data_editor(
        st.session_state.df_marsella,
        num_rows="dynamic",
        key="editor_marsella_widget_v12",
        column_config={
            "SKU": st.column_config.TextColumn("SKU a Buscar", required=True)
        }
    )

    if st.button("🚀 DESCARGAR FOTOS MARSELLA", type="primary", key="btn_marsella_start_v12"):
        
        try: import requests
        except ImportError: 
            st.error("⚠️ Falta librería requests.")
            st.stop()

        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        import time
        
        # User Agent estándar
        USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        HEADERS = {"User-Agent": USER_AGENT}

        df_work = editor_marsella.copy()
        df_work = df_work[df_work["SKU"].astype(str).str.strip() != ""] 

        if len(df_work) == 0:
            st.warning("⚠️ La tabla está vacía.")
        else:
            resultados_zip = BytesIO()
            log_errores = []
            
            progreso = st.progress(0)
            status = st.empty()
            total = len(df_work)
            
            # --- CONFIGURACIÓN CHROME ---
            options = webdriver.ChromeOptions()
            options.add_argument("--log-level=3")
            options.add_argument("--headless") 
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"user-agent={USER_AGENT}")
            options.add_argument("--window-size=1920,1080")
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 20)
            except Exception as e:
                st.error(f"Error driver: {e}")
                st.stop()

            with zipfile.ZipFile(resultados_zip, 'w') as zf:
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    sku_producto = str(row.get("SKU", "")).strip()
                    
                    progreso.progress((i + 1) / total)
                    status.text(f"🔍 ({i+1}/{total}) Procesando SKU: {sku_producto}...")

                    try:
                        # 1. BÚSQUEDA DIRECTA VTEX
                        # La estructura mágica: dominio/{sku}?_q={sku}&map=ft
                        # Esto fuerza al motor de búsqueda de VTEX a buscar el término exacto
                        url_busqueda = f"https://www.ferreteriamarsella.cl/{sku_producto}?_q={sku_producto}&map=ft"
                        driver.get(url_busqueda)
                        
                        # Esperar a que cargue algo (Lista o Producto)
                        try:
                            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                            time.sleep(2) # Pequeña pausa para scripts de VTEX
                        except: pass

                        # 2. DETECCIÓN DE ESTADO (¿LISTA O PRODUCTO?)
                        en_producto = False
                        
                        # A. Verificar si estamos en lista de resultados
                        # Buscamos la clase 'vtex-product-summary' que vi en tus fotos
                        try:
                            resultados = driver.find_elements(By.CSS_SELECTOR, ".vtex-product-summary-2-x-container")
                            if len(resultados) > 0:
                                # Estamos en una lista, click al primero
                                link = resultados[0].find_element(By.CSS_SELECTOR, "a.vtex-product-summary-2-x-clearLink")
                                driver.get(link.get_attribute("href"))
                                time.sleep(3) # Esperar carga de producto
                                en_producto = True
                        except: pass

                        # B. Verificar si ya estamos en producto (Redirección automática)
                        if not en_producto:
                            # Buscamos contenedor de imágenes de producto VTEX
                            if len(driver.find_elements(By.CSS_SELECTOR, ".vtex-store-components-3-x-productImagesContainer")) > 0:
                                en_producto = True

                        # 3. EXTRACCIÓN DE IMAGEN
                        url_imagen = None
                        
                        if en_producto or True: # Intentamos buscar la imagen de todas formas
                            try:
                                # ESTRATEGIA VTEX: Buscar la imagen principal
                                # Selector 1: Clase estándar de imagen de producto VTEX
                                targets = driver.find_elements(By.CSS_SELECTOR, "img.vtex-store-components-3-x-productImageTag")
                                
                                # Selector 2: Imagen dentro del Swiper (tu captura 3)
                                if not targets:
                                    targets = driver.find_elements(By.CSS_SELECTOR, ".swiper-wrapper img")
                                
                                # Selector 3: Genérico de la página
                                if not targets:
                                    targets = driver.find_elements(By.CSS_SELECTOR, ".vtex-store-components-3-x-productImage img")

                                for img in targets:
                                    src = img.get_attribute("src")
                                    # Filtramos iconos pequeños o placeholders
                                    if src and "http" in src and "commondatastorage" not in src:
                                        url_imagen = src
                                        break # Nos quedamos con la primera (la principal)

                            except Exception as e:
                                print(f"Error selector imagen: {e}")

                        # 4. DESCARGAR Y GUARDAR
                        if url_imagen:
                            try:
                                response = requests.get(url_imagen, headers=HEADERS, timeout=10)
                                if response.status_code == 200:
                                    zf.writestr(f"{sku_producto}.jpg", response.content)
                                else:
                                    log_errores.append(f"{sku_producto}: Error HTTP {response.status_code}")
                            except Exception as e:
                                log_errores.append(f"{sku_producto}: Error descarga - {str(e)}")
                        else:
                            log_errores.append(f"{sku_producto}: No se encontró imagen o producto")

                    except Exception as e:
                        log_errores.append(f"{sku_producto}: Error general - {str(e)}")

            driver.quit()
            status.success("✅ ¡Descarga de Marsella Completa!")
            progreso.empty()

            st.download_button(
                label="📦 Descargar Fotos (ZIP)",
                data=resultados_zip.getvalue(),
                file_name="Fotos_Marsella_VTEX.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

            if log_errores:
                with st.expander(f"⚠️ Errores ({len(log_errores)})"):
                    st.write(log_errores)

    if st.button("🗑️ Limpiar Tabla", key="clean_marsella"):
        st.session_state.df_marsella = pd.DataFrame({"SKU": [""] * 5})
        st.rerun()
        
        


# ---------------------------------------------------------
# PESTAÑA: GESTOR DE PRODUCTOS E INTEGRACIÓN (CÓDIGO FINAL)
# ---------------------------------------------------------

with tab_creacion:
    # --- 1. ESTADOS DE SESIÓN (CRUCIAL) ---
    if 'index_navegacion' not in st.session_state:
        st.session_state.index_navegacion = 0
    if 'producto_a_editar' not in st.session_state:
        st.session_state.producto_a_editar = None

    # Función para mover el índice
    def mover_navegacion(direccion):
        total = len(st.session_state.lista_productos)
        if total > 0:
            st.session_state.index_navegacion = (st.session_state.index_navegacion + direccion) % total

    # --- 2. SELECTOR DE VISTA PRINCIPAL ---
    # Usamos un radio horizontal como "Switch" de modo de trabajo
    modo_trabajo = st.radio(
        "Selecciona Modo de Trabajo:",
        ["➕ Crear / Editar", "📋 Inventario Maestro", "🚀 Navegación Rápida"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.divider()

    # =========================================================
    # VISTA 1: CREAR / EDITAR (CON CONTEO EN TIEMPO REAL)
    # =========================================================
    if modo_trabajo == "➕ Crear / Editar":
        es_edicion = st.session_state.producto_a_editar is not None
        
        if es_edicion:
            st.subheader("📝 Modo Edición Activo")
            p_edit = st.session_state.producto_a_editar
            valor_defecto = (
                f"{p_edit['sku']}\t{p_edit['nombre']}\t{p_edit['marca']}\n"
                f"Descripción del producto:\n{p_edit.get('desc_solo', '')}\n"
                f"Especificaciones Técnicas:\n{p_edit.get('specs_solo', '')}\n"
                f"Meta descripción:\n{p_edit.get('meta', '')}\n"
                f"Palabras sustitutas:\n{p_edit.get('tags', '')}"
            )
            if st.button("❌ Salir de Edición (Volver a Crear)"):
                st.session_state.producto_a_editar = None
                st.rerun()
        else:
            st.subheader("➕ Ingreso de Nuevo Producto")
            valor_defecto = ""

        # Área de texto principal
        raw_text = st.text_area(
            "Pega el bloque de información aquí:",
            value=valor_defecto,
            height=300,
            key="area_ingreso_master"
        )

        # --- LÓGICA DE CONTEO EN TIEMPO REAL ---
        def analizar_bloque(t):
            # Extraer meta y specs mediante regex para el conteo
            meta_match = re.search(r"Meta descripción.*?:(.*?)(?=Palabras|$)", t, re.S | re.I)
            specs_match = re.search(r"Especificaciones Técnicas:(.*?)(?=Meta|$)", t, re.S | re.I)
            
            m_text = meta_match.group(1).strip() if meta_match else ""
            s_text = specs_match.group(1).strip() if specs_match else ""
            
            lineas_specs = [l for l in s_text.split('\n') if l.strip()]
            return len(m_text), len(lineas_specs)

        caracteres_meta, total_lineas_specs = analizar_bloque(raw_text)

        # Mostrar métricas de validación
        m1, m2 = st.columns(2)
        with m1:
            color_meta = "normal" if caracteres_meta <= 160 else "inverse"
            st.metric("Caracteres Meta Descripción", f"{caracteres_meta} / 160", 
                      delta=caracteres_meta-160, delta_color=color_meta)
        with m2:
            color_specs = "normal" if total_lineas_specs <= 15 else "inverse"
            st.metric("Líneas de Especificaciones", f"{total_lineas_specs} / 15", 
                      delta=total_lineas_specs-15, delta_color=color_specs)

        # Botones de Acción
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            label_principal = "💾 Actualizar Producto" if es_edicion else "💾 Guardar Producto"
            if st.button(label_principal, type="primary", use_container_width=True):
                if raw_text.strip():
                    # --- PARSEO ---
                    def extraer(ini, fin, txt):
                        pattern = f"{ini}(.*?)(?={re.escape(fin)}|$)"
                        m = re.search(pattern, txt, re.DOTALL | re.IGNORECASE)
                        return m.group(1).strip() if m else ""

                    lineas = raw_text.strip().split('\n')
                    header = lineas[0].split('\t')
                    
                    sku_val = header[0].strip()
                    nom_val = header[1].strip() if len(header) > 1 else ""
                    mar_val = header[2].strip() if len(header) > 2 else ""

                    d = extraer("Descripción del producto:", "Especificaciones Técnicas:", raw_text)
                    s = extraer("Especificaciones Técnicas:", "Meta descripción", raw_text)
                    m = extraer("Meta descripción.*?:", "Palabras sustitutas:", raw_text)
                    t = extraer("Palabras sustitutas:", "FIN", raw_text)

                    nuevo_p = {
                        "sku": sku_val, "nombre": nom_val, "marca": mar_val,
                        "desc_solo": d, "specs_solo": s,
                        "vtex_body": f"{d}\n\nEspecificaciones Técnicas:\n{s}".strip(),
                        "meta": m, "tags": t
                    }

                    if es_edicion:
                        sku_orig = st.session_state.producto_a_editar['sku']
                        st.session_state.lista_productos = [nuevo_p if p['sku'] == sku_orig else p for p in st.session_state.lista_productos]
                        st.session_state.producto_a_editar = None
                    else:
                        st.session_state.lista_productos.append(nuevo_p)

                    guardar_en_base_datos(st.session_state.lista_productos)
                    st.toast("✅ ¡Guardado con éxito!")
                    st.rerun()

        with c_btn2:
            if es_edicion:
                if st.button("🗑️ Eliminar Producto", type="secondary", use_container_width=True):
                    sku_orig = st.session_state.producto_a_editar['sku']
                    st.session_state.lista_productos = [p for p in st.session_state.lista_productos if p['sku'] != sku_orig]
                    guardar_en_base_datos(st.session_state.lista_productos)
                    st.session_state.producto_a_editar = None
                    st.rerun()

    # =========================================================
    # VISTA 2: INVENTARIO MAESTRO (BUSCADOR + SELECCIÓN)
    # =========================================================
    elif modo_trabajo == "📋 Inventario Maestro":
        st.subheader("🗃️ Catálogo de Productos Registrados")
        
        if not st.session_state.lista_productos:
            st.info("No hay productos registrados.")
        else:
            busq = st.text_input("🔍 Buscar por SKU, Nombre o Marca:", placeholder="Escribe para filtrar...")
            
            df_m = pd.DataFrame(st.session_state.lista_productos)[["sku", "nombre", "marca"]]
            
            if busq:
                df_m = df_m[
                    df_m['sku'].str.contains(busq, case=False) | 
                    df_m['nombre'].str.contains(busq, case=False) |
                    df_m['marca'].str.contains(busq, case=False)
                ]

            st.caption("Haz clic en el checkbox ✏️ para ver o editar el producto completo.")
            df_m.insert(0, "Seleccionar", False)
            
            grid_resp = st.data_editor(
                df_m,
                hide_index=True,
                use_container_width=True,
                column_config={"Seleccionar": st.column_config.CheckboxColumn("✏️", default=False)},
                key="editor_tabla_maestra"
            )

            # Lógica de selección para editar
            for i in range(len(grid_resp)):
                if grid_resp.iloc[i]["Seleccionar"]:
                    sku_sel = grid_resp.iloc[i]["sku"]
                    prod_full = next(p for p in st.session_state.lista_productos if p['sku'] == sku_sel)
                    st.session_state.producto_a_editar = prod_full
                    # Saltamos automáticamente a la vista de edición
                    # modo_trabajo = "➕ Crear / Editar" <--- Streamlit no permite cambiar el radio así, 
                    # pero le indicamos al usuario que ya está cargado.
                    st.success(f"✅ Producto {sku_sel} cargado. Ve a la pestaña 'Crear / Editar' para modificarlo.")
                    st.rerun()

    # =========================================================
    # VISTA 3: NAVEGACIÓN RÁPIDA (PARA PUBLICAR EN VTEX)
    # =========================================================
    # =========================================================
    # VISTA 3: NAVEGACIÓN RÁPIDA (FILTRADA Y ORDENADA POR LISTA DE SKUs)
    # =========================================================
    elif modo_trabajo == "🚀 Navegación Rápida":
        if not st.session_state.lista_productos:
            st.warning("No hay productos en la base de datos.")
        else:
            st.subheader("📋 Secuenciador de Ruta para VTEX")
            
            # 1. Campo para pegar el listado de SKUs en el orden deseado
            lista_skus_raw = st.text_area(
                "Pega aquí la lista de SKUs en el orden exacto que quieres recorrer (uno por línea):",
                placeholder="abc\nabcd\nabcde",
                key="lista_skus_navegacion_manual",
                height=150
            )
            
            # Procesar la lista pegada por el usuario
            skus_ordenados = [sku.strip() for sku in lista_skus_raw.split("\n") if sku.strip()]
            
            # 2. Reconstruir la lista de productos basada EN EL ORDEN de la lista pegada
            productos_filtrados_y_ordenados = []
            
            if skus_ordenados:
                for sku_buscar in skus_ordenados:
                    # Buscamos el producto exacto en la base de datos local
                    encontrado = next((p for p in st.session_state.lista_productos if str(p.get('sku')).strip() == sku_buscar), None)
                    if encontrado:
                        productos_filtrados_y_ordenados.append(encontrado)
                    else:
                        # Opcional: Mostrar una pequeña advertencia si tipeaste mal un SKU de la lista
                        st.caption(f"⚠️ Nota: El SKU `{sku_buscar}` se saltará porque no existe en la base de datos.")
            else:
                # Si el campo está vacío, por defecto te muestra todos los productos sin orden especial
                productos_filtrados_y_ordenados = st.session_state.lista_productos

            # 3. Control de navegación sobre la lista resultante
            total = len(productos_filtrados_y_ordenados)
            
            if total == 0:
                st.info("Ninguno de los SKUs de la lista fue encontrado en la base de datos o la lista está vacía.")
            else:
                if st.session_state.index_navegacion >= total:
                    st.session_state.index_navegacion = 0
                
                idx = st.session_state.index_navegacion
                p = productos_filtrados_y_ordenados[idx]

                # Función local para mover el índice en la lista personalizada
                def mover_navegacion_personalizada(direccion):
                    st.session_state.index_navegacion = (st.session_state.index_navegacion + direccion) % total

                st.divider()

                # Controles superiores de navegación
                nav1, nav2, nav3 = st.columns([1, 2, 1])
                with nav1:
                    if st.button("⬅️ Anterior", use_container_width=True, key="btn_nav_ant_lista"):
                        mover_navegacion_personalizada(-1)
                        st.rerun()
                with nav2:
                    st.markdown(f"<h3 style='text-align: center; color: #f04;'>Producto {idx + 1} de {total}</h3>", unsafe_allow_html=True)
                with nav3:
                    if st.button("Siguiente ➡️", use_container_width=True, key="btn_nav_sig_lista"):
                        mover_navegacion_personalizada(1)
                        st.rerun()

                # Información del Producto actual
                st.markdown(f"**SKU Actual:** `{p['sku']}` | **Marca:** {p['marca']} | **Posición en tu lista:** {idx + 1}")
                st.subheader(p['nombre'])

                # Botón de edición rápida
                if st.button("🛠️ Editar este producto completo", key="btn_nav_edit_lista"):
                    st.session_state.producto_a_editar = p
                    st.success("Cargado en el editor. Cambia a la pestaña 'Crear / Editar'.")

                # Paneles de Copia interactivos
                col_v1, col_v2 = st.columns([2, 1])
                with col_v1:
                    cuadro_copiado_vtex("📄 Cuerpo VTEX (Descripción + Specs)", p.get('vtex_body', ''), height=450)
                
                with col_v2:
                    cuadro_copiado_vtex("🌐 Meta Descripción", p.get('meta', ''), height=200, font_size="14px")
                    cuadro_copiado_vtex("🏷️ Tags / Palabras", p.get('tags', ''), height=200, font_size="14px")
        
from selenium_stealth import stealth # <--- Asegúrate de tenerlo importado arriba

with tab_CatalogoVtex:
    st.header("🤖 Validador de Catálogo VTEX")
    st.markdown("""
    Este robot verifica si los SKUs existen en el Administrador. 
    **Nota:** La primera vez deberás iniciar sesión manualmente en la ventana que se abra.
    """)

    # 1. Inicializar la tabla en el estado de sesión
    if 'df_admin_vtex_final' not in st.session_state:
        st.session_state.df_admin_vtex_final = pd.DataFrame({
            "SKU": [""] * 10, 
            "Estado": ["Pendiente"] * 10
        })

    editor_vtex = st.data_editor(
        st.session_state.df_admin_vtex_final,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_vtex_admin_v20"
    )

    if st.button("🚀 INICIAR VALIDACIÓN EN VTEX", type="primary"):
        df_work = editor_vtex.copy()
        skus_reales = [str(s).strip() for s in df_work["SKU"] if str(s).strip() != ""]
        
        if not skus_reales:
            st.warning("⚠️ Ingresa al menos un SKU en la tabla.")
        else:
            # --- CONFIGURACIÓN DEL PERFIL INDEPENDIENTE ---
            options = webdriver.ChromeOptions()
            
            # Ruta a la carpeta que creaste en Documentos
            user_data_robot = os.path.join(os.path.expanduser("~"), "Documents", "vtex_automation_session")
            options.add_argument(f"--user-data-dir={user_data_robot}")
            options.add_argument("--start-maximized")
            
            # Evitar detección de automatización
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("--disable-blink-features=AutomationControlled")

            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            except Exception as e:
                st.error(f"❌ Error al abrir el navegador: {e}")
                st.stop()

            wait = WebDriverWait(driver, 25)
            
            # 2. Navegar al Admin
            URL_ADMIN = "https://ferreteriamarsella.myvtex.com/admin/catalog-products"
            driver.get(URL_ADMIN)
            
            # Pausa inicial: 15 seg para que cargue la sesión o te loguees la primera vez
            st.info("🕒 Esperando carga de página (Inicia sesión si es necesario)...")
            time.sleep(15) 

            progreso = st.progress(0)
            status_v = st.empty()
            resultados = []

            for i, sku in enumerate(skus_reales):
                progreso.progress((i + 1) / len(skus_reales))
                status_v.text(f"🔎 Validando en VTEX: {sku}")
                
                try:
                    # --- TU LÓGICA DE ESCRITURA ---
                    driver.switch_to.default_content() 
                    if "catalog-products" in driver.current_url:
                        if len(driver.find_elements(By.TAG_NAME, "iframe")) > 0:
                            try:
                                driver.switch_to.frame(0)
                            except: pass

                    xpath_vtex = "//input[contains(@placeholder, 'buscar') or @id='search-combobox']"
                    
                    try:
                        caja = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_vtex)))
                    except:
                        driver.execute_script("document.querySelector('button[aria-label=\"Search\"], .vtex-input-suffix').click();")
                        time.sleep(1)
                        caja = driver.switch_to.active_element

                    caja.click()
                    caja.send_keys(Keys.COMMAND + "a")
                    caja.send_keys(Keys.BACKSPACE)
                    time.sleep(0.5)

                    caja.send_keys(sku)
                    time.sleep(0.5)
                    caja.send_keys(Keys.ENTER)
                    
                    # --- ESPERA DE FILTRADO ---
                    time.sleep(5)

                    # --- LÓGICA DE VALIDACIÓN BILINGÜE ---
                    # Extraemos todo el texto visible de la página
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    
                    # Definimos las frases de "No existe" en ambos idiomas
                    mensajes_negativos = [
                        "No se han encontrado resultados", 
                        "No results found",
                        "Intenta usar diferentes términos", # Parte del mensaje en español
                        "Try using different search terms" # Parte del mensaje en inglés
                    ]
                    
                    # Verificamos si alguna de esas frases aparece en el texto visible
                    no_existe = any(mensaje in page_text for mensaje in mensajes_negativos)

                    if no_existe:
                        resultados.append("❌ NO EXISTE")
                    else:
                        # Si no hay mensajes de error, asumimos que el producto apareció en la tabla
                        resultados.append("✅ ENCONTRADO")

                except Exception as e:
                    resultados.append("⚠️ ERROR")
                    driver.switch_to.default_content()#Volver al raíz para
            
            driver.quit()
            status_v.success("¡Validación completada!")
            
            # Rellenar con vacíos para que coincida con el largo de la tabla
            while len(resultados) < len(df_work):
                resultados.append("")
                
            df_work["Estado"] = resultados
            st.session_state.df_admin_vtex_final = df_work
            st.rerun()

    # --- GENERADOR DE MENSAJE PARA SUPERVISOR ---
    st.divider()
    df_actual = st.session_state.df_admin_vtex_final
    faltantes = df_actual[df_actual["Estado"] == "❌ NO EXISTE"]["SKU"].tolist()

    if faltantes:
        st.error(f"Se encontraron {len(faltantes)} productos que no están en VTEX.")
        msg_supervisor = "Hola, los siguientes SKUs no aparecen en VTEX:\n\n" + "\n".join(faltantes)
        st.text_area("Copia este mensaje:", value=msg_supervisor, height=150)
        if st.button("📋 Copiar Reporte"):
            # Usamos un componente de JS simple para copiar
            components.html(f"""
                <script>
                navigator.clipboard.writeText(`{msg_supervisor}`);
                </script>
            """, height=0)
            st.toast("Reporte copiado")
            

                    
                    
# ---------------------------------------------------------
# PESTAÑA: GENERACIÓN MASIVA DE FICHAS TÉCNICAS (CON FILTROS AVANZADOS)
# ---------------------------------------------------------
with tab_masivo:
    st.header("🏭 Generación Masiva de Fichas Técnicas")
    st.markdown("""
    Genera fichas técnicas para múltiples productos de tu base de datos utilizando filtros avanzados.
    - Las imágenes de los productos pasarán automáticamente por el **Ajustador Inteligente (Auto-Trim)**.
    - Las fichas resultantes se guardarán en la carpeta `salidas/` como `FT-{SKU}.jpg`.
    """)

    productos_db = st.session_state.lista_productos

    if not productos_db:
        st.warning("⚠️ No hay productos en la base de datos. Primero carga algunos en la pestaña 'Productos'.")
    else:
        # --- NUEVO SELECTOR DE MODALIDAD DE FILTRO ---
        modo_seleccion = st.radio(
            "Selecciona el método de lote para producción:",
            ["✅ Todos los productos", "🏷️ Filtrar por Marca", "✏️ Elegir SKUs específicos"],
            horizontal=True,
            key="modo_masivo_avanzado"
        )

        skus_a_procesar = []

        # MODALIDAD 1: POR MARCA
        if modo_seleccion == "🏷️ Filtrar por Marca":
            # Extraer marcas únicas de la base de datos, limpiando espacios y omitiendo vacíos
            marcas_disponibles = sorted(list(set([p["marca"].strip() for p in productos_db if p.get("marca", "").strip()])))
            
            if marcas_disponibles:
                marca_elegida = st.selectbox("Selecciona la marca que deseas generar:", marcas_disponibles)
                # Filtrar SKUs que correspondan a la marca elegida
                skus_a_procesar = [p["sku"] for p in productos_db if p.get("marca", "").strip().lower() == marca_elegida.lower()]
                st.caption(f"🔎 Se encontraron {len(skus_a_procesar)} productos asociados a la marca **{marca_elegida}**.")
            else:
                st.warning("⚠️ No se encontraron marcas registradas en los productos de la base de datos.")

        # MODALIDAD 2: SELECCIÓN MANUAL (TABLA)
        elif modo_seleccion == "✏️ Elegir SKUs específicos":
            df_seleccion = pd.DataFrame([
                {"Seleccionar": False, "SKU": p["sku"], "Nombre": p["nombre"], "Marca": p.get("marca", "")}
                for p in productos_db
            ])
            df_editado = st.data_editor(
                df_seleccion,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn("📌", default=False),
                    "SKU": "Código",
                    "Nombre": "Producto",
                    "Marca": "Marca"
                },
                key="editor_seleccion_masiva_v2"
            )
            skus_a_procesar = df_editado[df_editado["Seleccionar"]]["SKU"].tolist()

        # MODALIDAD 3: TODO EL UNIVERSO DE LA DB
        else:
            skus_a_procesar = [p["sku"] for p in productos_db]

        # --- PANEL DE CONFIRMACIÓN E INICIO ---
        st.divider()
        if skus_a_procesar:
            st.info(f"📊 Lote preparado: Se procesarán **{len(skus_a_procesar)}** fichas técnicas.")
        else:
            st.warning("📋 No hay productos seleccionados o el criterio de búsqueda está vacío.")

        if st.button("🚀 INICIAR GENERACIÓN MASIVA", type="primary", use_container_width=True, key="btn_ejecutar_masivo_v2"):
            if not skus_a_procesar:
                st.error("Por favor, selecciona o filtra al menos un SKU válido antes de iniciar.")
            else:
                errores = []
                exitosos = 0
                total = len(skus_a_procesar)

                prog_bar = st.progress(0, text="Inicializando motor de renderizado...")
                status_text = st.empty()

                for i, sku in enumerate(skus_a_procesar):
                    prog_bar.progress((i + 1) / total, text=f"Progreso: {i+1}/{total} (SKU: {sku})")
                    status_text.text(f"🔄 Procesando y aplicando Auto-Trim al SKU: {sku}")

                    # 1. Buscar el producto en la sesión
                    producto = next((p for p in st.session_state.lista_productos if p.get("sku") == sku), None)
                    if not producto:
                        errores.append(f"{sku}: No encontrado en la base de datos local")
                        continue

                    nombre = producto.get("nombre", "")
                    specs_raw = producto.get("specs_solo", "")
                    marca = producto.get("marca", "")

                    # 2. Buscar foto original en la estructura local
                    foto_path = None
                    extensiones_img = [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]
                    nombres_a_buscar = [sku, f"{sku}_A", f"{sku}_1"]

                    for root, dirs, files in os.walk(CARPETA_FOTOS):
                        for nombre_base in nombres_a_buscar:
                            for ext in extensiones_img:
                                archivo_objetivo = f"{nombre_base}{ext}"
                                if archivo_objetivo in files:
                                    foto_path = os.path.join(root, archivo_objetivo)
                                    break
                            if foto_path: break
                        if foto_path: break
                    
                    if not foto_path:
                        for root, dirs, files in os.walk(CARPETA_FOTOS):
                            for f in files:
                                if f.startswith(sku) and f.lower().endswith(tuple(extensiones_img)):
                                    foto_path = os.path.join(root, f)
                                    break
                            if foto_path: break

                    # 3. Buscar logo de la marca
                    logo_path = None
                    if marca:
                        extensiones_logo = [".png", ".jpg", ".jpeg", ".webp", ".PNG", ".JPG", ".JPEG"]
                        for ext in extensiones_logo:
                            ruta_logo = os.path.join(CARPETA_LOGOS, f"{marca}{ext}")
                            if os.path.isfile(ruta_logo):
                                logo_path = ruta_logo
                                break
                        if not logo_path:
                            for f in os.listdir(CARPETA_LOGOS):
                                nombre_sin_ext = os.path.splitext(f)[0]
                                if nombre_sin_ext.lower() == marca.lower():
                                    logo_path = os.path.join(CARPETA_LOGOS, f)
                                    break

                    # 4. Validaciones de consistencia
                    if not nombre:
                        errores.append(f"{sku}: Estructura corrupta (Falta nombre)")
                        continue
                    if not specs_raw:
                        errores.append(f"{sku}: Estructura corrupta (Faltan especificaciones)")
                        continue
                    if not foto_path:
                        errores.append(f"{sku}: La imagen no existe en la carpeta '{CARPETA_FOTOS}'")
                        continue
                    if not logo_path:
                        errores.append(f"{sku}: No existe el logo corporativo para la marca '{marca}' en '{CARPETA_LOGOS}'")
                        continue

                    # 5. Pipeline de procesamiento: Ajuste Inteligente + Renderizado HTML/Jinja
                    try:
                        # Auto-Trim dinámico
                        imagen_recortada = ajustar_imagen_producto(foto_path, threshold=10)
                        
                        # Guardado temporal de la imagen procesada en memoria física
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
                            imagen_recortada.save(tmp_img.name, format="PNG")
                            foto_para_ficha = tmp_img.name

                        # Construcción del documento
                        specs_parsed = parse_specs(specs_raw)
                        out = generar_documento(
                            nombre=nombre,
                            datos=specs_parsed,
                            sku=sku,
                            foto_producto=foto_para_ficha, # Imagen limpia sin fondos excedentes
                            logo_marca=logo_path,
                            skus_matriz=sku
                        )
                        
                        # Reubicación a destino final en carpeta 'salidas'
                        ruta_final = os.path.join("salidas", f"FT-{sku}.jpg")
                        if os.path.exists(out):
                            os.replace(out, ruta_final)
                        else:
                            if out != ruta_final and os.path.exists(out):
                                os.replace(out, ruta_final)
                        
                        # Liberación de basura del sistema
                        try: os.unlink(foto_para_ficha)
                        except: pass
                        
                        exitosos += 1
                        
                    except Exception as e:
                        errores.append(f"{sku}: Falla en el pipeline masivo - {str(e)}")

                # --- CIERRE DE PROCESO ---
                prog_bar.empty()
                status_text.empty()

                if exitosos > 0:
                    st.success(f"✅ ¡Lote finalizado! Se generaron y optimizaron con éxito {exitosos} fichas en la carpeta 'salidas/'.")
                if errores:
                    st.warning(f"⚠️ El proceso terminó con {len(errores)} inconsistencias:")
                    with st.expander("Desplegar reporte detallado de errores"):
                        for err in errores:
                            st.write(f"❌ {err}")
                else:
                    st.balloons()

# --- PESTAÑA: SUBIDA CMS VTEX ---
with tab_cms: 
    st.header("🖼️ Subida Masiva a Media Gallery VTEX")
    st.markdown("""
    1. Selecciona las Fichas Técnicas generadas (en carpeta `salidas`).
    2. El robot las subirá una a una y validará que aparezcan en el CMS.
    3. Al finalizar, obtendrás la URL pública de cada archivo.
    """)

    fichas_disponibles = [f for f in os.listdir("salidas") if f.endswith(".jpg")]
    fichas_seleccionadas = st.multiselect("Selecciona fichas para subir:", fichas_disponibles)

    if st.button("🚀 INICIAR CARGA AL CMS", type="primary"):
        if not fichas_seleccionadas:
            st.warning("Selecciona al menos una ficha.")
        else:
            options = webdriver.ChromeOptions()
            user_data_robot = os.path.join(os.path.expanduser("~"), "Documents", "vtex_automation_session")
            options.add_argument(f"--user-data-dir={user_data_robot}")
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 20)
                driver.get("https://ferreteriamarsella.myvtex.com/admin/new-cms/media-gallery")
                time.sleep(10) # Aumentado a 10 por estabilidad inicial
                
                resultados_cms = []
                progreso_cms = st.progress(0)

                for i, nombre_archivo in enumerate(fichas_seleccionadas):
                    ruta_completa = os.path.abspath(os.path.join("salidas", nombre_archivo))
                    progreso_cms.progress((i + 1) / len(fichas_seleccionadas))
                    
                    try:
                        # --- PASO A: MANEJO DE IFRAME ---
                        driver.switch_to.default_content()
                        time.sleep(2)
                        
                        iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        if len(iframes) > 0:
                            driver.switch_to.frame(0)

                        # --- PASO B: SUBIDA DE ARCHIVO ---
                        input_xpath = "//input[@type='file']"
                        wait.until(EC.presence_of_element_located((By.XPATH, input_xpath)))
                        input_file = driver.find_element(By.XPATH, input_xpath)
                        
                        driver.execute_script(
                            "arguments[0].style.display = 'block'; arguments[0].style.opacity = '1'; arguments[0].style.width = '100px'; arguments[0].style.height = '100px';", 
                            input_file
                        )
                        input_file.send_keys(ruta_completa)
                        
                        # --- PASO C: VALIDACIÓN ---
                        archivo_subido_ok = False
                        for intento in range(15):
                            # Selector basado en Captura de pantalla 2026-05-08 a las 7.37.26 p. m.
                            primer_card = driver.find_elements(By.CSS_SELECTOR, "[data-testid='media-gallery-card']")
                            if primer_card:
                                title_vtex = primer_card[0].get_attribute("title")
                                if nombre_archivo in title_vtex:
                                    archivo_subido_ok = True
                                    break
                            time.sleep(3)
                        
                        if archivo_subido_ok:
                            # 1. LOCALIZAR LA TARJETA
                            # Re-localizamos para asegurar que tenemos la versión fresca del elemento
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='media-gallery-card']")))
                            tarjeta = driver.find_elements(By.CSS_SELECTOR, "[data-testid='media-gallery-card']")[0]

                            # 2. SIMULAR HOVER (Mover el mouse encima del cuadro)
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(driver)
                            actions.move_to_element(tarjeta).perform() # Aquí movemos el mouse físicamente
                            time.sleep(1.5) # Esperamos a que la animación de VTEX muestre los botones

                            # 3. CLIC EN LOS 3 PUNTOS
                            # Ahora que el mouse está encima, el botón debería ser clicable
                            btn_puntos = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='media-gallery-menu']")))
                            btn_puntos.click()
                            time.sleep(1.5)
                            
                            # 4. CLIC EN COPIAR URL
                            btn_copy = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='media-gallery-menu-copy-url']")))
                            btn_copy.click()
                            time.sleep(1)
                            
                            import pyperclip
                            url_vtex = pyperclip.paste()
                            
                            # Limpiar portapapeles para la siguiente vuelta (opcional)
                            # pyperclip.copy('') 

                            resultados_cms.append({"Archivo": nombre_archivo, "Estado": "✅ Subido", "URL": url_vtex})
                        else:
                            resultados_cms.append({"Archivo": nombre_archivo, "Estado": "❌ No apareció en galería", "URL": ""})

                    except Exception as e_inner:
                        # Corregida la identación del bloque de error interno
                        resultados_cms.append({"Archivo": nombre_archivo, "Estado": "❌ Error interno", "URL": str(e_inner)[:100]})

                driver.quit()
                st.subheader("Resultados de la carga")
                st.table(pd.DataFrame(resultados_cms))
                
            except Exception as e:
                st.error(f"Error crítico en el driver: {e}")
                
# =========================================================
# PESTAÑA: SINCRONIZADOR DE CATÁLOGO VTEX (PARTE 1)
# =========================================================
with tab_creacionvtex: # O tab_vtex_sync si la definiste en la lista de tabs
    st.header("🔗 Sincronización de Catálogo (Draft)")
    st.markdown("""
    Esta herramienta automatiza el llenado de información dentro del nuevo editor de VTEX.
    - **Paso 1:** Busca el SKU y entra al editor.
    - **Paso 2:** Rellena Descripción y Especificaciones.
    - **Paso 3:** Configura la Categoría Global en SEO.
    """)

    # 1. Selección de producto desde la base de datos local
    productos_db = st.session_state.get('lista_productos', [])
    
    if not productos_db:
        st.warning("No hay productos cargados en la base de datos.")
    else:
        opciones_busqueda = [f"{p['sku']} - {p['nombre']}" for p in productos_db]
        seleccion_prod = st.selectbox("Selecciona producto para sincronizar:", opciones_busqueda)
        
        # Extraemos los datos del producto seleccionado
        sku_target = seleccion_prod.split(" - ")[0]
        producto_data = next(p for p in productos_db if p['sku'] == sku_target)

        if st.button("🚀 INICIAR SINCRONIZACIÓN VTEX", type="primary"):
            # Configuración de Chrome con Sesión Persistente (Alexssander Lopez)
            options = webdriver.ChromeOptions()
            user_data_robot = os.path.join(os.path.expanduser("~"), "Documents", "vtex_automation_session")
            options.add_argument(f"--user-data-dir={user_data_robot}")
            options.add_argument("--start-maximized")
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 25)
                
                # --- PASO 1: BÚSQUEDA Y ACCESO ---
                url_admin = f"https://ferreteriamarsella.myvtex.com/admin/catalog/products?q={sku_target}"
                driver.get(url_admin)
                
                # Clic en el producto (basado en Captura 8.06.18 p.m.)
                fila = wait.until(EC.element_to_be_clickable((By.XPATH, f"//td[contains(text(), '{sku_target}')]")))
                fila.click()
                time.sleep(6) # Tiempo para carga del editor pesado

                # --- PASO 2: ENTRAR AL IFRAME (RACCOON) ---
                # Localización basada en Captura 8.19.02 p.m.
                driver.switch_to.default_content()
                iframe_selector = "iframe[id^='raccoon-iframe']"
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector)))
                driver.switch_to.frame(driver.find_element(By.CSS_SELECTOR, iframe_selector))
                st.toast("✅ Dentro del Iframe de VTEX")

                # --- PASO 3: RELLENAR DESCRIPCIÓN (Editor Quill) ---
                # Selector basado en Captura 8.36.23 p.m.
                editor_desc = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".ql-editor")))
                editor_desc.click()
                
                # Limpieza con comandos de Mac (M1)
                editor_desc.send_keys(Keys.COMMAND + "a")
                editor_desc.send_keys(Keys.BACKSPACE)
                
                # Inyección de descripción + specs
                editor_desc.send_keys(producto_data['vtex_body'])
                st.toast("✅ Descripción cargada")

                # --- PASO 4: NAVEGAR A SEO Y CATEGORÍA GLOBAL ---
                # Clic en el menú lateral SEO
                btn_seo = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'SEO')]")))
                btn_seo.click()
                time.sleep(2)

                # Input de Categoría Global (Captura 8.37.33 p.m. / 8.38.59 p.m.)
                input_cat = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='AcceptedGlobalCategoryId']")))
                
                # Aquí puedes decidir la categoría según tu lógica
                cat_texto = "Bricolaje" 
                input_cat.send_keys(cat_texto)
                time.sleep(3) # Espera al árbol desplegable

                # Selección del ítem en el árbol de Ant Design
                try:
                    opcion_arbol = wait.until(EC.element_to_be_clickable((
                        By.XPATH, f"//div[contains(@class, 'ant-select-tree-title') and contains(text(), '{cat_texto}')]"
                    )))
                    opcion_arbol.click()
                    st.success(f"✅ Categoría '{cat_texto}' vinculada.")
                except:
                    st.warning("⚠️ Menú de categorías no detectado, selecciónalo manualmente.")

                # Dejamos el driver abierto o podrías agregar el clic en Guardar aquí
                st.info("Sincronización parcial completada. Revisa los datos antes de Guardar.")

            except Exception as e:
                st.error(f"Error en la sincronización: {e}")
            # driver.quit() # Comentado para que puedas ver el resultado