import streamlit as st
import tempfile
import os
from pdf2image import convert_from_path
from PIL import Image

@st.cache_data(show_spinner=False)
def procesar_pdf_a_imagenes(pdf_bytes):
    """
    Recibe los bytes del PDF, lo guarda temporalmente y lo convierte a imágenes.
    Usa caché para no re-procesar si el usuario interactúa con la UI.
    """
    # Guardar bytes en un archivo temporal físico (necesario para poppler)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
        tf.write(pdf_bytes)
        temp_path = tf.name

    try:
        # Convertimos PDF a lista de imágenes (150 DPI es buen balance calidad/velocidad para pantalla)
        images = convert_from_path(temp_path, dpi=150)
        return images
    except Exception as e:
        st.error(f"Error al procesar PDF: {e}")
        return []
    finally:
        # Limpiamos el archivo temporal
        if os.path.exists(temp_path):
            os.remove(temp_path)

def unir_imagenes_verticalmente(images):
    """
    Une una lista de imágenes PIL verticalmente.
    """
    if not images:
        return None

    # 1. Calcular dimensiones totales
    widths, heights = zip(*(i.size for i in images))
    max_width = max(widths)
    total_height = sum(heights)

    # 2. Crear lienzo blanco
    long_image = Image.new('RGB', (max_width, total_height), (255, 255, 255))

    # 3. Pegar una a una
    y_offset = 0
    for im in images:
        # Centramos la imagen horizontalmente
        x_offset = (max_width - im.width) // 2
        long_image.paste(im, (x_offset, y_offset))
        y_offset += im.height

    return long_image