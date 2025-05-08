# README

## Overview

This repository contains a Python script designed to automate the backup of projects from Overleaf Community Edition. The script, named `exportar_y_enviar_log.py`, uses the Overleaf Toolkit to export projects and send logs via email. Below, you will find instructions on how to configure and use the script, including setting up the necessary credentials, scheduling it to run daily, and creating a GitHub repository with a personal access token.

---

## Prerequisites

- Python 3.x installed on your system.
- Overleaf Community Edition installed on the same machine with the Overleaf Toolkit.
- A GitHub account.
- Access to an SMTP server for email notifications.

---

## Configuration

Before running the script, you need to modify the `config.py` file to include your GitHub token and SMTP server password.

1. Open the `config.py` file in a text editor.
2. Locate the following variables:
    ```python
    git_token = "your_github_token_here"
    smtp_pass = "your_smtp_password_here"
    ```
3. Replace `"your_github_token_here"` with your GitHub personal access token.
4. Replace `"your_smtp_password_here"` with your SMTP server password.
5. Save the file.

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
    0 2 * * * /usr/bin/python3 /path/to/your/exportar_y_enviar_log.py
    ```
    Replace `/path/to/your/exportar_y_enviar_log.py` with the full path to your Python script.
3. Save and exit the editor.

To verify the cron job is set up correctly, run:
```bash
crontab -l
```

---

## Creating a GitHub Repository and Generating a Token

1. Log in to your GitHub account.
2. Create a new repository:
    - Go to [GitHub](https://github.com).
    - Click on the **New** button to create a repository.
    - Fill in the repository name and other details, then click **Create repository**.
3. Generate a personal access token:
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

