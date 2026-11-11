"""Authenticated inventory and router update API for Home Assistant."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

MAX_CONTENT_SIZE = 1_000_000
EXPECTED_HEADERS = ["MAC", "IP", "Nimi", "Oma nimi", "Tila", "Viimeksi nähty"]
EXTENDED_HEADERS = EXPECTED_HEADERS + ["Yhteys", "Signaali", "Tukiasema"]


def validate_content(content: str) -> None:
    """Validate the inventory format.

    :param content: Inventory text.
    :return: None; raises ValueError for invalid content.
    """
    if len(content.encode("utf-8")) > MAX_CONTENT_SIZE:
        raise ValueError("macip.txt ylittää sallitun kokorajan.")
    if "\x00" in content:
        raise ValueError("macip.txt sisältää virheellisiä ohjausmerkkejä.")
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError("macip.txt ei voi olla tyhjä.")
    headers = [part.strip() for part in lines[0].split("|")]
    if headers not in (EXPECTED_HEADERS, EXTENDED_HEADERS):
        raise ValueError("macip.txt:n otsikot eivät vastaa odotettua muotoa.")
    for line_number, line in enumerate(lines[1:], start=2):
        if len(line.split("|")) != len(headers):
            raise ValueError(f"macip.txt:n rivillä {line_number} on virheellinen määrä sarakkeita.")


def _read_inventory(path: Path) -> dict[str, str]:
    content = path.read_bytes()
    return {"content": content.decode("utf-8-sig"), "revision": hashlib.sha256(content).hexdigest()}


def _read_or_create_inventory(path: Path) -> dict[str, str]:
    try:
        return _read_inventory(path)
    except FileNotFoundError:
        try:
            with path.open("x", encoding="utf-8", newline="\n") as inventory:
                inventory.write(" | ".join(EXTENDED_HEADERS) + "\n")
        except FileExistsError:
            pass
        return _read_inventory(path)


def _save_inventory(path: Path, content: str, expected_revision: str) -> str:
    current = _read_inventory(path)
    if current["revision"] != expected_revision:
        raise web.HTTPConflict(text="Tiedosto on muuttunut latauksen jälkeen. Lataa se uudelleen.")
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_summaries(output: str) -> list[dict]:
    summaries = []
    for line in output.splitlines():
        if not line.startswith("MACIP_SUMMARY "):
            continue
        summary = json.loads(line[len("MACIP_SUMMARY "):])
        if (not isinstance(summary, dict) or not isinstance(summary.get("router"), str)
                or not isinstance(summary.get("new_devices"), list)
                or not isinstance(summary.get("ip_changes"), list)):
            raise ValueError("Reititinpäivityksen yhteenveto on virheellinen.")
        for key, fields in (("new_devices", ("mac", "name", "ip")),
                            ("ip_changes", ("mac", "name", "old_ip", "new_ip"))):
            if any(not isinstance(item, dict) or any(
                not isinstance(item.get(field), str) for field in fields
            ) for item in summary[key]):
                raise ValueError("Reititinpäivityksen yhteenveto on virheellinen.")
        summaries.append(summary)
    return summaries


def _read_commands(directory: Path) -> list[list[str]]:
    config = json.loads((directory / "macip_server_config.json").read_text(encoding="utf-8-sig"))
    commands = config.get("update_commands") if isinstance(config, dict) else None
    if not isinstance(commands, list) or not commands or any(
        not isinstance(command, list) or not command or
        not all(isinstance(part, str) and part for part in command) for command in commands
    ):
        raise ValueError("Asetustiedoston update_commands-lista on virheellinen.")
    return commands


def _update_inventory(directory: Path, expected_revision: str) -> dict:
    path = directory / "macip.txt"
    if _read_inventory(path)["revision"] != expected_revision:
        raise web.HTTPConflict(text="Tiedosto on muuttunut latauksen jälkeen. Lataa se uudelleen.")
    summaries, missing, failures = [], [], []
    for command in _read_commands(directory):
        label = " ".join(command)
        try:
            result = subprocess.run(
                [sys.executable, *command], cwd=directory, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=180,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            failures.append({"command": label, "error": "Aikakatkaisu (180 s)."})
            continue
        except OSError as error:
            failures.append({"command": label, "error": f"Komentoa ei voitu käynnistää: {error}"})
            continue
        if result.returncode:
            failures.append({"command": label, "error": (
                f"Paluukoodi {result.returncode}. {(result.stderr or result.stdout).strip()}"
            )})
            continue
        try:
            found = _parse_summaries(result.stdout)
        except ValueError as error:
            failures.append({"command": label, "error": f"Päivitys suoritettiin, mutta {error}"})
            continue
        if found:
            summaries.extend(found)
        else:
            missing.append(label)
    return {**_read_inventory(path), "summaries": summaries,
            "missing_summaries": missing, "failures": failures}


class MacipView(HomeAssistantView):
    """Serve the authenticated inventory and update operations."""

    url = "/api/macip"
    name = "api:macip"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.directory = Path(hass.config.path("macip_scripts"))
        self.lock = asyncio.Lock()

    async def get(self, request) -> web.Response:
        async with self.lock:
            try:
                data = await self.hass.async_add_executor_job(
                    _read_or_create_inventory, self.directory / "macip.txt"
                )
            except FileNotFoundError as error:
                raise web.HTTPNotFound(text="macip_scripts-kansiota ei löydy.") from error
        return self.json(data)

    async def post(self, request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError as error:
            raise web.HTTPBadRequest(text="Pyynnön sisältö ei ole kelvollista JSONia.") from error
        content = payload.get("content") if isinstance(payload, dict) else None
        revision = payload.get("revision") if isinstance(payload, dict) else None
        if not isinstance(content, str) or not isinstance(revision, str):
            raise web.HTTPBadRequest(text="Sisältö tai tiedoston versio puuttuu.")
        try:
            validate_content(content)
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error)) from error
        task = asyncio.create_task(self._save(content, revision))
        return self.json({"revision": await asyncio.shield(task)})

    async def _save(self, content: str, revision: str) -> str:
        async with self.lock:
            return await self.hass.async_add_executor_job(
                _save_inventory, self.directory / "macip.txt", content, revision
            )


class MacipUpdateView(HomeAssistantView):
    """Run configured router updates through an authenticated endpoint."""

    url = "/api/macip/update"
    name = "api:macip:update"
    requires_auth = True

    def __init__(self, view: MacipView) -> None:
        self.view = view

    async def post(self, request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError as error:
            raise web.HTTPBadRequest(text="Pyynnön sisältö ei ole kelvollista JSONia.") from error
        revision = payload.get("revision") if isinstance(payload, dict) else None
        if not isinstance(revision, str):
            raise web.HTTPBadRequest(text="Tiedoston versio puuttuu.")
        task = asyncio.create_task(self._run(revision))
        return self.json(await asyncio.shield(task))

    async def _run(self, revision: str) -> dict:
        async with self.view.lock:
            return await self.view.hass.async_add_executor_job(
                _update_inventory, self.view.directory, revision
            )
