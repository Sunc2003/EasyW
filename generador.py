import base64
import os
from jinja2 import Environment, FileSystemLoader
from html2image import Html2Image
from PIL import Image

def encode_img(path):
    if not path or not os.path.exists(path):
        return "" 
    ext = path.split(".")[-1].lower()
    if ext == "jpg": ext = "jpeg"
    with open(path, "rb") as f:
        data = f.read()
    return f"data:image/{ext};base64," + base64.b64encode(data).decode()

# --- GENERADOR 1: FICHA TÉCNICA NORMAL ---
def generar_ficha(sku, nombre, modelo, foto_producto, logo_marca, especificaciones):
    num_specs = len(especificaciones)
    
    if num_specs <= 7:
        ancho_cap, alto_cap = 1280, 1203
        ancho_final, alto_final = 1280, 1103
    else:
        ancho_cap, alto_cap = 1225, 1580
        ancho_final, alto_final = 1225, 1475

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("ficha.html")

    html_final = template.render(
        sku=sku, nombre=nombre, modelo=modelo,
        foto_producto=encode_img(foto_producto),
        logo_marca=encode_img(logo_marca),
        especificaciones=especificaciones,
        header_img=encode_img("header_marsella.png"),
        footer_img=encode_img("footer_marsella.png"),
        num_specs=num_specs
    )

    output_dir = os.path.abspath("salidas")
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"FT-{sku}.png"
    output_path = os.path.join(output_dir, file_name)

    # --- SOLUCIÓN PARA MAC (SIN custom_temp_path) ---
    # Instanciamos solo con el directorio de salida
    hti = Html2Image(output_path=output_dir)
    
    try:
        # Generar captura
        hti.screenshot(html_str=html_final, save_as=file_name, size=(ancho_cap, alto_cap))
    except Exception as e:
        # Si la imagen se guardó a pesar del error de borrado, ignoramos el error
        if not os.path.exists(output_path):
            raise e

    if os.path.exists(output_path):
        with Image.open(output_path) as img:
            img.crop((0, 0, ancho_final, alto_final)).save(output_path)

    return output_path

# --- GENERADOR 2: FICHA MATRIZ ---
def generar_ficha_matriz(nombre, skus_concatenados, datos_matriz, foto_producto=None, logo_marca=None):
    num_total = len(datos_matriz)
    
    if num_total <= 11:
        ancho_final, alto_final = 1280, 1103
        alto_cap = 1250 
    else:
        ancho_final, alto_final = 1225, 1475
        alto_cap = 1600 

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("ficha_matriz.html")

    html_final = template.render(
        nombre=nombre,
        skus_concatenados=skus_concatenados,
        datos_matriz=datos_matriz,
        foto_producto=encode_img(foto_producto),
        logo_marca=encode_img(logo_marca),
        header_img=encode_img("header_marsella.png"),
        footer_img=encode_img("footer_marsella.png")
    )

    output_dir = os.path.abspath("salidas")
    os.makedirs(output_dir, exist_ok=True)
    nombre_limpio = "".join(x for x in nombre if x.isalnum())[:15]
    file_name = f"MATRIZ-{nombre_limpio}.png"
    output_path = os.path.join(output_dir, file_name)

    hti = Html2Image(output_path=output_dir)
    try:
        hti.screenshot(html_str=html_final, save_as=file_name, size=(ancho_final, alto_cap))
    except Exception as e:
        if not os.path.exists(output_path):
            raise e

    if os.path.exists(output_path):
        with Image.open(output_path) as img:
            img.crop((0, 0, ancho_final, alto_final)).save(output_path)

    return output_path

# --- CEREBRO INTELIGENTE ---
def generar_documento(nombre, datos, sku=None, modelo=None, foto_producto=None, logo_marca=None, skus_matriz=None):
    if isinstance(datos, dict):
        return generar_ficha(
            sku=sku, 
            nombre=nombre, 
            modelo=modelo, 
            foto_producto=foto_producto, 
            logo_marca=logo_marca, 
            especificaciones=datos
        )
    elif isinstance(datos, list):
        skus_final = skus_matriz if skus_matriz else sku
        return generar_ficha_matriz(
            nombre=nombre, 
            skus_concatenados=skus_final, 
            foto_producto=foto_producto, 
            logo_marca=logo_marca,
            datos_matriz=datos
        )
    else:
        raise ValueError("Formato de datos no soportado.")