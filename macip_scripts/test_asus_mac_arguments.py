import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import asus_mac


class AsusMacArgumentsTests(unittest.TestCase):
    def test_requested_clients_are_printed_even_when_offline(self):
        config = {"ip": "192.0.2.1"}
        session = MagicMock()
        clients = {
            "maclist": [],
            "AA:BB:CC:DD:EE:FF": {"isOnline": "0", "rssi": "-42"},
            "11:22:33:44:55:66": {"isOnline": "1"},
        }
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", [
            "asus_mac.py", "secret.txt", "aa:bb:cc:dd:ee:ff",
            "11:22:33:44:55:66", "00:00:00:00:00:00",
        ]), \
             patch.object(asus_mac, "read_config", return_value=config), \
             patch.object(asus_mac, "login", return_value=session), \
             patch.object(asus_mac, "get_client_list", return_value=clients), \
             patch.object(asus_mac, "get_router_list", return_value={
                 "AP": {"5G": ["aa:bb:cc:dd:ee:ff", "22:33:44:55:66:77"]},
             }) as wireless, \
             patch.object(asus_mac, "update_macip") as update, \
             patch.object(asus_mac, "logout") as logout, \
             redirect_stdout(output):
            asus_mac.main()

        self.assertIn("192.0.2.1 AA:BB:CC:DD:EE:FF: {'isOnline': '0', 'rssi': '-42'}", output.getvalue())
        self.assertIn("192.0.2.1 11:22:33:44:55:66: {'isOnline': '1'}", output.getvalue())
        self.assertIn("00:00:00:00:00:00: ei löydy", output.getvalue())
        self.assertIn("get_wclientlist: AP 5G", output.getvalue())
        self.assertIn("get_wclientlist: ei listassa", output.getvalue())
        wireless.assert_called_once_with(session, config, "get_wclientlist")
        update.assert_not_called()
        logout.assert_called_once_with(session, config, quiet=True)
        session.__exit__.assert_called_once()
        self.assertNotIn("ASUS-laitteita:", output.getvalue())

    def test_quiet_login_and_logout_keep_errors_visible(self):
        config = {"ip": "192.0.2.1", "protocol": "http", "verify": "true",
                  "username": "user", "password": "password"}
        session = MagicMock()
        session.cookies.get.return_value = None
        session.post.return_value.status_code = 200
        output = io.StringIO()
        with patch.object(asus_mac.requests, "Session", return_value=session), redirect_stdout(output):
            self.assertIsNone(asus_mac.login(config, quiet=True))
        self.assertIn("Kirjautuminen epäonnistui", output.getvalue())
        self.assertNotIn("Alustavat evästeet", output.getvalue())

        session.cookies.get.return_value = "token"
        output = io.StringIO()
        with patch.object(asus_mac.requests, "Session", return_value=session), redirect_stdout(output):
            asus_mac.login(config, quiet=True)
            asus_mac.logout(session, config, quiet=True)
        self.assertEqual(output.getvalue(), "")

    def test_debug_wireless_failure_reports_error_and_logs_out(self):
        config = {"ip": "192.0.2.1"}
        session = MagicMock()
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "secret.txt", ".*"]), \
             patch.object(asus_mac, "read_config", return_value=config), \
             patch.object(asus_mac, "login", return_value=session), \
             patch.object(asus_mac, "get_client_list", return_value={}), \
             patch.object(asus_mac, "get_router_list", side_effect=ValueError("listan haku epäonnistui")), \
             patch.object(asus_mac, "update_macip") as update, \
             patch.object(asus_mac, "logout") as logout, redirect_stdout(output):
            with self.assertRaises(SystemExit):
                asus_mac.main()
        self.assertIn("listan haku epäonnistui", output.getvalue())
        update.assert_not_called()
        logout.assert_called_once_with(session, config, quiet=True)

    def test_without_requested_clients_preserves_normal_output(self):
        config = {"ip": "192.0.2.1"}
        clients = {"maclist": [], "AA:BB:CC:DD:EE:FF": {"isOnline": "0"}}
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "secret.txt"]), \
             patch.object(asus_mac, "read_config", return_value=config), \
             patch.object(asus_mac, "login", return_value=MagicMock()), \
             patch.object(asus_mac, "get_client_list", return_value=clients), \
             patch.object(asus_mac, "get_router_list") as wireless, \
             patch.object(asus_mac, "update_macip") as update, \
             patch.object(asus_mac, "sync_nicknames") as sync, \
             patch.object(asus_mac, "logout"), \
             redirect_stdout(output):
            asus_mac.main()

        self.assertNotIn("AA:BB:CC:DD:EE:FF", output.getvalue())
        wireless.assert_not_called()
        update.assert_called_once_with(clients, config)
        sync.assert_called_once()

    def test_patterns_match_all_clients_and_wireless_only_devices(self):
        output = io.StringIO()
        clients = {"maclist": [], "ClientAPILevel": "5", "AA:BB:CC:DD:EE:FF": {"isOnline": "0"}}
        wireless = {"AP": {"5G": ["11:22:33:44:55:66"]}}
        with redirect_stdout(output):
            asus_mac.print_requested_clients(
                clients, wireless, [asus_mac.re.compile(".*")], "192.0.2.1"
            )
        self.assertIn("AA:BB:CC:DD:EE:FF: {'isOnline': '0'}", output.getvalue())
        self.assertIn("11:22:33:44:55:66: ei löydy get_clientlist-listasta", output.getvalue())
        self.assertIn("get_wclientlist: AP 5G", output.getvalue())
        self.assertNotIn("ClientAPILevel", output.getvalue())
        self.assertNotIn("maclist:", output.getvalue())

    def test_invalid_pattern_fails_before_login(self):
        stderr = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py", "secret.txt", "["]), \
             patch.object(asus_mac, "login") as login, \
             patch.object(asus_mac.sys, "stderr", stderr):
            with self.assertRaises(SystemExit):
                asus_mac.main()
        self.assertIn("Virheellinen MAC-säännöllinen lauseke", stderr.getvalue())
        login.assert_not_called()

    def test_malformed_wireless_list_is_reported(self):
        with self.assertRaises(ValueError):
            asus_mac.print_requested_clients({}, {"AP": {"5G": "bad"}}, [], "192.0.2.1")

    def test_router_list_fetches_requested_hook(self):
        session = MagicMock()
        session.get.return_value.text = "{}"
        session.get.return_value.json.return_value = {"get_wclientlist": {"AP": {"5G": []}}}
        result = asus_mac.get_router_list(
            session, {"ip": "192.0.2.1", "protocol": "http", "verify": "true"}, "get_wclientlist"
        )
        self.assertEqual(result, {"AP": {"5G": []}})
        self.assertEqual(session.get.call_args.kwargs["params"], {"hook": "get_wclientlist()"})

    def test_no_configuration_shows_usage(self):
        output = io.StringIO()
        with patch.object(asus_mac.sys, "argv", ["asus_mac.py"]), redirect_stdout(output):
            with self.assertRaises(SystemExit):
                asus_mac.main()
        self.assertIn("[MAC-säännöllinen-lauseke ...]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
