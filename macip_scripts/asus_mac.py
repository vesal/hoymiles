"""Fetch ASUS router devices and update the local inventory.

Copyright (c) 2026 vesal.
Developed with assistance from GitHub Copilot.
"""

import sys
import base64
import re
import requests

from pathlib import Path
from datetime import datetime
from typing import Any
from urllib.parse import unquote

import urllib3
from urllib3.exceptions import InsecureRequestWarning

from macip_common import format_ip_changes, get_verify, ip_sort_key, print_update_summary, read_config


def login(config: dict[str, str], quiet: bool = False) -> requests.Session | None:
    """Log in to the ASUS router.

    :param config: Connection and login settings.
    :param quiet: Suppress successful connection messages.
    :return: Authenticated session, or None if the token cookie is missing.
    """
    ip = config["ip"]
    username = config["username"]
    password = config["password"]
    protocol = config["protocol"].lower()

    base_url = f"{protocol}://{ip}"
    verify = get_verify(config)

    if not verify:
        urllib3.disable_warnings(InsecureRequestWarning)

    authorization = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")

    session = requests.Session()

    initial = session.get(
        base_url + "/Main_Login.asp",
        timeout=15,
        verify=verify
    )
    initial.raise_for_status()

    if not quiet:
        print("Alustavat evästeet:", list(session.cookies.keys()))

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": base_url + "/Main_Login.asp",
    }

    data = {
        "group_id": "",
        "action_mode": "",
        "action_script": "",
        "action_wait": "5",
        "current_page": "Main_Login.asp",
        "next_page": "index.asp",
        "login_authorization": authorization,
        "login_captcha": "",
    }

    response = session.post(
        base_url + "/login.cgi",
        headers=headers,
        data=data,
        timeout=15,
        verify=verify
    )

    response.raise_for_status()

    token = session.cookies.get("asus_token")

    if not token:
        print("Kirjautuminen epäonnistui: asus_token puuttuu.")
        print("HTTP-status:", response.status_code)
        return None

    if not quiet:
        print("Kirjautuminen onnistui!")
        print("Reititin:", ip)
        print("Protokolla:", protocol)
        print("asus_token saatu.")

    return session


def logout(session: requests.Session, config: dict[str, str], quiet: bool = False) -> None:
    """Log out from the ASUS router using the authenticated session.

    :param session: Authenticated router session.
    :param config: Router connection settings.
    :param quiet: Suppress the successful logout message.
    :return: None; raises a request error if logout fails.
    """
    base_url = f"{config['protocol'].lower()}://{config['ip']}"
    response = session.get(
        base_url + "/Logout.asp",
        headers={"Referer": base_url + "/index.asp"},
        timeout=15,
        verify=get_verify(config),
    )
    response.raise_for_status()
    if not quiet:
        print("Uloskirjautumispyyntö lähetetty.")


def get_router_list(session: requests.Session, config: dict[str, str], hook: str) -> dict[str, Any]:
    """Fetch a named client list from the ASUS router."""
    ip = config["ip"]
    protocol = config["protocol"].lower()
    base_url = f"{protocol}://{ip}"
    verify = get_verify(config)

    response = session.get(
        base_url + "/appGet.cgi",
        params={"hook": f"{hook}()"},
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": base_url + "/index.asp",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        timeout=30,
        verify=verify
    )

    response.raise_for_status()

    if "Main_Login.asp" in response.text:
        raise RuntimeError(
            "ASUS palautti kirjautumissivun API-kutsun sijasta."
        )

    data = response.json()
    clients = data[hook]
    if not isinstance(clients, dict):
        raise ValueError(f"ASUS palautti virheellisen {hook}-listan.")

    return clients


def get_client_list(session: requests.Session, config: dict[str, str]) -> dict[str, Any]:
    """Fetch the device list returned by the ASUS router."""
    return get_router_list(session, config, "get_clientlist")


