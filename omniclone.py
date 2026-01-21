#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2026 Kopert

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import getpass
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- Path Resolution ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
FLAGS_FILE = SCRIPT_DIR / "flags.json"
SERVICE_TEMPLATE = SCRIPT_DIR / "omniclone.service"
TIMER_TEMPLATE = SCRIPT_DIR / "omniclone.timer"
LOG_FILE = SCRIPT_DIR / "omniclone.log"

# --- Logging Setup ---
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
LOG_STREAM_FORMATTER = logging.Formatter("[%(levelname)s] %(message)s")
LOG_FILE_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
LOG_FILE_HANDLER = RotatingFileHandler(
    LOG_FILE,
    mode="a",
    maxBytes=5 * 1024 * 1024,
    backupCount=1,
    encoding="utf-8",
    delay=False,
)
LOG_FILE_HANDLER.setFormatter(LOG_FILE_FORMATTER)
LOGGER.addHandler(LOG_FILE_HANDLER)
LOG_STREAM_HANDLER = logging.StreamHandler(sys.stdout)
LOG_STREAM_HANDLER.setFormatter(LOG_STREAM_FORMATTER)
LOGGER.addHandler(LOG_STREAM_HANDLER)

# --- Argument Parser ---
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    "--service", action="store_true", help="Force service-mode behavior"
)
PARSER.add_argument(
    "--install", action="store_true", help="Install as a systemd service"
)
PARSER.add_argument(
    "--uninstall", action="store_true", help="Uninstall the systemd service"
)
PARSER.add_argument(
    "--status", action="store_true", help="Show the status of the systemd service"
)
ARGS = PARSER.parse_args()
IS_SERVICE = ARGS.service
IS_INSTALL = ARGS.install
IS_UNINSTALL = ARGS.uninstall
IS_STATUS = ARGS.status


# --- Load Data ---
def load_json(path):
    if not path.exists():
        LOGGER.error(f"Error: Required file not found at {path}")
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
        LOGGER.warning(
            f"Lock directory exists. Another instance may be running. If not, delete {LOCK_DIR}"
        )
        return False


def release_lock():
    try:
        if LOCK_DIR.exists():
            LOCK_DIR.rmdir()
    except Exception as e:
        LOGGER.warning(f"Could not release lock: {e}")


# --- Linux Service Management Functions ---
def install_systemd():
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    # Path to the actual script, not the symlink
    script_path = os.path.abspath(__file__)
    exec_start_cmd = (
        f"{shlex.quote(sys.executable)} {shlex.quote(script_path)} --service"
    )

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
    LOGGER.info(f"Enabling linger for {current_user} (requires sudo)...")
    subprocess.run(["sudo", "loginctl", "enable-linger", current_user])
    LOGGER.info("Installation complete.")


def uninstall_systemd():
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{SERVICE_NAME}.timer"],
        stderr=subprocess.DEVNULL,
    )
    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.service").unlink(missing_ok=True)
    (SYSTEMD_USER_DIR / f"{SERVICE_NAME}.timer").unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    LOGGER.info("Uninstalled systemd units.")


def show_status_systemd():
    subprocess.run(
        ["systemctl", "--user", "list-timers", f"{SERVICE_NAME}.timer", "--no-pager"]
    )
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


