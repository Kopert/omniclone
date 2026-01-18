#!/usr/bin/env python3
import getpass
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Path Resolution ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
FLAGS_FILE = SCRIPT_DIR / "flags.json"
SERVICE_TEMPLATE = SCRIPT_DIR / "omniclone.service"
TIMER_TEMPLATE = SCRIPT_DIR / "omniclone.timer"


# --- Load Data ---
def load_json(path):
    if not path.exists():
        logger.error(f"Error: Required file not found at {path}")
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


CONFIG = load_json(CONFIG_FILE)
FLAGS_DATA = load_json(FLAGS_FILE)

TASKS = CONFIG.get("tasks", {})
LOCK_DIR = Path(tempfile.gettempdir()) / f"omniclone_lock_{getpass.getuser()}"
SERVICE_NAME = "omniclone"
SYSTEMD_USER_DIR = Path.home() / ".config/systemd/user"

# --- Construct Flag Arrays ---
# Merging base flags with the specific sync-type flags from JSON
FLAGS_BISYNC = FLAGS_DATA["base"] + FLAGS_DATA["bisync"]
FLAGS_BACKUP = FLAGS_DATA["base"] + FLAGS_DATA["backup"]
FLAGS_TERMINAL = FLAGS_DATA["terminal"]
FLAGS_SYSTEMD = FLAGS_DATA["systemd"]


# --- Utility Functions ---
def check_internet():
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", "5000", "8.8.8.8"]
    else:
        cmd = ["ping", "-c", "1", "-W", "5", "8.8.8.8"]

    try:
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_filter_flags(mode, task):
    """
    Constructs rclone filter flags based on file existence.
    Checks for global: filters.backup.txt
    Checks for specific: filters.backup.backup_test.txt
    """
    filters = []

    # 1. Check for Global Mode Filter (e.g., filters.bisync.txt)
    global_filter = SCRIPT_DIR / f"filters.{mode}.txt"
    if global_filter.exists():
        filters.extend(["--filter-from", str(global_filter)])

    # 2. Check for Task-Specific Filter (e.g., filters.bisync.rclone.txt)
    task_filter = SCRIPT_DIR / f"filters.{mode}.{task}.txt"
    if task_filter.exists():
        filters.extend(["--filter-from", str(task_filter)])

    return filters


def acquire_lock():
    try:
        LOCK_DIR.mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        logger.warning(
            f"Lock directory exists. Another instance may be running. If not, delete {LOCK_DIR}"
        )
        return False


def release_lock():
    try:
        if LOCK_DIR.exists():
            LOCK_DIR.rmdir()
    except Exception as e:
        logger.warning(f"Could not release lock: {e}")


# --- Linux Service Management Functions ---
def install_systemd():
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    # Path to the actual script, not the symlink
    script_path = os.path.abspath(__file__)
    exec_start_cmd = f"{shlex.quote(sys.executable)} {shlex.quote(script_path)}"

    # Load and process templates
    service_content = SERVICE_TEMPLATE.read_text().replace(
        "{{EXEC_START}}", exec_start_cmd
    )
    timer_content = TIMER_TEMPLATE.read_text()

    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.service").write_text(service_content)
    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.timer").write_text(timer_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{SERVICE_NAME}.timer"])

    current_user = getpass.getuser()
    logger.info(f"Enabling linger for {current_user} (requires sudo)...")
    subprocess.run(["sudo", "loginctl", "enable-linger", current_user])
    logger.info("Installation complete.")


def uninstall_systemd():
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{SERVICE_NAME}.timer"],
        stderr=subprocess.DEVNULL,
    )
    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.service").unlink(missing_ok=True)
    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.timer").unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    logger.info("Uninstalled systemd units.")


def show_status():
    logger.info("--- Timer Status ---")
    subprocess.run(
        ["systemctl", "--user", "list-timers", f"{SERVICE_NAME}.timer", "--no-pager"]
    )
    logger.info("\n--- Last Sync Logs ---")
    subprocess.run(
        [
            "journalctl",
            "--user",
            "-u",
            f"{SERVICE_NAME}.service",
            "-n",
            "20",
            "--no-hostname",
            "--no-pager",
        ]
    )


# --- Core Sync Function ---
def run_rclone(cmd_type, src, dst, base_flags, extra_flags):
    cmd = ["rclone", "bisync" if cmd_type == "bisync" else "sync", str(src), str(dst)]
    mode_flags = FLAGS_TERMINAL if sys.stdout.isatty() else FLAGS_SYSTEMD
    full_flags = base_flags + mode_flags + extra_flags

    logger.info(
        f"Starting {cmd_type}: {src} {'<-->' if cmd_type == 'bisync' else '-->'} {dst}"
    )

    result = subprocess.run(cmd + full_flags)

    if result.returncode == 0:
        logger.info(f"Finished {cmd_type}: {src}")
    else:
        logger.error(f"{cmd_type} failed for {src} with exit code {result.returncode}")


# --- Main Execution ---
def main():
    if len(sys.argv) > 1:
        if os.name == "nt":
            logger.warning("Automatic service management is not supported on Windows.")
            return
        arg = sys.argv[1].lower()
        if arg == "install":
            install_systemd()
        elif arg == "uninstall":
            uninstall_systemd()
        elif arg == "status":
            show_status()
        return

    if not acquire_lock():
        logger.error("Another instance is already running.")
        sys.exit(0)

    try:
        if not check_internet():
            logger.error("No internet connection. Skipping sync.")
            sys.exit(1)
        # Iterate through TASKS (bisync, backup)
        for mode, tasks in TASKS.items():
            # Select base flags from flags.json based on key name
            base_flags = FLAGS_BISYNC if mode == "bisync" else FLAGS_BACKUP

            for task_name, cfg in tasks.items():
                # 1. Expand paths
                src_path = Path(cfg["src"]).expanduser().resolve()
                dst_raw = cfg["dst"]
                # Expand dst only if it doesn't look like a remote (doesn't contain ':')
                if ":" not in dst_raw:
                    dst_path = str(Path(dst_raw).expanduser().resolve())
                else:
                    dst_path = dst_raw

                # 2. Get cascading filters
                filters = get_filter_flags(mode, task_name)

                # 3. Collect extra flags from config.json
                extras = cfg.get("extra_flags", [])

                # 4. Run it
                run_rclone(mode, src_path, dst_path, base_flags, filters + extras)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
