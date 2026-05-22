import base64
import os
from jinja2 import Environment, FileSystemLoader
from html2image import Html2Image
from PIL import Image

def encode_img(path):
    if not os.path.exists(path):
        return "" # Evita que el programa explote si falta una imagen
    ext = path.split(".")[-1].lower()
    with open(path, "rb") as f:
        data = f.read()
    return f"data:image/{ext};base64," + base64.b64encode(data).decode()

# --- GENERADOR 1: FICHA TÉCNICA NORMAL ---
def generar_ficha(sku, nombre, modelo, foto_producto, logo_marca, especificaciones):
    num_specs = len(especificaciones)
    
    if num_specs <= 10:
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

    output_dir = "salidas"
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"FT-{sku}.png"
    output_path = os.path.join(output_dir, file_name)

    hti = Html2Image(output_path=output_dir)
    hti.screenshot(html_str=html_final, save_as=file_name, size=(ancho_cap, alto_cap))

    # Recorte de precisión
    with Image.open(output_path) as img:
        img.crop((0, 0, ancho_final, alto_final)).save(output_path)

    return output_path

# --- GENERADOR 2: FICHA MATRIZ (TABLA LARGA) ---
def generar_ficha_matriz(nombre, skus_concatenados, datos_matriz):
    num_filas = len(datos_matriz)
    
    # Cálculo dinámico del alto (45px aprox por fila de tabla + cabecera)
    alto_calculado = 650 + (num_filas * 45)
    alto_final = max(1475, min(3000, alto_calculado)) # Subí el máximo a 3000 por si la tabla es gigante
    alto_captura = alto_final + 150 # Más margen para el renderizado

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("ficha_matriz.html")

    html_final = template.render(
        nombre=nombre,
        skus_concatenados=skus_concatenados,
        datos_matriz=datos_matriz,
        header_img=encode_img("header_marsella.png"),
        footer_img=encode_img("footer_marsella.png")
    )

    output_dir = "salidas"
    os.makedirs(output_dir, exist_ok=True)
    # Limpiamos el nombre para el archivo
    nombre_limpio = "".join(x for x in nombre if x.isalnum())[:15]
    file_name = f"MATRIZ-{nombre_limpio}.png"
    output_path = os.path.join(output_dir, file_name)

    hti = Html2Image(output_path=output_dir)
    hti.screenshot(html_str=html_final, save_as=file_name, size=(1225, alto_captura))

    # Recorte de precisión para matriz
    with Image.open(output_path) as img:
        img.crop((0, 0, 1225, alto_final)).save(output_path)

    return output_path


def generar_documento(nombre, datos, sku=None, modelo=None, foto=None, logo=None, skus_matriz=None):
    """
    Cerebro del programa: Detecta si 'datos' es un Diccionario (Ficha Normal)
    o una Lista de Listas (Ficha Matriz) y actúa en consecuencia.
    """
    
    # CASO A: FICHA TÉCNICA NORMAL (DICCIONARIO)
    if isinstance(datos, dict):
        print(f"Detectada Ficha Normal para: {nombre}")
        return generar_ficha(
            sku=sku, 
            nombre=nombre, 
            modelo=modelo, 
            foto_producto=foto, 
            logo_marca=logo, 
            especificaciones=datos
        )
    
    # CASO B: FICHA MATRIZ (LISTA DE LISTAS)
    elif isinstance(datos, list):
        print(f"Detectada Ficha Matriz para: {nombre}")
        # Si es matriz, el SKU suele ser una lista concatenada
        skus_final = skus_matriz if skus_matriz else sku
        return generar_ficha_matriz(
            nombre=nombre, 
            skus_concatenados=skus_final, 
            datos_matriz=datos
        )
    
    else:
        raise ValueError("El formato de datos no es válido. Debe ser dict o list.")