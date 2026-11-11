"""Serve the local macip editor and its file and router update APIs.

Copyright (c) 2026 vesal.
Developed with assistance from GitHub Copilot.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


HOST = "127.0.0.1"
PORT = 8765
DIRECTORY = Path(__file__).resolve().parent
EDITOR_FILE = DIRECTORY / "macip.html"
FILTER_FILE = DIRECTORY / "macip_filter.js"
INVENTORY_FILE = DIRECTORY / "macip.txt"
CONFIG_FILE = DIRECTORY / "macip_server_config.json"
MAX_REQUEST_SIZE = 2_000_000
inventory_lock = threading.Lock()


def revision(content: bytes) -> str:
    """Hash file content to detect concurrent changes.

    :param content: File content as bytes.
    :return: SHA-256 checksum in hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()


def validate_content(content: str) -> None:
    """Validate the headers and column counts of the inventory to save.

    :param content: Inventory text to save.
    :return: None; raises ValueError for invalid content.
    """
    if "\x00" in content:
        raise ValueError("Tiedostossa on virheellinen ohjausmerkki.")
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Laiteluettelo ei voi olla tyhjä.")
    headers = [part.strip() for part in lines[0].split("|")]
    if not headers or headers[0].lower() != "mac" or "Oma nimi" not in headers:
        raise ValueError("Otsikoissa pitää olla MAC- ja Oma nimi -sarakkeet.")
    for number, line in enumerate(lines[1:], 2):
        if len(line.split("|")) != len(headers):
            raise ValueError(f"Rivillä {number} on virheellinen määrä sarakkeita.")


def write_inventory(content: str) -> None:
    """Replace the inventory file using a temporary file.

    :param content: Inventory text to save.
    :return: None.
    """
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            dir=INVENTORY_FILE.parent, delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
        os.replace(temporary_name, INVENTORY_FILE)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def read_commands() -> list[list[str]]:
    """Read and validate the router update command list.

    :return: Python scripts and their arguments in execution order.
    """
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    commands = config.get("update_commands") if isinstance(config, dict) else None
    if not isinstance(commands, list) or not commands:
        raise ValueError("Asetustiedoston update_commands-lista puuttuu tai on tyhjä.")
    for command in commands:
        if (not isinstance(command, list) or not command
                or not all(isinstance(part, str) and part for part in command)):
            raise ValueError("Jokaisen päivityskomennon pitää olla epätyhjä merkkijonolista.")
    return commands


def read_summaries(output: str) -> list[dict[str, object]]:
    """Extract machine-readable update summaries from command output.

    :param output: Standard output from a router update command.
    :return: Summary objects in their original order.
    """
    summaries = []
    for line in output.splitlines():
        if not line.startswith("MACIP_SUMMARY "):
            continue
        summary = json.loads(line[len("MACIP_SUMMARY "):])
        if (not isinstance(summary, dict) or not isinstance(summary.get("router"), str)
                or not isinstance(summary.get("ip_changes"), list)
                or not isinstance(summary.get("new_devices"), list)):
            raise ValueError("Reititinpäivityksen yhteenveto on virheellinen.")
        for key, fields in (
            ("ip_changes", ("mac", "name", "old_ip", "new_ip")),
            ("new_devices", ("mac", "name", "ip")),
        ):
            for entry in summary[key]:
                if not isinstance(entry, dict) or not all(
                    isinstance(entry.get(field), str) for field in fields
                ):
                    raise ValueError("Reititinpäivityksen yhteenveto sisältää virheellisiä laitetietoja.")
        summaries.append(summary)
    return summaries


