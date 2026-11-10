import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
