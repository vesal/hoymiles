import tempfile
import unittest
from pathlib import Path

import macip_common
from macip_scripts import asys_mac, huawei_lan_inventory


class SharedInventoryTests(unittest.TestCase):
    def test_both_scripts_use_same_config_and_verify_helpers(self):
        self.assertIs(asys_mac.read_config, macip_common.read_config)
        self.assertIs(huawei_lan_inventory.read_config, macip_common.read_config)
        self.assertIs(asys_mac.get_verify, huawei_lan_inventory.get_verify)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.txt"
            path.write_text("ip=192.0.2.1\npassword=a=b\nverify=no\n", encoding="utf-8")
            config = macip_common.read_config(path)
        self.assertEqual(config["password"], "a=b")
        self.assertEqual(config["macip"], "macip.txt")
        self.assertFalse(macip_common.get_verify(config))

    def test_both_inventories_use_same_numeric_ip_order(self):
        entries = [
            ("00:00:00:00:00:05", "--"),
            ("00:00:00:00:00:04", "2001:db8::1"),
            ("00:00:00:00:00:03", "192.0.2.123"),
            ("00:00:00:00:00:02", "192.0.2.25"),
            ("00:00:00:00:00:01", "192.0.2.25"),
            ("00:00:00:00:00:06", ""),
        ]
        rows = {mac: {"MAC": mac, "IP": ip} for mac, ip in entries}
        devices = {
            mac: huawei_lan_inventory.Device(mac=mac, ip=ip)
            for mac, ip in entries
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "macip.txt"
            asys_mac.save_macip(path, ["MAC", "IP"], rows)
            asus_lines = path.read_text(encoding="utf-8").splitlines()[1:]
        huawei_lines = huawei_lan_inventory.format_inventory(devices).splitlines()[1:]
        asus_order = [line.split("|")[0].strip() for line in asus_lines]
        huawei_order = [line.split("|")[0].strip() for line in huawei_lines]
        expected = [entries[i][0] for i in (4, 3, 2, 1, 0, 5)]
        self.assertEqual(asus_order, expected)
        self.assertEqual(huawei_order, expected)


if __name__ == "__main__":
    unittest.main()
