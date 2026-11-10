"""Shared configuration and inventory helpers for the router scripts.

Copyright (c) 2026 vesal.
Developed with assistance from GitHub Copilot.
"""

import ipaddress
import json
from pathlib import Path


def read_config(filename: str | Path) -> dict[str, str]:
    """Read router settings from a key=value file.

    :param filename: Configuration file path.
    :return: Settings with defaults filled in.
    """
    config = {}

    with open(filename, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    config.setdefault("protocol", "http")
    config.setdefault("macip", "macip.txt")
    config.setdefault("verify", "true")
    config.setdefault("router_nickname", "")
    config.setdefault("update_last_seen", "false")
    return config


def get_verify(config: dict[str, str]) -> bool:
    """Determine whether to verify the router's TLS certificate.

    :param config: Router settings.
    :return: True if the certificate should be verified.
    """
    return config["verify"].lower() not in ("false", "0", "no")


def ip_sort_key(ip: str, mac: str) -> tuple[bool, int, int, str]:
    """Create a numeric IP sort key, using MAC addresses to break ties.

    :param ip: IP address to sort.
    :param mac: MAC address used to break ties.
    :return: Sort key placing invalid addresses after valid ones.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True, 0, 0, mac.lower()
    return False, address.version, int(address), mac.lower()


def format_ip_changes(changes: list[tuple[str, str, str, str]]) -> str:
    """Format changes to existing devices' IP addresses.

    :param changes: Tuples of MAC address, device name, old IP and new IP.
    :return: Summary text containing each change, or a no-changes message.
    """
    if not changes:
        return "IP-osoitteet eivät muuttuneet."
    lines = ["Muuttuneet IP-osoitteet:"]
    for mac, name, old_ip, new_ip in changes:
        label = f"{name} ({mac})" if name and name not in ("--", "0") else mac
        lines.append(f"  {label}: {old_ip or '--'} -> {new_ip or '--'}")
    return "\n".join(lines)


def print_update_summary(
    router: str,
    changes: list[tuple[str, str, str, str]],
    new_devices: list[tuple[str, str, str]],
) -> None:
    """Print a machine-readable update summary on a single stdout line.

    :param router: Router name or address.
    :param changes: MAC, name, old IP and new IP for changed devices.
    :param new_devices: MAC, name and IP for newly discovered devices.
    :return: None.
    """
    summary = {
        "router": router,
        "ip_changes": [
            {"mac": mac, "name": name, "old_ip": old_ip, "new_ip": new_ip}
            for mac, name, old_ip, new_ip in changes
        ],
        "new_devices": [
            {"mac": mac, "name": name, "ip": ip}
            for mac, name, ip in new_devices
        ],
    }
    print("MACIP_SUMMARY " + json.dumps(summary, ensure_ascii=True))
