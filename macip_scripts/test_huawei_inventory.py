import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from macip_scripts import huawei_lan_inventory as inventory


class InventoryTests(unittest.TestCase):
    def test_config_uses_asus_format_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.txt"
            path.write_text(
                "ip=192.0.2.1:8080\nusername=test\npassword=a=b\n",
                encoding="utf-8",
            )
            config = inventory.read_config(path)
        self.assertEqual(inventory.router_url(config), "http://192.0.2.1:8080")
        self.assertEqual(config["password"], "a=b")
        self.assertEqual(config["macip"], "macip.txt")
        self.assertTrue(inventory.get_verify(config))

    def test_login_uses_settings_and_router_hostname_for_cookie(self):
        session = Mock()
        session.get.side_effect = [Mock(), Mock(text="home")]
        session.post.side_effect = [Mock(text="token"), Mock()]
        session.cookies.get.return_value = "sid=test"
        config = {
            "username": "test", "password": "password",
            "verify": "false",
        }
        with patch.object(inventory.requests, "Session", return_value=session):
            self.assertIs(inventory.login(config, "https://192.0.2.1:8080"), session)
        self.assertEqual(session.cookies.set.call_args.kwargs["domain"], "192.0.2.1")
        self.assertEqual(session.post.call_args.kwargs["data"]["UserName"], "test")
        self.assertFalse(session.post.call_args.kwargs["verify"])
        self.assertFalse(session.get.call_args.kwargs["verify"])

    def test_main_uses_configured_inventory_and_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.txt"
            config = Path(directory) / "config.txt"
            config.write_text(
                f"protocol=https\nip=192.0.2.1\nusername=test\npassword=test\n"
                f"macip={path}\nverify=false\n",
                encoding="utf-8",
            )
            session = Mock()
            session.get.return_value.text = "USERDevice"
            devices = {"001122334455": inventory.Device(
                mac="00:11:22:33:44:55", status="Online"
            )}
            with patch.object(sys, "argv", ["huawei_lan_inventory.py", str(config)]), \
                 patch.object(inventory, "login", return_value=session) as login, \
                 patch.object(inventory, "router_devices", return_value=devices), \
                 patch.object(sys, "stdout"):
                self.assertEqual(inventory.main(), 0)
            self.assertTrue(path.exists())
            self.assertEqual(login.call_args.args[1], "https://192.0.2.1")
            self.assertEqual(session.get.call_args.args[0],
                             "https://192.0.2.1/html/bbsp/common/GetLanUserDevInfo.asp")
            self.assertFalse(session.get.call_args.kwargs["verify"])

    def test_main_requires_config_argument(self):
        with patch.object(sys, "argv", ["huawei_lan_inventory.py"]), \
             patch.object(sys, "stderr"):
            self.assertEqual(inventory.main(), 1)

    def test_main_reports_changed_existing_ips_after_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.txt"
            path.write_text(
                "MAC | IP | Nimi | Oma nimi | Tila | Viimeksi nähty\n"
                "00:11:22:33:44:55 | 192.0.2.5 | router | nimi | Offline | vanha\n"
                "00:11:22:33:44:66 | 192.0.2.6 | router | toinen | Offline | vanha\n",
                encoding="utf-8",
            )
            config = Path(directory) / "config.txt"
            config.write_text(
                f"ip=192.0.2.1\nusername=test\npassword=test\nmacip={path}\n",
                encoding="utf-8",
            )
            session = Mock()
            session.get.return_value.text = "USERDevice"
            devices = {
                "001122334455": inventory.Device(
                    mac="00:11:22:33:44:55", ip="192.0.2.10", status="Online"
                ),
                "001122334466": inventory.Device(
                    mac="00:11:22:33:44:66", ip="--", status="Offline"
                ),
                "001122334477": inventory.Device(
                    mac="00:11:22:33:44:77", ip="192.0.2.20", status="Online"
                ),
            }
            output = io.StringIO()
            standard_output = io.StringIO()
            with patch.object(sys, "argv", ["huawei_lan_inventory.py", str(config)]), \
                 patch.object(inventory, "login", return_value=session), \
                 patch.object(inventory, "router_devices", return_value=devices), \
                 patch.object(sys, "stderr", output), \
                 patch.object(sys, "stdout", standard_output):
                self.assertEqual(inventory.main(), 0)
            self.assertIn("nimi (00:11:22:33:44:55): 192.0.2.5 -> 192.0.2.10",
                          output.getvalue())
            self.assertNotIn("192.0.2.20", output.getvalue())
            self.assertNotIn("toinen (00:11:22:33:44:66)", output.getvalue())
            line = next(line for line in standard_output.getvalue().splitlines()
                        if line.startswith("MACIP_SUMMARY "))
            summary = json.loads(line.removeprefix("MACIP_SUMMARY "))
            self.assertEqual(len(summary["ip_changes"]), 1)
            self.assertEqual(summary["new_devices"][0]["ip"], "192.0.2.20")

    def test_placeholder_names_do_not_replace_existing_name(self):
        for name in ("0", "--", "", "  0  "):
            with self.subTest(name=name):
                old = {"001122334455": inventory.Device(
                    mac="00:11:22:33:44:55", router_name="laite"
                )}
                current = {"001122334455": inventory.Device(
                    mac="00:11:22:33:44:55", router_name=name, status="Online"
                )}
                merged = inventory.merge_inventory(old, current, "nyt")
                self.assertEqual(merged["001122334455"].router_name, "laite")

    def test_router_name_uses_next_valid_candidate(self):
        args = [""] * 17
        args[1], args[2], args[7] = "192.0.2.5", "00:11:22:33:44:55", "Online"
        args[10], args[13], args[14] = "oikea nimi", "--", "0"
        with patch.object(inventory, "extract_constructor_calls",
                          return_value=[("USERDeviceNew", args)]), \
             patch.object(inventory, "js_string", side_effect=lambda value: value):
            devices = inventory.router_devices("")
        self.assertEqual(devices["001122334455"].router_name, "oikea nimi")
        previous = {"001122334455": inventory.Device(
            mac="00:11:22:33:44:55", router_name="vanha"
        )}
        merged = inventory.merge_inventory(previous, devices, "nyt")
        self.assertEqual(merged["001122334455"].router_name, "oikea nimi")

    def test_asus_columns_survive_huawei_update(self):
        source = (
            "MAC | IP | Reitittimen nimi | Oma nimi | Tila | Viimeksi nähty"
            " | Yhteys | Signaali | Tukiasema\n"
            "00:11:22:33:44:55 | 192.0.2.5 | router | nimi | Offline"
            " | vanha | 5 GHz | -65 | 192.0.2.2\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            path.write_text(source, encoding="utf-8")
            old = inventory.read_inventory(path)
            current = {
                "001122334455": inventory.Device(
                    mac="00:11:22:33:44:55", ip="192.0.2.6", status="Online"
                ),
                "aabbccddeeff": inventory.Device(
                    mac="aa:bb:cc:dd:ee:ff", status="Offline"
                ),
            }
            inventory.save_inventory(path, inventory.merge_inventory(old, current, "nyt"))
            loaded = inventory.read_inventory(path)

        updated = loaded["001122334455"]
        self.assertEqual((updated.connection, updated.signal, updated.access_point),
                         ("5 GHz", "-65", "192.0.2.2"))
        self.assertEqual((updated.ip, updated.own_name, updated.last_seen),
                         ("192.0.2.6", "nimi", "nyt"))
        new_device = loaded["aabbccddeeff"]
        self.assertEqual((new_device.connection, new_device.signal, new_device.access_point),
                         ("", "", ""))
        self.assertEqual(new_device.last_seen, "")

    def test_old_six_column_inventory(self):
        source = (
            "MAC | IP | Reitittimen nimi | Oma nimi | Tila | Viimeksi nähty\n"
            "00:11:22:33:44:55 | 192.0.2.5 | router | nimi | Offline | vanha\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            path.write_text(source, encoding="utf-8")
            devices = inventory.read_inventory(path)
            inventory.save_inventory(path, devices)
            output = path.read_text(encoding="utf-8")
            loaded = inventory.read_inventory(path)
        self.assertEqual([item.strip() for item in output.splitlines()[0].split("|")],
                         inventory.HEADERS)
        self.assertEqual(loaded["001122334455"].own_name, "nimi")
        self.assertEqual(loaded["001122334455"].signal, "")


if __name__ == "__main__":
    unittest.main()