def print_requested_clients(clients: dict[str, Any], wireless: dict[str, Any],
                            patterns: list[re.Pattern[str]], router_ip: str) -> None:
    """Print matching client details and wireless-list membership."""
    mac_format = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", re.IGNORECASE)
    client_keys = {key.upper(): key for key in clients if mac_format.fullmatch(key)}
    wireless_members: dict[str, list[str]] = {}
    for access_point, bands in wireless.items():
        if not isinstance(bands, dict):
            raise ValueError(f"Virheellinen get_wclientlist-tukiasema: {access_point}")
        for band, macs in bands.items():
            if not isinstance(macs, list) or not all(isinstance(mac, str) for mac in macs):
                raise ValueError(f"Virheellinen get_wclientlist-taajuus: {access_point} {band}")
            for mac in macs:
                wireless_members.setdefault(mac.upper(), []).append(f"{access_point} {band}")

    all_macs = sorted(set(client_keys) | set(wireless_members))
    for pattern in patterns:
        matches = [mac for mac in all_macs if pattern.fullmatch(mac)]
        if not matches:
            print(f"\n{pattern.pattern}: ei löydy reitittimen {router_ip} tiedoista")
        for mac in matches:
            key = client_keys.get(mac)
            if key is None:
                print(f"\n{router_ip} {mac}: ei löydy get_clientlist-listasta")
            else:
                print(f"\n{router_ip} {key}: {clients[key]}")
            memberships = wireless_members.get(mac, [])
            print("get_wclientlist:", ", ".join(memberships) if memberships else "ei listassa")


def get_custom_clientlist(session: requests.Session, config: dict[str, str]) -> str:
    """Read the complete ASUS nickname configuration."""
    base_url = f"{config['protocol'].lower()}://{config['ip']}"
    response = session.get(
        base_url + "/appGet.cgi",
        params={"hook": "nvram_char_to_ascii(custom_clientlist,custom_clientlist)"},
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": base_url + "/index.asp",
                 "Cache-Control": "no-cache", "Pragma": "no-cache"},
        timeout=30, verify=get_verify(config),
    )
    response.raise_for_status()
    if "Main_Login.asp" in response.text:
        raise RuntimeError("ASUS palautti kirjautumissivun nimilistan sijasta.")
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("custom_clientlist"), str):
        raise ValueError("ASUS palautti virheellisen custom_clientlist-asetuksen.")
    value = data["custom_clientlist"]
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("ASUS palautti virheellisesti koodatun custom_clientlist-asetuksen.")
    return unquote(value, encoding="utf-8", errors="strict").replace("&#62", ">").replace("&#60", "<")


def build_custom_clientlist(raw: str, clients: dict[str, Any],
                            rows: dict[str, dict[str, str]]) -> tuple[str, int]:
    """Merge inventory names into the router's complete nickname list."""
    mac_format = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", re.IGNORECASE)
    if raw and not raw.startswith("<"):
        raise ValueError("ASUSin custom_clientlist on odottamattomassa muodossa.")
    entries = raw.split("<")[1:] if raw else []
    positions: dict[str, int] = {}
    for index, entry in enumerate(entries):
        fields = entry.split(">")
        if len(fields) < 6 or not mac_format.fullmatch(fields[1]):
            raise ValueError("ASUSin custom_clientlist sisältää virheellisen rivin.")
        mac = fields[1].lower()
        if mac in positions:
            raise ValueError(f"ASUSin custom_clientlist sisältää saman MAC-osoitteen kahdesti: {mac}")
        positions[mac] = index

    changes = 0
    for key, device in clients.items():
        if not mac_format.fullmatch(key) or not isinstance(device, dict):
            continue
        mac = key.lower()
        name = rows.get(mac, {}).get("Oma nimi", "").strip()
        if not name or name in ("--", "0"):
            continue
        if any(char in name for char in "<>\r\n") or any(ord(char) < 32 for char in name):
            raise ValueError(f"Nimeä ei voi tallentaa ASUSiin ({mac}): nimi sisältää kiellettyjä merkkejä.")
        if mac in positions:
            index = positions[mac]
            fields = entries[index].split(">")
            if fields[0] == name:
                continue
            fields[0] = name
            entries[index] = ">".join(fields)
        else:
            device_type = str(device.get("type", "0"))
            if not device_type.isdecimal():
                raise ValueError(f"ASUSin laitetyyppi on virheellinen: {mac}")
            entries.append(">".join((name, key.upper(), "0", device_type, "", "")))
            positions[mac] = len(entries) - 1
        changes += 1
    return "".join("<" + entry for entry in entries), changes


