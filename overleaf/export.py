#!/usr/bin/env python3
"""
Overleaf Backup Script
======================
Automatic backup of Overleaf projects to GitHub with intelligent change detection.

Features:
- ✅ Deleted/trashed projects filter
- ✅ It uses timestamps directly from the project document (much faster than scanning docs collection)
- ✅ Parallel processing with ThreadPoolExecutor for faster exports
- ✅ Safe Git operations with automatic rebase to handle concurrent changes
- ✅ Concise email reports with summary and only relevant details (errors and updates)
- ✅ Dry-run mode for testing without making changes
- ✅ Configurable number of parallel workers for optimal performance
- ✅ Cleanup of old backups for deleted projects with optional --cleanup-deleted flag

Usage:
    python3 overleaf_backup.py
    python3 overleaf_backup.py --force
    python3 overleaf_backup.py --cleanup-deleted
    python3 overleaf_backup.py --dry-run
"""

from json import loads
from os import environ
from subprocess import run, DEVNULL, CalledProcessError, TimeoutExpired
from shutil import rmtree
from smtplib import SMTP
from email.mime.text import MIMEText
from email.utils import formataddr
from hashlib import sha1
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import zipfile
import logging
import config
import argparse
from pathlib import Path

# Configuration
SOURCE_DIR = Path("/root/overleaf-toolkit")
GITHUB_REPO_LOCAL = Path("/root/overleaf-backups")
CONTAINER = "sharelatex"
MONGO_CONTAINER = "mongo"
SMTP_SERVER = config.smtp_server
SMTP_PORT = config.smtp_port
FROM_EMAIL = config.from_email
TO_EMAIL = config.to_email
FROM_PASSWORD = config.smtp_pass
environ["GIT_ASKPASS"] = config.git_token

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Track different categories (for console logging and email)
log_updated = []      # Projects actually updated
log_nochanges = []    # Projects processed but no changes
log_skipped = []      # Deleted/trashed/spam projects skipped
log_errors = []       # Failed projects
log_git = []          # Git operations
log_cleanup = []      # Cleanup actions


def export_mongo_collection_with_timestamp(collection_name):
    """Export MongoDB collection with timeout and error handling"""
    cmd = [
        "docker", "exec", MONGO_CONTAINER,
        "mongoexport",
        "--db=sharelatex",
        "--host=localhost:27017",
        f"--collection={collection_name}",
        "--jsonArray"
    ]
    try:
        logger.info(f"  Exporting {collection_name}...")
        result = run(cmd, capture_output=True, text=True, check=True, timeout=120)
        data = loads(result.stdout)
        logger.info(f"  ✓ {collection_name}: {len(data)} documents")
        return data
    except CalledProcessError as e:
        raise RuntimeError(f"Failed to export '{collection_name}': {e.stderr[:300]}")
    except TimeoutExpired:
        raise RuntimeError(f"Timeout exporting '{collection_name}' (120s)")


def is_project_active(project):
    """
    Determine if a project should be backed up based on Overleaf's schema.
    Returns: (is_active: bool, reason: str)

    Based on actual MongoDB structure:
    - trashed: [] (empty array) or [ObjectId] (if trashed)
    - deleted: may not exist, or be in deletedDocs
    - active: boolean field
    """
    # Skip projects without owner (orphaned/corrupted)
    if "owner_ref" not in project or "$oid" not in project["owner_ref"]:
        return False, "orphaned (no owner)"

    # Skip inactive projects
    if not project.get("active", True):
        return False, "inactive"

    # Skip trashed projects (trashed is an array - non-empty means trashed)
    trashed = project.get("trashed", [])
    if trashed and len(trashed) > 0:
        return False, "trashed"

    # Skip projects with deleted flag (if exists)
    if project.get("deleted", False):
        return False, "deleted"

    # Skip spam-flagged projects
    if project.get("spam", False):
        return False, "spam-flagged"

    # Skip projects with no name (corrupted)
    if not project.get("name") or not project["name"].strip():
        return False, "unnamed/corrupted"

    return True, None


