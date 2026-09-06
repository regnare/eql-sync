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

Configuration is saved to `~/.config/eql-sync/config.json`.

### Optional: Installing as a global command (`install`)
To run `eql-sync` from any directory without specifying the script path, run:
```bash
./eql_sync.py install
```
This will:
*   Make the script executable (`chmod +x`).
*   Create symlinks `eql-sync` and `eql_sync` in `~/.local/bin/`.
*   Migrate any local `config.json` to `~/.config/eql-sync/config.json` automatically.
*   Detect your active shell (`~/.zshrc`, `~/.bashrc`, `config.fish`), check if `~/.local/bin` is in your `$PATH`, and prompt you to automatically add it if missing (or pass `--add-path` to add it automatically without prompting).

## Usage

### Viewing Options & Help
To view options for a specific subcommand, put `-h` after the command (e.g. `eql-sync play -h`).
To view all available options across all subcommands in one reference:
```bash
eql-sync --help-all
# or: eql-sync --all
```

### Pushing local settings to the sync folder
When you finish playing on a machine and want to save your macros, hotkeys, spell slots, and (optionally) UI layout:
```bash
eql-sync push
# or: python eql_sync.py push
```
*If the game is still running, the script will show a warning.*

**Options:**
*   `--no-ui`: Skip UI/HUD layout sync for this run (only pushes macros/hotbars/spell slots).
*   `--ui-mode {scale_position,scale_all,exact,none}`: Override UI sync mode temporarily.
*   `--force`: Bypass process checks (if the game is running) and force-overwrite synced files.
*   `--dry-run`: Simulate pushing settings without writing any files or changes.

*Example (only push hotbars/macros/spell slots):*
```bash
python eql_sync.py push --no-ui
```

### Pulling settings from the sync folder
Before you launch the game on the other machine, pull the latest changes:
```bash
python eql_sync.py pull
```
*This will automatically create a backup of your local files in `[EQ_Dir]/sync_backups/` before applying any changes.*

**Options:**
*   `--no-ui`: Skip pulling/applying UI/HUD layouts for this run.
*   `--ui-mode {scale_position,scale_all,exact,none}`: Override UI sync mode temporarily.
*   `--force`: Bypass confirmation prompts and process checks.
*   `--dry-run`: Simulate pulling settings without writing any local files, changes, or backups.

*Example (only pull macros/hotbars/spell slots):*
```bash
python eql_sync.py pull --no-ui
```

### Checking status (`status` / `check`)
Inspect timestamps side-by-side to see whether your local files or shared sync files are newer, along with a recommendation on whether to push or pull:
```bash
python eql_sync.py status
# or
python eql_sync.py check
```

Example output:
```text
--- Character: Regnare ---
  Profile: Regnare_freeport_LO1
    Settings/Macros (Regnare_freeport_LO1.ini):
      Local:  2026-09-04 17:47:58
      Sync:   2026-09-04 17:47:58
      Status: [IN SYNC]
  Profile: Regnare_freeport_LO2
    Settings/Macros (Regnare_freeport_LO2.ini):
      Local:  2026-09-05 13:20:00
      Sync:   2026-09-01 16:20:16
      Status: [LOCAL NEWER -> PUSH RECOMMENDED]

=== Summary Recommendation ===
-> Local files are newer (1 file(s) to push).
   Recommended command: ./eql_sync.py push
```

### Intelligent Auto-Sync (`auto` / `sync`)
Automatically compares file modification times on a per-profile basis and pushes or pulls in the correct direction:
```bash
python eql_sync.py auto
# or
python eql_sync.py sync
```
*   **Local is newer**: Backs up the sync copy in `[Sync_Dir]/sync_backups/` and pushes local $\to$ sync.
*   **Sync is newer**: Backs up your local file in `[EQ_Dir]/sync_backups/` and pulls sync $\to$ local.
*   **Already in sync**: Leaves files untouched.
*   Supports `--dry-run` (`-d`) to preview all decisions safely without modifying anything.

### Seamless Play Session Wrapper (`play`)
Automates the entire gaming lifecycle with pre-game and post-game synchronization:
```bash
eql-sync play
# or: python eql_sync.py play
```
1. **Pre-Game Sync**: Runs `auto` to pull any newer macros, hotbars, or settings from your other computer before starting.
2. **Launches EverQuest**: Executes your platform launch command (`open -a osxEQL` on macOS, `faugus-launcher` on Linux).
3. **Monitors Session**: Detects `eqgame.exe` in the background and monitors the session until you exit.
4. **Post-Game Sync**: Waits 3 seconds for file buffers to flush, then runs `auto` to push your updated character settings back to the sync folder.

**Options:**
*   `-c`, `--command "..."`: Override the game launch command for this run.
*   `--wait-timeout [seconds]`: Seconds to wait for `eqgame.exe` to start (default: 120).
*   `--no-pre-sync`: Skip pre-game sync.
*   `--no-post-sync`: Skip post-game sync.
*   `-d`, `--dry-run`: Preview the play workflow without launching the game or writing files.

### Smart Backup Pruning (`prune`)
Backups are created automatically in `sync_backups/` whenever files are modified or pulled. The built-in pruner keeps your folders tidy:
*   **Retention**: Keeps the **10 most recent backups** per file.
*   **Safety rule**: Backups older than **30 days** are removed, but a minimum of **3 most recent backups** are always preserved.
*   Pruning runs automatically during backups, or you can trigger it manually:
```bash
python eql_sync.py prune
```
Options:
*   `--max-backups [N]`: Customize the number of backups kept per file (default: 10).
*   `--max-days [N]`: Customize maximum age in days (default: 30).
*   `-d`, `--dry-run`: Preview what would be deleted without removing files.

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