class EditorHandler(BaseHTTPRequestHandler):
    """Handle the editor's local HTTP requests."""

    server: ThreadingHTTPServer

    def valid_host(self) -> bool:
        """Check that the Host header identifies the local server.

        :return: True if the Host header is accepted.
        """
        port = self.server.server_port
        return self.headers.get("Host", "").lower() in (
            f"localhost:{port}", f"127.0.0.1:{port}",
        )

    def send_data(self, status: int, content: bytes, content_type: str) -> None:
        """Send an HTTP response containing bytes.

        :param status: HTTP status code.
        :param content: Response body.
        :param content_type: Response Content-Type header.
        :return: None.
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status: int, data: dict[str, object]) -> None:
        """Send a JSON HTTP response.

        :param status: HTTP status code.
        :param data: Response object to serialize as JSON.
        :return: None.
        """
        self.send_data(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def do_GET(self) -> None:
        """Return the editor page or device inventory for a GET request.

        :return: None.
        """
        if not self.valid_host():
            self.send_json(403, {"error": "Virheellinen palvelimen osoite."})
            return
        request_path = urlsplit(self.path).path
        try:
            if request_path in ("/", "/macip.html"):
                self.send_data(200, EDITOR_FILE.read_bytes(), "text/html; charset=utf-8")
            elif request_path == "/macip_filter.js":
                self.send_data(200, FILTER_FILE.read_bytes(), "text/javascript; charset=utf-8")
            elif request_path == "/api/macip":
                with inventory_lock:
                    content = INVENTORY_FILE.read_bytes()
                self.send_json(200, {
                    "content": content.decode("utf-8-sig"),
                    "revision": revision(content),
                    "name": INVENTORY_FILE.name,
                })
            else:
                self.send_json(404, {"error": "Osoitetta ei löydy."})
        except (OSError, UnicodeError) as error:
            self.send_json(500, {"error": f"Tiedoston lukeminen epäonnistui: {error}"})

    def do_POST(self) -> None:
        """Validate and handle a save or router update request.

        :return: None.
        """
        host = self.headers.get("Host", "").lower()
        if not self.valid_host() or self.headers.get("Origin") != f"http://{host}":
            self.send_json(403, {"error": "Pyyntö ei tullut editorin sivulta."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Pyynnön on oltava JSON-muotoinen."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if length < 0 or length > MAX_REQUEST_SIZE:
                raise ValueError("Pyynnön koko on virheellinen tai liian suuri.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Pyynnön pitää olla JSON-objekti.")
            path = urlsplit(self.path).path
            if path == "/api/macip":
                self.save_inventory(payload)
            elif path == "/api/update":
                self.update_routers()
            else:
                self.send_json(404, {"error": "Osoitetta ei löydy."})
        except (ValueError, UnicodeError) as error:
            self.send_json(400, {"error": str(error)})
        except OSError as error:
            self.send_json(500, {"error": f"Toiminto epäonnistui: {error}"})

    def save_inventory(self, payload: dict[str, object]) -> None:
        """Save the inventory if the file has not changed since it was loaded.

        :param payload: Request containing the content and original revision.
        :return: None.
        """
        content = payload.get("content")
        expected_revision = payload.get("revision")
        if not isinstance(content, str) or not isinstance(expected_revision, str):
            raise ValueError("Sisältö tai tiedoston versio puuttuu.")
        validate_content(content)
        with inventory_lock:
            if revision(INVENTORY_FILE.read_bytes()) != expected_revision:
                self.send_json(409, {"error": "Tiedosto on muuttunut latauksen jälkeen. "
                                             "Lataa se uudelleen ennen tallennusta."})
                return
            write_inventory(content)
            new_revision = revision(content.encode("utf-8"))
        self.send_json(200, {"revision": new_revision})

    def update_routers(self) -> None:
        """Run the router update commands and return the updated inventory.

        :return: None.
        """
        commands = read_commands()
        if not inventory_lock.acquire(blocking=False):
            self.send_json(409, {"error": "Toinen tallennus tai päivitys on kesken."})
            return
        try:
            summaries = []
            missing_summaries = []
            failures = []
            for command in commands:
                command_name = subprocess.list2cmdline(command)
                try:
                    result = subprocess.run(
                        [sys.executable, *command], cwd=DIRECTORY,
                        capture_output=True, text=True, encoding="utf-8",
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        errors="replace", timeout=180,
                    )
                except subprocess.TimeoutExpired:
                    failures.append({"command": command_name, "error": "Aikakatkaisu (180 s)."})
                    continue
                except OSError as error:
                    failures.append({"command": command_name,
                                     "error": f"Komentoa ei voitu käynnistää: {error}"})
                    continue
                if result.returncode:
                    detail = (result.stderr or result.stdout).strip()
                    failures.append({"command": command_name,
                                     "error": f"Paluukoodi {result.returncode}. {detail}".strip()})
                    continue
                try:
                    command_summaries = read_summaries(result.stdout)
                except ValueError as error:
                    failures.append({"command": command_name,
                                     "error": f"Päivitys suoritettiin, mutta yhteenveto on virheellinen: {error}"})
                    continue
                if not command_summaries:
                    missing_summaries.append(command_name)
                summaries.extend(command_summaries)
            content = INVENTORY_FILE.read_bytes()
            self.send_json(200, {
                "content": content.decode("utf-8-sig"),
                "revision": revision(content),
                "name": INVENTORY_FILE.name,
                "summaries": summaries,
                "missing_summaries": missing_summaries,
                "failures": failures,
            })
        finally:
            inventory_lock.release()

    def log_message(self, format_string: str, *args: object) -> None:
        """Print an HTTP server log message.

        :param format_string: Log message format string.
        :param args: Values to interpolate into the message.
        :return: None.
        """
        print(f"{self.address_string()} - {format_string % args}")


def main() -> None:
    """Start the local server and open the editor in a browser.

    :return: None after the server has stopped.
    """
    url = f"http://localhost:{PORT}/macip.html"
    try:
        server = ThreadingHTTPServer((HOST, PORT), EditorHandler)
    except OSError as error:
        raise SystemExit(
            f"Paikallista palvelinta ei voitu käynnistää osoitteeseen "
            f"{HOST}:{PORT}. Sulje mahdollinen toinen macip-editori ja yritä uudelleen.\n"
            f"{error}"
        ) from error

    print(f"macip-editori: {url}")
    print("Palvelin pysyy käynnissä tämän ikkunan ollessa auki. Lopeta Ctrl+C:llä.")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPalvelin suljetaan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