def sync_nicknames(session: requests.Session, config: dict[str, str],
                   clients: dict[str, Any]) -> None:
    """Synchronize local names after the inventory has been saved."""
    _, _, rows = read_macip(config["macip"])
    original = get_custom_clientlist(session, config)
    updated, count = build_custom_clientlist(original, clients, rows)
    if not count:
        print("ASUS-nimien synkronointi: ei muutoksia.")
        return
    # if get_custom_clientlist(session, config) != original:
    #    raise RuntimeError("ASUSin nimilista muuttui synkronoinnin aikana; kirjoitus peruttu.")
    base_url = f"{config['protocol'].lower()}://{config['ip']}"
    response = session.post(
        base_url + "/start_apply2.htm",
        headers={"Referer": base_url + "/index.asp"},
        data={"modified": "0", "flag": "background", "action_mode": "apply",
              "action_script": "saveNvram", "action_wait": "1",
              "custom_clientlist": updated},
        timeout=30, verify=get_verify(config),
    )
    response.raise_for_status()
    # if "Main_Login.asp" in response.text:
    #    raise RuntimeError("ASUS palautti kirjautumissivun nimien tallennuksessa.")
    if get_custom_clientlist(session, config) != updated:
        raise RuntimeError("ASUSin tallentamaa nimilistaa ei voitu varmistaa.")
    print(f"ASUS-nimien synkronointi: {count} muutosta.")


def read_macip(filename: str | Path) -> tuple[Path, list[str], dict[str, dict[str, str]]]:
    """Read the MAC inventory and add any missing column headers.

    :param filename: Inventory file path.
    :return: File path, headers and rows keyed by MAC address.
    """
    path = Path(filename)

    required = [
        "MAC",
        "IP",
        "Nimi",
        "Oma nimi",
        "Tila",
        "Viimeksi nähty",
        "Yhteys",
        "Signaali",
        "Tukiasema",
    ]

    if not path.exists():
        print("MAC-tiedostoa ei löydy. Luodaan uusi:", path.resolve())
        return path, required, {}

    with open(path, encoding="utf-8-sig") as f:
        lines = [line.rstrip("\r\n") for line in f]

    if not lines:
        return path, required, {}

    headers = [x.strip() for x in lines[0].split("|")]

    for column in required:
        if column not in headers:
            headers.append(column)

    rows = {}

    for line in lines[1:]:
        if not line.strip():
            continue

        values = [x.strip() for x in line.split("|")]
        values += [""] * (len(headers) - len(values))

        row = dict(zip(headers, values))
        mac = row["MAC"].lower()

        if mac:
            row["MAC"] = mac
            rows[mac] = row

    return path, headers, rows


def save_macip(path: Path, headers: list[str], rows: dict[str, dict[str, str]]) -> None:
    """Save the inventory sorted by IP address.

    :param path: Destination file path.
    :param headers: Column headers in their output order.
    :param rows: Rows to save, keyed by MAC address.
    :return: None.
    """
    all_rows = [dict(zip(headers, headers))]

    all_rows.extend(sorted(
        rows.values(), key=lambda row: ip_sort_key(row.get("IP", ""), row.get("MAC", ""))
    ))

    widths = {}

    for header in headers:
        widths[header] = max(
            len(header),
            max(
                (len(str(row.get(header, ""))) for row in all_rows),
                default=0
            )
        )

    with open(path, "w", encoding="utf-8") as f:

        for index, row in enumerate(all_rows):
            values = [
                str(row.get(header, ""))
                for header in headers
            ]

            line = " | ".join(
                value.ljust(widths[header])
                for header, value in zip(headers, values)
            )

            f.write(line.rstrip() + "\n")

    print("\nMAC-tiedosto tallennettu:", path.resolve())


