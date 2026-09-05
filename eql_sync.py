#!/usr/bin/env python3
import os
import sys
import json
import shutil
import datetime
import subprocess
import configparser
import re
import time

CONFIG_FILENAME = "config.json"
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.config/eql-sync")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, CONFIG_FILENAME)

def get_config_path():
    # 1. Primary standard path: ~/.config/eql-sync/config.json
    if os.path.exists(DEFAULT_CONFIG_PATH):
        return DEFAULT_CONFIG_PATH

    # 2. Check current working directory for local override
    cwd_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if os.path.exists(cwd_path):
        return cwd_path

    # 3. Check script directory
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
    if os.path.exists(script_path):
        return script_path

    # Default to ~/.config/eql-sync/config.json
    return DEFAULT_CONFIG_PATH

def load_config():
    path = get_config_path()
    if not os.path.exists(path):
        print(f"Error: Configuration file not found. Please run 'init' first.")
        print(f"Expected path: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config, target_path=None):
    if target_path is None:
        target_path = get_config_path()
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Configuration saved to: {target_path}")

def is_game_running():
    """Detects if eqgame.exe is running on macOS/Linux using Wine/Proton."""
    # 1. Try pgrep (fast and clean on both Linux and macOS)
    try:
        res = subprocess.run(["pgrep", "-i", "-f", "eqgame.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 2. Fallback to ps aux
    try:
        res = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = res.stdout.splitlines()
        for line in lines:
            if "eqgame.exe" in line.lower() and "grep" not in line.lower():
                return True
    except Exception:
        pass
    return False

def check_game_state_and_confirm(force=False):
    if force:
        print("Bypassing running game checks (--force).")
        return
    if is_game_running():
        print("\n" + "!" * 60)
        print("WARNING: EverQuest Legends process (eqgame.exe) is currently running!")
        print("Syncing while the game is running can lead to lost settings or corrupt files,")
        print("as the game client frequently overwrites settings when zoning or logging out.")
        print("!" * 60 + "\n")
        confirm = input("Do you want to force the sync anyway? (y/N): ")
        if confirm.lower() != 'y':
            print("Sync operation cancelled by user.")
            sys.exit(0)
    else:
        # Re-confirm closure manually just to be absolutely sure
        print("Checking processes... EverQuest does not appear to be running.")

def detect_resolution(eq_dir, config_resolution):
    """
    Parses eqclient.ini to detect the game's active resolution.
    Falls back to config_resolution if detection fails.
    """
    eqclient_path = os.path.join(eq_dir, "eqclient.ini")
    if not os.path.exists(eqclient_path):
        print(f"Warning: eqclient.ini not found in {eq_dir}. Using config fallback: {config_resolution}")
        return config_resolution
    
    try:
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        parser.optionxform = str
        with open(eqclient_path, 'r', encoding='utf-8', errors='ignore') as f:
            parser.read_file(f)
        
        if "VideoMode" in parser:
            video_mode = parser["VideoMode"]
            # 1. Check windowed mode
            is_windowed = video_mode.get("WindowedMode", "").upper() == "TRUE"
            if is_windowed:
                w = video_mode.get("WindowedWidth")
                h = video_mode.get("WindowedHeight")
                if w and h:
                    print(f"Detected Windowed Resolution: {w}x{h} (from eqclient.ini)")
                    return [int(w), int(h)]
            
            # 2. Fallback to fullscreen mode resolution
            w = video_mode.get("Width")
            h = video_mode.get("Height")
            if w and h:
                print(f"Detected Fullscreen Resolution: {w}x{h} (from eqclient.ini)")
                return [int(w), int(h)]
    except Exception as e:
        print(f"Warning: Failed to parse eqclient.ini for resolution ({e}). Using config fallback: {config_resolution}")
    
    return config_resolution

def prune_backups(backup_dir, max_backups=10, max_days=30, dry_run=False):
    """
    Prunes old backup files in backup_dir:
    - Retains up to max_backups most recent backups per original filename.
    - Prunes backups older than max_days, guaranteeing at least 3 most recent backups remain.
    """
    if not os.path.isdir(backup_dir):
        return []

    bak_pattern = re.compile(r"^(.*?)\.(\d{8}_\d{6})\.bak$")
    now = datetime.datetime.now()
    cutoff_time = now - datetime.timedelta(days=max_days)

    grouped_backups = {}
    try:
        entries = sorted(os.listdir(backup_dir))
    except Exception:
        return []

    for entry in entries:
        match = bak_pattern.match(entry)
        if match:
            orig_name = match.group(1)
            time_str = match.group(2)
            try:
                dt = datetime.datetime.strptime(time_str, "%Y%m%d_%H%M%S")
            except ValueError:
                dt = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(backup_dir, entry)))
            grouped_backups.setdefault(orig_name, []).append((dt, entry))

    pruned = []
    for orig_name, backups in grouped_backups.items():
        # Sort descending by timestamp (newest first)
        backups.sort(key=lambda x: x[0], reverse=True)

        for idx, (dt, entry) in enumerate(backups):
            file_path = os.path.join(backup_dir, entry)
            should_prune = False
            reason = ""

            if idx >= max_backups:
                should_prune = True
                reason = f"exceeds retention count of {max_backups}"
            elif idx >= 3 and dt < cutoff_time:
                should_prune = True
                reason = f"older than {max_days} days"

            if should_prune:
                pruned.append(entry)
                if dry_run:
                    print(f"    [DRY-RUN] Would prune old backup ({reason}): {entry}")
                else:
                    try:
                        os.remove(file_path)
                        print(f"    Pruned old backup ({reason}): {entry}")
                    except Exception as e:
                        print(f"    Warning: Could not remove {entry}: {e}")

    return pruned

def make_backup(directory, filename, dry_run=False, max_backups=10, max_days=30):
    """Creates a timestamped backup of a file in the sync_backups folder of directory and prunes old ones."""
    src = os.path.join(directory, filename)
    if not os.path.exists(src):
        return
    
    backup_dir = os.path.join(directory, "sync_backups")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"{filename}.{timestamp}.bak")
    if dry_run:
        print(f"    [DRY-RUN] Would create backup of {filename} at {dst}")
        prune_backups(backup_dir, max_backups=max_backups, max_days=max_days, dry_run=True)
        return
        
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Backup created: {dst}")
    prune_backups(backup_dir, max_backups=max_backups, max_days=max_days, dry_run=False)