def parse_iso_timestamp(timestamp_str):
    """
    Parse ISO 8601 timestamp from MongoDB export.
    Handles both formats: "2024-08-27T12:36:46.583Z" and epoch millis
    """
    if not timestamp_str:
        return None

    try:
        # MongoDB exports ISODate as: {"$date": "2024-08-27T12:36:46.583Z"}
        if isinstance(timestamp_str, dict) and "$date" in timestamp_str:
            ts_str = timestamp_str["$date"]
        else:
            ts_str = str(timestamp_str)

        # Parse ISO 8601 format
        ts = ts_str.replace('Z', '+00:00') if 'Z' in ts_str else ts_str
        dt = datetime.fromisoformat(ts)

        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except (ValueError, TypeError, KeyError) as e:
        logger.debug(f"  Invalid timestamp '{timestamp_str}': {e}")
        return None


def get_project_last_updated(project):
    """
    Get the lastUpdated timestamp directly from the project document.
    This is much faster than scanning the docs collection.

    Project structure has:
    - lastUpdated: ISODate (when project was last modified)
    - lastOpened: ISODate (when project was last opened)
    - lastUpdatedBy: ObjectId (who modified it)
    """
    # Try lastUpdated field first (most accurate for modifications)
    last_updated = project.get("lastUpdated")

    if last_updated:
        dt = parse_iso_timestamp(last_updated)
        if dt:
            return dt, "lastUpdated field"

    # Fallback to lastOpened if lastUpdated not available
    last_opened = project.get("lastOpened")
    if last_opened:
        dt = parse_iso_timestamp(last_opened)
        if dt:
            return dt, "lastOpened field (fallback)"

    # No timestamp available
    return None, "no timestamp available"


def should_export_project(project, last_backup_time, force_export=False):
    """
    Determine if project should be exported based on its lastUpdated timestamp.
    Returns: (should_export: bool, reason: str)
    """
    if force_export:
        return True, "forced export"

    if last_backup_time is None:
        return True, "no previous backup timestamp"

    # Get project's last update time directly from project document
    last_updated, source = get_project_last_updated(project)

    if last_updated is None:
        # Project has no timestamp - export to be safe
        return True, "no timestamp (exporting to be safe)"

    # Compare timestamps
    if last_updated > last_backup_time:
        time_str = last_updated.strftime('%Y-%m-%d %H:%M')
        return True, f"modified at {time_str} ({source})"
    else:
        time_str = last_backup_time.strftime('%Y-%m-%d %H:%M')
        return False, f"no changes since {time_str}"


