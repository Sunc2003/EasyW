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


st.title("🛠️ Herramientas")

tab_fichas, tab_creacion, tab_CatalogoVtex, tab_masivo, tab_cms, tab_creacionvtex, tab_pdf, tab_robot, tab_ohiggins, tab_kukko, tab_gys, tab_ohiggins2, tab_femi, tab_ohiggins20, tab_marsellitta, tab_samsung= st.tabs([
    "Fichas Tecnicas", 
    "Productos",
    "Buscador Vtex",
    "Generacion masiva",
    "Carga de fichas tecnicas",
    "Sincronizacion con Vtex",
    "PDF a JPG", 
    "URL Web Marsella", 
    "Fichas Tecnicas O'Higgins",
    "Fichas Tecnicas KUKKO",
    "Fichas Tecnicas GYS",
    "Descarga Imagen ohiggins",
    "Fichas Tecnicas Femi",
    "Fichas Tecnicas O'Higgins Mitutoyo ",
    "Imagen Producto Marsella",
    "Buscador Samsung"
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
        
        foto_f = st.file_uploader("📸 Subir foto manualmente", type=["jpg", "png"], key="foto_f")
        ruta_auto = st.session_state.get("foto_local_path")
        if ruta_auto and not foto_f:
            st.success(f"🖼️ Foto detectada: `{os.path.basename(ruta_auto)}`")
            st.image(ruta_auto, width=150)
        
        logo_f = st.file_uploader("🏷 Logo marca *", type=["jpg", "png"], key="logo_f")
        ruta_logo_auto_mostrar = st.session_state.get("logo_auto_path")
        if ruta_logo_auto_mostrar and not logo_f:
            st.success(f"🏷️ Logo detectado para la marca: `{os.path.basename(ruta_logo_auto_mostrar)}`")
            st.image(ruta_logo_auto_mostrar, width=100)
        specs_f = st.text_area("Especificaciones *", height=250, key="specs_auto_field")
        
        if st.button("📄 Generar Ficha Técnica", use_container_width=True, type="primary"):
            # --- Obtener SKU actual desde session_state ---
            sku_actual = st.session_state.get("sku_input_manual", "").strip()
            
            # --- Foto final ---
            foto_final = None
            if foto_f:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    tf.write(foto_f.read())
                    foto_final = tf.name
            elif ruta_auto:
                foto_final = ruta_auto
            
            # --- Logo final (priorizar manual; si no, usar el automático actualizado) ---
            ruta_logo_auto = st.session_state.get("logo_auto_path")   # ← dentro del botón
            logo_path = None
            if logo_f:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tl:
                    tl.write(logo_f.read())
                    logo_path = tl.name
            elif ruta_logo_auto:
                logo_path = ruta_logo_auto
            
            if nombre_f and sku_actual and foto_final and logo_path and specs_f:
                specs_parsed = parse_specs(specs_f)
                out = generar_documento(
                    nombre=nombre_f,
                    datos=specs_parsed,
                    sku=sku_actual,
                    foto_producto=foto_final,
                    logo_marca=logo_path,
                    skus_matriz=sku_actual
                )
                # Guardar vista previa
                ruta_salida = os.path.join("salidas", f"FT-{sku_actual}.jpg")
                os.replace(out, ruta_salida)
                st.session_state.preview_image = ruta_salida
                st.success("✅ Ficha Generada")
            else:
                st.error("Faltan datos obligatorios (nombre, SKU, foto, logo, especificaciones).")
    
    with col_f2:
        st.subheader("Vista Previa")
        if st.session_state.preview_image:
            st.image(st.session_state.preview_image, width=400)
            nombre_archivo_ft = os.path.basename(st.session_state.preview_image)
            boton_copiar_texto(nombre_archivo_ft, label=f"📋 Copiar: {nombre_archivo_ft}")
            with open(st.session_state.preview_image, "rb") as f:
                st.download_button("⬇️ Descargar Ficha", f, file_name=nombre_archivo_ft)
        else:
            st.info("Escribe un SKU arriba para auto-rellenar los datos guardados.")
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
# PESTAÑA 5: ROBOT KUKKO (FINAL - CON BOTONES DE COPIADO)
# ---------------------------------------------------------
with tab_kukko:
    st.header("🔧 Extractor de Fichas Kukko")
    st.markdown("""
    **Modo Automático:**
    1. Pega la descripción larga.
    2. Se busca el PDF.
    3. **Te entrega el Link listo para copiar.**
    """)

    if 'df_kukko' not in st.session_state:
        st.session_state.df_kukko = pd.DataFrame({"DESCRIPCION": [""] * 10})

    editor_kukko = st.data_editor(
        st.session_state.df_kukko,
        num_rows="dynamic",
        key="editor_kukko_widget",
        column_config={
            "DESCRIPCION": st.column_config.TextColumn("Descripción Completa", required=True)
        }
    )

    if st.button("BUSCAR LINKS", type="primary"):
        df_work = editor_kukko.copy()
        df_work = df_work[df_work["DESCRIPCION"].astype(str).str.strip() != ""]

        if len(df_work) == 0:
            st.warning("Tabla vacía. Pega tus descripciones.")
        else:
            resultados = []
            
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            except:
                st.error("Error al iniciar Chrome Driver.")
                st.stop()
            
            barra = st.progress(0)
            total = len(df_work)
            status_k = st.empty()

            for i, (idx, row) in enumerate(df_work.iterrows()):
                texto_original = str(row["DESCRIPCION"])
                
                # --- PASO 1: EXTRAER Y LIMPIAR ---
                match = re.search(r'\((.*?)\)', texto_original)
                if match:
                    codigo_modelo = match.group(1).strip()
                    codigo_modelo = codigo_modelo.replace("‑", "-").replace("–", "-").replace("—", "-")
                else:
                    resultados.append({"Descripción": texto_original, "Modelo": "---", "Link PDF": "Sin paréntesis"})
                    continue
                
                barra.progress((i+1)/total)
                status_k.text(f"🔎 ({i+1}/{total}) Procesando: {codigo_modelo}")

                try:
                    # --- PASO 2: BUSCAR ---
                    driver.get("https://www.kukko.com/es")
                    time.sleep(2)
                    
                    try:
                        driver.find_element(By.ID, "prodsearchDesktop").click()
                        time.sleep(0.5)
                        driver.switch_to.active_element.send_keys(codigo_modelo + Keys.ENTER)
                        time.sleep(3)
                    except Exception as e:
                        raise Exception(f"Error buscador: {e}")

                    # --- PASO 3: SELECCIONAR (H3) ---
                    target_link = ""
                    encontrados_debug = []
                    
                    try:
                        resultados_busqueda = driver.find_elements(By.CLASS_NAME, "resultLink")
                        for res in resultados_busqueda:
                            try:
                                titulo_h3 = res.find_element(By.TAG_NAME, "h3").text.strip()
                                titulo_clean = titulo_h3.replace("‑", "-").replace("–", "-").replace("—", "-")
                                encontrados_debug.append(titulo_clean)
                                
                                if titulo_clean.lower() == codigo_modelo.lower():
                                    target_link = res.get_attribute("href")
                                    break
                                elif titulo_clean.startswith(codigo_modelo):
                                    target_link = res.get_attribute("href")
                                    break
                            except:
                                continue
                        
                        if target_link:
                            driver.get(target_link)
                            time.sleep(2.5)
                        else:
                            if len(resultados_busqueda) > 0:
                                raise Exception(f"Vi productos ({', '.join(encontrados_debug[:3])}...) pero ninguno era '{codigo_modelo}'")
                            else:
                                pass 

                    except Exception as ex_nav:
                        raise ex_nav

                    # --- PASO 4: EXTRAER LINK ---
                    try:
                        pdf_element = driver.find_element(By.XPATH, "//a[contains(@href, 'ImageServer')]")
                        link_final = pdf_element.get_attribute("href")
                        
                        resultados.append({
                            "Descripción": texto_original,
                            "Modelo": codigo_modelo,
                            "Link PDF": link_final
                        })
                    except:
                        try:
                            pdf_element = driver.find_element(By.XPATH, "//a[contains(text(), 'Ficha de datos')]")
                            link_final = pdf_element.get_attribute("href")
                            resultados.append({
                                "Descripción": texto_original,
                                "Modelo": codigo_modelo,
                                "Link PDF": link_final
                            })
                        except:
                            resultados.append({
                                "Descripción": texto_original,
                                "Modelo": codigo_modelo,
                                "Link PDF": "No se encontró botón PDF"
                            })

                except Exception as e:
                    resultados.append({
                        "Descripción": texto_original,
                        "Modelo": codigo_modelo,
                        "Link PDF": f"Error: {str(e)}"
                    })

            driver.quit()
            barra.empty()
            status_k.success("¡Búsqueda completada!")
            
            st.divider()
            
            # --- ZONA DE COPIADO RÁPIDO ---
            st.subheader("Links Listos para Copiar")
            st.info("Haz clic en el icono a la derecha de cada link para copiarlo.")
            
            for item in resultados:
                # Solo mostramos el bloque de copiado si es un link válido
                if "http" in item["Link PDF"]:
                    st.caption(f"**{item['Modelo']}**")
                    # st.code genera un bloque con botón de copiar automático
                    st.code(item["Link PDF"], language="text")
                else:
                    st.error(f"{item['Modelo']}: {item['Link PDF']}")

            # Tabla resumen al final
            with st.expander("Ver Tabla Resumen"):
                st.data_editor(pd.DataFrame(resultados), use_container_width=True)
                
# ---------------------------------------------------------
# PESTAÑA 6: ROBOT GYS (URL DIRECTA - ULTRARÁPIDO)
# ---------------------------------------------------------
with tab_gys:
    st.header("GYS (Generador de Links)")
    st.markdown("""
    1. Pega tu SKU y Descripción.
    2. Se extrae el código GYS `(XXXXXX)` y **calcula el link del PDF**.
    3. Copia el link con un clic. (No se descarga nada).
    """)

    # --- INICIALIZAR ESTADO DE TABLA GYS ---
    if 'df_gys' not in st.session_state:
        st.session_state.df_gys = pd.DataFrame({
            "SKU": [""] * 15,
            "DESCRIPCION": [""] * 15
        })

    editor_gys = st.data_editor(
        st.session_state.df_gys,
        num_rows="dynamic",
        height=400,
        use_container_width=True,
        key="editor_gys_widget",
        column_config={
            "SKU": st.column_config.TextColumn("SKU Marsella (Ref)", required=True),
            "DESCRIPCION": st.column_config.TextColumn("Descripción (Contiene el código GYS)", required=True)
        }
    )

    c_btn1, c_btn2 = st.columns([1, 4])

    with c_btn1:
        if st.button("GENERAR LINKS", type="primary", use_container_width=True):
            
            # Filtramos filas válidas
            df_work = editor_gys.copy()
            df_work = df_work[df_work["SKU"].astype(str).str.strip() != ""]
            df_work = df_work[df_work["DESCRIPCION"].astype(str).str.strip() != ""]

            if len(df_work) == 0:
                st.warning("La tabla está vacía o incompleta.")
            else:
                resultados = []
                
                # --- PROCESO INSTANTÁNEO ---
                for i, (index, row) in enumerate(df_work.iterrows()):
                    sku_marsella = str(row["SKU"]).strip()
                    desc_original = str(row["DESCRIPCION"]).strip()
                    
                    # 1. EXTRAER CÓDIGO
                    match = re.search(r'\((.*?)\)', desc_original)
                    
                    if match:
                        codigo_gys = match.group(1).strip()
                        # 2. GENERAR URL MAGICA
                        url_pdf = f"https://planet.gys.fr/pdf/datasheet/es/{codigo_gys}.pdf"
                        
                        resultados.append({
                            "SKU": sku_marsella,
                            "Código GYS": codigo_gys,
                            "Link PDF": url_pdf
                        })
                    else:
                        resultados.append({
                            "SKU": sku_marsella,
                            "Código GYS": "---",
                            "Link PDF": "No se encontró código entre paréntesis"
                        })

                st.success(f"✅ ¡{len(resultados)} Links generados!")
                st.divider()

                # --- ZONA DE COPIADO ---
                st.subheader("Links Listos para Copiar")
                st.info("Haz clic en el icono a la derecha del link para copiar.")

                for item in resultados:
                    if "http" in item["Link PDF"]:
                        st.markdown(f"**SKU: {item['SKU']}** (Ref: {item['Código GYS']})")
                        st.code(item["Link PDF"], language="text")
                    else:
                        st.error(f"SKU {item['SKU']}: {item['Link PDF']}")

                with st.expander("Ver Tabla Resumen"):
                    st.data_editor(
                        pd.DataFrame(resultados), 
                        use_container_width=True,
                         column_config={
                            "Link PDF": st.column_config.LinkColumn("Enlace Generado")
                        }
                    )

    with c_btn2:
        if st.button("🗑️ Limpiar Tabla", key="limpiar_tab6"):
            st.session_state.df_gys = pd.DataFrame({"SKU": [""] * 15, "DESCRIPCION": [""] * 15})
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


# ---------------------------------------------------------
# PESTAÑA 8: ROBOT FEMI (V24 - INYECCIÓN BASE64)
# ---------------------------------------------------------
with tab_femi:
    st.header("🖨️ Robot Femi (Ficha Blindada V24)")
    st.markdown("""
    **Solución Final V24:**
    1. Descarga la imagen en memoria.
    2. La convierte a código **Base64** e inyecta los pixeles directamente en el HTML.
    3. Genera el PDF (La imagen saldrá sí o sí porque ya es parte del código).
    """)

    if 'df_femi' not in st.session_state:
        st.session_state.df_femi = pd.DataFrame({
            "SKU": [""] * 10,
            "DESCRIPCION": [""] * 10
        })

    editor_femi = st.data_editor(
        st.session_state.df_femi,
        num_rows="dynamic",
        key="editor_femi_widget_v24",
        column_config={
            "SKU": st.column_config.TextColumn("SKU Marsella", required=True),
            "DESCRIPCION": st.column_config.TextColumn("Descripción (con ID entre paréntesis)", required=True)
        }
    )

    if st.button("🚀 GENERAR CON BASE64", type="primary", key="btn_femi_start_v24"):
        
        try:
            import fitz  # PyMuPDF
            import requests # Para descargar la imagen antes de inyectarla
        except ImportError:
            st.error("⚠️ Faltan librerías. Instala: pip install pymupdf requests")
            st.stop()

        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from urllib.parse import quote 
        import base64
        
        df_work = editor_femi.copy()
        df_work = df_work[df_work["DESCRIPCION"].astype(str).str.strip() != ""]

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
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 15)
            except Exception as e:
                st.error(f"Error driver: {e}")
                st.stop()

            with zipfile.ZipFile(resultados_zip, 'w') as zf:
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    sku_marsella = str(row["SKU"]).strip()
                    desc_original = str(row["DESCRIPCION"]).strip()
                    
                    progreso.progress((i + 1) / total)
                    
                    match = re.search(r'\((.*?)\)', desc_original)
                    if not match:
                        log_errores.append(f"{sku_marsella}: No encontré ID entre paréntesis")
                        continue
                    
                    id_producto = match.group(1).strip()
                    status.text(f"💉 ({i+1}/{total}) Inyectando Imagen: {id_producto}...")

                    try:
                        # 1. BÚSQUEDA
                        id_safe = quote(id_producto)
                        driver.get(f"https://www.femi.it/es/ricerca.php?q={id_safe}&brand=femi")
                        
                        try: wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "li.grid-item")))
                        except: pass
                        
                        tarjetas = driver.find_elements(By.CSS_SELECTOR, "li.grid-item")
                        link_final = None
                        for t in tarjetas:
                            if id_producto.lower() in t.text.lower():
                                link_final = t.find_element(By.TAG_NAME, "a").get_attribute("href")
                                break
                        if not link_final and len(tarjetas) == 1:
                            link_final = tarjetas[0].find_element(By.TAG_NAME, "a").get_attribute("href")
                        
                        if not link_final:
                            log_errores.append(f"{sku_marsella}: No encontrado")
                            continue

                        # 2. IR A LA FICHA
                        driver.get(link_final)
                        
                        # Obtener URL de la imagen REAL antes de tocar nada
                        img_url = None
                        try:
                            # Esperar a que cargue
                            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".col-foto img")))
                            # Intentar sacar la src
                            img_elem = driver.find_element(By.CSS_SELECTOR, ".col-foto img")
                            img_url = img_elem.get_attribute("src")
                            # Si hay un link padre (zoom), mejor usar ese
                            try:
                                parent_link = driver.find_element(By.CSS_SELECTOR, ".col-foto a")
                                if parent_link.get_attribute("href"):
                                    img_url = parent_link.get_attribute("href")
                            except: pass
                        except:
                            log_errores.append(f"{sku_marsella}: No encontré URL de imagen")

                        # --- FASE 3: DESCARGA Y CONVERSIÓN A BASE64 (PYTHON) ---
                        b64_string = ""
                        if img_url:
                            try:
                                response = requests.get(img_url, timeout=5)
                                if response.status_code == 200:
                                    b64_data = base64.b64encode(response.content).decode('utf-8')
                                    b64_string = f"data:image/jpeg;base64,{b64_data}"
                            except:
                                pass # Si falla descarga, quedará vacío

                        # --- FASE 4: INYECCIÓN QUIRÚRGICA ---
                        driver.execute_script(f"""
                            // 1. Limpieza de basura y Cookies (V22)
                            const selectoresBasura = [
                                '#iubenda-cs-banner', '.iubenda-cs-banner', '.iubenda-banner-content', 
                                '#cookie-notice', '.cookie-bar', '#iubenda-cs-badge', 
                                'header', 'footer', '.breadcrumbs', '.share-block', '.back-to-top',
                                '.allegati', '#allegati', '.btn-pdf-stampa', '.hide-print', '.gallery-thumbnail'
                            ];
                            selectoresBasura.forEach(sel => {{ document.querySelectorAll(sel).forEach(el => el.remove()); }});

                            // Limpieza por texto (Cookies)
                            const divs = document.querySelectorAll('div, section');
                            divs.forEach(div => {{
                                const style = window.getComputedStyle(div);
                                if ((style.position === 'fixed' || style.position === 'absolute') && div.innerText.toLowerCase().includes('cookies')) {{
                                    div.remove();
                                }}
                            }});

                            // 2. INYECCIÓN DE LA IMAGEN BASE64
                            var base64Img = "{b64_string}";
                            var imgContainer = document.querySelector('.col-foto');
                            
                            if (imgContainer && base64Img) {{
                                // Borramos todo lo que había (galerías, scripts, basura)
                                imgContainer.innerHTML = '';
                                
                                // Creamos la imagen estática
                                var newImg = document.createElement('img');
                                newImg.src = base64Img;
                                newImg.style.width = '100%';
                                newImg.style.maxWidth = '500px'; // Tamaño controlado
                                newImg.style.height = 'auto';
                                newImg.style.display = 'block';
                                newImg.style.margin = '0 auto'; // Centrada
                                
                                imgContainer.appendChild(newImg);
                            }}
                        """)
                        time.sleep(1)

                        # --- FASE 5: GENERAR PDF ---
                        pdf_data_b64 = driver.execute_cdp_cmd("Page.printToPDF", {
                            "printBackground": True,
                            "paperWidth": 8.27,
                            "paperHeight": 11.69,
                            "marginTop": 0.2,
                            "marginBottom": 0.2,
                            "marginLeft": 0.2,
                            "marginRight": 0.2,
                            "pageRanges": "1",
                            "preferCSSPageSize": True
                        })

                        pdf_bytes = base64.b64decode(pdf_data_b64['data'])

                        if pdf_bytes:
                            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                            page = doc.load_page(0)
                            pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0)) 
                            img_data = pix.tobytes("jpg")
                            zf.writestr(f"FT-{sku_marsella}.jpg", img_data)
                        else:
                            log_errores.append(f"{sku_marsella}: Falló PDF")

                    except Exception as e:
                        log_errores.append(f"{sku_marsella}: Error - {str(e)}")

            driver.quit()
            status.success("✅ ¡Fichas Blindadas V24 Generadas!")
            progreso.empty()

            st.download_button(
                label="📦 Descargar Fichas (ZIP Final)",
                data=resultados_zip.getvalue(),
                file_name="Fichas_Femi_V24_Base64.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

            if log_errores:
                with st.expander(f"⚠️ Errores ({len(log_errores)})"):
                    st.write(log_errores)

    if st.button("🗑️ Limpiar Tabla", key="clean_femi_v24"):
        st.session_state.df_femi = pd.DataFrame({"SKU": [""] * 10, "DESCRIPCION": [""] * 10})
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
    st.header("Skus a crear")
    
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

    # --- Estado para guardar el bloque y las validaciones ---
    if "raw_block" not in st.session_state:
        st.session_state.raw_block = ""
    if "validate_meta_len" not in st.session_state:
        st.session_state.validate_meta_len = 0
    if "validate_specs_lines" not in st.session_state:
        st.session_state.validate_specs_lines = 0

    # Función que se ejecuta en cada cambio del text_area
    def actualizar_validaciones():
        texto = st.session_state.raw_block_area
        # Extraer meta descripción y especificaciones
        def extraer_rapido(ini, fin, txt):
            pattern = f"{ini}(.*?)(?={re.escape(fin)}|$)"
            m = re.search(pattern, txt, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else ""
        
        meta = extraer_rapido("Meta descripción.*?:", "Palabras sustitutas:", texto)
        specs = extraer_rapido("Especificaciones Técnicas:", "Meta descripción", texto)
        
        st.session_state.validate_meta_len = len(meta)
        lineas_specs = specs.split('\n') if specs else []
        st.session_state.validate_specs_lines = len([l for l in lineas_specs if l.strip() != ""])

    # Área de carga (con callback en tiempo real)
    with st.expander("➕ Cargar Nuevo Producto (pegar bloque)", expanded=False):
        raw_text = st.text_area(
            "Pega el bloque completo aquí (SKU, Nombre, Marca, Descripción, Especificaciones, Meta, Tags):",
            value=st.session_state.raw_block,
            height=300,
            key="raw_block_area",
            on_change=actualizar_validaciones,
            help="Se validará automáticamente la meta (≤160 caracteres) y las especificaciones (≤15 líneas)."
        )
        
        # Mostrar validaciones en tiempo real
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            meta_len = st.session_state.validate_meta_len
            if meta_len > 160:
                st.error(f"❌ Meta descripción: {meta_len} / 160 caracteres (excede el límite)")
            else:
                st.success(f"✅ Meta descripción: {meta_len} / 160 caracteres")
        with col_v2:
            specs_lines = st.session_state.validate_specs_lines
            if specs_lines > 15:
                st.error(f"❌ Especificaciones: {specs_lines} / 15 líneas (excede el límite)")
            else:
                st.success(f"✅ Especificaciones: {specs_lines} / 15 líneas")
        
        # Botón guardar (con validación final)
        if st.button("📦 Procesar y guardar producto", type="primary"):
            if not raw_text.strip():
                st.error("❌ El bloque está vacío. Pega el contenido.")
            else:
                # Parseo completo
                lineas = raw_text.strip().split('\n')
                primera = lineas[0]
                partes = primera.split('\t')
                
                if len(partes) >= 3:
                    sku_det = partes[0].strip()
                    nom_det = partes[1].strip()
                    marca_det = partes[2].strip()
                elif len(partes) == 2:
                    sku_det = partes[0].strip()
                    nom_det = partes[1].strip()
                    marca_det = ""
                else:
                    sku_m = re.search(r'([A-Z0-9\-]+)', primera)
                    sku_det = sku_m.group(1) if sku_m else "S/N"
                    nom_det = primera.replace(sku_det, "").strip()
                    marca_det = ""

                def extraer(ini, fin, txt):
                    pattern = f"{ini}(.*?)(?={re.escape(fin)}|$)"
                    m = re.search(pattern, txt, re.DOTALL | re.IGNORECASE)
                    return m.group(1).strip() if m else ""

                d = extraer("Descripción del producto:", "Especificaciones Técnicas:", raw_text)
                s = extraer("Especificaciones Técnicas:", "Meta descripción", raw_text)
                m = extraer("Meta descripción.*?:", "Palabras sustitutas:", raw_text)
                t = extraer("Palabras sustitutas:", "FIN_IMAGINARIO", raw_text)
                vtex_body = f"{d}\n\n\n\nEspecificaciones Técnicas:\n{s}"
                
                # Validaciones finales (aunque ya están mostradas)
                errores = []
                if len(m) > 160:
                    errores.append(f"Meta descripción tiene {len(m)} caracteres (máx 160)")
                lineas_specs = s.split('\n') if s else []
                num_lineas = len([l for l in lineas_specs if l.strip() != ""])
                if num_lineas > 15:
                    errores.append(f"Especificaciones tienen {num_lineas} líneas (máx 15)")
                
                if errores:
                    for err in errores:
                        st.error(f"❌ {err}")
                    st.info("✏️ Corrige el bloque de texto y vuelve a intentar.")
                else:
                    nuevo = {
                        "sku": sku_det,
                        "nombre": nom_det,
                        "marca": marca_det,
                        "desc_solo": d,
                        "specs_solo": s,
                        "vtex_body": vtex_body.strip(),
                        "meta": m.strip(),
                        "tags": t.strip()
                    }
                    st.session_state.lista_productos.append(nuevo)
                    guardar_en_base_datos(st.session_state.lista_productos)
                    st.success(f"✅ Producto {sku_det} guardado correctamente.")
                    # Limpiar todo
                    st.session_state.raw_block = ""
                    st.session_state.raw_block_area = ""
                    st.session_state.validate_meta_len = 0
                    st.session_state.validate_specs_lines = 0
                    st.rerun()

    # --- RESTO DE LA PESTAÑA (buscador, listado, etc.) ---
    st.subheader("🔍 Buscar productos")
    col_search1, col_search2 = st.columns([3, 1])
    with col_search1:
        search_term = st.text_input("Buscar por SKU, nombre, marca, descripción, especificaciones, meta o tags:", placeholder="Ej: SAMSUNG, PROTO, llave...")
    with col_search2:
        st.write("")
        clear_search = st.button("🗑️ Limpiar búsqueda", use_container_width=True)

    if clear_search:
        search_term = ""
        st.rerun()

    productos_db = st.session_state.lista_productos
    if search_term:
        term_lower = search_term.lower()
        filtered = []
        for p in productos_db:
            if (term_lower in p.get("sku", "").lower() or
                term_lower in p.get("nombre", "").lower() or
                term_lower in p.get("marca", "").lower() or
                term_lower in p.get("desc_solo", "").lower() or
                term_lower in p.get("specs_solo", "").lower() or
                term_lower in p.get("meta", "").lower() or
                term_lower in p.get("tags", "").lower()):
                filtered.append(p)
    else:
        filtered = productos_db

    if not filtered:
        st.info("No se encontraron productos con ese criterio.")
    else:
        st.write(f"**{len(filtered)} producto(s) encontrado(s)**")
        df_productos = pd.DataFrame([
            {"SKU": p.get("sku", ""), "Nombre": p.get("nombre", ""), "Marca": p.get("marca", "")}
            for p in filtered
        ])
        df_productos.insert(0, "Seleccionar", False)
        edited_df = st.data_editor(
            df_productos,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn("📌", default=False, width="small"),
                "SKU": "SKU",
                "Nombre": "Nombre del Producto",
                "Marca": "Marca",
            }
        )
        selected_rows = edited_df[edited_df["Seleccionar"]]
        if not selected_rows.empty:
            selected_sku = selected_rows.iloc[0]["SKU"]
            prod_seleccionado = next((p for p in filtered if p.get("sku") == selected_sku), None)
            if prod_seleccionado:
                st.session_state.producto_detalle = prod_seleccionado
        else:
            st.session_state.producto_detalle = None

        if st.session_state.get("producto_detalle"):
            prod = st.session_state.producto_detalle
            st.divider()
            st.subheader(f"📄 Detalle del producto: {prod.get('sku')} | {prod.get('nombre')}")
            cuadro_copiado_vtex("Cuerpo VTEX", prod.get("vtex_body"))
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                cuadro_copiado_vtex("Meta descripción", prod.get("meta"), 150, "14px")
            with col_s2:
                cuadro_copiado_vtex("Palabras sustitutas", prod.get("tags"), 150, "14px")
            if st.button("🗑️ Borrar este producto", key="borrar_detalle"):
                st.session_state.lista_productos = [p for p in st.session_state.lista_productos if p.get("sku") != prod.get("sku")]
                guardar_en_base_datos(st.session_state.lista_productos)
                st.session_state.producto_detalle = None
                st.rerun()
        else:
            if filtered:
                st.info("Selecciona un producto de la tabla para ver su detalle completo.")

    if st.button("⚠️ VACIAR TODA LA BASE DE DATOS", key="vaciar_todo"):
        st.session_state.lista_productos = []
        guardar_en_base_datos([])
        st.session_state.producto_detalle = None
        st.rerun()
        
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
# PESTAÑA: ROBOT SAMSUNG (VERSIÓN CORREGIDA AISearch)
# ---------------------------------------------------------
with tab_samsung:
    st.header("📱 Robot Samsung Chile (V10 - Alta Precisión)")
    st.markdown("""
    **Mejoras aplicadas:**
    1. **Estructura HD:** Basado en el contenedor `.hdd02-gallery` detectado en tu captura.
    2. **Persistencia:** Guarda las URLs en la tabla y el ZIP en memoria sin borrarse.
    3. **Límite:** Extrae exactamente hasta 5 imágenes (A, B, C, D, E).
    """)

    # 1. Inicialización de estados de sesión
    if 'df_samsung' not in st.session_state:
        st.session_state.df_samsung = pd.DataFrame({
            "SKU": [""] * 5, 
            "URL Encontrada": [""] * 5
        })
    
    if 'samsung_zip_ready' not in st.session_state:
        st.session_state.samsung_zip_ready = None

    # 2. Tabla Editable
    editor_samsung = st.data_editor(
        st.session_state.df_samsung,
        num_rows="dynamic",
        key="editor_samsung_v10",
        use_container_width=True,
        column_config={
            "URL Encontrada": st.column_config.LinkColumn("Link Producto", help="Capturado automáticamente")
        }
    )

    if st.button("🚀 INICIAR DESCARGA Y EXTRACCIÓN", type="primary"):
        from urllib.parse import quote
        import string
        
        df_work = editor_samsung.copy()
        # Identificar SKUs y sus posiciones originales
        items_a_procesar = [(idx, str(row["SKU"]).strip()) for idx, row in df_work.iterrows() if str(row["SKU"]).strip() != ""]

        if not items_a_procesar:
            st.warning("⚠️ Ingresa al menos un SKU.")
        else:
            zip_buffer = BytesIO()
            log_errores = []
            progreso = st.progress(0)
            status_s = st.empty()
            total_skus = len(items_a_procesar)

            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                wait = WebDriverWait(driver, 15)
            except Exception as e:
                st.error(f"Error driver: {e}")
                st.stop()

            total_imgs_global = 0

            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                for i, (idx_orig, sku) in enumerate(items_a_procesar):
                    progreso.progress((i + 1) / total_skus)
                    status_s.info(f"🔍 Procesando {i+1}/{total_skus}: SKU `{sku}`")
                    
                    try:
                        # Búsqueda Samsung
                        driver.get(f"https://www.samsung.com/cl/search/?searchvalue={quote(sku)}")
                        
                        # 1. ENTRAR A LA FICHA Y CAPTURAR URL
                        try:
                            selector_boton = "a.aisearch-product__cta--learn-more, a[aria-label*='información'], .aisearch-product__title a"
                            btn_ficha = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector_boton)))
                            driver.execute_script("arguments[0].click();", btn_ficha)
                            time.sleep(5) # Tiempo para carga completa de ficha
                            
                            # Guardar URL en la tabla
                            df_work.at[idx_orig, "URL Encontrada"] = driver.current_url
                        except:
                            log_errores.append(f"{sku}: No se encontró resultado de búsqueda.")
                            continue

                        # 2. INTERACCIÓN CON MINIATURAS (Basado en tu captura .hdd02)
                        img_urls = []
                        # Selector específico li de tu captura
                        miniaturas = driver.find_elements(By.CSS_SELECTOR, "li.hdd02-gallery__thumbnail-item")
                        
                        if not miniaturas:
                            # Fallback si usa otra clase de galería
                            miniaturas = driver.find_elements(By.CSS_SELECTOR, ".pd-g-gallery__thumbnail, .hdd02-gallery__thumbnail-item button")

                        for idx_m, minia in enumerate(miniaturas):
                            if len(img_urls) >= 5: break # Límite de 5 fotos
                            
                            try:
                                # Click para activar imagen
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", minia)
                                driver.execute_script("arguments[0].click();", minia)
                                time.sleep(2.2) # Pausa vital para que cambie la imagen HD
                                
                                # Capturar la imagen que se activó en el contenedor principal
                                targets = driver.find_elements(By.CSS_SELECTOR, ".hdd02-pdp-header__gallery-area img, .pd-g-gallery__main-image, .swiper-slide-active img")
                                
                                for t in targets:
                                    src = t.get_attribute("data-src") or t.get_attribute("src")
                                    if src and "http" in src and src not in img_urls:
                                        # Filtro de basura (logos/iconos)
                                        if not any(x in src.lower() for x in ["icon", "logo", "indicator", "360-view", "sec-logo"]):
                                            img_urls.append(src)
                                            break # Salir del loop de targets una vez encontrada la de este clic
                            except:
                                continue

                        if not img_urls:
                            log_errores.append(f"{sku}: No se detectaron imágenes en la galería.")
                            continue

                        # 3. GUARDADO EN ZIP (Máximo 5)
                        letras = ["A", "B", "C", "D", "E"]
                        folder = sku.replace("/", "-").replace("\\", "-").replace(" ", "").strip()
                        
                        count_sku = 0
                        for url in img_urls:
                            if count_sku >= 5: break
                            try:
                                # Limpiar URL para bajar calidad original
                                url_clean = url.split("?")[0] if "samsung.com" in url else url
                                resp = requests.get(url_clean, timeout=12)
                                if resp.status_code == 200:
                                    nombre_foto = f"{folder}/{folder}_{letras[count_sku]}.jpg"
                                    zf.writestr(nombre_foto, resp.content)
                                    count_sku += 1
                                    total_imgs_global += 1
                            except: continue

                    except Exception as e:
                        log_errores.append(f"{sku}: Error crítico - {str(e)}")

            driver.quit()
            
            # GUARDAR RESULTADOS EN EL ESTADO DE SESIÓN
            st.session_state.df_samsung = df_work
            st.session_state.samsung_zip_ready = zip_buffer.getvalue()
            if log_errores: st.session_state.samsung_errors = log_errores
            
            st.rerun() # Refrescar para mostrar tabla y botón

    # 4. ÁREA DE DESCARGA (Persistente después del rerun)
    if st.session_state.samsung_zip_ready:
        st.divider()
        st.success("✅ ¡Proceso Terminado!")
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                label="⬇️ DESCARGAR ZIP DE IMÁGENES",
                data=st.session_state.samsung_zip_ready,
                file_name="Galeria_Samsung_Pro.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
        with c2:
            if st.button("🗑️ Limpiar Resultados", use_container_width=True):
                st.session_state.samsung_zip_ready = None
                st.session_state.df_samsung = pd.DataFrame({"SKU": [""] * 5, "URL Encontrada": [""] * 5})
                st.rerun()

        if 'samsung_errors' in st.session_state:
            with st.expander("⚠️ Reporte de Errores"):
                for err in st.session_state.samsung_errors:
                    st.write(f"- {err}")
                    
                    
                    
