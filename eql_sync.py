#!/usr/bin/env python3
import os
import sys
import json
import shutil
import datetime
import subprocess
import configparser

CONFIG_FILENAME = "config.json"

def get_config_path():
    # Look for config.json in the current working directory first,
    # then fallback to the script's directory.
    cwd_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if os.path.exists(cwd_path):
        return cwd_path
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
    return script_path

def load_config():
    path = get_config_path()
    if not os.path.exists(path):
        print(f"Error: Configuration file not found. Please run 'init' first.")
        print(f"Expected path: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Configuration saved to: {path}")

def is_game_running():
    """Detects if eqgame.exe is running on macOS/Linux using Wine/Proton."""
    try:
        # Run ps aux to list all running processes
        res = subprocess.run(["ps", "aux"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = res.stdout.splitlines()
        for line in lines:
            if "eqgame.exe" in line.lower() and "grep" not in line.lower():
                return True
    except Exception as e:
        print(f"Warning: Failed to scan process list: {e}")
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

def make_backup(eq_dir, filename, dry_run=False):
    """Creates a local timestamped backup of a file in the sync_backups folder."""
    src = os.path.join(eq_dir, filename)
    if not os.path.exists(src):
        return
    
    backup_dir = os.path.join(eq_dir, "sync_backups")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"{filename}.{timestamp}.bak")
    if dry_run:
        print(f"    [DRY-RUN] Would create backup of {filename} at {dst}")
        return
        
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Backup created: {dst}")

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
    default_eq_dir = ""
    if current_os == "darwin": # macOS
        default_eq_dir = "/Users/ben/Library/Application Support/osxEQL/prefix/drive_c/users/Public/Daybreak Game Company/Installed Games/EverQuest Legends"
    else: # linux or others
        default_eq_dir = "/mnt/games/Faugus/everquest-legends/drive_c/users/Public/Daybreak Game Company/Installed Games/EverQuest Legends"

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

    config = {
      "eq_dir": eq_dir,
      "sync_dir": sync_dir,
      "characters": characters,
      "ui_sync_mode": ui_sync_mode,
      "resolution": resolution,
      "machine_name": machine_name
    }
    
    save_config(config)
    print("\nSetup complete! You can run 'python eql_sync.py push' to sync local changes up to the shared folder.")

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
        dry_run = getattr(args, "dry_run", False)
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
        dry_run = getattr(args, "dry_run", False)
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

def cmd_status():
    config = load_config()
    print("=== EverQuest Legends Sync Status ===")
    print(f"Machine Name:  {config.get('machine_name')}")
    print(f"Local EQ Dir:  {config.get('eq_dir')}")
    print(f"Sync Dir:      {config.get('sync_dir')}")
    print(f"UI Sync Mode:  {config.get('ui_sync_mode')}")
    print(f"Config Res:    {config.get('resolution')}")
    
    eq_dir = config["eq_dir"]
    detected_res = detect_resolution(eq_dir, config["resolution"])
    print(f"Detected Res:  {detected_res[0]}x{detected_res[1]}")
    
    print("\nCharacters Syncing:")
    for char in config.get("characters", []):
        print(f"  - {char}")
        # Search both local and sync dir to list status of all profiles
        char_configs = find_character_configs(eq_dir, char)
        if not char_configs:
            char_configs = find_character_configs(sync_dir, char)
            
        if not char_configs:
            print("    Local/Sync profile: NOT FOUND")
            continue
            
        for config_name in char_configs:
            print(f"    Profile: {config_name}")
            char_path = os.path.join(eq_dir, f"{config_name}.ini")
            if os.path.exists(char_path):
                local_time = datetime.datetime.fromtimestamp(os.path.getmtime(char_path)).isoformat()
                print(f"      Local .ini modified: {local_time}")
            else:
                print("      Local .ini: NOT FOUND")

            ui_path = os.path.join(eq_dir, f"UI_{config_name}.ini")
            if os.path.exists(ui_path):
                local_time = datetime.datetime.fromtimestamp(os.path.getmtime(ui_path)).isoformat()
                print(f"      Local UI modified:   {local_time}")
            else:
                print("      Local UI:   NOT FOUND")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="EverQuest Legends Sync Tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")
    
    # init
    subparsers.add_parser("init", help="Configure local settings")
    
    # push
    push_parser = subparsers.add_parser("push", help="Push local settings to sync folder")
    push_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    push_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    push_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and confirmation prompts")
    push_parser.add_argument("--dry-run", action="store_true", help="Simulate pushing settings without writing any files")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull settings from sync folder")
    pull_parser.add_argument("--no-ui", action="store_true", help="Skip UI layout sync for this run")
    pull_parser.add_argument("--ui-mode", choices=["scale_position", "scale_all", "exact", "none"], help="Override UI sync mode")
    pull_parser.add_argument("--force", action="store_true", help="Bypass running game warnings and confirmation prompts")
    pull_parser.add_argument("--dry-run", action="store_true", help="Simulate pulling settings without writing any files")

    # status
    subparsers.add_parser("status", help="Show current sync status")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    cmd = args.command.lower()
    if cmd == "init":
        cmd_init()
    elif cmd == "push":
        cmd_push(args)
    elif cmd == "pull":
        cmd_pull(args)
    elif cmd == "status":
        cmd_status()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
