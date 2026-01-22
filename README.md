# Omniclone

Omniclone is an automated rclone-based sync and backup orchestrator. It manages multiple rclone tasks (bisync and backup) using a unified configuration and filter system, and can be run manually or as a systemd timer/service for scheduled operation.

# Features

- Automated rclone bisync and backup tasks
- Configurable targets via `config.json`
- Customizable filter files for exclusions
- Systemd integration for scheduled runs on Linux
- Task Scheduler integration for scheduled runs on Windows
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
        "service_name": "myservice",
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

### Global Parameters

- `service_name`: required only if you're using systemd/Windows Task Scheduler services with `--install`, `--uninstall`, and `--status`. It allows you to have multiple, independent `--config-dir` for multiple services.

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

- **Global filter for a mode**: `filters.bisync.txt` or `filters.backup.txt` in the script directory
- **Target-specific filter**: `filters.bisync.<target>.txt` or `filters.backup.<target>.txt` in the `--config-dir` directory (defaults to script directory)

**Example:**

- `filters.bisync.rclone.txt` applies only to the `rclone` bisync target
- `filters.backup.backup_test.txt` applies only to the `backup_test` backup target
- `filters.backup.txt` applies to all backup tasks

Filter files use rclone's filter syntax. Example:

```
- *.tmp         # Exclude all .tmp files
- .cache/       # Exclude .cache directory
```

## Supported Flags

Omniclone supports several command-line flags to control its behavior:

- `--install`: Install Omniclone as a systemd timer (Linux) or Windows Task Scheduler task (Windows).
- `--uninstall`: Uninstall the Omniclone scheduled task or timer.
- `--status`: Show the status of the Omniclone scheduled task or timer.
- `--service`: Force service-mode behavior (used internally by the scheduler/timer).
- `--config-dir`: Override the config directory (default: script directory). Use this to point to a different config, flags, and filter set.

**Example:**

```bash
./omniclone.py --config-dir /path/to/your/config --install
```

### Flags from `flags.json`

Omniclone uses `flags.json` to define the rclone flags used for all sync and backup operations. These are split into:

- **base**: Flags applied to all rclone operations (e.g., logging, stats, color, etc.)
- **bisync**: Additional flags for bisync tasks
- **backup**: Additional flags for backup tasks

You can customize these flags in `flags.json` to control rclone's behavior globally or per mode. Extra flags can also be set per target in `config.json`.

### Locking

Omniclone prevents concurrent runs using a lockfile directory.

### Internet check

Omniclone skips sync if no internet connection is detected.

## Requirements

- Python 3.8+
- rclone installed and configured

## License

MIT
