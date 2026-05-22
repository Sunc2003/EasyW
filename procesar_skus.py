"""
procesar_skus.py
────────────────
Lee una carpeta raíz con subcarpetas de SKUs, redimensiona cada JPG/PNG
a 597px de alto, la centra en un canvas de 1000x597px con fondo blanco
y guarda el resultado en _EXPORTADOS/NombreSKU/ como JPG calidad 100.

USO:
    python procesar_skus.py
    (te pide la carpeta raíz con un diálogo, o podés editar ROOT_FOLDER abajo)

REQUISITOS:
    pip install Pillow
"""

import os
import sys
from pathlib import Path
from PIL import Image

# ============================================================
#  CONFIGURACIÓN
# ============================================================
CANVAS_W      = 1000          # Ancho del canvas final (px)
CANVAS_H      = 597           # Alto del canvas final (px)
JPG_QUALITY   = 100           # Calidad JPG exportado (0-100)
OUTPUT_FOLDER = "_EXPORTADOS" # Nombre de carpeta de salida dentro de la raíz
VALID_EXT     = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
ROOT_FOLDER   = ""            # Dejá vacío para que abra el diálogo
# ============================================================


def elegir_carpeta():
    """Abre un diálogo para elegir carpeta (funciona en Mac y Windows)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Seleccioná la carpeta raíz con los SKUs")
        root.destroy()
        return folder
    except Exception:
        # Fallback: pedir por consola
        return input("Escribí la ruta de la carpeta raíz: ").strip()


def procesar_imagen(img_path: Path, dest_path: Path):
    """Redimensiona la imagen a alto=CANVAS_H y la centra en canvas blanco."""
    with Image.open(img_path) as img:
        # Convertir a RGB (por si es PNG con transparencia o modo P)
        img = img.convert("RGB")

        orig_w, orig_h = img.size

        # Calcular nuevo tamaño manteniendo proporción
        escala  = CANVAS_H / orig_h
        new_w   = round(orig_w * escala)
        new_h   = CANVAS_H

        # Redimensionar con Lanczos (máxima calidad)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Crear canvas blanco
        canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))

        # Centrar la imagen en el canvas
        offset_x = (CANVAS_W - new_w) // 2
        offset_y = 0  # ya tiene el alto exacto

        canvas.paste(img_resized, (offset_x, offset_y))

        # Guardar como JPG calidad 100
        canvas.save(dest_path, "JPEG", quality=JPG_QUALITY, subsampling=0)


def main():
    # 1. Elegir carpeta raíz
    root = ROOT_FOLDER or elegir_carpeta()
    if not root:
        print("Operación cancelada.")
        return

    root_path = Path(root)
    if not root_path.is_dir():
        print(f"Error: la carpeta no existe: {root}")
        return

    # 2. Obtener subcarpetas de SKUs (ignorar _EXPORTADOS)
    sku_folders = sorted([
        f for f in root_path.iterdir()
        if f.is_dir() and f.name != OUTPUT_FOLDER
    ])

    if not sku_folders:
        print("No se encontraron subcarpetas dentro de:", root)
        return

    print(f"\nSe encontraron {len(sku_folders)} carpetas de SKUs.")

    # 3. Crear carpeta de salida
    output_root = root_path / OUTPUT_FOLDER
    output_root.mkdir(exist_ok=True)

    # 4. Procesar
    total_ok    = 0
    total_error = 0

    for sku_folder in sku_folders:
        sku_name = sku_folder.name

        # Obtener imágenes válidas
        imagenes = sorted([
            f for f in sku_folder.iterdir()
            if f.is_file() and f.suffix.lower() in VALID_EXT
        ])

        if not imagenes:
            print(f"  [{sku_name}] Sin imágenes válidas, omitiendo.")
            continue

        # Crear subcarpeta de salida
        sku_out = output_root / sku_name
        sku_out.mkdir(exist_ok=True)

        print(f"\n  [{sku_name}] Procesando {len(imagenes)} imágenes...")

        for img_path in imagenes:
            dest = sku_out / (img_path.stem + ".jpg")
            try:
                procesar_imagen(img_path, dest)
                print(f"    ✓ {img_path.name}")
                total_ok += 1
            except Exception as e:
                print(f"    ✗ {img_path.name}: {e}")
                total_error += 1

    # 5. Resumen
    print(f"\n{'='*50}")
    print(f"Proceso completado.")
    print(f"  Exportadas: {total_ok}")
    print(f"  Errores:    {total_error}")
    print(f"  Carpeta:    {output_root}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()