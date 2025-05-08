from json import loads
from os import path as ospath, makedirs, environ
from subprocess import run, DEVNULL
from tempfile import TemporaryDirectory
from shutil import rmtree, copytree, copy2
from smtplib import SMTP
from email.mime.text import MIMEText
import config  # Import the configuration file

# General configuration
# [overleaf-toolkit-location]/data/overleaf/data/user_files
SOURCE_DIR = "/root/overleaf-toolkit/data/overleaf/data/user_files"
GITHUB_REPO_LOCAL = "/root/overleaf-backups"
# mongo server
SERVER="localhost"
# mongo port, 27017 is default
PORT="27017"
# overleaf container name, sharelatex is default
CONTAINER="sharelatex"

# Email configuration
SMTP_SERVER = "CONFIGURATE THIS"
SMTP_PORT = 587
FROM_EMAIL = "CONFIGURATE THIS"
TO_EMAIL = "CONFIGURATE THIS"

FROM_PASSWORD = config.smtp_pass
environ["GIT_ASKPASS"] = config.git_token


# Logs
log = []
errores = []

def restaurar_proyecto(project_id, projects_data, docs_data, source_dir, dest_dir="./"):
    """
    Restores an Overleaf project by copying files and generating documents.
    This function processes the project data, extracts the necessary files,
    and saves them to the specified destination directory.
    It uses the project ID to identify the specific project to restore.
    It traverses the folder structure of the project, mapping file references
    to their corresponding paths in the source directory.
    It is designed to work with Overleaf projects, which may contain
    various types of files, including LaTeX documents and images.
    Parameters:
    - project_id (str): ID of the project to restore.
    - projects_data (list): Content of the JSON containing all projects.
    - docs_data (list): Content of the JSON with the documents.
    - source_dir (str): Directory where the original files are located.
    - dest_dir (str): Directory where the project will be restored.  
    """
    # JSON cointains a project by line.
    json_data = next((p for p in projects_data if p["_id"]["$oid"] == project_id), None)
    
    if not json_data:
        print(f"Project {project_id} not found in the provided data.")
        return

    # Dictionary {oid: file path}
    file_map = {}

    def process_folder(folder, path=""):
        """
        Traverses the folder structure and stores the file paths.
        Args:
            folder (dict): Folder data from the JSON.
            path (str): Current path in the folder structure.        
        """
        folder_path = ospath.join(path, folder["name"])

        # Process documents (tex and related files) / These must be extracted from the JSON
        for doc in folder.get("docs", []):
            file_map[doc["_id"]["$oid"]] = ospath.join(folder_path, doc["name"])
        
        # Process files (images and others) / These are in source_dir location
        for file in folder.get("fileRefs", []):
            file_map[file["_id"]["$oid"]] = ospath.join(folder_path, file["name"])

        # Process subfolders recursively
        for subfolder in folder.get("folders", []):
            process_folder(subfolder, folder_path)
    
    # Process all folders in rootFolder
    for root_folder in json_data["rootFolder"]:
        process_folder(root_folder)        

    # No files found for project
    if not file_map:
        return
    
    # Copy files from source_dir (/data/overleaf/data/user_files) to dest_dir removing the rootFolder prefix
    for oid, dest_path in file_map.items():
        source_file = ospath.join(source_dir, f"{project_id}_{oid}")
        
        if ospath.exists(source_file):            
            new_dir = ospath.dirname(ospath.join(dest_dir, dest_path)).replace("/rootFolder/", "/")            
            makedirs(new_dir, exist_ok=True)            
            copy2(source_file, ospath.join(dest_dir, dest_path).replace("/rootFolder/", "/")  )

    # Extract the documents from the JSON
    if docs_data:
        for doc in docs_data:
            oid = doc["_id"]["$oid"]

            if oid in file_map:
                # create the path for the document removing the rootFolder prefix
                new_path = ospath.join(dest_dir, file_map[oid]).replace("/rootFolder/", "/")
                new_dir = ospath.dirname(new_path)

                # Create directory if it doesn't exist
                makedirs(new_dir, exist_ok=True)

                # Save the content of the document in the file
                with open(new_path, "w", encoding="utf-8") as output_file:
                    lineas = "\n".join(doc.get("lines", ""))
                    output_file.write(lineas)  


