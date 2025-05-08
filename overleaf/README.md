# README

## Overview

This repository contains a Python script designed to automate the backup of projects from [Overleaf Community Edition](https://github.com/overleaf/). The script, named `exportar_y_enviar_log.py`, uses Docker to export the Mongo collections of all projects, including external files, and send logs via email. Below, you will find instructions on how to configure and use the script, including setting up the necessary credentials, scheduling it to run daily, and creating a GitHub repository with a personal access token.

---

## Prerequisites

- Python 3.x installed on your system.
- Overleaf Community Edition installed on the same machine with the Overleaf Toolkit.
- A GitHub account.
- Access to an SMTP server for email notifications.

---

## Configuration

Before running the script, you need to modify the `config.py` file to include your credentials and other necessary variables.

1. Open the `config.py` file in a text editor.
2. Locate and configure the following variables:
    ```python
    git_token = "your_github_token_here"
    smtp_pass = "your_smtp_password_here"
    ```
3. Replace the placeholder values with your actual credentials and paths:
    - `"your_github_token_here"`: Your GitHub personal access token.
    - `"your_smtp_password_here"`: Your SMTP server password.
4. Save the file.
5. Open the `exportar_y_enviar_log.py` file in a text editor.
6. Locate and configure the following variables:
    ```python
    SMTP_SERVER = "your_smtp_server_here"
    SMTP_PORT = your_smtp_port_here
    FROM_EMAIL = "your_email_here"
    TO_EMAIL = "recipient_email_here"
    SOURCE_DIR = "/path/to/overleaf/toolkit"
    GITHUB_REPO_LOCAL = "/path/to/cloned/repository"
    SERVER = "overleaf_server_name"
    PORT = overleaf_server_port
    CONTAINER = "overleaf_container_name"
7. Replace the placeholder values with your actual credentials and paths:
    - `"your_smtp_server_here"`: The address of your SMTP server.
    - `your_smtp_port_here`: The port number for your SMTP server.
    - `"your_email_here"`: The email address used to send notifications.
    - `"recipient_email_here"`: The email address to receive notifications.
    - `"/path/to/overleaf/toolkit"`: The directory where the Overleaf Toolkit is installed.
    - `"/path/to/cloned/repository"`: The directory where the GitHub repository was cloned.
    - `"overleaf_server_name"`, `overleaf_server_port`, and `"overleaf_container_name"`: Update these if you did not use the default names during the Overleaf Toolkit installation.
    ```
---

## Running the Script

To execute the script, run the following command in your terminal:
```bash
python3 exportar_y_enviar_log.py
```

---

## Scheduling with Cron (Linux)

To run the script daily, you can use `cron` on a Linux machine:

1. Open the crontab editor:
    ```bash
    crontab -e
    ```
2. Add the following line to schedule the script to run daily at 2:00 AM:
    ```bash
    0 2 * * * /usr/bin/python3 /path/to/your/exportar_y_enviar_log.py >/dev/null 2>&1
    ```
    Replace `/path/to/your/exportar_y_enviar_log.py` with the full path to your Python script.
3. Save and exit the editor.

To verify the cron job is set up correctly, run:
```bash
crontab -l
```

---

## Creating and Cloning a GitHub Repository

1. Log in to your GitHub account.
2. Create a new repository:
    - Go to [GitHub](https://github.com).
    - Click on the **New** button to create a repository.
    - Fill in the repository name and other details, then click **Create repository**.
3. Clone the repository to your local machine:
    ```bash
    git clone https://github.com/your_username/your_repository_name.git
    ```
    Replace `your_username` and `your_repository_name` with your GitHub username and repository name.

---

## Generating a GitHub Token

1. Generate a personal access token:
    - Go to **Settings** > **Developer settings** > **Personal access tokens** > **Tokens (classic)**.
    - Click **Generate new token**.
    - Select the required scopes (e.g., `repo` for repository access).
    - Copy the generated token and store it in `config.py`.

This token enables the script to make commits without requiring login credentials.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Contributions

Contributions are welcome! Feel free to open issues or submit pull requests.

---

## Contact

For any questions or issues, please contact me.

