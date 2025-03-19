import os
import json
import shutil
import argparse

# Configurar argumentos de línea de comandos
parser = argparse.ArgumentParser(description="Restaura archivos de un proyecto Overleaf desde JSON.")
parser.add_argument("json_file", help="Ruta del archivo JSON del proyecto")
parser.add_argument("docs_json", help="Ruta del archivo JSON con los documentos")
parser.add_argument("source_dir", help="Directorio donde están los archivos originales")
parser.add_argument("dest_dir", help="Directorio de destino para la estructura organizada")
args = parser.parse_args()

# Directorios de origen y destino
source_dir = args.source_dir
dest_dir = args.dest_dir

# Cargar el JSON del proyecto
with open(args.json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# ID del proyecto
project_id = data["_id"]["$oid"]

# Diccionario para mapear oid a la ruta esperada del archivo
file_map = {}

def process_folder(folder, path=""):
    """Recorre recursivamente la estructura del proyecto y almacena la ruta de los archivos."""
    folder_path = os.path.join(path, folder["name"])

    # Procesar documentos (docs) → Estos deben extraerse desde el JSON de documentos
    for doc in folder.get("docs", []):
        file_map[doc["_id"]["$oid"]] = os.path.join(folder_path, doc["name"])

    # Procesar archivos (fileRefs) → Estos están en source_dir
    for file in folder.get("fileRefs", []):
        file_map[file["_id"]["$oid"]] = os.path.join(folder_path, file["name"])

    # Procesar subcarpetas dentro de "folders"
    for subfolder in folder.get("folders", []):
        process_folder(subfolder, folder_path)

# Procesar todas las carpetas en rootFolder
# ingresa toda la información en file_map
for root_folder in data["rootFolder"]:
    process_folder(root_folder)

# Copiar archivos en la estructura correcta (para fileRefs)
for filename in os.listdir(source_dir):
    parts = filename.split("_")
    if len(parts) == 2 and parts[0] == project_id:
        oid = parts[1]
        if oid in file_map:
            new_path = os.path.join(dest_dir, file_map[oid])
            new_dir = os.path.dirname(new_path)

            # Crear directorio si no existe
            os.makedirs(new_dir, exist_ok=True)

            # Copiar archivo
            shutil.copy2(os.path.join(source_dir, filename), new_path)
            print(f"Copiado: {filename} → {new_path}")

# Extraer y restaurar archivos desde el JSON de documentos
# NOTA: el json de la exportación no tiene un formato estándar
#       * debe eliminarse la primera y la última línea
#       * debe agregarse [] alrededor de todo el archivo y reemplazar
#          "}\r\n{" por "},\r\n{"

# Leer el archivo original
with open(args.docs_json, 'r', encoding='utf-8') as file:
    lineas = file.readlines()

# Verificar que hay suficientes líneas para eliminar
if len(lineas) > 2: 
    contenido = "[" + "".join(lineas[1:-1]).replace("}\n{", "},\n{") + "]"

    # Cargar el JSON en una variable
    docs_data = json.loads(contenido)

    for doc in docs_data:
        oid = doc["_id"]["$oid"]

        if oid in file_map:
            new_path = os.path.join(dest_dir, file_map[oid])
            new_dir = os.path.dirname(new_path)

            # Crear directorio si no existe
            os.makedirs(new_dir, exist_ok=True)

            # Guardar el contenido del documento en el archivo
            with open(new_path, "w", encoding="utf-8") as output_file:
                lineas = "\n".join(doc.get("lines", ""))
                output_file.write(lineas)  
            
            print(f"Restaurado desde JSON: {oid} → {new_path}")
    print("Proceso completado.")
   
else:
    print("Error: El archivo tiene menos de 3 líneas, no se puede procesar correctamente.")
    