def export_mongo_collection(collection_name):
    """
    Exports a MongoDB collection to JSON format using docker exec.
    Args:
        collection_name (str): The name of the MongoDB collection to export.
    Returns:
        list: A list of dictionaries representing the exported documents.
    Raises:
        subprocess.CalledProcessError: If the export command fails.
    """
    # Docker command to export the collection in JSON format
    cmd = [
        "docker", "exec", "mongo",
        "mongoexport",
        "--db=sharelatex",
        "-h", SERVER+":"+PORT,
        f"--collection={collection_name}",
        "--jsonArray"
    ]
    
    result = run(cmd, capture_output=True, text=True, check=True)    
    return loads(result.stdout)

def git_commit_and_push_if_changed(repo_path, mensaje):
    """
    Commit and push changes to a Git repository if there are any changes.
    Args:
        repo_path (str): Path to the Git repository.
        mensaje (str): Commit message.
    Returns:
        bool: True if changes were committed and pushed, False otherwise.
    """
    run(["git", "-C", repo_path, "add", "."], check=True, stdout = DEVNULL, stderr = DEVNULL)
    result = run(["git", "-C", repo_path, "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        run(["git", "-C", repo_path, "commit", "-m", mensaje], check=True, stdout = DEVNULL, stderr = DEVNULL)
        run(["git", "-C", repo_path, "push"], check=True, stdout = DEVNULL, stderr = DEVNULL)
        # changes
        return True
    # no changes
    return False

def enviar_log_por_correo(asunto, cuerpo):
    """
    Sends an email with the log and errors.
    Args:
        asunto (str): Subject of the email.
        cuerpo (str): Body of the email.
    """
    msg = MIMEText(cuerpo)
    msg["Subject"] = asunto
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL

    with SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(FROM_EMAIL, FROM_PASSWORD)
        server.send_message(msg)

# Export users collection
users = export_mongo_collection("users")
# Create a map {user oid -> email}
user_email_map = {user["_id"]["$oid"]: user.get("email", "desconocido") for user in users}
# Export projects collection
projects = export_mongo_collection("projects")
# Export docs collection
docs_all = export_mongo_collection("docs")

# Process projects
for project in projects:
    project_id = project["_id"]["$oid"]
    project_name = project["name"]
    owner_id = project["owner_ref"]["$oid"]
    owner_email = user_email_map.get(owner_id, "desconocido")

    mensaje_log = f"📁 {project_name} ({owner_email})"

    try:        
        with TemporaryDirectory() as temp_dir:
            # copy files to a temporary directory
            restaurar_proyecto(
                project_id=project_id,
                projects_data=projects,
                docs_data=docs_all,
                source_dir=SOURCE_DIR,
                dest_dir=temp_dir
            )

            # repository path is [owner_email]/[project_name]
            repo_dest = ospath.join(GITHUB_REPO_LOCAL, owner_email, project_name)
            if ospath.exists(repo_dest):
                rmtree(repo_dest)
            # copy restored project to the repository path
            copytree(temp_dir, repo_dest)

            # commit and push, log projects with changes only
            if git_commit_and_push_if_changed(GITHUB_REPO_LOCAL, f"Actualizar proyecto '{project_name}'"):
                log.append(f"✅ {mensaje_log} — Cambios subidos.")

    except Exception as e:
        errores.append(f"❌ {mensaje_log} — Error: {e}")
        log.append(f"❌ {mensaje_log} — Error al procesar.")

# Send email with log
asunto = "[Exportación Overleaf] "
if errores:
    asunto += "Errores al exportar proyectos"
    cuerpo = "\n".join(log + ["", "Errores detallados:"] + errores)
else:
    asunto += "Proyectos exportados con éxito"
    cuerpo = "Todos los proyectos fueron exportados correctamente."
    cuerpo += "\n\nResumen:\n" + "\n".join(log) if (log) else "\n\nSin cambios."


enviar_log_por_correo(asunto, cuerpo)

