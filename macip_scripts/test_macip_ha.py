import importlib.util
import asyncio
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class HTTPConflict(Exception):
    def __init__(self, *, text):
        super().__init__(text)


class FakeView:
    pass


modules = {
    "aiohttp": types.ModuleType("aiohttp"),
    "homeassistant": types.ModuleType("homeassistant"),
    "homeassistant.components": types.ModuleType("homeassistant.components"),
    "homeassistant.components.http": types.ModuleType("homeassistant.components.http"),
    "homeassistant.core": types.ModuleType("homeassistant.core"),
}
modules["aiohttp"].web = types.SimpleNamespace(Response=object, HTTPConflict=HTTPConflict)
modules["homeassistant.components.http"].HomeAssistantView = FakeView
modules["homeassistant.core"].HomeAssistant = object
path = Path(__file__).parent / "home_assistant" / "custom_components" / "macip" / "http.py"
spec = importlib.util.spec_from_file_location("macip_ha_http", path)
app = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, modules):
    spec.loader.exec_module(app)

CONTENT = (
    "MAC | IP | Nimi | Oma nimi | Tila | Viimeksi nähty | Yhteys | Signaali | Tukiasema\n"
    "00:11:22:33:44:55 | 192.0.2.1 | testi | oma | on |  | wifi |  | AP\n"
)
COMMANDS = [["asys_mac.py", "secret3.txt"], ["asys_mac.py", "secret2.txt"],
            ["huawei_lan_inventory.py", "secret1.txt"]]


class MacipHaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.inventory = self.directory / "macip.txt"
        self.inventory.write_text(CONTENT, encoding="utf-8")
        (self.directory / "macip_server_config.json").write_text(
            json.dumps({"update_commands": COMMANDS}), encoding="utf-8"
        )

    def test_revision_and_stale_save(self):
        initial = app._read_inventory(self.inventory)
        changed = CONTENT.replace("oma", "uusi")
        app.validate_content(changed)
        updated = app._save_inventory(self.inventory, changed, initial["revision"])
        self.assertEqual(updated, app._read_inventory(self.inventory)["revision"])
        with self.assertRaises(HTTPConflict):
            app._save_inventory(self.inventory, CONTENT, initial["revision"])
        self.assertEqual(self.inventory.read_text(encoding="utf-8"), changed)

    def test_missing_inventory_is_created_with_valid_headers(self):
        self.inventory.unlink()
        result = app._read_or_create_inventory(self.inventory)
        expected = " | ".join(app.EXTENDED_HEADERS) + "\n"
        self.assertEqual(result["content"], expected)
        self.assertEqual(result, app._read_inventory(self.inventory))
        app.validate_content(result["content"])

    def test_existing_inventory_is_not_modified(self):
        before = self.inventory.read_bytes()
        result = app._read_or_create_inventory(self.inventory)
        self.assertEqual(self.inventory.read_bytes(), before)
        self.assertEqual(result["content"], before.decode("utf-8"))

    def test_creation_does_not_replace_file_created_concurrently(self):
        self.inventory.unlink()
        original_open = Path.open

        def create_concurrently(path, mode="r", *args, **kwargs):
            if mode == "x":
                path.write_text(CONTENT, encoding="utf-8")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", create_concurrently):
            result = app._read_or_create_inventory(self.inventory)
        self.assertEqual(result["content"], self.inventory.read_bytes().decode("utf-8"))
        self.assertEqual(self.inventory.read_text(encoding="utf-8"), CONTENT)

    def test_missing_parent_or_permission_failure_is_not_hidden(self):
        with self.assertRaises(FileNotFoundError):
            app._read_or_create_inventory(self.directory / "missing" / "macip.txt")
        self.inventory.unlink()
        with patch.object(Path, "open", side_effect=PermissionError("access denied")):
            with self.assertRaises(PermissionError):
                app._read_or_create_inventory(self.inventory)

    def test_get_creates_inventory_and_update_can_start(self):
        self.inventory.unlink()

        class FakeHass:
            config = types.SimpleNamespace(path=lambda *args: str(self.directory))

            async def async_add_executor_job(self, func, *args):
                return func(*args)

        view = app.MacipView(FakeHass())
        view.json = lambda data: data
        result = asyncio.run(view.get(None))
        self.assertEqual(result["content"], " | ".join(app.EXTENDED_HEADERS) + "\n")
        with patch.object(app.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "", "")) as runner:
            updated = app._update_inventory(self.directory, result["revision"])
        self.assertEqual(runner.call_count, len(COMMANDS))
        self.assertEqual(updated["revision"], result["revision"])

    def test_view_uses_macip_scripts_directory(self):
        config = types.SimpleNamespace(path=lambda *parts: str(self.directory.joinpath(*parts)))
        view = app.MacipView(types.SimpleNamespace(config=config))
        self.assertEqual(view.directory, self.directory / "macip_scripts")

    def test_router_failure_continues_and_returns_updated_inventory(self):
        summary = {"router": "test", "new_devices": [], "ip_changes": []}
        calls = []

        def run(command, **kwargs):
            calls.append(command[1:])
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(command, 180)
            if len(calls) == 2:
                self.inventory.write_text(CONTENT.replace("oma", "uusi"), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "MACIP_SUMMARY " + json.dumps(summary), "")
            return subprocess.CompletedProcess(command, 1, "", "virhe")

        with patch.object(app.subprocess, "run", side_effect=run):
            result = app._update_inventory(self.directory, app._read_inventory(self.inventory)["revision"])
        self.assertEqual(calls, COMMANDS)
        self.assertEqual(len(result["failures"]), 2)
        self.assertEqual(result["summaries"], [summary])
        self.assertIn("uusi", result["content"])

    def test_invalid_summary_does_not_stop_later_commands(self):
        output = subprocess.CompletedProcess([], 0, 'MACIP_SUMMARY {"router":"x"}', "")
        with patch.object(app.subprocess, "run", return_value=output) as runner:
            result = app._update_inventory(self.directory, app._read_inventory(self.inventory)["revision"])
        self.assertEqual(runner.call_count, 3)
        self.assertEqual(len(result["failures"]), 3)

    def test_stale_update_does_not_start_commands(self):
        with patch.object(app.subprocess, "run") as runner:
            with self.assertRaises(HTTPConflict):
                app._update_inventory(self.directory, "stale")
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
