# Omniclone

Omniclone is an automated rclone-based sync and backup orchestrator. It manages multiple rclone tasks (bisync and backup) using a unified configuration and filter system, and can be run manually or as a systemd timer/service for scheduled operation.

# Features

- Automated rclone bisync and backup tasks
- Configurable targets via `config.json`
- Customizable filter files for exclusions
- Systemd integration for scheduled runs on Linux
- Locking and logging for safe, traceable operation

## Quick Start

1. Clone or copy the project files to a directory.
2. Edit `config.json` to define your sync and backup targets.
3. (Optional) Create custom filter files to exclude files/folders.
4. Run manually or install as a systemd timer/service.

## Configuration: `config.json`

The `config.json` file defines all sync and backup tasks. Example:

```json
{
    "tasks": {
        "bisync": {
            "rclone": {
                "src": "~/rclone-gdrive",
                "dst": "gdrive:rclone",
                "extra_flags": ["--drive-skip-gdocs"]
            }
        },
        "backup": {
            "backup_test": {
                "src": "~/rclone-gdrive-backup",
                "dst": "gdrive:backup_test",
                "disabled": true
            }
        }
    }
}
```

### Target Types

- **BISYNC**: Uses rclone's `bisync` mode for two-way synchronization. Changes on both sides are mirrored. Good for folders that need to stay identical in both locations. **Remember**: `--resync` is necessary for the first run; you can add it to the `extra_flags` on the target and remove it afterwards.
- **BACKUP**: Uses rclone's `sync` mode for one-way backup. Source is copied to destination, and files deleted from source are also deleted from destination. Use for backup scenarios.

Each target must specify:

- `src`: Source directory (local path, can use `~` for home)
- `dst`: Destination (rclone remote path)
- `extra_flags`: (Optional, array) Additional rclone flags for this target
- `disabled`: (Optional, boolean) If set to `true`, the task will be skipped during execution. Useful for temporarily disabling sync/backup jobs without removing their configuration

## Custom Filters

Omniclone supports exclusion filters using rclone's `--filter-from` option. Filters can be set globally or per-target:

- **Global filter for a mode**: `filters.bisync.txt` or `filters.backup.txt`
- **Target-specific filter**: `filters.bisync.<target>.txt` or `filters.backup.<target>.txt`

**Example:**

- `filters.bisync.rclone.txt` applies only to the `rclone` bisync target
- `filters.backup.backup_test.txt` applies only to the `backup_test` backup target
- `filters.backup.txt` applies to all backup tasks

Filter files use rclone's filter syntax. Example:

```
- *.tmp         # Exclude all .tmp files
- .cache/       # Exclude .cache directory
```

## Running Omniclone

- **Manual run:**
    ```bash
    ./omniclone.py
    ```
- **Linux only: Install as systemd timer/service:**
    ```bash
    ./omniclone.py install
    ```
    This sets up a user systemd timer to run every 30 minutes.
- **Linux only: Uninstall systemd timer/service:**
    ```bash
    ./omniclone.py uninstall
    ```
- **Linux only: Check status/logs:**
    ```bash
    ./omniclone.py status
    ```

## Advanced

- **Flags:**
    - Global and per-mode flags are set in `flags.json`.
    - Terminal and systemd runs use different logging/stats flags.
- **Locking:**
    - Prevents concurrent runs using a lockfile directory.
- **Internet check:**
    - Skips sync if no internet connection is detected.

## Requirements

- Python 3
- rclone installed and configured
- For automated service management, requires a systemd-based Linux system

## License

MIT
