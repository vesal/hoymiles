#!/usr/bin/env python3
"""Fetch Huawei router devices and merge them into the local inventory.

Copyright (c) 2026 vesal.
Developed with assistance from GitHub Copilot.
"""

import base64
import ipaddress
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from collections.abc import Iterator

import requests

from macip_common import format_ip_changes, get_verify, ip_sort_key, print_update_summary, read_config

HEADERS = [
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


@dataclass
class Device:
    """Represent one device in the inventory.

    :param mac: Device MAC address.
    :param ip: Device IP address.
    :param router_name: Device name reported by the router.
    :param own_name: User-provided device name.
    :param status: Device status reported by the router.
    :param last_seen: Time the device was last seen.
    :param connection: Connection type or frequency.
    :param signal: Wireless signal strength.
    :param access_point: Access point name or IP address.
    """

    mac: str
    ip: str = "--"
    router_name: str = "--"
    own_name: str = ""
    status: str = "--"
    last_seen: str = ""
    connection: str = ""
    signal: str = ""
    access_point: str = ""


def normalize_mac(value: str) -> str:
    """Remove separators from a MAC address.

    :param value: MAC address.
    :return: Lowercase address without separators.
    """
    return re.sub(r"[^0-9a-f]", "", value.lower())


def valid_mac(value: str) -> bool:
    """Check the length and hexadecimal digits of a MAC address.

    :param value: Address to check.
    :return: True if the normalized address is valid.
    """
    return bool(re.fullmatch(r"[0-9a-f]{12}", normalize_mac(value)))


def valid_ip(value: str) -> bool:
    """Check an IP address.

    :param value: Address to check.
    :return: True if the address is a valid IPv4 or IPv6 address.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def format_mac(value: str) -> str:
    """Format a MAC address with colon separators.

    :param value: MAC address to normalize.
    :return: Formatted address.
    """
    mac = normalize_mac(value)
    return ":".join(mac[i:i + 2] for i in range(0, 12, 2))


def valid_router_name(value: str) -> bool:
    """Check that a name is neither empty nor an unknown-value placeholder.

    :param value: Name to check.
    :return: True if the name can be used.
    """
    return value.strip() not in ("", "0", "--")


def router_url(config: dict[str, str]) -> str:
    """Build and validate the router URL from its configuration.

    :param config: Router connection settings.
    :return: Router URL without a trailing slash.
    """
    protocol = config["protocol"].lower()
    address = config["ip"]
    if protocol not in ("http", "https") or not address:
        raise ValueError("Aseta reitittimen ip sekä protocol=http tai https.")
    url = f"{protocol}://{address}".rstrip("/")
    parsed = urlsplit(url)
    if not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Reitittimen ip-asetus ei ole kelvollinen osoite.")
    return url


def login(config: dict[str, str], router: str) -> requests.Session:
    """Log in to the Huawei router.

    :param config: Router connection and login settings.
    :param router: Router base URL.
    :return: Authenticated HTTP session.
    """
    session = requests.Session()
    verify = get_verify(config)
    router_ip = urlsplit(router).hostname

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
    })

    response = session.get(router + "/", timeout=15, verify=verify)
    response.raise_for_status()

    session.cookies.set(
        "Cookie",
        "body:Language:english:id=-1",
        domain=router_ip,
        path="/",
    )

    response = session.post(
        router + "/asp/GetRandCount.asp",
        headers={
            "Referer": router + "/",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=15,
        verify=verify,
    )
    response.raise_for_status()

    token = response.text.lstrip("\ufeff").strip()

    if not token:
        raise RuntimeError("Huawei ei palauttanut kirjautumistokenia.")

    payload = {
        "UserName": config["username"],
        "PassWord": base64.b64encode(
            config["password"].encode("utf-8")
        ).decode("ascii"),
        "Language": "english",
        "x.X_HW_Token": token,
    }

    response = session.post(
        router + "/login.cgi",
        data=payload,
        headers={
            "Referer": router + "/",
            "Origin": router,
        },
        timeout=15,
        verify=verify,
    )
    response.raise_for_status()

    cookie = session.cookies.get("Cookie", "")

    if "sid=" not in cookie:
        raise RuntimeError("Huawei-kirjautuminen epäonnistui.")

    response = session.get(router + "/index.asp", timeout=15, verify=verify)
    response.raise_for_status()

    if "Waiting..." in response.text:
        raise RuntimeError("Huawei palautti kirjautumisen jälkeen Waiting-sivun.")

    return session


def split_js_arguments(text: str) -> list[str]:
    """Split JavaScript function arguments at commas outside quotes.

    :param text: Function argument text.
    :return: Arguments in their original order.
    """

    result = []
    start = 0
    quote = None
    escaped = False

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None

        elif char in ("'", '"'):
            quote = char

        elif char == ",":
            result.append(text[start:index].strip())
            start = index + 1

    result.append(text[start:].strip())

    return result


def js_string(value: str) -> str:
    """Remove JavaScript string quotes and decode supported escapes.

    :param value: JavaScript value as text.
    :return: Decoded value.
    """
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]

    value = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda m: chr(int(m.group(1), 16)),
        value
    )

    value = value.replace(r"\'", "'").replace(r'\"', '"')
    value = value.replace(r"\\", "\\")

    return value


def extract_constructor_calls(source: str) -> Iterator[tuple[str, list[str]]]:
    """Find constructor calls in the Huawei device list.

    :param source: JavaScript source returned by the router.
    :return: Constructor name and arguments for each call.
    """
    pattern = re.compile(
        r"\bnew\s+(USERDeviceNew|USERDevice)\s*\("
    )

    for match in pattern.finditer(source):
        constructor = match.group(1)

        pos = match.end()
        start = pos
        depth = 1
        quote = None
        escaped = False

        while pos < len(source) and depth:
            char = source[pos]

            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None

            else:
                if char in ("'", '"'):
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1

            pos += 1

        if depth == 0:
            arguments = source[start:pos - 1]
            args = [
                js_string(x)
                for x in split_js_arguments(arguments)
            ]

            yield constructor, args


def router_devices(source: str) -> dict[str, Device]:
    """Extract devices from the source returned by the router.

    :param source: JavaScript source returned by the router.
    :return: Devices keyed by normalized MAC address.
    """
    devices = {}

    for constructor, args in extract_constructor_calls(source):
        args = [js_string(value) for value in args]

        if constructor == "USERDeviceNew":
            if len(args) < 17:
                continue

            ip = args[1]
            mac = args[2]
            status = args[7]
            hostname = args[10]
            device_type = args[13]
            alias = args[14]

        else:
            if len(args) < 16:
                continue

            ip = args[1]
            mac = args[2]
            status = args[6]
            hostname = args[9]
            device_type = args[12]
            alias = args[13]

        if not valid_mac(mac):
            continue

        router_name = next(
            (
                name.strip()
                for name in (alias, hostname, device_type)
                if valid_router_name(name)
            ),
            "--",
        )

        mac_key = normalize_mac(mac)

        devices[mac_key] = Device(
            mac=format_mac(mac),
            ip=ip.strip() if valid_ip(ip.strip()) else "--",
            router_name=router_name,
            status=status.strip() or "Tuntematon",
        )

    return devices


def detect_separator(line: str) -> str | None:
    """Identify the inventory's column separator.

    :param line: Header or data row to inspect.
    :return: Separator, or None if no separator is found.
    """
    if "|" in line:
        return "|"

    if ";" in line:
        return ";"

    return None


def read_inventory(path: Path) -> dict[str, Device]:
    """Read the device inventory from a file.

    :param path: Inventory file path.
    :return: Devices keyed by normalized MAC address.
    """
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]

    if not lines:
        return {}

    separator = detect_separator(lines[0])

    if separator is None:
        raise RuntimeError("macip.txt-tiedostosta ei löydy erotinmerkkiä.")

    inventory = {}
    extra_columns: dict[str, int] = {}

    for line_number, line in enumerate(lines):

        parts = [
            part.strip()
            for part in line.split(separator)
        ]

        if line_number == 0 and parts[0].lower() == "mac":
            extra_columns = {
                name: parts.index(name)
                for name in ("Yhteys", "Signaali", "Tukiasema")
                if name in parts
            }
            continue

        if len(parts) < 6:
            print(
                f"Varoitus: virheellinen rivi {line_number + 1}",
                file=sys.stderr,
            )
            continue

        mac, ip, router_name, own_name, status, last_seen = parts[:6]

        if not valid_mac(mac):
            print(
                f"Varoitus: virheellinen MAC rivillä {line_number + 1}",
                file=sys.stderr,
            )
            continue

        key = normalize_mac(mac)

        def extra_value(name: str) -> str:
            """Return an optional column's value from the current row.

            :param name: Column header.
            :return: Column value or an empty string.
            """
            index = extra_columns.get(name)
            if index is None or index >= len(parts):
                return ""
            return parts[index]

        inventory[key] = Device(
            mac=format_mac(mac),
            ip=ip or "--",
            router_name=router_name or "--",
            own_name=own_name or "--",
            status=status or "--",
            last_seen=last_seen,
            connection=extra_value("Yhteys"),
            signal=extra_value("Signaali"),
            access_point=extra_value("Tukiasema"),
        )

    return inventory


def merge_inventory(
    old: dict[str, Device], current: dict[str, Device], now: str
) -> dict[str, Device]:
    """Merge router observations into the previous inventory.

    Existing device objects are also updated in place.

    :param old: Previous devices keyed by normalized MAC address.
    :param current: Router devices keyed in the same format.
    :param now: New last-seen timestamp for online devices.
    :return: Merged device inventory.
    """
    merged = dict(old)

    # Mark existing devices as not observed before applying router results.
    for device in merged.values():
        device.status = "--"

    # Update devices reported by the router.
    for mac, found in current.items():

        if mac in merged:
            previous = merged[mac]

            if found.ip != "--":
                previous.ip = found.ip

            if valid_router_name(found.router_name):
                previous.router_name = found.router_name

            previous.status = found.status
            if found.status.casefold() == "online":
                previous.last_seen = now

        else:
            if found.status.casefold() == "online":
                found.last_seen = now
            merged[mac] = found

    return merged


def format_inventory(devices: dict[str, Device]) -> str:
    """Format devices in columns sorted by IP address.

    :param devices: Devices to format.
    :return: Inventory text suitable for saving to a file.
    """
    rows = [
        [
            device.mac,
            device.ip,
            device.router_name,
            device.own_name,
            device.status,
            device.last_seen,
            device.connection,
            device.signal,
            device.access_point,
        ]
        for device in sorted(
            devices.values(),
            key=lambda device: ip_sort_key(device.ip, device.mac)
        )
    ]

    widths = [
        max(
            len(HEADERS[i]),
            max((len(row[i]) for row in rows), default=0),
        )
        for i in range(len(HEADERS))
    ]

    lines = [" | ".join(
        HEADERS[i].ljust(widths[i])
        for i in range(len(HEADERS))
    )]

    for row in rows:
        lines.append(
            " | ".join(
                row[i].ljust(widths[i])
                for i in range(len(HEADERS))
            )
        )

    return "\n".join(lines) + "\n"


def save_inventory(path: Path, devices: dict[str, Device]) -> None:
    """Save the inventory using a temporary file.

    :param path: Destination file path.
    :param devices: Devices to save.
    :return: None.
    """
    content = format_inventory(devices)

    temporary = path.with_suffix(".txt.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    """Read the command-line configuration and update the device inventory.

    :return: Zero on success, otherwise one.
    """
    if len(sys.argv) != 2:
        print("Käyttö: python huawei_lan_inventory.py huawei_secret.txt", file=sys.stderr)
        return 1

    try:
        config = read_config(sys.argv[1])
        router = router_url(config)
        inventory_file = Path(config["macip"])

        print("Kirjaudutaan Huawei-reitittimeen...", file=sys.stderr)

        session = login(config, router)

        print("Haetaan laiteluetteloa...", file=sys.stderr)

        response = session.get(
            router + "/html/bbsp/common/GetLanUserDevInfo.asp",
            timeout=30,
            verify=get_verify(config),
        )
        response.raise_for_status()

        source = response.text.lstrip("\ufeff")

        if "USERDevice" not in source:
            raise RuntimeError(
                "Huawei ei palauttanut tunnistettavaa laiteluetteloa."
            )

        current = router_devices(source)

        print(
            f"Reitittimeltä löytyi {len(current)} laitetta.",
            file=sys.stderr,
        )

        if not current:
            raise RuntimeError(
                "Laiteluettelosta ei löytynyt yhtään kelvollista MAC-osoitetta."
            )

        old = read_inventory(inventory_file)
        previous_ips = {mac: device.ip for mac, device in old.items()}

        now = datetime.now().astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        merged = merge_inventory(old, current, now)

        save_inventory(inventory_file, merged)

        ip_changes: list[tuple[str, str, str, str]] = []
        for mac, old_ip in previous_ips.items():
            device = merged[mac]
            if old_ip != device.ip:
                name = device.own_name if valid_router_name(device.own_name) else device.router_name
                ip_changes.append((device.mac, name, old_ip, device.ip))
        print(format_ip_changes(ip_changes), file=sys.stderr)
        new_devices = []
        for mac, device in merged.items():
            if mac not in previous_ips:
                name = device.own_name if valid_router_name(device.own_name) else device.router_name
                new_devices.append((device.mac, name, device.ip))
        print_update_summary(router, ip_changes, new_devices)

        # Write the inventory itself to stdout.
        # sys.stdout.write(format_inventory(merged))

        print(
            f"Tallennettu {len(merged)} laitetta tiedostoon "
            f"{inventory_file}",
            file=sys.stderr,
        )

        return 0

    except requests.RequestException as error:
        print(f"Verkkovirhe: {error}", file=sys.stderr)
        return 1

    except Exception as error:
        print(f"Virhe: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
