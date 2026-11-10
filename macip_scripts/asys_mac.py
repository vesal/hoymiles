"""Fetch ASUS router devices and update the local inventory.

Copyright (c) 2026 vesal.
Developed with assistance from GitHub Copilot.
"""

import sys
import base64
import requests

from pathlib import Path
from datetime import datetime
from typing import Any

import urllib3
from urllib3.exceptions import InsecureRequestWarning

from macip_common import format_ip_changes, get_verify, ip_sort_key, print_update_summary, read_config


def login(config: dict[str, str]) -> requests.Session | None:
    """Log in to the ASUS router.

    :param config: Connection and login settings.
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

    print("Kirjautuminen onnistui!")
    print("Reititin:", ip)
    print("Protokolla:", protocol)
    print("asus_token saatu.")

    return session


def get_client_list(session: requests.Session, config: dict[str, str]) -> dict[str, Any]:
    """Fetch the device list returned by the ASUS router.

    :param session: Authenticated HTTP session.
    :param config: Router connection settings.
    :return: Router's get_clientlist JSON object.
    """
    ip = config["ip"]
    protocol = config["protocol"].lower()
    base_url = f"{protocol}://{ip}"
    verify = get_verify(config)

    response = session.get(
        base_url + "/appGet.cgi",
        params={"hook": "get_clientlist()"},
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
    clients = data["get_clientlist"]

    return clients


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

    maclist = set(clients.get("maclist", []))
    router_nickname = config.get("router_nickname", "").strip()
    update_last_seen = config.get("update_last_seen", "false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

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

        if is_wireless == "1":
            row["Yhteys"] = "2.4 GHz"
            row["Signaali"] = rssi
            row["Tukiasema"] = router_nickname or router_ip

        elif is_wireless == "2":
            row["Yhteys"] = "5 GHz"
            row["Signaali"] = rssi
            row["Tukiasema"] = router_nickname or router_ip

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
    """Read the command-line configuration file and update the inventory.

    :return: None.
    """
    if len(sys.argv) != 2:
        print("Käyttö: python asys_mac.py secret2.txt")
        sys.exit(1)

    config = read_config(sys.argv[1])

    try:
        session = login(config)

        if not session:
            sys.exit(1)

        clients = get_client_list(session, config)

        print("\nASUS-laitteita:", len(set(
            clients.get("maclist", [])
        )))

        update_macip(clients, config)

    except Exception as e:
        print("\nVirhe:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
