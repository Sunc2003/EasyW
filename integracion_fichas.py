import os
import json
import base64
import requests
import re
import time
from io import BytesIO
from PIL import Image
# Importamos tus funciones de generador.py
from generador import generar_documento 

# --- CONFIGURACIÓN ---
FOLDER_FICHAS_VIEJAS = "./fichas_antiguas" 
CARPETA_FOTOS_HD = "imagenes_productos"
URL_LM_STUDIO = "http://192.168.1.18:1234/v1/chat/completions"
MODELO = "nemotron-3-nano-omni-30b-a3b-reasoning" 

# --- OPTIMIZACIONES DE IMAGEN ---
MAX_IMAGE_RES = 1560  # Resolución máxima para ahorrar tokens
IMAGE_QUALITY = 85    # Calidad de compresión JPG

def optimizar_imagen_b64(path_imagen):
    """Redimensiona y comprime la imagen para reducir el peso de tokens."""
    try:
        with Image.open(path_imagen) as img:
            # Convertir a RGB si es necesario (para evitar errores con PNG/RGBA)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # Redimensionar manteniendo aspecto si supera el máximo
            if max(img.size) > MAX_IMAGE_RES:
                img.thumbnail((MAX_IMAGE_RES, MAX_IMAGE_RES), Image.LANCZOS)
            
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=IMAGE_QUALITY)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"❌ Error optimizando imagen {path_imagen}: {e}")
        return None

def extraer_sku_desde_nombre(nombre_archivo):
    nombre_sin_ext = os.path.splitext(nombre_archivo)[0]
    match = re.search(r'(?:FT-)?([A-Z0-9]+)', nombre_sin_ext, re.IGNORECASE)
    if match:
        return match.group(1).upper().strip()
    return nombre_sin_ext.upper().strip()

def buscar_foto_hd(sku):
    extensiones = [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]
    nombres_a_buscar = [sku, f"{sku}_A", f"{sku}_1"]
    for root, dirs, files in os.walk(CARPETA_FOTOS_HD):
        for nb in nombres_a_buscar:
            for ext in extensiones:
                if f"{nb}{ext}" in files:
                    return os.path.join(root, f"{nb}{ext}")
    return None

def extraer_datos_tecnicos(path_imagen, sku_archivo, intentos=3):
    """Extrae datos con reintentos y limpieza de memoria."""
    img_b64 = optimizar_imagen_b64(path_imagen)
    if not img_b64: return None
    
    prompt = f"""Analiza esta ficha técnica antigua. SKU: {sku_archivo}.
    Extrae la información EXACTAMENTE en este formato JSON:
    {{
        "nombre": "Título",
        "modelo": "Modelo",
        "specs_dict": {{ "Característica": "Valor" }}
    }}
    Responde SOLO el JSON puro."""

    payload = {
        "model": MODELO,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ],
        "temperature": 0.1
    }

    for i in range(intentos):
        try:
            response = requests.post(URL_LM_STUDIO, json=payload, timeout=1000)
            content = response.json()['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"⚠️ Intento {i+1} fallido para {sku_archivo}: {e}")
            time.sleep(2) # Pausa de seguridad
    return None

def procesar_todo():
    os.makedirs("salidas", exist_ok=True)
    log_errores = []
    
    fichas = [f for f in os.listdir(FOLDER_FICHAS_VIEJAS) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    print(f"🚀 Procesando {len(fichas)} archivos en {MODELO}")

    for archivo in fichas:
        path_viejas = os.path.join(FOLDER_FICHAS_VIEJAS, archivo)
        sku_detectado = extraer_sku_desde_nombre(archivo)
        
        print(f"\n📦 Procesando: {sku_detectado}")

        # Inferencia atómica (limpia memoria de tokens en cada ciclo)
        datos = extraer_datos_tecnicos(path_viejas, sku_detectado)
        
        if datos:
            foto_hd = buscar_foto_hd(sku_detectado) or path_viejas
            try:
                generar_documento(
                    nombre=datos['nombre'],
                    datos=datos['specs_dict'],
                    sku=sku_detectado,
                    modelo=datos.get('modelo', ""),
                    foto_producto=foto_hd,
                    logo_marca="templates/logo_marsella.png" 
                )
                print(f"✅ Ficha generada: {sku_detectado}")
            except Exception as e:
                print(f"💥 Error en generador: {e}")
                log_errores.append(f"{sku_detectado}: Error en generador")
        else:
            print(f"❌ Falló extracción técnica: {sku_detectado}")
            log_errores.append(f"{sku_detectado}: Fallo en IA")

    if log_errores:
        with open("procesamiento_errores.log", "w") as f:
            f.write("\n".join(log_errores))
        print(f"\n⚠️ Proceso terminado con {len(log_errores)} errores. Ver procesamiento_errores.log")

if __name__ == "__main__":
    procesar_todo()