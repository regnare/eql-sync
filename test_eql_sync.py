#!/usr/bin/env python3
import os
import unittest
import tempfile
import shutil
import configparser
from eql_sync import scale_ui_coordinates, detect_resolution, load_ini, save_ini

class TestEverQuestSync(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for tests
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Remove temp directory
        shutil.rmtree(self.test_dir)

    def test_scale_ui_coordinates_position_only(self):
        # Setup mock ini parser contents
        ini_content = """[ChatWindow1]
XPos=100
YPos=200
Width=300
Height=400
Locked=1
[SpellBarWnd]
XOffset=50
YOffset=150
Width=100
Height=200
"""
        temp_ini_path = os.path.join(self.test_dir, "UI_test.ini")
        with open(temp_ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        # Load it
        parser = load_ini(temp_ini_path)

        # Scale from 2000x1000 to 1000x500 (Scale factor = 0.5)
        src_res = [2000, 1000]
        dest_res = [1000, 500]
        scaled = scale_ui_coordinates(parser, src_res, dest_res, "scale_position")

        # Check coordinates (should be halved)
        self.assertEqual(scaled.get("ChatWindow1", "XPos"), "50")
        self.assertEqual(scaled.get("ChatWindow1", "YPos"), "100")
        self.assertEqual(scaled.get("SpellBarWnd", "XOffset"), "25")
        self.assertEqual(scaled.get("SpellBarWnd", "YOffset"), "75")

        # Check sizes (should NOT be scaled in scale_position mode)
        self.assertEqual(scaled.get("ChatWindow1", "Width"), "300")
        self.assertEqual(scaled.get("ChatWindow1", "Height"), "400")
        self.assertEqual(scaled.get("SpellBarWnd", "Width"), "100")

    def test_scale_ui_coordinates_scale_all(self):
        ini_content = """[ChatWindow1]
XPos=100
YPos=200
Width=300
Height=400
"""
        temp_ini_path = os.path.join(self.test_dir, "UI_test.ini")
        with open(temp_ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        parser = load_ini(temp_ini_path)

        # Scale from 2000x1000 to 3000x2000 (Scale factor: X=1.5, Y=2.0)
        src_res = [2000, 1000]
        dest_res = [3000, 2000]
        scaled = scale_ui_coordinates(parser, src_res, dest_res, "scale_all")

        # Check coordinates
        self.assertEqual(scaled.get("ChatWindow1", "XPos"), "150")
        self.assertEqual(scaled.get("ChatWindow1", "YPos"), "400")

        # Check sizes (should be scaled in scale_all mode)
        self.assertEqual(scaled.get("ChatWindow1", "Width"), "450")
        self.assertEqual(scaled.get("ChatWindow1", "Height"), "800")

    def test_scale_ui_coordinates_identity(self):
        ini_content = """[ChatWindow1]
XPos=100
Width=300
"""
        temp_ini_path = os.path.join(self.test_dir, "UI_test.ini")
        with open(temp_ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        parser = load_ini(temp_ini_path)

        # Scale to same resolution
        scaled = scale_ui_coordinates(parser, [1920, 1080], [1920, 1080], "scale_position")
        self.assertEqual(scaled.get("ChatWindow1", "XPos"), "100")

    def test_detect_resolution_windowed(self):
        # Create mock eqclient.ini
        eqclient_content = """[Defaults]
Sound=TRUE
[VideoMode]
Width=1024
Height=768
WindowedWidth=1920
WindowedHeight=1080
WindowedMode=TRUE
"""
        eqclient_path = os.path.join(self.test_dir, "eqclient.ini")
        with open(eqclient_path, "w", encoding="utf-8") as f:
            f.write(eqclient_content)

        res = detect_resolution(self.test_dir, [800, 600])
        self.assertEqual(res, [1920, 1080])

    def test_detect_resolution_fullscreen(self):
        eqclient_content = """[VideoMode]
Width=1440
Height=900
WindowedWidth=1920
WindowedHeight=1080
WindowedMode=FALSE
"""
        eqclient_path = os.path.join(self.test_dir, "eqclient.ini")
        with open(eqclient_path, "w", encoding="utf-8") as f:
            f.write(eqclient_content)

        res = detect_resolution(self.test_dir, [800, 600])
        self.assertEqual(res, [1440, 900])

    def test_detect_resolution_missing_file_fallback(self):
        res = detect_resolution(os.path.join(self.test_dir, "nonexistent"), [800, 600])
        self.assertEqual(res, [800, 600])

    def test_ini_formatting_preservation(self):
        # Test that standard config parser casing and format are preserved when saving.
        # Specifically: case-sensitivity of keys, and no spaces around the '=' delimiter.
        ini_content = """[ChatWindow]
XPos=100
YPos=200
Locked=1
SomeCamelCaseKey=Value
"""
        temp_ini_path = os.path.join(self.test_dir, "UI_test.ini")
        with open(temp_ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        parser = load_ini(temp_ini_path)
        
        # Modify a value
        parser.set("ChatWindow", "XPos", "150")
        
        # Save it
        save_ini(parser, temp_ini_path)

        # Read the raw file to verify styling
        with open(temp_ini_path, "r", encoding="utf-8") as f:
            raw_data = f.read()

        # Should contain "XPos=150" with no spaces, and preserve capitalization of camel case key
        self.assertIn("XPos=150", raw_data)
        self.assertNotIn("XPos = 150", raw_data)
        self.assertIn("SomeCamelCaseKey=Value", raw_data)

    def test_cmd_push_pull_overrides(self):
        import json
        from eql_sync import cmd_push, cmd_pull
        
        # 1. Setup directories
        eq_dir = os.path.join(self.test_dir, "eq")
        sync_dir = os.path.join(self.test_dir, "sync")
        os.makedirs(eq_dir)
        os.makedirs(sync_dir)
        
        # Write config.json
        config = {
            "eq_dir": eq_dir,
            "sync_dir": sync_dir,
            "characters": ["Faugus_legends"],
            "ui_sync_mode": "scale_position",
            "resolution": [2560, 1440],
            "machine_name": "desktop"
        }
        config_path = os.path.join(self.test_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
            
        # Mock get_config_path
        import eql_sync
        old_get_config_path = eql_sync.get_config_path
        eql_sync.get_config_path = lambda: config_path
        
        try:
            # Create character files
            char_ini = "Faugus_legends.ini"
            ui_ini = "UI_Faugus_legends.ini"
            
            with open(os.path.join(eq_dir, char_ini), "w") as f:
                f.write("[Socials]\nPage1Button1Line1=/say Hello\n")
            with open(os.path.join(eq_dir, ui_ini), "w") as f:
                f.write("[ChatWindow]\nXPos=100\n")
                
            # Define mock args
            class MockArgs:
                def __init__(self, no_ui=False, ui_mode=None, force=True):
                    self.no_ui = no_ui
                    self.ui_mode = ui_mode
                    self.force = force
                    
            # 1. Test pushing with --no-ui
            args_no_ui = MockArgs(no_ui=True)
            cmd_push(args_no_ui)
            
            # Verify char.ini is in sync_dir, but UI_char.ini is NOT (since --no-ui was passed)
            self.assertTrue(os.path.exists(os.path.join(sync_dir, char_ini)))
            self.assertFalse(os.path.exists(os.path.join(sync_dir, ui_ini)))
            
            # 2. Test pushing with default (no args) -> should push both
            cmd_push()
            self.assertTrue(os.path.exists(os.path.join(sync_dir, ui_ini)))
            
            # Remove local files to test pulling
            os.remove(os.path.join(eq_dir, char_ini))
            os.remove(os.path.join(eq_dir, ui_ini))
            
            # 3. Test pulling with --no-ui
            cmd_pull(args_no_ui)
            self.assertTrue(os.path.exists(os.path.join(eq_dir, char_ini)))
            self.assertFalse(os.path.exists(os.path.join(eq_dir, ui_ini)))
            
        finally:
            eql_sync.get_config_path = old_get_config_path

    def test_prefix_pattern_discovery(self):
        import json
        from eql_sync import cmd_push, cmd_pull
        
        # Setup directories
        eq_dir = os.path.join(self.test_dir, "eq")
        sync_dir = os.path.join(self.test_dir, "sync")
        os.makedirs(eq_dir)
        os.makedirs(sync_dir)
        
        # Write config.json with character prefix "Regnare"
        config = {
            "eq_dir": eq_dir,
            "sync_dir": sync_dir,
            "characters": ["Regnare"],
            "ui_sync_mode": "none",
            "resolution": [2560, 1440],
            "machine_name": "desktop"
        }
        config_path = os.path.join(self.test_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
            
        # Mock get_config_path
        import eql_sync
        old_get_config_path = eql_sync.get_config_path
        eql_sync.get_config_path = lambda: config_path
        
        try:
            # Create files with server name suffix
            char1_ini = "Regnare_freeport_LO1.ini"
            char2_ini = "Regnare_freeport_LO2.ini"
            
            with open(os.path.join(eq_dir, char1_ini), "w") as f:
                f.write("[Socials]\nPage1=1\n")
            with open(os.path.join(eq_dir, char2_ini), "w") as f:
                f.write("[Socials]\nPage1=2\n")
                
            # Define mock args
            class MockArgs:
                def __init__(self, force=True):
                    self.no_ui = False
                    self.ui_mode = None
                    self.force = force
            
            # Push
            cmd_push(MockArgs())
            
            # Verify both files are copied to sync_dir
            self.assertTrue(os.path.exists(os.path.join(sync_dir, char1_ini)))
            self.assertTrue(os.path.exists(os.path.join(sync_dir, char2_ini)))
            
            # Remove local files
            os.remove(os.path.join(eq_dir, char1_ini))
            os.remove(os.path.join(eq_dir, char2_ini))
            
            # Pull
            cmd_pull(MockArgs())
            
            # Verify both files are pulled back
            self.assertTrue(os.path.exists(os.path.join(eq_dir, char1_ini)))
            self.assertTrue(os.path.exists(os.path.join(eq_dir, char2_ini)))
            
        finally:
            eql_sync.get_config_path = old_get_config_path

    def test_dry_run_push_pull(self):
        import json
        from eql_sync import cmd_push, cmd_pull
        
        # Setup directories
        eq_dir = os.path.join(self.test_dir, "eq")
        sync_dir = os.path.join(self.test_dir, "sync")
        os.makedirs(eq_dir)
        os.makedirs(sync_dir)
        
        # Write config.json
        config = {
            "eq_dir": eq_dir,
            "sync_dir": sync_dir,
            "characters": ["Faugus_legends"],
            "ui_sync_mode": "scale_position",
            "resolution": [2560, 1440],
            "machine_name": "desktop"
        }
        config_path = os.path.join(self.test_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
            
        # Mock get_config_path
        import eql_sync
        old_get_config_path = eql_sync.get_config_path
        eql_sync.get_config_path = lambda: config_path
        
        try:
            # Create local character file
            char_ini = "Faugus_legends.ini"
            with open(os.path.join(eq_dir, char_ini), "w") as f:
                f.write("[Socials]\nPage1=1\n")
                
            class MockArgs:
                def __init__(self, dry_run=True):
                    self.no_ui = False
                    self.ui_mode = None
                    self.force = False
                    self.global_dry_run = dry_run
                    self.sub_dry_run = False
                    
            # Push with dry-run
            cmd_push(MockArgs(dry_run=True))
            
            # Verify no files were created in sync directory
            self.assertFalse(os.path.exists(os.path.join(sync_dir, char_ini)))
            
            # Now push normally to write it
            cmd_push(MockArgs(dry_run=False))
            self.assertTrue(os.path.exists(os.path.join(sync_dir, char_ini)))
            
            # Remove local file to test pulling
            os.remove(os.path.join(eq_dir, char_ini))
            
            # Pull with dry-run
            cmd_pull(MockArgs(dry_run=True))
            # Verify file was NOT pulled
            self.assertFalse(os.path.exists(os.path.join(eq_dir, char_ini)))
            
            # Pull normally
            cmd_pull(MockArgs(dry_run=False))
            # Verify file WAS pulled
            self.assertTrue(os.path.exists(os.path.join(eq_dir, char_ini)))
            
        finally:
            eql_sync.get_config_path = old_get_config_path

    def test_prune_backups(self):
        import datetime
        from eql_sync import prune_backups
        backup_dir = os.path.join(self.test_dir, "test_backups")
        os.makedirs(backup_dir)

        now = datetime.datetime.now()
        # Create 15 backups: 1 day old to 15 days old (all within 30-day window)
        for i in range(1, 16):
            dt = now - datetime.timedelta(days=i)
            fname = f"Regnare_freeport_LO1.ini.{dt.strftime('%Y%m%d_%H%M%S')}.bak"
            with open(os.path.join(backup_dir, fname), "w") as f:
                f.write(f"Backup {i}\n")

        # Dry run should not delete any files
        pruned_dry = prune_backups(backup_dir, max_backups=10, max_days=30, dry_run=True)
        self.assertEqual(len(pruned_dry), 5)
        self.assertEqual(len(os.listdir(backup_dir)), 15)

        # Actual run should prune 5 oldest, keeping 10 newest (days 1 to 10)
        pruned = prune_backups(backup_dir, max_backups=10, max_days=30, dry_run=False)
        self.assertEqual(len(pruned), 5)
        remaining = os.listdir(backup_dir)
        self.assertEqual(len(remaining), 10)

        # Add a 45-day-old backup to test age-based pruning
        old_dt = now - datetime.timedelta(days=45)
        old_fname = f"Regnare_freeport_LO1.ini.{old_dt.strftime('%Y%m%d_%H%M%S')}.bak"
        with open(os.path.join(backup_dir, old_fname), "w") as f:
            f.write("Old backup\n")

        # Running prune with max_backups=15 should prune the 45-day-old file
        pruned_age = prune_backups(backup_dir, max_backups=15, max_days=30, dry_run=False)
        self.assertEqual(pruned_age, [old_fname])
        self.assertNotIn(old_fname, os.listdir(backup_dir))

    def test_cmd_status_and_auto_sync(self):
        import io
        import json
        import time
        from contextlib import redirect_stdout
        from eql_sync import cmd_status, cmd_auto

        eq_dir = os.path.join(self.test_dir, "auto_eq")
        sync_dir = os.path.join(self.test_dir, "auto_sync")
        os.makedirs(eq_dir)
        os.makedirs(sync_dir)

        config = {
            "eq_dir": eq_dir,
            "sync_dir": sync_dir,
            "characters": ["Regnare"],
            "ui_sync_mode": "none",
            "resolution": [2560, 1440],
            "machine_name": "desktop"
        }
        config_path = os.path.join(self.test_dir, "auto_config.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        import eql_sync
        old_get_config_path = eql_sync.get_config_path
        eql_sync.get_config_path = lambda: config_path

        try:
            # Profile 1: Local is newer
            p1_local = os.path.join(eq_dir, "Regnare_freeport_LO1.ini")
            p1_sync = os.path.join(sync_dir, "Regnare_freeport_LO1.ini")
            with open(p1_sync, "w") as f:
                f.write("LO1 old sync content\n")
            time.sleep(1.1)
            with open(p1_local, "w") as f:
                f.write("LO1 new local content\n")

            # Profile 2: Sync is newer
            p2_local = os.path.join(eq_dir, "Regnare_freeport_LO2.ini")
            p2_sync = os.path.join(sync_dir, "Regnare_freeport_LO2.ini")
            with open(p2_local, "w") as f:
                f.write("LO2 old local content\n")
            time.sleep(1.1)
            with open(p2_sync, "w") as f:
                f.write("LO2 new sync content\n")

            # Test cmd_status output
            status_buf = io.StringIO()
            with redirect_stdout(status_buf):
                cmd_status()
            status_output = status_buf.getvalue()

            self.assertIn("LOCAL NEWER -> PUSH RECOMMENDED", status_output)
            self.assertIn("SYNC NEWER -> PULL RECOMMENDED", status_output)
            self.assertIn("Mixed states detected", status_output)

            # Test cmd_auto in dry-run mode
            class MockArgs:
                def __init__(self, dry_run=True):
                    self.no_ui = False
                    self.ui_mode = None
                    self.force = True
                    self.global_dry_run = dry_run
                    self.sub_dry_run = False

            dry_buf = io.StringIO()
            with redirect_stdout(dry_buf):
                cmd_auto(MockArgs(dry_run=True))
            dry_output = dry_buf.getvalue()

            self.assertIn("[AUTO-PUSH] Local Regnare_freeport_LO1.ini is newer", dry_output)
            self.assertIn("[AUTO-PULL] Synced Regnare_freeport_LO2.ini is newer", dry_output)
            # Verify dry run didn't alter sync file 1 or local file 2
            with open(p1_sync) as f:
                self.assertEqual(f.read(), "LO1 old sync content\n")
            with open(p2_local) as f:
                self.assertEqual(f.read(), "LO2 old local content\n")

            # Execute real cmd_auto
            auto_buf = io.StringIO()
            with redirect_stdout(auto_buf):
                cmd_auto(MockArgs(dry_run=False))

            # Verify files were updated in their respective directions
            with open(p1_sync) as f:
                self.assertEqual(f.read(), "LO1 new local content\n")
            with open(p2_local) as f:
                self.assertEqual(f.read(), "LO2 new sync content\n")

            # Verify backups were created in both backup folders
            sync_backups = os.listdir(os.path.join(sync_dir, "sync_backups"))
            eq_backups = os.listdir(os.path.join(eq_dir, "sync_backups"))
            self.assertTrue(any("Regnare_freeport_LO1.ini" in b for b in sync_backups))
            self.assertTrue(any("Regnare_freeport_LO2.ini" in b for b in eq_backups))

            # Running status again should show in sync
            in_sync_buf = io.StringIO()
            with redirect_stdout(in_sync_buf):
                cmd_status()
            in_sync_output = in_sync_buf.getvalue()
            self.assertIn("All character files are in sync!", in_sync_output)

        finally:
            eql_sync.get_config_path = old_get_config_path

    def test_config_path_precedence(self):
        import eql_sync
        fake_default = os.path.join(self.test_dir, "default_config.json")
        fake_cwd = os.path.join(self.test_dir, "cwd_config.json")
        with open(fake_default, "w") as f:
            f.write("{}")
        with open(fake_cwd, "w") as f:
            f.write("{}")

        orig_default = eql_sync.DEFAULT_CONFIG_PATH
        orig_cwd = os.getcwd
        orig_filename = eql_sync.CONFIG_FILENAME
        try:
            eql_sync.DEFAULT_CONFIG_PATH = fake_default
            self.assertEqual(eql_sync.get_config_path(), fake_default)
            
            # If default doesn't exist, fallback to cwd
            eql_sync.DEFAULT_CONFIG_PATH = os.path.join(self.test_dir, "nonexistent.json")
            os.getcwd = lambda: self.test_dir
            eql_sync.CONFIG_FILENAME = "cwd_config.json"
            self.assertEqual(eql_sync.get_config_path(), fake_cwd)
        finally:
            eql_sync.DEFAULT_CONFIG_PATH = orig_default
            eql_sync.CONFIG_FILENAME = orig_filename
            os.getcwd = orig_cwd

    def test_cmd_install_dry_run(self):
        import io
        from contextlib import redirect_stdout
        from eql_sync import cmd_install

        fake_home = os.path.join(self.test_dir, "fake_home")
        old_expanduser = os.path.expanduser
        os.path.expanduser = lambda path: path.replace("~", fake_home)

        class MockArgs:
            def __init__(self, dry_run=True):
                self.global_dry_run = dry_run
                self.sub_dry_run = False
                self.add_path = False

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_install(MockArgs(dry_run=True))
            output = buf.getvalue()
            self.assertIn("[DRY-RUN] Would create symlink", output)
        finally:
            os.path.expanduser = old_expanduser

    def test_shell_rc_path_detection(self):
        from eql_sync import get_shell_rc_path
        old_shell = os.environ.get("SHELL")
        try:
            os.environ["SHELL"] = "/bin/zsh"
            self.assertTrue(get_shell_rc_path().endswith(".zshrc"))

            os.environ["SHELL"] = "/usr/bin/fish"
            self.assertTrue(get_shell_rc_path().endswith("config.fish"))

            os.environ["SHELL"] = "/bin/bash"
            rc = get_shell_rc_path()
            self.assertTrue(rc.endswith(".bashrc") or rc.endswith(".bash_profile"))
        finally:
            if old_shell is not None:
                os.environ["SHELL"] = old_shell
            else:
                os.environ.pop("SHELL", None)

    def test_cmd_install_add_path(self):
        import io
        from contextlib import redirect_stdout
        import eql_sync
        from eql_sync import cmd_install

        mock_rc = os.path.join(self.test_dir, ".mock_zshrc")
        old_get_rc = eql_sync.get_shell_rc_path
        eql_sync.get_shell_rc_path = lambda: mock_rc

        class MockArgs:
            def __init__(self):
                self.global_dry_run = False
                self.sub_dry_run = False
                self.add_path = True

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_install(MockArgs())
            self.assertTrue(os.path.exists(mock_rc))
            with open(mock_rc) as f:
                content = f.read()
            self.assertIn(".local/bin", content)
        finally:
            eql_sync.get_shell_rc_path = old_get_rc

    def test_cmd_play_dry_run(self):
        import io
        from contextlib import redirect_stdout
        import eql_sync
        from eql_sync import cmd_play

        class MockArgs:
            def __init__(self):
                self.global_dry_run = True
                self.sub_dry_run = False
                self.launch_command = None
                self.force = False
                self.no_pre_sync = False
                self.no_post_sync = False
                self.wait_timeout = 10

        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = cmd_play(MockArgs())
        output = buf.getvalue()
        self.assertEqual(ret, 0)
        self.assertIn("DRY-RUN MODE", output)
        self.assertIn("Would execute command:", output)
        self.assertIn("Would execute post-game auto-sync", output)

    def test_cmd_play_already_running_guard(self):
        import io
        from contextlib import redirect_stdout
        import eql_sync
        from eql_sync import cmd_play

        old_is_running = eql_sync.is_game_running
        eql_sync.is_game_running = lambda: True

        class MockArgs:
            def __init__(self):
                self.global_dry_run = False
                self.sub_dry_run = False
                self.launch_command = None
                self.force = False
                self.no_pre_sync = False
                self.no_post_sync = False
                self.wait_timeout = 10

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = cmd_play(MockArgs())
            output = buf.getvalue()
            self.assertEqual(ret, 1)
            self.assertIn("WARNING: EverQuest Legends process (eqgame.exe) is already running!", output)
            self.assertIn("Aborting play session", output)
        finally:
            eql_sync.is_game_running = old_is_running

    def test_cmd_play_full_lifecycle(self):
        import io
        import time
        from contextlib import redirect_stdout
        import eql_sync
        from eql_sync import cmd_play

        old_is_running = eql_sync.is_game_running
        old_sleep = time.sleep
        old_popen = eql_sync.subprocess.Popen
        old_cmd_auto = eql_sync.cmd_auto

        state_iter = iter([False, True, True, False])
        eql_sync.is_game_running = lambda: next(state_iter, False)
        time.sleep = lambda s: None

        auto_calls = []
        eql_sync.cmd_auto = lambda args=None: auto_calls.append("auto")

        popen_calls = []
        class MockPopen:
            def __init__(self, cmd, **kwargs):
                popen_calls.append(cmd)
        eql_sync.subprocess.Popen = MockPopen

        class MockArgs:
            def __init__(self):
                self.global_dry_run = False
                self.sub_dry_run = False
                self.launch_command = "test-launcher"
                self.force = False
                self.no_pre_sync = False
                self.no_post_sync = False
                self.wait_timeout = 10

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = cmd_play(MockArgs())
            output = buf.getvalue()
            self.assertEqual(ret, 0)
            self.assertEqual(len(popen_calls), 1)
            self.assertEqual(popen_calls[0], "test-launcher")
            self.assertEqual(len(auto_calls), 2)
            self.assertIn("Game process detected! Enjoy your session.", output)
            self.assertIn("EverQuest (eqgame.exe) has exited.", output)
            self.assertIn("Post-game sync complete!", output)
        finally:
            eql_sync.is_game_running = old_is_running
            time.sleep = old_sleep
            eql_sync.subprocess.Popen = old_popen
            eql_sync.cmd_auto = old_cmd_auto

    def test_cmd_play_startup_timeout(self):
        import io
        import time
        from contextlib import redirect_stdout
        import eql_sync
        from eql_sync import cmd_play

        old_is_running = eql_sync.is_game_running
        old_sleep = time.sleep
        old_popen = eql_sync.subprocess.Popen
        old_cmd_auto = eql_sync.cmd_auto

        eql_sync.is_game_running = lambda: False
        time.sleep = lambda s: None

        auto_calls = []
        eql_sync.cmd_auto = lambda args=None: auto_calls.append("auto")

        class MockPopen:
            def __init__(self, cmd, **kwargs):
                pass
        eql_sync.subprocess.Popen = MockPopen

        class MockArgs:
            def __init__(self):
                self.global_dry_run = False
                self.sub_dry_run = False
                self.launch_command = "test-launcher"
                self.force = False
                self.no_pre_sync = False
                self.no_post_sync = False
                self.wait_timeout = -1

        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = cmd_play(MockArgs())
            output = buf.getvalue()
            self.assertEqual(ret, 1)
            self.assertEqual(len(auto_calls), 1)
            self.assertIn("was not detected within", output)
            self.assertIn("Skipping post-game auto-sync", output)
        finally:
            eql_sync.is_game_running = old_is_running
            time.sleep = old_sleep
            eql_sync.subprocess.Popen = old_popen
            eql_sync.cmd_auto = old_cmd_auto

    def test_help_all_flag(self):
        import io
        import sys
        from contextlib import redirect_stdout
        import eql_sync

        old_argv = sys.argv
        try:
            sys.argv = ["eql_sync.py", "--help-all"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    eql_sync.main()
            self.assertEqual(cm.exception.code, 0)
            output = buf.getvalue()
            self.assertIn("SUBCOMMAND DETAILS & OPTIONS", output)
            self.assertIn("eql-sync play", output)
            self.assertIn("eql-sync auto (sync)", output)
            self.assertIn("eql-sync push", output)
            self.assertIn("eql-sync pull", output)
            self.assertIn("eql-sync status (check)", output)
            self.assertIn("eql-sync prune", output)
            self.assertIn("eql-sync install", output)
            self.assertIn("eql-sync init", output)
        finally:
            sys.argv = old_argv

if __name__ == "__main__":
    unittest.main()
