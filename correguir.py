import json
import re

# Cargar el JSON desde un archivo (o desde una variable)
with open('base_productos.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Procesar cada objeto
for item in data:
    if 'specs_solo' in item:
        # Eliminar punto cuando es el último carácter antes de \n o al final de la cadena
        item['specs_solo'] = re.sub(r'\.(?=\n|$)', '', item['specs_solo'])

# Guardar el resultado en un nuevo archivo
with open('productos_sin_puntos.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)