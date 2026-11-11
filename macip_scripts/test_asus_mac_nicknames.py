import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from urllib.parse import quote

import requests
import asus_mac


class AsusNicknameTests(unittest.TestCase):
    def setUp(self):
        self.mac = "AA:BB:CC:DD:EE:FF"
        self.other = "11:22:33:44:55:66"
        self.clients = {self.mac: {"type": "2", "isOnline": "0"},
                        self.other: {"type": "0", "isOnline": "1"}, "maclist": [self.other]}
        self.rows = {self.mac.lower(): {"Oma nimi": "Päivin laite"},
                     self.other.lower(): {"Oma nimi": "Uusi"}}
        self.original = f"<Vanha>{self.mac}>7>2>callback>keep>extra<Untouched>00:00:00:00:00:01>0>0>>"

    def test_merge_preserves_other_fields_and_adds_offline_or_online_clients(self):
        result, count = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
        self.assertEqual(count, 2)
        self.assertEqual(result, f"<Päivin laite>{self.mac}>7>2>callback>keep>extra"
                                 f"<Untouched>00:00:00:00:00:01>0>0>>"
                                 f"<Uusi>{self.other}>0>0>>")
        self.assertEqual(asus_mac.build_custom_clientlist(result, self.clients, self.rows), (result, 0))

    def test_invalid_or_duplicate_entries_and_names_rejected(self):
        for raw in ("broken", "<bad", self.original + f"<duplicate>{self.mac}>0>0>>"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                asus_mac.build_custom_clientlist(raw, self.clients, self.rows)
        self.rows[self.mac.lower()]["Oma nimi"] = "Bad<name"
        with self.assertRaises(ValueError):
            asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)

    def test_missing_empty_and_placeholder_names_do_not_replace_router_names(self):
        for name in ("", "  ", "--", "0"):
            with self.subTest(name=name):
                self.rows[self.mac.lower()]["Oma nimi"] = name
                result, count = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
                self.assertIn(f"<Vanha>{self.mac}>7>2>callback>keep>extra", result)
                self.assertEqual(count, 1)

    def test_read_custom_list_decodes_utf8_and_rejects_bad_response(self):
        session = MagicMock()
        response = session.get.return_value
        response.text = "{}"
        response.json.return_value = {"custom_clientlist": quote(self.original, safe="")}
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "true"}
        self.assertEqual(asus_mac.get_custom_clientlist(session, config), self.original)
        self.assertEqual(session.get.call_args.kwargs["params"]["hook"],
                         "nvram_char_to_ascii(custom_clientlist,custom_clientlist)")
        response.json.return_value = {"custom_clientlist": "%ZZ"}
        with self.assertRaises(ValueError):
            asus_mac.get_custom_clientlist(session, config)
        response.json.return_value = {}
        with self.assertRaises(ValueError):
            asus_mac.get_custom_clientlist(session, config)

    def test_sync_posts_only_changes_and_verifies(self):
        updated, _ = asus_mac.build_custom_clientlist(self.original, self.clients, self.rows)
        session = MagicMock()
        session.post.return_value.text = ""
        config = {"protocol": "http", "ip": "192.0.2.1", "verify": "true", "macip": "file"}
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], self.rows)), \
             patch.object(asus_mac, "get_custom_clientlist", side_effect=[self.original, self.original, updated]), \
             redirect_stdout(io.StringIO()):
            asus_mac.sync_nicknames(session, config, self.clients)
        self.assertEqual(session.post.call_args.args[0], "http://192.0.2.1/start_apply2.htm")
        self.assertEqual(session.post.call_args.kwargs["data"]["custom_clientlist"], updated)
        self.assertEqual(session.post.call_args.kwargs["data"]["action_script"], "saveNvram")

    def test_sync_no_changes_or_concurrent_change_never_posts(self):
        session = MagicMock()
        config = {"macip": "file"}
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], {})), \
             patch.object(asus_mac, "get_custom_clientlist", return_value=self.original), \
             redirect_stdout(io.StringIO()):
            asus_mac.sync_nicknames(session, config, self.clients)
        session.post.assert_not_called()
        with patch.object(asus_mac, "read_macip", return_value=(Path("file"), [], self.rows)), \
             patch.object(asus_mac, "get_custom_clientlist", side_effect=[self.original, self.original + "<changed"]):
            with self.assertRaises(RuntimeError):
                asus_mac.sync_nicknames(session, config, self.clients)
        session.post.assert_not_called()

    def test_main_saves_before_sync_and_failure_is_reported(self):
        config = {"ip": "192.0.2.1"}
        session = MagicMock()
        order = MagicMock()
        order.sync.side_effect = requests.ConnectionError("sync failed")
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "config"]), \
             patch.object(asus_mac, "read_config", return_value=config), \
             patch.object(asus_mac, "login", return_value=session), \
             patch.object(asus_mac, "get_client_list", return_value={"maclist": []}), \
             patch.object(asus_mac, "update_macip", order.update), \
             patch.object(asus_mac, "sync_nicknames", order.sync), \
             patch.object(asus_mac, "logout") as logout, redirect_stdout(output):
            with self.assertRaises(SystemExit):
                asus_mac.main()
        self.assertEqual(order.mock_calls, [call.update({"maclist": []}, config),
                                            call.sync(session, config, {"maclist": []})])
        self.assertIn("sync failed", output.getvalue())
        logout.assert_called_once()

    def test_opt_out_and_debug_do_not_synchronize(self):
        for argv, config in [
            (["asus_mac.py", "config"], {"ip": "192.0.2.1", "sync_nicknames": "false"}),
            (["asus_mac.py", "config", ".*"], {"ip": "192.0.2.1"}),
        ]:
            with self.subTest(argv=argv), \
                 patch.object(asus_mac.sys, "argv", argv), \
                 patch.object(asus_mac, "read_config", return_value=config), \
                 patch.object(asus_mac, "login", return_value=MagicMock()), \
                 patch.object(asus_mac, "get_client_list", return_value={"maclist": []}), \
                 patch.object(asus_mac, "get_router_list", return_value={}), \
                 patch.object(asus_mac, "update_macip"), \
                 patch.object(asus_mac, "sync_nicknames") as sync, \
                 patch.object(asus_mac, "logout"), redirect_stdout(io.StringIO()):
                asus_mac.main()
                sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
