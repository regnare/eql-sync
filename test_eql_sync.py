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

if __name__ == "__main__":
    unittest.main()