def restore_project_to_dest(project_id, dest_dir):
    """
    Export project from Overleaf and extract directly to destination.
    Returns True if ZIP was valid and extracted, False otherwise.
    Git will detect actual changes automatically.

    It uses the script described in https://docs.overleaf.com/on-premises/maintenance/data-and-backups/exporting-projects
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Docker export command
    cmd = [
        "docker", "exec", CONTAINER,
        "/bin/bash", "-ce",
        f"source /etc/container_environment.sh && cd /overleaf/services/web && "
        f"node modules/server-ce-scripts/scripts/export-user-projects.mjs "
        f"--project-id={project_id} --output=/var/lib/overleaf/data/exports/{project_id}.zip"
    ]

    try:
        run(cmd, capture_output=True, text=True, check=True, timeout=300)
    except CalledProcessError as e:
        raise RuntimeError(f"Docker export failed: {e.stderr[:300]}")
    except Exception as e:
        raise RuntimeError(f"Docker export failed: {str(e)[:300]}")

    zip_source = SOURCE_DIR / f"data/overleaf/data/exports/{project_id}.zip"

    # Check if ZIP is valid
    if not zip_source.exists() or zip_source.stat().st_size == 0:
        if zip_source.exists():
            zip_source.unlink()
        return False

    try:
        # Extract ZIP directly to destination (overwrites existing files)
        with zipfile.ZipFile(zip_source, 'r') as zf:
            zf.extractall(dest_dir)
        zip_source.unlink()
        return True
    except (zipfile.BadZipFile, RuntimeError, Exception) as e:
        logger.warning(f"Invalid ZIP for {project_id}: {e}")
        if zip_source.exists():
            zip_source.unlink()
        return False


def process_project(project, user_email_map, last_backup_time, force_export=False):
    """
    Process a single Overleaf project for backup.

    This function determines whether a project should be exported based on its
    activity status and last updated timestamp. If the project is eligible for
    export, it is backed up to the local repository.

    Args:
        project (dict): The project document from the MongoDB collection.
            Expected to contain fields like '_id', 'name', 'owner_ref', etc.
        user_email_map (dict): A mapping of user IDs to their email addresses.
        last_backup_time (datetime or None): The timestamp of the last backup.
            If None, all projects are considered for export.
        force_export (bool): If True, forces export of all projects regardless
            of their last updated timestamp.

    Returns:
        tuple:
            - bool: True if the project was successfully exported, False otherwise.
            - str: A message describing the result of the operation.
            - pathlib.Path or None: The path to the exported project repository,
              or None if the project was not exported.

    Logs:
        - Skipped projects (inactive, trashed, etc.) are logged to `log_skipped`.
        - Projects with no changes are logged to `log_nochanges`.
        - Successfully exported projects are logged to `log_updated`.
        - Errors during export are logged to `log_errors`.
    """
    project_id = project["_id"]["$oid"]
    project_name = project["name"]
    owner_id = project["owner_ref"]["$oid"]
    owner_email = user_email_map.get(owner_id, "unknown")

    # Skip deleted/trashed projects
    is_active, reason = is_project_active(project)
    if not is_active:
        skip_msg = f"⏭️  {project_name} ({owner_email}) — {reason}"
        log_skipped.append(skip_msg)
        logger.debug(skip_msg)
        return None, None, None

    # Check if project needs export based on timestamps
    should_export, export_reason = should_export_project(project, last_backup_time, force_export)

    if not should_export:
        skip_msg = f"⏭️  {project_name} ({owner_email}) — {export_reason}"
        log_nochanges.append(skip_msg)
        logger.debug(skip_msg)
        return None, None, None

    # Export and extract project
    short_id = sha1(project_id.encode()).hexdigest()[:7]
    repo_dest = Path(GITHUB_REPO_LOCAL) / owner_email / f"{project_name}__{short_id}"

    try:
        logger.debug(f"  📤 Exporting: {project_name} ({export_reason})")

        if not restore_project_to_dest(project_id, repo_dest):
            err_msg = f"⚠️  {project_name} ({owner_email}) — Empty/invalid export"
            log_errors.append(err_msg)
            logger.error(err_msg)
            return False, err_msg, None

        msg = f"✅ {project_name} ({owner_email})"
        log_updated.append(msg)
        logger.info(msg)
        return True, msg, repo_dest

    except Exception as e:
        err_msg = f"❌ {project_name} ({owner_email}) — {str(e)[:200]}"
        log_errors.append(err_msg)
        logger.error(err_msg)
        return False, err_msg, None


def cleanup_deleted_projects(active_project_paths, cleanup_mode=False):
    """
    Remove directories of deleted/trashed projects from backup repo.

    Args:
        active_project_paths: Set of paths for ACTIVE projects (to keep)
        cleanup_mode: If True, actually delete directories; if False, just report

    Returns:
        List of messages about cleanup actions
    """
    cleanup_log = []

    # Walk through all owner directories in backup repo
    for owner_dir in Path(GITHUB_REPO_LOCAL).iterdir():
        if not owner_dir.is_dir():
            continue

        owner_email = owner_dir.name

        # Check each project directory under this owner
        for project_path in owner_dir.iterdir():
            if not project_path.is_dir():
                continue

            # Skip if this is an active project path
            if project_path in active_project_paths:
                continue

            # This project directory exists in backup but NOT in active projects → likely deleted/trashed
            relative_path = project_path.relative_to(GITHUB_REPO_LOCAL)
            action = "Would remove" if not cleanup_mode else "Removed"
            msg = f"🗑️  {action} backup for deleted/trashed project: {relative_path}"
            cleanup_log.append(msg)
            logger.info(msg)

            if cleanup_mode:
                try:
                    rmtree(project_path)
                except Exception as e:
                    err_msg = f"❌ Failed to remove {relative_path}: {e}"
                    cleanup_log.append(err_msg)
                    logger.error(err_msg)

    return cleanup_log


def ensure_repo_synced(repo_path):
    """Ensure local repo is synced with remote on startup (safe reset)"""
    try:
        run(["git", "-C", repo_path, "remote", "get-url", "origin"],
            check=True, stdout=DEVNULL, stderr=DEVNULL, timeout=10)
        run(["git", "-C", repo_path, "fetch", "origin"],
            check=True, stdout=DEVNULL, stderr=DEVNULL, timeout=30)
        run(["git", "-C", repo_path, "reset", "--hard", "origin/main"],
            check=True, stdout=DEVNULL, stderr=DEVNULL, timeout=30)
        logger.info("✓ Repository synced with remote origin/main")
    except Exception as e:
        logger.warning(f"Could not sync repo with remote: {e}")


def git_commit_and_push(repo_path, message):
    """Single batch commit/push with safe rebase to handle non-fast-forward"""
    try:
        # Stage changes
        run(["git", "-C", repo_path, "add", "."], check=True, stdout=DEVNULL, stderr=DEVNULL)

        # Check if there are changes to commit
        status = run(["git", "-C", repo_path, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=30)
        if not status.stdout.strip():
            return False, "No changes to commit"

        # Commit locally
        run(["git", "-C", repo_path, "commit", "-m", message],
            check=True, stdout=DEVNULL, stderr=DEVNULL)

        # SAFETY: Pull with rebase to integrate remote changes BEFORE push
        pull = run(["git", "-C", repo_path, "pull", "--rebase", "origin", "main"],
                  capture_output=True, text=True, timeout=60)

        if pull.returncode != 0:
            # If rebase fails (conflicts), abort to avoid data corruption
            run(["git", "-C", repo_path, "rebase", "--abort"],
                capture_output=True, text=True, timeout=10)
            raise RuntimeError(
                f"Rebase failed (possible concurrent modification). "
                f"Stderr: {pull.stderr[:400]}"
            )

        # Now push
        push = run(["git", "-C", repo_path, "push", "origin", "main"],
                  capture_output=True, text=True, timeout=180)
        if push.returncode != 0:
            raise RuntimeError(f"Push failed after rebase: {push.stderr[:400]}")

        changed_files = len([l for l in status.stdout.strip().split('\n') if l])
        return True, f"Pushed {changed_files} files"

    except Exception as e:
        raise RuntimeError(f"Git operation failed: {e}")


def send_log_by_email(subject, body):
    """
    Send an email containing the backup report.

    This function sends an email with the specified subject and body content
    using the configured SMTP server. It is used to notify the user about
    the results of the backup process, including any errors, updates, or
    other relevant details.

    Args:
        subject (str): The subject line of the email.
        body (str): The body content of the email, typically a detailed
            report of the backup process.

    Logs:
        - Logs an error message if the email fails to send.

    Raises:
        Exception: If there is an issue with the SMTP connection or sending
        the email, the exception is logged but not re-raised.
    """
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg['From'] = formataddr(('ICIC Overleaf Backup script', 'overleaf-backups@icic.uns.edu.ar'))
    msg["Reply-To"] = FROM_EMAIL
    msg["To"] = TO_EMAIL

    try:
        with SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(FROM_EMAIL, FROM_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def main():
    """Main backup orchestration function"""
    parser = argparse.ArgumentParser(
        description='Overleaf backup script with intelligent change detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 overleaf_backup.py                    # Incremental backup (default)
  python3 overleaf_backup.py --force            # Force export all active projects
  python3 overleaf_backup.py --cleanup-deleted  # Remove backups of deleted projects
  python3 overleaf_backup.py --dry-run          # Simulate without making changes
  python3 overleaf_backup.py --workers 8        # Use 8 parallel workers
        """
    )
    parser.add_argument('--force', action='store_true',
                        help='Force export of ALL active projects (ignores timestamps)')
    parser.add_argument('--cleanup-deleted', action='store_true',
                        help='Remove backup directories of deleted/trashed projects')
    parser.add_argument('--workers', type=int, default=4,
                        help='Number of parallel workers (default: 4)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulate backup without making changes')
    parser.add_argument('--verbose-email', action='store_true',
                        help='Include detailed logs in email (default: summary only)')
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    force_mode = args.force
    cleanup_mode = args.cleanup_deleted and not args.dry_run
    dry_run = args.dry_run
    verbose_email = args.verbose_email

    if dry_run:
        logger.warning("⚠️  DRY RUN MODE - No changes will be committed or pushed")

    # Load metadata from MongoDB
    logger.info("Exporting MongoDB collections...")
    users = export_mongo_collection_with_timestamp("users")
    user_email_map = {u["_id"]["$oid"]: u.get("email", "unknown") for u in users}

    projects = export_mongo_collection_with_timestamp("projects")
    # Note: We don't need the "docs" collection anymore for timestamp checking!

    # Sync repo with remote BEFORE processing (critical for safety)
    if not dry_run:
        logger.info("Syncing repository with remote...")
        ensure_repo_synced(GITHUB_REPO_LOCAL)

    # Get last backup time from Git log (for timestamp comparison)
    last_backup_time = None
    if not force_mode:
        try:
            last_commit = run(["git", "-C", GITHUB_REPO_LOCAL, "log", "-1", "--format=%cI"],
                             capture_output=True, text=True, timeout=10)
            if last_commit.returncode == 0 and last_commit.stdout.strip():
                ts = last_commit.stdout.strip().replace('Z', '+00:00')
                last_backup_time = datetime.fromisoformat(ts)
                if last_backup_time.tzinfo is None:
                    last_backup_time = last_backup_time.replace(tzinfo=timezone.utc)
                logger.info(f"Last backup: {last_backup_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            logger.warning(f"Could not determine last backup time: {e}")

    # Filter active projects and pre-count exports
    active_projects = []
    for p in projects:
        is_active, _ = is_project_active(p)
        if is_active:
            active_projects.append(p)

    # Pre-count projects that will be exported vs skipped
    export_count = 0
    skip_count = 0
    for p in active_projects:
        should_export, _ = should_export_project(p, last_backup_time, force_mode)
        if should_export:
            export_count += 1
        else:
            skip_count += 1

    mode_msg = "FORCED" if force_mode else "INCREMENTAL"
    if cleanup_mode:
        mode_msg += " + CLEANUP"

    logger.info(f"Projects: {len(projects)} total, {len(active_projects)} active, "
                f"{export_count} to export, {skip_count} skipped (no changes)")
    logger.info(f"Processing in {mode_msg} mode with {args.workers} workers...")

    # Track paths of active projects for cleanup later
    active_project_paths = set()

    # Parallel processing of projects
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_project,
                p,
                user_email_map,
                last_backup_time,
                force_mode
            ): p
            for p in active_projects
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result(timeout=600)  # 10 min timeout per project

                # Skip deleted/trashed projects
                if result[0] is None and result[1] is None:
                    continue

                changed, msg, repo_dest = result
                if repo_dest:
                    active_project_paths.add(repo_dest)

            except Exception as e:
                proj = futures[future]
                pname = proj.get("name", "unknown")
                oid = proj.get("owner_ref", {}).get("$oid", "unknown")
                email = user_email_map.get(oid, "unknown")
                err_msg = f"❌ {pname} ({email}) — Timeout/exception"
                log_errors.append(err_msg)
                logger.error(f"{err_msg}: {str(e)[:200]}")

    # Cleanup deleted/trashed project directories (optional)
    if cleanup_mode or args.dry_run:
        logger.info(f"Scanning for deleted/trashed project backups to {'remove' if cleanup_mode else 'report'}...")
        cleanup_log = cleanup_deleted_projects(active_project_paths, cleanup_mode=cleanup_mode)
        log_cleanup.extend(cleanup_log)

    # Git operations (commit and push)
    git_result = "Skipped (dry-run)"
    git_pushed = False
    if not dry_run:
        try:
            # Build commit message
            commit_parts = []
            if force_mode:
                commit_parts.append("FORCED")
            if cleanup_mode:
                commit_parts.append("CLEANUP")
            commit_prefix = " ".join(commit_parts) + " " if commit_parts else ""
            commit_msg = f"{commit_prefix}Backup {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Commit and push
            pushed, git_msg = git_commit_and_push(GITHUB_REPO_LOCAL, commit_msg)
            git_pushed = pushed
            git_result = git_msg if pushed else "No changes"
            if pushed:
                log_git.append(f"📤 Git: {git_msg}")
                logger.info(f"📤 Git: {git_msg}")
        except Exception as e:
            err_msg = f"❌ Git push failed: {e}"
            log_errors.append(err_msg)
            logger.error(err_msg)

    # Calculate statistics
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    total_projects = len(projects)
    active_count = len(active_projects)
    deleted_count = len(log_skipped)
    updated_count = len(log_updated)
    error_count = len(log_errors)
    cleaned_count = len([m for m in log_cleanup if 'Removed' in m])

    # Build CONCISE email (only what matters)
    subject_prefix = "[DRY-RUN] " if dry_run else ""
    subject_suffix = " ✅" if git_pushed and not log_errors else (" ⚠️" if log_errors else "")

    if log_errors:
        subject = f"{subject_prefix}[Overleaf Backup] {error_count} errors"
    elif updated_count > 0:
        subject = f"{subject_prefix}[Overleaf Backup] {updated_count} project(s) updated{subject_suffix}"
    else:
        subject = f"{subject_prefix}[Overleaf Backup] No changes{subject_suffix}"

    # Email body - concise by default
    body_lines = []
    body_lines.append(f"OVERLEAF BACKUP REPORT")
    body_lines.append(f"{'='*50}")
    body_lines.append(f"")
    body_lines.append(f"Duration: {duration:.1f} seconds")
    body_lines.append(f"Mode: {mode_msg}")
    body_lines.append(f"Workers: {args.workers}")
    body_lines.append(f"")
    body_lines.append(f"SUMMARY")
    body_lines.append(f"{'-'*50}")
    body_lines.append(f"• Total projects in DB: {total_projects}")
    body_lines.append(f"• Active projects: {active_count}")
    body_lines.append(f"• Deleted/trashed skipped: {deleted_count}")
    body_lines.append(f"• Projects exported: {export_count}")
    body_lines.append(f"• Projects updated: {updated_count}")
    if cleaned_count > 0:
        body_lines.append(f"• Old backups cleaned: {cleaned_count}")
    body_lines.append(f"• Errors: {error_count}")
    body_lines.append(f"")

    # Only show updated projects (what was actually pushed to GitHub)
    if updated_count > 0:
        body_lines.append(f"UPDATED PROJECTS ({updated_count})")
        body_lines.append(f"{'-'*50}")
        for msg in log_updated:
            body_lines.append(f"  {msg}")
        body_lines.append(f"")

    # Always show errors (actionable)
    if log_errors:
        body_lines.append(f"ERRORS ({error_count})")
        body_lines.append(f"{'-'*50}")
        for msg in log_errors:
            body_lines.append(f"  {msg}")
        body_lines.append(f"")

    # Git result
    body_lines.append(f"GIT OPERATIONS")
    body_lines.append(f"{'-'*50}")
    body_lines.append(f"  Status: {git_result}")

    # Verbose mode (for debugging)
    if verbose_email:
        body_lines.append(f"")
        body_lines.append(f"{'='*50}")
        body_lines.append(f"VERBOSE LOG (for debugging)")
        body_lines.append(f"{'='*50}")

        if log_nochanges:
            body_lines.append(f"")
            body_lines.append(f"No changes detected: {len(log_nochanges)} projects")

        if log_skipped:
            body_lines.append(f"")
            body_lines.append(f"Skipped (deleted/trashed): {deleted_count} projects")
            if deleted_count <= 20:  # Only list if not too many
                for msg in log_skipped[:20]:
                    body_lines.append(f"  {msg}")
            else:
                body_lines.append(f"  (too many to list - check logs)")

        if log_cleanup:
            body_lines.append(f"")
            body_lines.append(f"Cleanup actions: {len(log_cleanup)}")
            for msg in log_cleanup[:20]:
                body_lines.append(f"  {msg}")

    body = "\n".join(body_lines)

    # Send email
    if not dry_run:
        send_log_by_email(subject, body)

    # Console summary
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"BACKUP COMPLETED")
    logger.info(f"{'='*60}")
    logger.info(f"Duration: {duration:.1f}s | Active: {active_count}/{total_projects}")
    logger.info(f"Exported: {export_count} | Updated: {updated_count} | Errors: {error_count}")
    if cleaned_count > 0:
        logger.info(f"Cleaned: {cleaned_count} old backups")
    logger.info(f"{'='*60}")

    # Exit code for automation
    exit(1 if log_errors else 0)


if __name__ == "__main__":
    main()