# ---------------------------------------------------------
# PESTAÑA: GENERACIÓN MASIVA DE FICHAS TÉCNICAS (GUARDADO LOCAL)
# ---------------------------------------------------------
with tab_masivo:
    st.header("🏭 Generación Masiva de Fichas Técnicas")
    st.markdown("""
    Genera fichas técnicas para múltiples productos de tu base de datos de una sola vez.
    - Se usan los datos guardados (nombre, especificaciones, marca).
    - Se busca automáticamente la foto del producto en `imagenes_productos/` y el logo en `Logos/`.
    - **Las fichas se guardan directamente en la carpeta `salidas/`** con el nombre `FT-{SKU}.jpg`.
    """)

    productos_db = st.session_state.lista_productos

    if not productos_db:
        st.warning("⚠️ No hay productos en la base de datos. Primero carga algunos en la pestaña 'Productos'.")
    else:
        # Modo de selección
        modo = st.radio(
            "Selecciona los productos a procesar:",
            ["✅ Todos los productos", "✏️ Elegir SKUs específicos"],
            horizontal=True
        )

        skus_a_procesar = []
        if modo == "✏️ Elegir SKUs específicos":
            df_seleccion = pd.DataFrame([
                {"Seleccionar": False, "SKU": p["sku"], "Nombre": p["nombre"]}
                for p in productos_db
            ])
            df_editado = st.data_editor(
                df_seleccion,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn("📌", default=False),
                    "SKU": "Código",
                    "Nombre": "Producto"
                }
            )
            skus_a_procesar = df_editado[df_editado["Seleccionar"]]["SKU"].tolist()
        else:
            skus_a_procesar = [p["sku"] for p in productos_db]

        st.info(f"📊 Se procesarán **{len(skus_a_procesar)}** fichas.")

        if st.button("🚀 INICIAR GENERACIÓN MASIVA", type="primary", use_container_width=True):
            if not skus_a_procesar:
                st.error("No has seleccionado ningún SKU.")
            else:
                errores = []
                exitosos = 0
                total = len(skus_a_procesar)

                prog_bar = st.progress(0, text="Inicializando...")
                status_text = st.empty()

                for i, sku in enumerate(skus_a_procesar):
                    prog_bar.progress((i + 1) / total, text=f"Procesando {i+1}/{total}: {sku}")
                    status_text.text(f"🔄 Generando ficha para SKU: {sku}")

                    # 1. Buscar el producto en la base de datos
                    producto = next((p for p in st.session_state.lista_productos if p.get("sku") == sku), None)
                    if not producto:
                        errores.append(f"{sku}: No encontrado en la base de datos")
                        continue

                    nombre = producto.get("nombre", "")
                    specs_raw = producto.get("specs_solo", "")
                    marca = producto.get("marca", "")

                    # 2. Buscar foto del producto (misma lógica que buscar_y_rellenar)
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
                            if foto_path:
                                break
                        if foto_path:
                            break
                    if not foto_path:
                        # fallback: cualquier archivo que empiece por el SKU
                        for root, dirs, files in os.walk(CARPETA_FOTOS):
                            for f in files:
                                if f.startswith(sku) and f.lower().endswith(tuple(extensiones_img)):
                                    foto_path = os.path.join(root, f)
                                    break
                            if foto_path:
                                break

                    # 3. Buscar logo según la marca
                    logo_path = None
                    if marca:
                        extensiones_logo = [".png", ".jpg", ".jpeg", ".webp", ".PNG", ".JPG", ".JPEG"]
                        for ext in extensiones_logo:
                            ruta_logo = os.path.join(CARPETA_LOGOS, f"{marca}{ext}")
                            if os.path.isfile(ruta_logo):
                                logo_path = ruta_logo
                                break
                        if not logo_path:
                            # buscar sin distinguir mayúsculas
                            for f in os.listdir(CARPETA_LOGOS):
                                nombre_sin_ext = os.path.splitext(f)[0]
                                if nombre_sin_ext.lower() == marca.lower():
                                    logo_path = os.path.join(CARPETA_LOGOS, f)
                                    break

                    # 4. Validar datos obligatorios
                    if not nombre:
                        errores.append(f"{sku}: Falta el nombre del producto")
                        continue
                    if not specs_raw:
                        errores.append(f"{sku}: Faltan especificaciones técnicas")
                        continue
                    if not foto_path:
                        errores.append(f"{sku}: No se encontró foto del producto en {CARPETA_FOTOS}")
                        continue
                    if not logo_path:
                        errores.append(f"{sku}: No se encontró logo para la marca '{marca}' en {CARPETA_LOGOS}")
                        continue

                    # 5. Generar la ficha técnica
                    try:
                        specs_parsed = parse_specs(specs_raw)
                        out = generar_documento(
                            nombre=nombre,
                            datos=specs_parsed,
                            sku=sku,
                            foto_producto=foto_path,
                            logo_marca=logo_path,
                            skus_matriz=sku
                        )
                        # Mover a la carpeta salidas con el nombre estándar
                        ruta_final = os.path.join("salidas", f"FT-{sku}.jpg")
                        if os.path.exists(out):
                            os.replace(out, ruta_final)
                        else:
                            # Si generar_documento ya devuelve la ruta final, igual la movemos
                            if out != ruta_final and os.path.exists(out):
                                os.replace(out, ruta_final)
                        exitosos += 1
                    except Exception as e:
                        errores.append(f"{sku}: Error al generar ficha - {str(e)}")

                # Fin del bucle
                prog_bar.empty()
                status_text.empty()

                # Resumen final
                if exitosos > 0:
                    st.success(f"✅ ¡Proceso completado! Se generaron {exitosos} fichas correctamente en la carpeta 'salidas/'.")
                if errores:
                    st.warning(f"⚠️ Se encontraron {len(errores)} errores:")
                    with st.expander("Ver detalles de errores"):
                        for err in errores:
                            st.write(f"- {err}")
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