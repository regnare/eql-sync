# EverQuest Legends Sync Tool (eql-sync)

This is a portable, zero-dependency Python script to synchronize macros, hotbars, keybinds, and HUD layouts between macOS and Linux.

It features Wine-aware game process checking, automatic resolution detection from `eqclient.ini`, local coordinate translation (scaling), and automatic safety backups.

## Setup Instructions

### 1. Installation
Copy the `eql_sync.py` script to both of your systems. It requires only Python 3 (installed by default on macOS and CachyOS Linux).

### 2. Initialization
Run the initialization wizard on each machine to configure paths, screen resolution fallback, sync folder, and character list:

```bash
python eql_sync.py init
```

This will guide you through entering:
*   **EverQuest Path**: The directory where `eqclient.ini` and character files reside (e.g. `Faugus_legends.ini`).
*   **Sync Shared Directory**: A shared folder synced via **Dropbox**, **Syncthing**, **iCloud**, etc.
*   **Characters**: Names of characters to sync (comma-separated, e.g. `Faugus_legends`).
*   **UI Sync Mode**: Options to scale coordinates (`scale_position`), scale everything (`scale_all`), copy layout exactly (`exact`), or skip layout sync (`none`).
*   **Resolution Fallback**: Default resolution if `eqclient.ini` can't be parsed.
*   **Machine Name**: E.g. `desktop` or `macbook`.

This generates a local `config.json` file.

## Usage

### Pushing local settings to the sync folder
When you finish playing on a machine and want to save your macros, hotkeys, and UI layout:
```bash
python eql_sync.py push
```
*If the game is still running, the script will show a warning.*

### Pulling settings from the sync folder
Before you launch the game on the other machine, pull the latest changes:
```bash
python eql_sync.py pull
```
*This will automatically create a backup of your local files in `[EQ_Dir]/sync_backups/` before applying any changes.*

### Checking status
You can check the modification times and current sync configuration by running:
```bash
python eql_sync.py status
```

## How Resolution Scaling Works
EverQuest UI coordinates are stored in absolute pixels in `UI_[CharacterName]_[ServerName].ini`.
When you `push`, the script automatically detects your active resolution (by reading `eqclient.ini`) and uploads the UI file with a small `.meta.json` file containing the resolution details.

When you `pull` on the other system, if the source resolution differs from the destination, the script:
1. Detects your destination resolution from `eqclient.ini`.
2. Translates the position coordinates (`XPos`, `YPos`, `XOffset`, `YOffset`) of all UI windows proportionally.
3. Leaves window widths/heights constant (under `scale_position` mode) so text remains fully readable and doesn't clip.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer
This project was developed with the assistance of Antigravity, an AI coding assistant by Google DeepMind.