def update_macip(clients: dict[str, Any], config: dict[str, str]) -> None:
    """Update active ASUS devices in the inventory file.

    :param clients: Device list returned by the router.
    :param config: Router and inventory file settings.
    :return: None.
    """
    path, headers, rows = read_macip(config["macip"])

    now = datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    router_ip = config["ip"]

    updated = 0
    added = 0
    ignored = 0
    ip_changes: list[tuple[str, str, str, str]] = []
    new_devices: list[tuple[str, str, str]] = []

    maclist_value = clients.get("maclist")
    if not isinstance(maclist_value, list) or not all(
        isinstance(mac, str) for mac in maclist_value
    ):
        raise ValueError("ASUS palautti virheellisen tai puuttuvan maclist-listan.")
    maclist = set(maclist_value)
    router_nickname = config.get("router_nickname", "").strip()
    access_point = router_nickname or router_ip
    update_last_seen = config.get("update_last_seen", "false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

    for row in rows.values():
        if row.get("Tukiasema", "") == access_point:
            row["Yhteys"] = ""
            row["Signaali"] = ""
            row["Tukiasema"] = ""

    for source_mac in sorted(maclist):

        # Look up the device using the router's original MAC address casing.
        device = clients.get(source_mac)

        if not isinstance(device, dict) or not device:
            continue

        # Store MAC addresses in lowercase.
        mac = source_mac.lower()

        online = str(device.get("isOnline", "0")) == "1"

        if not online:
            ignored += 1
            continue

        is_wireless = str(device.get("isWL", "0"))
        rssi = str(device.get("rssi", ""))
        try:
            signal = int(rssi)
        except ValueError:
            if rssi:
                print(f"Virheellinen signaali laitteella {source_mac}: {rssi}", file=sys.stderr)
            signal = 0
        pap_mac = device.get("amesh_papMac")

        is_new = mac not in rows
        if is_new:
            rows[mac] = {
                header: ""
                for header in headers
            }

            rows[mac]["MAC"] = mac
            added += 1

        row = rows[mac]

        previous_ip = row.get("IP", "")
        row["IP"] = str(device.get("ip", ""))

        router_name = str(device.get("name", "")).strip()

        if router_name and router_name != "0":
            row["Nimi"] = router_name

        if is_new or previous_ip != row["IP"]:
            name = row.get("Oma nimi", "")
            if not name or name in ("--", "0"):
                name = row.get("Nimi", "")
            if is_new:
                new_devices.append((mac, name, row["IP"]))
            else:
                ip_changes.append((mac, name, previous_ip, row["IP"]))

        row["Tila"] = "Online"
        if update_last_seen:
            row["Viimeksi nähty"] = now

        if (is_wireless in ("1", "2") and isinstance(pap_mac, str)
                and pap_mac.strip() and signal < 0):
            row["Yhteys"] = "2.4 GHz" if is_wireless == "1" else "5 GHz"
            row["Signaali"] = rssi
            row["Tukiasema"] = access_point

        updated += 1

    save_macip(path, headers, rows)

    print("\nPäivityksen yhteenveto")
    print("-" * 40)
    print("Reititin:", router_ip)
    print("Aktiivisia päivitetty:", updated)
    print("Uusia MAC-osoitteita:", added)
    print("Passiivisia ohitettu:", ignored)
    print("MAC-osoitteita tiedostossa:", len(rows))
    print(format_ip_changes(ip_changes))
    print_update_summary(router_nickname or router_ip, ip_changes, new_devices)


def main() -> None:
    """Print requested clients, or update the inventory when none are requested.

    :return: None.
    """
    if len(sys.argv) < 2:
        print(f"Käyttö: python {Path(sys.argv[0]).name} secret2.txt [MAC-säännöllinen-lauseke ...]")
        sys.exit(1)

    try:
        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in sys.argv[2:]]
    except re.error as error:
        print(f"Virheellinen MAC-säännöllinen lauseke: {error}", file=sys.stderr)
        sys.exit(1)

    config = read_config(sys.argv[1])

    try:
        session = login(config, quiet=True) if patterns else login(config)

        if not session:
            sys.exit(1)

        with session:
            try:
                clients = get_client_list(session, config)

                if patterns:
                    wireless = get_router_list(session, config, "get_wclientlist")
                    print_requested_clients(clients, wireless, patterns, config["ip"])
                else:
                    print("\nASUS-laitteita:", len(set(
                        clients.get("maclist", [])
                    )))

                    update_macip(clients, config)
                    sync_setting = config.get("sync_nicknames", "true").strip().lower()
                    if sync_setting not in ("true", "1", "yes", "on", "false", "0", "no", "off"):
                        raise ValueError("Virheellinen sync_nicknames-asetus.")
                    if sync_setting in ("true", "1", "yes", "on"):
                        sync_nicknames(session, config, clients)
            finally:
                pending_error = sys.exc_info()[0] is not None
                try:
                    if patterns:
                        logout(session, config, quiet=True)
                    else:
                        logout(session, config)
                except requests.RequestException as error:
                    print(f"Uloskirjautuminen epäonnistui: {error}", file=sys.stderr)
                    if not pending_error:
                        raise

    except Exception as e:
        print("\nVirhe:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
