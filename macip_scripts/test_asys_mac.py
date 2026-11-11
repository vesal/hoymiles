import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from macip_scripts import asys_mac


class FixedDateTime:
    @classmethod
    def now(cls):
        return cls()

    def astimezone(self):
        return self

    def strftime(self, _format):
        return "2026-11-10 10:00:00"


class AsusMacTests(unittest.TestCase):
    def setUp(self):
        self.source = (
            "MAC | IP | Reitittimen nimi | Oma nimi | Tila | Viimeksi nähty"
            " | Yhteys | Signaali | Tukiasema\n"
            "00:11:22:33:44:55 | 192.0.2.5 | router | nimi | Online"
            " | vanha aika | 2.4 GHz | -50 | 192.0.2.1\n"
        )
        self.clients = {
            "maclist": ["00:11:22:33:44:55"],
            "00:11:22:33:44:55": {
                "isOnline": "1",
                "isWL": "1",
                "rssi": "-60",
                "ip": "192.0.2.10",
                "name": "laite",
            },
        }

    def run_update(self, router_nickname="", update_last_seen="false"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            path.write_text(self.source, encoding="utf-8")
            config = {
                "macip": str(path),
                "ip": "192.0.2.1",
                "router_nickname": router_nickname,
                "update_last_seen": update_last_seen,
            }
            original_datetime = asys_mac.datetime
            asys_mac.datetime = FixedDateTime
            try:
                asys_mac.update_macip(self.clients, config)
            finally:
                asys_mac.datetime = original_datetime
            _, _, rows = asys_mac.read_macip(path)
            return rows["00:11:22:33:44:55"]

    def test_nickname_replaces_access_point_ip_and_last_seen_is_preserved(self):
        row = self.run_update(router_nickname="Asus olo", update_last_seen="false")

        self.assertEqual(row["Tukiasema"], "Asus olo")
        self.assertEqual(row["Viimeksi nähty"], "vanha aika")

    def test_empty_nickname_uses_access_point_ip(self):
        row = self.run_update()

        self.assertEqual(row["Tukiasema"], "192.0.2.1")

    def test_last_seen_can_be_enabled(self):
        row = self.run_update(update_last_seen="true")

        self.assertEqual(row["Viimeksi nähty"], "2026-11-10 10:00:00")

    def test_ip_change_report_excludes_new_and_offline_devices(self):
        self.clients["maclist"] += ["00:11:22:33:44:66", "00:11:22:33:44:77"]
        self.clients["00:11:22:33:44:66"] = {
            "isOnline": "1", "ip": "192.0.2.20"
        }
        self.clients["00:11:22:33:44:77"] = {
            "isOnline": "0", "ip": "192.0.2.21"
        }
        output = io.StringIO()
        with redirect_stdout(output):
            self.run_update()
        self.assertIn("nimi (00:11:22:33:44:55): 192.0.2.5 -> 192.0.2.10",
                      output.getvalue())
        line = next(line for line in output.getvalue().splitlines()
                    if line.startswith("MACIP_SUMMARY "))
        summary = json.loads(line.removeprefix("MACIP_SUMMARY "))
        self.assertEqual(len(summary["ip_changes"]), 1)
        self.assertEqual(summary["new_devices"][0]["ip"], "192.0.2.20")
        self.assertNotIn("192.0.2.21", output.getvalue())

    def test_inventory_is_sorted_by_numeric_ip(self):
        headers = ["MAC", "IP"]
        rows = {
            "first": {"MAC": "first", "IP": "192.0.2.123"},
            "second": {"MAC": "second", "IP": "192.0.2.25"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            asys_mac.save_macip(path, headers, rows)
            saved_ips = [
                line.split("|")[1].strip()
                for line in path.read_text(encoding="utf-8").splitlines()[1:]
            ]

        self.assertEqual(saved_ips, ["192.0.2.25", "192.0.2.123"])

    def test_logout_uses_authenticated_session(self):
        session = MagicMock()
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "false"}
        asys_mac.logout(session, config)
        session.get.assert_called_once_with(
            "http://192.0.2.1/Logout.asp",
            headers={"Referer": "http://192.0.2.1/index.asp"},
            timeout=15, verify=False,
        )
        session.get.return_value.raise_for_status.assert_called_once()

    def test_main_logs_out_and_closes_session_on_success_and_failure(self):
        config = {"protocol": "http", "ip": "192.0.2.1"}
        for error in (None, ValueError("update failed")):
            with self.subTest(error=error):
                session = MagicMock()
                with patch.object(asys_mac.sys, "argv", ["asys_mac.py", "config.txt"]), \
                     patch.object(asys_mac, "read_config", return_value=config), \
                     patch.object(asys_mac, "login", return_value=session), \
                     patch.object(asys_mac, "get_client_list", return_value={"maclist": []}), \
                     patch.object(asys_mac, "update_macip", side_effect=error), \
                     patch.object(asys_mac, "logout") as logout:
                    if error:
                        with self.assertRaises(SystemExit):
                            asys_mac.main()
                    else:
                        asys_mac.main()
                    logout.assert_called_once_with(session, config)
                    session.__exit__.assert_called_once()

    def test_logout_failure_reports_error_and_fails(self):
        config = {"protocol": "http", "ip": "192.0.2.1"}
        session = MagicMock()
        stderr = io.StringIO()
        with patch.object(asys_mac.sys, "argv", ["asys_mac.py", "config.txt"]), \
             patch.object(asys_mac, "read_config", return_value=config), \
             patch.object(asys_mac, "login", return_value=session), \
             patch.object(asys_mac, "get_client_list", return_value={"maclist": []}), \
             patch.object(asys_mac, "update_macip"), \
             patch.object(asys_mac, "logout", side_effect=requests.ConnectionError("logout failed")), \
             patch.object(asys_mac.sys, "stderr", stderr):
            with self.assertRaises(SystemExit):
                asys_mac.main()
        self.assertIn("Uloskirjautuminen epäonnistui", stderr.getvalue())
        session.__exit__.assert_called_once()

    def test_logout_failure_does_not_hide_update_error(self):
        config = {"protocol": "http", "ip": "192.0.2.1"}
        output, stderr = io.StringIO(), io.StringIO()
        with patch.object(asys_mac.sys, "argv", ["asys_mac.py", "config.txt"]), \
             patch.object(asys_mac, "read_config", return_value=config), \
             patch.object(asys_mac, "login", return_value=MagicMock()), \
             patch.object(asys_mac, "get_client_list", side_effect=ValueError("update failed")), \
             patch.object(asys_mac, "logout", side_effect=requests.ConnectionError("logout failed")), \
             patch.object(asys_mac.sys, "stderr", stderr), redirect_stdout(output):
            with self.assertRaises(SystemExit):
                asys_mac.main()
        self.assertIn("update failed", output.getvalue())
        self.assertIn("Uloskirjautuminen epäonnistui", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