def load_ini(file_path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            parser.read_file(f)
    return parser

def save_ini(parser, file_path):
    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        parser.write(f, space_around_delimiters=False)

def scale_ui_coordinates(parser, src_res, dest_res, mode):
    """
    Modifies coordinate values inside the parsed UI INI configuration.
    - scale_position: Scales XPos, YPos, XOffset, YOffset coordinates.
    - scale_all: Scales coordinates and Width/Height dimensions.
    """
    if mode == "none" or mode == "exact":
        return parser

    src_w, src_h = src_res
    dest_w, dest_h = dest_res
    
    if src_w == dest_w and src_h == dest_h:
        # Resolutions are identical, no translation needed
        return parser

    scale_x = dest_w / src_w
    scale_y = dest_h / src_h

    # Properties to scale
    pos_keys = {"XPos", "YPos", "XOffset", "YOffset"}
    dim_keys = {"Width", "Height"} if mode == "scale_all" else set()

    for section in parser.sections():
        for key in parser.options(section):
            val_str = parser.get(section, key)
            try:
                val = int(val_str)
            except ValueError:
                continue # Skip non-numeric values
            
            # Perform scaling
            if key in pos_keys:
                if "X" in key:
                    parser.set(section, key, str(round(val * scale_x)))
                elif "Y" in key:
                    parser.set(section, key, str(round(val * scale_y)))
            elif key in dim_keys:
                if key == "Width":
                    parser.set(section, key, str(round(val * scale_x)))
                elif key == "Height":
                    parser.set(section, key, str(round(val * scale_y)))
                    
    return parser

def cmd_init():
    print("=== EverQuest Legends Sync Configuration Wizard ===")
    
    # Suggest paths based on OS
    current_os = sys.platform
    username = os.environ.get("USER") or "user"
    default_eq_dir = ""
    if current_os == "darwin": # macOS
        default_eq_dir = f"/Users/{username}/Library/Application Support/osxEQL/prefix/drive_c/users/Public/Daybreak Game Company/Installed Games/EverQuest Legends"
    else: # linux or others
        default_eq_dir = f"/mnt/games/{username}/everquest-legends/drive_c/users/Public/Daybreak Game Company/Installed Games/EverQuest Legends"

    # 1. Local EQ Directory
    eq_dir = input(f"Enter local EverQuest installation path [{default_eq_dir}]: ").strip()
    if not eq_dir:
        eq_dir = default_eq_dir
    
    # 2. Sync Shared Directory
    default_sync_dir = os.path.join(os.path.expanduser("~"), "Dropbox", "eql_sync")
    sync_dir = input(f"Enter shared sync directory path [{default_sync_dir}]: ").strip()
    if not sync_dir:
        sync_dir = default_sync_dir
    
    # 3. Characters to Sync
    chars_input = input("Enter character name(s) to sync, comma-separated (e.g. Faugus_legends): ").strip()
    characters = [c.strip() for c in chars_input.split(",") if c.strip()]
    if not characters:
        print("Warning: No characters specified yet. You can add them to config.json later.")
        characters = []

    # 4. UI Sync Mode
    print("\nUI Sync Modes:")
    print("  1. scale_position (Recommended) - Scales HUD window coordinates, keeps size constant.")
    print("  2. scale_all - Scales coordinates AND window sizes.")
    print("  3. exact - Exact copy of UI layout files with no scaling.")
    print("  4. none - Do not sync UI layout files (keys/macros only).")
    mode_choice = input("Select UI sync mode [1]: ").strip()
    ui_sync_mode = "scale_position"
    if mode_choice == "2":
        ui_sync_mode = "scale_all"
    elif mode_choice == "3":
        ui_sync_mode = "exact"
    elif mode_choice == "4":
        ui_sync_mode = "none"

    # 5. Default resolution
    default_res = "2560x1440" if current_os != "darwin" else "1710x1112"
    res_input = input(f"Enter default screen resolution [{default_res}]: ").strip()
    if not res_input:
        res_input = default_res
    try:
        res_w, res_h = map(int, res_input.lower().split("x"))
        resolution = [res_w, res_h]
    except Exception:
        print(f"Invalid format, defaulting to: {default_res}")
        resolution = [2560, 1440] if current_os != "darwin" else [1710, 1112]

    # 6. Machine name
    default_machine = "macbook" if current_os == "darwin" else "desktop"
    machine_name = input(f"Enter name for this machine [{default_machine}]: ").strip()
    if not machine_name:
        machine_name = default_machine

    # 7. Game Launch Command (used by 'play')
    default_launch_cmd = "open -a osxEQL" if current_os == "darwin" else "faugus-launcher"
    print("\nGame Launch Command:")
    print("  Used by 'eql-sync play' to launch EverQuest after pre-game sync.")
    if current_os == "darwin":
        print("  macOS default: open -a osxEQL (matches Spotlight app)")
    else:
        print("  Linux default: faugus-launcher (or desktop shortcut command)")
    launch_cmd_input = input(f"Enter game launch command [{default_launch_cmd}]: ").strip()
    if not launch_cmd_input:
        launch_cmd_input = default_launch_cmd

    config = {
      "eq_dir": eq_dir,
      "sync_dir": sync_dir,
      "characters": characters,
      "ui_sync_mode": ui_sync_mode,
      "resolution": resolution,
      "machine_name": machine_name,
      "launch_command": launch_cmd_input
    }
    
    save_config(config)
    print("\nSetup complete! You can run 'eql-sync status', 'eql-sync auto', or 'eql-sync play'.")

def find_character_configs(search_dir, char_name):
    """
    Finds all character INI configs matching the name prefix in the given directory.
    - If `char_name.ini` exists, it is included.
    - If any `char_name_*.ini` exists, they are included.
    - Ignores files starting with 'UI_'.
    Returns a list of base filenames (without extension).
    """
    configs = []
    
    # 1. Check exact match
    exact_file = f"{char_name}.ini"
    if os.path.exists(os.path.join(search_dir, exact_file)):
        configs.append(char_name)
        
    # 2. Check pattern matches (char_name_*.ini)
    if os.path.exists(search_dir):
        try:
            for f in os.listdir(search_dir):
                f_lower = f.lower()
                # Exclude UI_ files
                if f_lower.startswith("ui_"):
                    continue
                if f_lower.startswith(f"{char_name.lower()}_") and f_lower.endswith(".ini"):
                    base = os.path.splitext(f)[0]
                    # Retain original case of the filename found in directory
                    if base not in configs:
                        configs.append(base)
        except Exception as e:
            print(f"Warning: Failed to list directory {search_dir}: {e}")
            
    return configs

def cmd_push(args=None):
    config = load_config()
    eq_dir = config["eq_dir"]
    sync_dir = config["sync_dir"]
    characters = config["characters"]
    config_res = config["resolution"]

    # Handle overrides from command line arguments
    ui_mode = config["ui_sync_mode"]
    force = False
    dry_run = False
    if args:
        force = getattr(args, "force", False)
        dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
        if getattr(args, "no_ui", False):
            ui_mode = "none"
        elif getattr(args, "ui_mode", None):
            ui_mode = args.ui_mode

    if not os.path.exists(eq_dir):
        print(f"Error: EverQuest directory does not exist: {eq_dir}")
        sys.exit(1)

    if not dry_run:
        os.makedirs(sync_dir, exist_ok=True)
    
    check_game_state_and_confirm(force=(force or dry_run))
    local_res = detect_resolution(eq_dir, config_res)

    if dry_run:
        print("\n=== DRY-RUN MODE (No changes will be written) ===")

    print(f"\nPushing settings from machine '{config['machine_name']}'...")
    if ui_mode == "none":
        print("Note: UI layout sync is disabled/skipped.")
    
    for char in characters:
        print(f"\n--- Syncing Character: {char} ---")
        char_configs = find_character_configs(eq_dir, char)
        if not char_configs:
            print(f"Warning: No configuration files found matching '{char}' in local EQ directory.")
            continue
            
        for config_name in char_configs:
            print(f"  Syncing config profile: {config_name}")
            # 1. Character options & macros (e.g. Faugus_legends.ini)
            char_ini = f"{config_name}.ini"
            local_char_path = os.path.join(eq_dir, char_ini)
            sync_char_path = os.path.join(sync_dir, char_ini)
            
            if os.path.exists(local_char_path):
                # Check modification time to prevent overwriting newer sync data
                # unless forced.
                if os.path.exists(sync_char_path):
                    local_mtime = os.path.getmtime(local_char_path)
                    sync_mtime = os.path.getmtime(sync_char_path)
                    if sync_mtime > local_mtime:
                        print(f"    Warning: Synced file {char_ini} is newer than local file!")
                        if force or dry_run:
                            print("    Forcing overwrite of synced file (--force).")
                        else:
                            confirm = input("    Overwrite synced file anyway? (y/N): ")
                            if confirm.lower() != 'y':
                                print("    Skipping character settings.")
                                continue
                
                if dry_run:
                    print(f"    [DRY-RUN] Would copy {char_ini} to sync folder.")
                else:
                    shutil.copy2(local_char_path, sync_char_path)
                    print(f"    Copied {char_ini} to sync folder.")
            else:
                print(f"    Warning: Local file not found: {local_char_path}")

            # 2. UI options & window layout (e.g. UI_Faugus_legends.ini)
            if ui_mode != "none":
                ui_ini = f"UI_{config_name}.ini"
                local_ui_path = os.path.join(eq_dir, ui_ini)
                sync_ui_path = os.path.join(sync_dir, ui_ini)
                sync_meta_path = os.path.join(sync_dir, f"UI_{config_name}.meta.json")

                if os.path.exists(local_ui_path):
                    if dry_run:
                        print(f"    [DRY-RUN] Would copy {ui_ini} to sync folder.")
                        print(f"    [DRY-RUN] Would write layout metadata: {sync_meta_path}")
                    else:
                        # Copy the file to sync folder
                        shutil.copy2(local_ui_path, sync_ui_path)
                        print(f"    Copied {ui_ini} to sync folder.")
                        
                        # Write metadata detailing resolution and timestamp
                        meta = {
                            "source_machine": config["machine_name"],
                            "resolution": local_res,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        with open(sync_meta_path, "w", encoding="utf-8") as mf:
                            json.dump(meta, mf, indent=2)
                        print(f"    Saved layout metadata: {sync_meta_path}")
                else:
                    print(f"    Warning: Local UI layout file not found: {local_ui_path}")
            else:
                print("    UI layout sync disabled/skipped.")

    print("\nPush completed successfully!")

def cmd_pull(args=None):
    config = load_config()
    eq_dir = config["eq_dir"]
    sync_dir = config["sync_dir"]
    characters = config["characters"]
    config_res = config["resolution"]

    # Handle overrides from command line arguments
    ui_mode = config["ui_sync_mode"]
    force = False
    dry_run = False
    if args:
        force = getattr(args, "force", False)
        dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
        if getattr(args, "no_ui", False):
            ui_mode = "none"
        elif getattr(args, "ui_mode", None):
            ui_mode = args.ui_mode

    if not os.path.exists(sync_dir):
        print(f"Error: Shared sync directory does not exist: {sync_dir}")
        sys.exit(1)

    if not os.path.exists(eq_dir):
        print(f"Error: Local EverQuest directory does not exist: {eq_dir}")
        sys.exit(1)

    check_game_state_and_confirm(force=(force or dry_run))
    local_res = detect_resolution(eq_dir, config_res)

    if dry_run:
        print("\n=== DRY-RUN MODE (No changes will be written) ===")

    print(f"\nPulling settings to machine '{config['machine_name']}'...")

    for char in characters:
        print(f"\n--- Syncing Character: {char} ---")
        char_configs = find_character_configs(sync_dir, char)
        if not char_configs:
            print(f"Warning: No configuration files found matching '{char}' in sync directory.")
            continue
            
        for config_name in char_configs:
            print(f"  Syncing config profile: {config_name}")
            # 1. Character options & macros (e.g. Faugus_legends.ini)
            char_ini = f"{config_name}.ini"
            local_char_path = os.path.join(eq_dir, char_ini)
            sync_char_path = os.path.join(sync_dir, char_ini)

            if os.path.exists(sync_char_path):
                if os.path.exists(local_char_path):
                    local_mtime = os.path.getmtime(local_char_path)
                    sync_mtime = os.path.getmtime(sync_char_path)
                    if local_mtime > sync_mtime:
                        print(f"    Warning: Local file {char_ini} is newer than synced file!")
                        if force or dry_run:
                            print("    Forcing overwrite of local changes (--force).")
                        else:
                            confirm = input("    Overwrite local changes? (y/N): ")
                            if confirm.lower() != 'y':
                                print("    Skipping character settings pull.")
                                continue
                    
                    # Backup before overwrite
                    make_backup(eq_dir, char_ini, dry_run=dry_run)
                
                if dry_run:
                    print(f"    [DRY-RUN] Would update local {char_ini} from sync folder.")
                else:
                    shutil.copy2(sync_char_path, local_char_path)
                    print(f"    Updated local {char_ini} from sync folder.")
            else:
                print(f"    Warning: Synced file not found in shared folder: {sync_char_path}")

            # 2. UI options & window layout (e.g. UI_Faugus_legends.ini)
            if ui_mode != "none":
                ui_ini = f"UI_{config_name}.ini"
                local_ui_path = os.path.join(eq_dir, ui_ini)
                sync_ui_path = os.path.join(sync_dir, ui_ini)
                sync_meta_path = os.path.join(sync_dir, f"UI_{config_name}.meta.json")

                if os.path.exists(sync_ui_path):
                    # Check metadata to scale coordinates
                    src_res = local_res # Default assumption if meta missing
                    if os.path.exists(sync_meta_path):
                        try:
                            with open(sync_meta_path, "r", encoding="utf-8") as mf:
                                meta_data = json.load(mf)
                                src_res = meta_data.get("resolution", local_res)
                        except Exception as e:
                            print(f"    Warning: Failed to parse metadata file: {e}")

                    if os.path.exists(local_ui_path):
                        # Check modified times
                        local_mtime = os.path.getmtime(local_ui_path)
                        sync_mtime = os.path.getmtime(sync_ui_path)
                        if local_mtime > sync_mtime:
                            print(f"    Warning: Local UI file {ui_ini} is newer than synced file!")
                            if force or dry_run:
                                print("    Forcing overwrite of local UI changes (--force).")
                            else:
                                confirm = input("    Overwrite local UI changes? (y/N): ")
                                if confirm.lower() != 'y':
                                    print("    Skipping UI pull.")
                                    continue
                        
                        make_backup(eq_dir, ui_ini, dry_run=dry_run)

                    # Process scaling if modes dictate
                    if ui_mode in ("scale_position", "scale_all") and src_res != local_res:
                        if dry_run:
                            print(f"    [DRY-RUN] Would translate coordinates from {src_res[0]}x{src_res[1]} -> {local_res[0]}x{local_res[1]} and save to local {ui_ini}")
                        else:
                            print(f"    Translating coordinates from {src_res[0]}x{src_res[1]} -> {local_res[0]}x{local_res[1]} (Mode: {ui_mode})...")
                            ui_config = load_ini(sync_ui_path)
                            scaled_config = scale_ui_coordinates(ui_config, src_res, local_res, ui_mode)
                            save_ini(scaled_config, local_ui_path)
                            print(f"    Updated and scaled local {ui_ini}")
                    else:
                        if dry_run:
                            print(f"    [DRY-RUN] Would update local {ui_ini} (Exact copy)")
                        else:
                            # 'exact' copy or resolutions match
                            shutil.copy2(sync_ui_path, local_ui_path)
                            print(f"    Updated local {ui_ini} (Exact copy)")
                else:
                    print(f"    Warning: Synced UI file not found in shared folder: {sync_ui_path}")
            else:
                print("    UI layout sync disabled/skipped.")

    print("\nPull completed successfully!")

def cmd_status(args=None):
    config = load_config()
    eq_dir = config["eq_dir"]
    sync_dir = config["sync_dir"]
    characters = config.get("characters", [])
    ui_mode = config.get("ui_sync_mode", "none")
    config_res = config.get("resolution", [1920, 1080])

    default_cmd = "open -a osxEQL" if sys.platform == "darwin" else "faugus-launcher"
    launch_cmd = config.get("launch_command", default_cmd)

    print("=== EverQuest Legends Sync Status ===")
    print(f"Machine Name:  {config.get('machine_name')}")
    print(f"Local EQ Dir:  {eq_dir}")
    print(f"Sync Dir:      {sync_dir}")
    print(f"UI Sync Mode:  {ui_mode}")
    print(f"Launch Cmd:    {launch_cmd}")
    print(f"Config Res:    {config_res}")
    
    detected_res = detect_resolution(eq_dir, config_res)
    print(f"Detected Res:  {detected_res[0]}x{detected_res[1]}")

    if not os.path.exists(eq_dir):
        print(f"\nError: Local EverQuest directory does not exist: {eq_dir}")
        return
    if not os.path.exists(sync_dir):
        print(f"\nWarning: Shared sync directory does not exist: {sync_dir}")

    needs_push = 0
    needs_pull = 0
    in_sync_count = 0

    print("\nCharacters Syncing:")
    for char in characters:
        print(f"\n--- Character: {char} ---")
        local_configs = find_character_configs(eq_dir, char)
        sync_configs = find_character_configs(sync_dir, char) if os.path.exists(sync_dir) else []
        all_configs = sorted(list(set(local_configs + sync_configs)))

        if not all_configs:
            print("  No configuration files found in local or sync directory.")
            continue

        for config_name in all_configs:
            print(f"  Profile: {config_name}")

            def compare_file(filename, desc):
                nonlocal needs_push, needs_pull, in_sync_count
                local_path = os.path.join(eq_dir, filename)
                sync_path = os.path.join(sync_dir, filename)

                local_exists = os.path.exists(local_path)
                sync_exists = os.path.exists(sync_path)

                local_str = "NOT FOUND"
                sync_str = "NOT FOUND"
                status_tag = ""

                if local_exists:
                    local_mtime = os.path.getmtime(local_path)
                    local_str = datetime.datetime.fromtimestamp(local_mtime).strftime("%Y-%m-%d %H:%M:%S")
                if sync_exists:
                    sync_mtime = os.path.getmtime(sync_path)
                    sync_str = datetime.datetime.fromtimestamp(sync_mtime).strftime("%Y-%m-%d %H:%M:%S")

                if local_exists and sync_exists:
                    diff = local_mtime - sync_mtime
                    if abs(diff) <= 1.0:
                        status_tag = "[IN SYNC]"
                        in_sync_count += 1
                    elif diff > 1.0:
                        status_tag = "[LOCAL NEWER -> PUSH RECOMMENDED]"
                        needs_push += 1
                    else:
                        status_tag = "[SYNC NEWER -> PULL RECOMMENDED]"
                        needs_pull += 1
                elif local_exists and not sync_exists:
                    status_tag = "[LOCAL ONLY -> PUSH TO SHARE]"
                    needs_push += 1
                elif not local_exists and sync_exists:
                    status_tag = "[SYNC ONLY -> PULL TO LOCAL]"
                    needs_pull += 1
                else:
                    status_tag = "[MISSING]"

                print(f"    {desc} ({filename}):")
                print(f"      Local:  {local_str}")
                print(f"      Sync:   {sync_str}")
                print(f"      Status: {status_tag}")

            # 1. Compare character options/macros/spell slots
            char_ini = f"{config_name}.ini"
            compare_file(char_ini, "Settings/Macros")

            # 2. Compare UI layout (if applicable)
            if ui_mode != "none":
                ui_ini = f"UI_{config_name}.ini"
                compare_file(ui_ini, "UI Layout")

    # Overall recommendation
    print("\n=== Summary Recommendation ===")
    if needs_push > 0 and needs_pull == 0:
        print(f"-> Local files are newer ({needs_push} file(s) to push).")
        print("   Recommended command: ./eql_sync.py push")
    elif needs_pull > 0 and needs_push == 0:
        print(f"-> Synced files are newer ({needs_pull} file(s) to pull).")
        print("   Recommended command: ./eql_sync.py pull")
    elif needs_push > 0 and needs_pull > 0:
        print(f"-> Mixed states detected: {needs_push} file(s) to push, {needs_pull} file(s) to pull.")
        print("   Recommended command: ./eql_sync.py auto  (syncs each file based on newest timestamp)")
    elif in_sync_count > 0 and needs_push == 0 and needs_pull == 0:
        print("-> All character files are in sync! No action needed.")
    else:
        print("-> No character files found to compare.")

def cmd_auto(args=None):
    config = load_config()
    eq_dir = config["eq_dir"]
    sync_dir = config["sync_dir"]
    characters = config.get("characters", [])
    config_res = config.get("resolution", [1920, 1080])

    ui_mode = config.get("ui_sync_mode", "scale_position")
    force = False
    dry_run = False
    if args:
        force = getattr(args, "force", False)
        dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
        if getattr(args, "no_ui", False):
            ui_mode = "none"
        elif getattr(args, "ui_mode", None):
            ui_mode = args.ui_mode

    if not os.path.exists(eq_dir):
        print(f"Error: Local EverQuest directory does not exist: {eq_dir}")
        sys.exit(1)

    if not dry_run:
        os.makedirs(sync_dir, exist_ok=True)

    check_game_state_and_confirm(force=(force or dry_run))
    local_res = detect_resolution(eq_dir, config_res)

    if dry_run:
        print("\n=== DRY-RUN MODE (No changes will be written) ===")

    print(f"\nAuto-syncing machine '{config.get('machine_name')}' with shared folder...")
    if ui_mode == "none":
        print("Note: UI layout sync is disabled/skipped.")

    max_backups = config.get("backup_retention", 10)
    max_days = config.get("backup_retention_days", 30)

    pushed_count = 0
    pulled_count = 0
    in_sync_count = 0

    for char in characters:
        print(f"\n--- Checking Character: {char} ---")
        local_configs = find_character_configs(eq_dir, char)
        sync_configs = find_character_configs(sync_dir, char) if os.path.exists(sync_dir) else []
        all_configs = sorted(list(set(local_configs + sync_configs)))

        if not all_configs:
            print(f"Warning: No configuration files found matching '{char}'.")
            continue

        for config_name in all_configs:
            print(f"  Profile: {config_name}")

            # 1. Character options & macros ({config_name}.ini)
            char_ini = f"{config_name}.ini"
            local_char_path = os.path.join(eq_dir, char_ini)
            sync_char_path = os.path.join(sync_dir, char_ini)

            local_exists = os.path.exists(local_char_path)
            sync_exists = os.path.exists(sync_char_path)

            if local_exists and sync_exists:
                local_mtime = os.path.getmtime(local_char_path)
                sync_mtime = os.path.getmtime(sync_char_path)
                diff = local_mtime - sync_mtime

                if abs(diff) <= 1.0:
                    print(f"    [IN SYNC] {char_ini} is already up to date.")
                    in_sync_count += 1
                elif diff > 1.0:
                    # Local is newer -> Push to sync folder
                    print(f"    [AUTO-PUSH] Local {char_ini} is newer -> Updating sync folder...")
                    make_backup(sync_dir, char_ini, dry_run=dry_run, max_backups=max_backups, max_days=max_days)
                    if dry_run:
                        print(f"    [DRY-RUN] Would copy local {char_ini} to sync folder.")
                    else:
                        shutil.copy2(local_char_path, sync_char_path)
                        print(f"    Copied {char_ini} to sync folder.")
                    pushed_count += 1
                else:
                    # Sync is newer -> Pull to local EQ folder
                    print(f"    [AUTO-PULL] Synced {char_ini} is newer -> Updating local EQ folder...")
                    make_backup(eq_dir, char_ini, dry_run=dry_run, max_backups=max_backups, max_days=max_days)
                    if dry_run:
                        print(f"    [DRY-RUN] Would update local {char_ini} from sync folder.")
                    else:
                        shutil.copy2(sync_char_path, local_char_path)
                        print(f"    Updated local {char_ini} from sync folder.")
                    pulled_count += 1

            elif local_exists and not sync_exists:
                print(f"    [AUTO-PUSH] {char_ini} only exists locally -> Pushing to sync folder...")
                if dry_run:
                    print(f"    [DRY-RUN] Would copy {char_ini} to sync folder.")
                else:
                    shutil.copy2(local_char_path, sync_char_path)
                    print(f"    Copied {char_ini} to sync folder.")
                pushed_count += 1

            elif not local_exists and sync_exists:
                print(f"    [AUTO-PULL] {char_ini} only exists in sync folder -> Pulling to local folder...")
                if dry_run:
                    print(f"    [DRY-RUN] Would update local {char_ini} from sync folder.")
                else:
                    shutil.copy2(sync_char_path, local_char_path)
                    print(f"    Updated local {char_ini} from sync folder.")
                pulled_count += 1

            # 2. UI options & layout (UI_{config_name}.ini)
            if ui_mode != "none":
                ui_ini = f"UI_{config_name}.ini"
                local_ui_path = os.path.join(eq_dir, ui_ini)
                sync_ui_path = os.path.join(sync_dir, ui_ini)
                sync_meta_path = os.path.join(sync_dir, f"UI_{config_name}.meta.json")

                local_ui_exists = os.path.exists(local_ui_path)
                sync_ui_exists = os.path.exists(sync_ui_path)

                if local_ui_exists and sync_ui_exists:
                    local_ui_mtime = os.path.getmtime(local_ui_path)
                    sync_ui_mtime = os.path.getmtime(sync_ui_path)
                    diff_ui = local_ui_mtime - sync_ui_mtime

                    if abs(diff_ui) <= 1.0:
                        print(f"    [IN SYNC] {ui_ini} is already up to date.")
                    elif diff_ui > 1.0:
                        # Local UI is newer -> Push
                        print(f"    [AUTO-PUSH] Local {ui_ini} is newer -> Updating sync folder...")
                        make_backup(sync_dir, ui_ini, dry_run=dry_run, max_backups=max_backups, max_days=max_days)
                        if dry_run:
                            print(f"    [DRY-RUN] Would copy {ui_ini} to sync folder.")
                            print(f"    [DRY-RUN] Would write layout metadata: {sync_meta_path}")
                        else:
                            shutil.copy2(local_ui_path, sync_ui_path)
                            meta = {
                                "source_machine": config.get("machine_name"),
                                "resolution": local_res,
                                "timestamp": datetime.datetime.now().isoformat()
                            }
                            with open(sync_meta_path, "w", encoding="utf-8") as mf:
                                json.dump(meta, mf, indent=2)
                            print(f"    Saved layout and metadata to sync folder.")
                    else:
                        # Sync UI is newer -> Pull
                        print(f"    [AUTO-PULL] Synced {ui_ini} is newer -> Updating local EQ folder...")
                        src_res = local_res
                        if os.path.exists(sync_meta_path):
                            try:
                                with open(sync_meta_path, "r", encoding="utf-8") as mf:
                                    meta_data = json.load(mf)
                                    src_res = meta_data.get("resolution", local_res)
                            except Exception as e:
                                print(f"    Warning: Failed to parse metadata file: {e}")

                        make_backup(eq_dir, ui_ini, dry_run=dry_run, max_backups=max_backups, max_days=max_days)
                        if ui_mode in ("scale_position", "scale_all") and src_res != local_res:
                            if dry_run:
                                print(f"    [DRY-RUN] Would translate coordinates from {src_res[0]}x{src_res[1]} -> {local_res[0]}x{local_res[1]} and save to {ui_ini}")
                            else:
                                print(f"    Translating coordinates from {src_res[0]}x{src_res[1]} -> {local_res[0]}x{local_res[1]} (Mode: {ui_mode})...")
                                ui_config = load_ini(sync_ui_path)
                                scaled_config = scale_ui_coordinates(ui_config, src_res, local_res, ui_mode)
                                save_ini(scaled_config, local_ui_path)
                                print(f"    Updated and scaled local {ui_ini}")
                        else:
                            if dry_run:
                                print(f"    [DRY-RUN] Would update local {ui_ini} (Exact copy)")
                            else:
                                shutil.copy2(sync_ui_path, local_ui_path)
                                print(f"    Updated local {ui_ini} (Exact copy)")

                elif local_ui_exists and not sync_ui_exists:
                    print(f"    [AUTO-PUSH] {ui_ini} only exists locally -> Pushing to sync folder...")
                    if dry_run:
                        print(f"    [DRY-RUN] Would copy {ui_ini} to sync folder.")
                    else:
                        shutil.copy2(local_ui_path, sync_ui_path)
                        meta = {
                            "source_machine": config.get("machine_name"),
                            "resolution": local_res,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        with open(sync_meta_path, "w", encoding="utf-8") as mf:
                            json.dump(meta, mf, indent=2)
                        print(f"    Saved {ui_ini} to sync folder.")

                elif not local_ui_exists and sync_ui_exists:
                    print(f"    [AUTO-PULL] {ui_ini} only exists in sync folder -> Pulling to local folder...")
                    src_res = local_res
                    if os.path.exists(sync_meta_path):
                        try:
                            with open(sync_meta_path, "r", encoding="utf-8") as mf:
                                meta_data = json.load(mf)
                                src_res = meta_data.get("resolution", local_res)
                        except Exception:
                            pass
                    if ui_mode in ("scale_position", "scale_all") and src_res != local_res:
                        if dry_run:
                            print(f"    [DRY-RUN] Would scale and update local {ui_ini}")
                        else:
                            ui_config = load_ini(sync_ui_path)
                            scaled_config = scale_ui_coordinates(ui_config, src_res, local_res, ui_mode)
                            save_ini(scaled_config, local_ui_path)
                            print(f"    Updated and scaled local {ui_ini}")
                    else:
                        if dry_run:
                            print(f"    [DRY-RUN] Would copy {ui_ini} to local folder.")
                        else:
                            shutil.copy2(sync_ui_path, local_ui_path)
                            print(f"    Updated local {ui_ini} (Exact copy)")

    print(f"\nAuto-sync complete! (Pushed: {pushed_count}, Pulled: {pulled_count}, In Sync: {in_sync_count})")

def cmd_play(args=None):
    config = load_config()
    current_os = sys.platform
    default_cmd = "open -a osxEQL" if current_os == "darwin" else "faugus-launcher"

    launch_cmd = getattr(args, "launch_command", None) or config.get("launch_command") or default_cmd
    dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
    force = getattr(args, "force", False)
    no_pre_sync = getattr(args, "no_pre_sync", False)
    no_post_sync = getattr(args, "no_post_sync", False)
    wait_timeout = getattr(args, "wait_timeout", 120)

    print("=== EverQuest Legends Session Launcher ===")
    if dry_run:
        print("=== DRY-RUN MODE (No changes will be written, game will not be launched) ===")

    # Guard: check if game is already running
    if is_game_running() and not dry_run:
        print("\n" + "!" * 60)
        print("WARNING: EverQuest Legends process (eqgame.exe) is already running!")
        print("Cannot start a new play session while the game is active.")
        print("!" * 60 + "\n")
        if not force:
            print("Aborting play session. To force anyway, use --force.")
            return 1
        print("Continuing anyway (--force)...")

    # Step 1: Pre-game sync
    if not no_pre_sync:
        print("\n--- Step 1: Pre-Game Synchronization ---")
        cmd_auto(args)
    else:
        print("\n--- Step 1: Pre-Game Synchronization (Skipped: --no-pre-sync) ---")

    # Step 2: Launch game
    print(f"\n--- Step 2: Launching EverQuest ---")
    print(f"Launch command: {launch_cmd}")
    if dry_run:
        print(f"    [DRY-RUN] Would execute command: {launch_cmd}")
        print(f"    [DRY-RUN] Would poll for eqgame.exe (timeout: {wait_timeout}s).")
        print(f"    [DRY-RUN] Would monitor session until game exit.")
        print(f"    [DRY-RUN] Would wait 3s for disk flush.")
        print(f"    [DRY-RUN] Would execute post-game auto-sync.")
        return 0

    try:
        subprocess.Popen(launch_cmd, shell=True)
        print("Launcher started. Waiting for game process (eqgame.exe)...")
    except Exception as e:
        print(f"Error executing launch command '{launch_cmd}': {e}")
        return 1

    # Step 3: Wait for eqgame.exe to start
    start_wait = time.time()
    game_started = False
    print(f"Waiting for EverQuest (eqgame.exe) to start (timeout: {wait_timeout}s)...")
    print("Press Ctrl+C to cancel.")
    try:
        while time.time() - start_wait < wait_timeout:
            if is_game_running():
                game_started = True
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCancelled waiting for game startup.")
        return 0

    if not game_started:
        print(f"\nWarning: EverQuest process (eqgame.exe) was not detected within {wait_timeout} seconds.")
        print("Game may still be starting slowly, or was cancelled in the launcher.")
        print("Skipping post-game auto-sync to avoid syncing unintended changes.")
        return 1

    # Step 4: Monitor game session
    print(f"\n--- Step 3: EverQuest is Active ---")
    print("Game process detected! Enjoy your session.")
    print("Monitoring for exit... (Keep this terminal window open)")
    print("(Press Ctrl+C to stop monitoring without syncing)")

    try:
        while is_game_running():
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\nSession monitoring interrupted by user (Ctrl+C).")
        print("Skipping post-game auto-sync.")
        print("You can manually sync later using: eql-sync auto")
        return 0

    # Step 5: Grace period for file flush
    print("\nEverQuest (eqgame.exe) has exited.")
    print("Waiting 3 seconds for file buffers to flush...")
    time.sleep(3)

    # Step 6: Post-game sync
    if not no_post_sync:
        print("\n--- Step 4: Post-Game Synchronization ---")
        cmd_auto(args)
        print("\n✨ Post-game sync complete! Your session settings are backed up and synced.")
    else:
        print("\n--- Step 4: Post-Game Synchronization (Skipped: --no-post-sync) ---")

    return 0

def cmd_prune(args=None):
    config = load_config()
    eq_dir = config["eq_dir"]
    sync_dir = config["sync_dir"]
    dry_run = False
    max_backups = config.get("backup_retention", 10)
    max_days = config.get("backup_retention_days", 30)

    if args:
        dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
        if getattr(args, "max_backups", None) is not None:
            max_backups = args.max_backups
        if getattr(args, "max_days", None) is not None:
            max_days = args.max_days

    print("=== Pruning Old Backups ===")
    print(f"Retention limit: {max_backups} backups per file (max age: {max_days} days)")
    if dry_run:
        print("=== DRY-RUN MODE (No files will be deleted) ===")

    print(f"\nLocal EQ backups ({os.path.join(eq_dir, 'sync_backups')}):")
    prune_backups(os.path.join(eq_dir, "sync_backups"), max_backups=max_backups, max_days=max_days, dry_run=dry_run)

    print(f"\nShared sync backups ({os.path.join(sync_dir, 'sync_backups')}):")
    prune_backups(os.path.join(sync_dir, "sync_backups"), max_backups=max_backups, max_days=max_days, dry_run=dry_run)

    print("\nPrune complete!")

def get_shell_rc_path():
    """Returns the most appropriate shell configuration file for the current user and shell."""
    shell = os.environ.get("SHELL", "").lower()
    home = os.path.expanduser("~")

    if "zsh" in shell:
        return os.path.join(home, ".zshrc")
    elif "bash" in shell:
        if sys.platform == "darwin":
            profile = os.path.join(home, ".bash_profile")
            if os.path.exists(profile):
                return profile
        return os.path.join(home, ".bashrc")
    elif "fish" in shell:
        return os.path.join(home, ".config", "fish", "config.fish")

    # Fallback based on OS
    if sys.platform == "darwin":
        zshrc = os.path.join(home, ".zshrc")
        if os.path.exists(zshrc) or "zsh" in shell:
            return zshrc
        return os.path.join(home, ".bash_profile")
    return os.path.join(home, ".bashrc")

def cmd_install(args=None):
    dry_run = False
    add_path_flag = False
    if args:
        dry_run = getattr(args, "global_dry_run", False) or getattr(args, "sub_dry_run", False)
        add_path_flag = getattr(args, "add_path", False)

    script_path = os.path.abspath(__file__)
    bin_dir = os.path.expanduser("~/.local/bin")
    link_name = "eql-sync"
    link_path = os.path.join(bin_dir, link_name)
    alt_link_name = "eql_sync"
    alt_link_path = os.path.join(bin_dir, alt_link_name)

    print("=== Installing EverQuest Legends Sync Tool ===")
    if dry_run:
        print("=== DRY-RUN MODE (No changes will be made) ===")

    # 1. Make script executable (chmod +x)
    if dry_run:
        print(f"    [DRY-RUN] Would make executable (chmod +x): {script_path}")
    else:
        try:
            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | 0o111)
            print(f"Made script executable: {script_path}")
        except Exception as e:
            print(f"Warning: Could not set executable permission on {script_path}: {e}")

    # 2. Ensure ~/.local/bin exists
    if dry_run:
        print(f"    [DRY-RUN] Would ensure directory exists: {bin_dir}")
    else:
        os.makedirs(bin_dir, exist_ok=True)

    # 3. Create symlinks (both eql-sync and eql_sync)
    for target_link, name in [(link_path, link_name), (alt_link_path, alt_link_name)]:
        if os.path.islink(target_link) or os.path.exists(target_link):
            if os.path.islink(target_link) and os.path.realpath(target_link) == script_path:
                print(f"Symlink already up to date: {target_link} -> {script_path}")
                continue
            if dry_run:
                print(f"    [DRY-RUN] Would replace existing file/link at: {target_link}")
            else:
                try:
                    os.unlink(target_link)
                except Exception as e:
                    print(f"Warning: Could not remove existing {target_link}: {e}")

        if dry_run:
            print(f"    [DRY-RUN] Would create symlink: {target_link} -> {script_path}")
        else:
            try:
                os.symlink(script_path, target_link)
                print(f"Created symlink: {target_link} -> {script_path}")
            except Exception as e:
                print(f"Error creating symlink {target_link}: {e}")

    # 4. Migrate local config if ~/.config/eql-sync/config.json doesn't exist yet
    legacy_config = os.path.join(os.path.dirname(script_path), CONFIG_FILENAME)
    if os.path.exists(legacy_config) and not os.path.exists(DEFAULT_CONFIG_PATH):
        if dry_run:
            print(f"    [DRY-RUN] Would copy existing config from {legacy_config} to {DEFAULT_CONFIG_PATH}")
        else:
            try:
                os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
                shutil.copy2(legacy_config, DEFAULT_CONFIG_PATH)
                print(f"Migrated existing config to: {DEFAULT_CONFIG_PATH}")
            except Exception as e:
                print(f"Warning: Could not copy config to {DEFAULT_CONFIG_PATH}: {e}")

    # 5. Check PATH and optionally configure shell rc
    path_dirs = [os.path.abspath(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if os.path.abspath(bin_dir) not in path_dirs:
        rc_path = get_shell_rc_path()
        rc_display = rc_path.replace(os.path.expanduser("~"), "~")
        is_fish = "fish" in os.environ.get("SHELL", "").lower()
        export_cmd = 'fish_add_path "$HOME/.local/bin"' if is_fish else 'export PATH="$HOME/.local/bin:$PATH"'

        print(f"\nNotice: '{bin_dir}' is not currently in your PATH.")

        already_in_rc = False
        if os.path.exists(rc_path):
            try:
                with open(rc_path, "r", encoding="utf-8", errors="ignore") as f:
                    if ".local/bin" in f.read():
                        already_in_rc = True
            except Exception:
                pass

        if already_in_rc:
            print(f"'{bin_dir}' is already referenced in {rc_display}, but is not active in this session.")
            print(f"To activate it now, run:\n  source {rc_display}")
        else:
            add_path = add_path_flag
            if not add_path and sys.stdin.isatty() and not dry_run:
                try:
                    choice = input(f"Would you like to automatically add it to {rc_display}? (y/N): ").strip().lower()
                    if choice == 'y':
                        add_path = True
                except (EOFError, KeyboardInterrupt):
                    pass

            if add_path:
                if dry_run:
                    print(f"    [DRY-RUN] Would append '{export_cmd}' to {rc_display}")
                else:
                    try:
                        os.makedirs(os.path.dirname(rc_path), exist_ok=True)
                        with open(rc_path, "a", encoding="utf-8") as f:
                            f.write(f"\n# Added by eql-sync\n{export_cmd}\n")
                        print(f"Successfully added to {rc_display}!")
                        print(f"To activate in your current session, run:\n  source {rc_display}")
                    except Exception as e:
                        print(f"Warning: Could not write to {rc_display}: {e}")
                        print(f"To add it manually, append this line to {rc_display}:\n  {export_cmd}")
            else:
                print(f"To add it manually, append the following line to {rc_display}:")
                print(f"  {export_cmd}")
                print(f"Then reload your shell with:\n  source {rc_display}")
    else:
        print(f"\nSuccess! '{bin_dir}' is already in your PATH.")
        print(f"You can now run '{link_name}' from anywhere.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="EverQuest Legends Sync Tool")
    parser.add_argument("-d", "--dry-run", dest="global_dry_run", action="store_true", help="Simulate sync operations without writing any files")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")
    
    # init
    subparsers.add_parser("init", help="Configure local settings")
    
    # install
    install_parser = subparsers.add_parser("install", help="Install eql-sync as a command in ~/.local/bin")
    install_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate installation without creating symlinks")
    install_parser.add_argument("--add-path", action="store_true", help="Automatically add ~/.local/bin to your shell rc file without prompting")

    # push
    push_parser = subparsers.add_parser("push", help="Push local settings to sync folder")
    push_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    push_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    push_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and confirmation prompts")
    push_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate pushing settings without writing any files")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull settings from sync folder")
    pull_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    pull_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    pull_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and confirmation prompts")
    pull_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate pulling settings without writing any files")

    # auto / sync
    auto_parser = subparsers.add_parser("auto", aliases=["sync"], help="Intelligently push or pull each file based on newest timestamps")
    auto_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    auto_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    auto_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and confirmation prompts")
    auto_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate auto-sync without writing any files")

    # status / check
    subparsers.add_parser("status", aliases=["check"], help="Show current sync status and compare file timestamps")

    # prune
    prune_parser = subparsers.add_parser("prune", help="Prune old backup files in local and sync folders")
    prune_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate pruning without deleting files")
    prune_parser.add_argument("--max-backups", type=int, default=None, help="Maximum number of backups to keep per file (default: 10)")
    prune_parser.add_argument("--max-days", type=int, default=None, help="Maximum age in days for backups (default: 30)")

    # play
    play_parser = subparsers.add_parser("play", help="Auto-sync, launch EverQuest, monitor session, and auto-sync on exit")
    play_parser.add_argument("-c", "--command", dest="launch_command", help="Override game launch command (e.g. 'open -a osxEQL' or 'faugus-launcher')")
    play_parser.add_argument("--wait-timeout", type=int, default=120, help="Maximum seconds to wait for eqgame.exe to start (default: 120)")
    play_parser.add_argument("--no-pre-sync", action="store_true", help="Skip pre-game auto-sync")
    play_parser.add_argument("--no-post-sync", action="store_true", help="Skip post-game auto-sync")
    play_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    play_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    play_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and start play session anyway")
    play_parser.add_argument("-d", "--dry-run", dest="sub_dry_run", action="store_true", help="Simulate play session without launching game or writing files")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    cmd = args.command.lower()
    if cmd == "init":
        cmd_init()
    elif cmd == "install":
        cmd_install(args)
    elif cmd == "push":
        cmd_push(args)
    elif cmd == "pull":
        cmd_pull(args)
    elif cmd in ("auto", "sync"):
        cmd_auto(args)
    elif cmd in ("status", "check"):
        cmd_status(args)
    elif cmd == "prune":
        cmd_prune(args)
    elif cmd == "play":
        cmd_play(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
