import json
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from macip_scripts import macip_local_server as app


CONTENT = "MAC | IP | Oma nimi\n00:11:22:33:44:55 | 192.0.2.25 | vanha\n"


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        directory = Path(self.directory.name)
        self.inventory = directory / "macip.txt"
        self.inventory.write_bytes(CONTENT.encode("utf-8"))
        self.config = directory / "config.json"
        self.config.write_text(json.dumps({
            "update_commands": [["one.py", "secret.txt"], ["two.py"]]
        }), encoding="utf-8")
        self.patches = [
            patch.object(app, "INVENTORY_FILE", self.inventory),
            patch.object(app, "CONFIG_FILE", self.config),
            patch.object(app, "DIRECTORY", directory),
        ]
        for item in self.patches:
            item.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.EditorHandler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def request(self, path, payload=None, origin=True):
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            if origin:
                headers["Origin"] = self.base
        request = Request(self.base + path, data=data, headers=headers)
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_load_save_and_reject_stale_version(self):
        status, original = self.request("/api/macip")
        self.assertEqual(status, 200)
        self.assertEqual(original["content"], CONTENT)
        changed = CONTENT.replace("vanha", "uusi")
        status, saved = self.request("/api/macip", {
            "content": changed, "revision": original["revision"]
        })
        self.assertEqual(status, 200)
        self.assertEqual(self.inventory.read_text(encoding="utf-8"), changed)
        self.assertNotEqual(saved["revision"], original["revision"])
        status, _ = self.request("/api/macip", {
            "content": CONTENT, "revision": original["revision"]
        })
        self.assertEqual(status, 409)
        self.assertEqual(self.inventory.read_text(encoding="utf-8"), changed)

    def test_reject_cross_origin_and_other_files(self):
        status, _ = self.request("/api/update", {}, origin=False)
        self.assertEqual(status, 403)
        status, _ = self.request("/secret.txt")
        self.assertEqual(status, 404)

    def test_shared_filter_is_served(self):
        with urlopen(self.base + "/macip_filter.js") as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
            self.assertIn(b"ComparatorFilter", response.read())

    def test_router_commands_run_in_order_and_return_inventory(self):
        def run(command, **kwargs):
            self.assertEqual(kwargs["cwd"], Path(self.directory.name))
            if command[1] == "two.py":
                self.inventory.write_text(CONTENT.replace("vanha", "uusi"), encoding="utf-8")
            summary = {"router": command[1], "ip_changes": [],
                       "new_devices": [{"mac": "aa", "name": "", "ip": "192.0.2.1"}]}
            output = "log\nMACIP_SUMMARY " + json.dumps(summary) + "\n"
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch.object(app.subprocess, "run", side_effect=run) as runner:
            status, result = self.request("/api/update", {})
        self.assertEqual(status, 200)
        self.assertEqual([call.args[0][1:] for call in runner.call_args_list],
                         [["one.py", "secret.txt"], ["two.py"]])
        self.assertIn("uusi", result["content"])
        self.assertEqual([item["router"] for item in result["summaries"]],
                         ["one.py", "two.py"])
        self.assertEqual(result["missing_summaries"], [])

    def test_missing_summary_is_reported(self):
        success = subprocess.CompletedProcess([], 0, "log only", "")
        with patch.object(app.subprocess, "run", return_value=success):
            status, result = self.request("/api/update", {})
        self.assertEqual(status, 200)
        self.assertEqual(result["missing_summaries"], ["one.py secret.txt", "two.py"])

    def test_invalid_summary_is_reported(self):
        success = subprocess.CompletedProcess([], 0, 'MACIP_SUMMARY {"router": "bad"}\n', "")
        with patch.object(app.subprocess, "run", return_value=success):
            status, result = self.request("/api/update", {})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["failures"]), 2)
        self.assertIn("yhteenveto", result["failures"][0]["error"])

    def test_router_failure_does_not_stop_subsequent_commands(self):
        failed = subprocess.CompletedProcess([], 1, "", "virhe")
        summary = {"router": "two", "ip_changes": [], "new_devices": []}
        succeeded = subprocess.CompletedProcess(
            [], 0, "MACIP_SUMMARY " + json.dumps(summary), ""
        )
        def run(*_args, **_kwargs):
            if runner.call_count == 1:
                return failed
            self.inventory.write_bytes(CONTENT.replace("vanha", "uusi").encode("utf-8"))
            return succeeded

        with patch.object(app.subprocess, "run", side_effect=run) as runner:
            status, result = self.request("/api/update", {})
        self.assertEqual(status, 200)
        self.assertEqual(result["failures"][0]["command"], "one.py secret.txt")
        self.assertIn("virhe", result["failures"][0]["error"])
        self.assertEqual(result["summaries"][0]["router"], "two")
        self.assertIn("uusi", result["content"])
        self.assertEqual(result["revision"], app.revision(self.inventory.read_bytes()))
        self.assertEqual(runner.call_count, 2)

    def test_timeout_and_start_failure_do_not_stop_later_commands(self):
        self.config.write_text(json.dumps({
            "update_commands": [["one.py"], ["two.py"], ["three.py"]]
        }), encoding="utf-8")
        summary = {"router": "three", "ip_changes": [], "new_devices": []}
        effects = [
            subprocess.TimeoutExpired("one.py", 180),
            OSError("käynnistysvirhe"),
            subprocess.CompletedProcess([], 0, "MACIP_SUMMARY " + json.dumps(summary), ""),
        ]
        with patch.object(app.subprocess, "run", side_effect=effects) as runner:
            status, result = self.request("/api/update", {})
        self.assertEqual(status, 200)
        self.assertEqual([item["command"] for item in result["failures"]], ["one.py", "two.py"])
        self.assertIn("Aikakatkaisu", result["failures"][0]["error"])
        self.assertIn("käynnistysvirhe", result["failures"][1]["error"])
        self.assertEqual(result["summaries"][0]["router"], "three")
        self.assertEqual(runner.call_count, 3)

    def test_invalid_content_is_not_saved(self):
        _, original = self.request("/api/macip")
        status, _ = self.request("/api/macip", {
            "content": "MAC | Oma nimi\nbad | row | extra\n",
            "revision": original["revision"],
        })
        self.assertEqual(status, 400)
        self.assertEqual(self.inventory.read_text(encoding="utf-8"), CONTENT)


if __name__ == "__main__":
    unittest.main()