def windows_check_admin_and_elevate():
    import ctypes

    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False

    if not is_admin:
        LOGGER.info("Requesting elevation...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        LOGGER.info("Elevation requested. Exiting non-privileged instance.")
        sys.exit(0)  # Exit the non-privileged instance


def install_windows_task():
    windows_check_admin_and_elevate()

    LOGGER.info("Installing Windows Task Scheduler task via PowerShell...")

    script_path = os.path.abspath(__file__)
    # Using pythonw.exe ensures no console window pops up when the task runs
    python_exe = sys.executable.lower().replace("python.exe", "pythonw.exe")
    current_user = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"

    # We set up the task with a PowerShell script block to allow for S4U logon type (background task) with no password stored
    ps_command = f"""
    $action = New-ScheduledTaskAction -Execute '{python_exe}' -Argument '"{script_path}" --service'
    # Create a trigger for every 30 minutes
    $trigger = New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Minutes 15)
    # S4U is the "Do not store password" magic flag
    $principal = New-ScheduledTaskPrincipal -UserId "{current_user}" -LogonType S4U
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName "{SERVICE_NAME}" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Priority 8 -Force
    """

    try:
        run_subprocess_with_logging(
            ["powershell", "-NoProfile", "-Command", ps_command]
        )
        LOGGER.info(f"Windows Task '{SERVICE_NAME}' created successfully.")
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Failed to create Windows Task: {e.stderr}")
    except Exception as e:
        LOGGER.error(f"An unexpected error occurred: {e}")

    input("Press Enter to exit...")


def uninstall_windows_task():
    windows_check_admin_and_elevate()
    ps_command = f'Unregister-ScheduledTask -TaskName "{SERVICE_NAME}" -Confirm:$false'
    try:
        run_subprocess_with_logging(
            ["powershell", "-NoProfile", "-Command", ps_command]
        )
        LOGGER.info(f"Windows Task '{SERVICE_NAME}' unregistered successfully.")
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Failed to uninstall Windows Task: {e.stderr}")
    input("Press Enter to exit...")


def show_status_windows_task():
    try:
        # We capture output just so we can control the 'error' message if it's missing
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", SERVICE_NAME, "/V", "/FO", "LIST"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
    except subprocess.CalledProcessError:
        print(f"\n[!] Task '{SERVICE_NAME}' is not currently installed.")


def run_subprocess_with_logging(cmd):
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                clean_line = line.strip()
                if clean_line:
                    # Log everything coming from the subprocess
                    LOGGER.info(f"[subprocess] {clean_line}")

            process.stdout.close()

        return process.wait()
    except KeyboardInterrupt:
        LOGGER.warning("Script interrupted by user. Terminating...")
        if process:
            process.terminate()
        raise Exception("Interrupted by user")
    except Exception as e:
        LOGGER.error(f"An error occurred while running subprocess: {e}")
        if process:
            process.terminate()
        raise
    finally:
        if process and process.poll() is None:
            process.kill()


# --- Core Sync Function ---
def run_rclone(cmd_type, src, dst, base_flags, extra_flags):
    cmd = ["rclone", "bisync" if cmd_type == "bisync" else "sync", str(src), str(dst)]

    LOGGER.info(
        f"Starting {cmd_type}: {src} {'<-->' if cmd_type == 'bisync' else '-->'} {dst}"
    )

    try:
        return_code = run_subprocess_with_logging(cmd + base_flags + extra_flags)
        if return_code == 0:
            LOGGER.info(
                f"Finished {cmd_type}: {src} {'<-->' if cmd_type == 'bisync' else '-->'} {dst}"
            )
        else:
            LOGGER.error(f"{cmd_type} failed for {src} with exit code {return_code}")
    except Exception as e:
        LOGGER.error(f"An error occurred while running rclone: {e}")


# --- Main Execution ---
def main():
    if IS_INSTALL or IS_UNINSTALL or IS_STATUS:
        if IS_INSTALL:
            if os.name == "nt":
                install_windows_task()
            else:
                install_systemd()
        elif IS_UNINSTALL:
            if os.name == "nt":
                uninstall_windows_task()
            else:
                uninstall_systemd()
        elif IS_STATUS:
            if os.name == "nt":
                show_status_windows_task()
            else:
                show_status_systemd()
        return

    if not acquire_lock():
        LOGGER.error("Another instance is already running.")
        sys.exit(0)

    try:
        if not check_internet():
            LOGGER.error("No internet connection. Skipping sync.")
            sys.exit(1)
        # Iterate through TASKS (bisync, backup)
        for mode, tasks in TASKS.items():
            # Select base flags from flags.json based on key name
            base_flags = FLAGS_BISYNC if mode == "bisync" else FLAGS_BACKUP

            for task_name, cfg in tasks.items():
                # Skip disabled tasks
                if cfg.get("disabled", False):
                    LOGGER.info(f"Skipping disabled task: {task_name} ({mode})")
                    continue
                # Expand paths
                src_path = Path(cfg["src"]).expanduser().resolve()
                dst_path = (
                    str(Path(cfg["dst"]).expanduser().resolve())
                    if ":" not in cfg["dst"]
                    else cfg["dst"]
                )

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
