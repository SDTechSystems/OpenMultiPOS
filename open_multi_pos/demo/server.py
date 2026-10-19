"""Loopback-only demonstration server. Never deploy with real business data."""

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from open_multi_pos.demo.store import ConflictError, DemoStore
from open_multi_pos.fiscal import DisabledFiscalProvider
from open_multi_pos.hardware import BrowserPrinterAdapter, printer_profiles, profile_list

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def make_server(store: DemoStore, port: int = 8765) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Avoid logging receipt IDs or payloads.

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; object-src 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.valid_host():
                self.respond(403, {"error": "Host no permitido"})
                return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            user = self.headers.get("X-Demo-User", "owner")
            try:
                if url.path in STATIC:
                    name, mime = STATIC[url.path]
                    self.respond(
                        200,
                        files("open_multi_pos.demo").joinpath(f"static/{name}").read_text(),
                        mime,
                    )
                elif url.path == "/api/context":
                    result = store.context(user)
                    result.update(
                        {
                            "token": token,
                            "printers": profile_list(),
                            "fiscal": DisabledFiscalProvider().status().__dict__,
                        }
                    )
                    self.respond(200, result)
                elif url.path == "/api/catalog":
                    self.respond(200, store.catalog(user, query.get("brand", [""])[0]))
                elif url.path == "/api/receipt":
                    receipt = store.receipt(user, query.get("id", [""])[0])
                    profile = printer_profiles()[query.get("profile", ["generic-58"])[0]]
                    html = BrowserPrinterAdapter().preview(receipt, profile)
                    self.respond(200, html, "text/html; charset=utf-8")
                else:
                    self.respond(404, {"error": "Ruta no encontrada"})
            except PermissionError as exc:
                self.respond(403, {"error": str(exc)})
            except (ValueError, KeyError) as exc:
                self.respond(400, {"error": str(exc)})

        def do_POST(self):
            if not self.valid_host():
                self.respond(403, {"error": "Host no permitido"})
                return
            expected_origin = f"http://{self.headers.get('Host')}"
            if self.headers.get("Origin") != expected_origin or not secrets.compare_digest(
                self.headers.get("X-Demo-Token", ""), token
            ):
                self.respond(403, {"error": "Origen o token demo inválido"})
                return
            if self.path != "/api/checkout":
                self.respond(404, {"error": "Ruta no encontrada"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 16384:
                    self.respond(413, {"error": "Tamaño de solicitud inválido"})
                    return
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Se requiere application/json")
                data = json.loads(self.rfile.read(length))
                self.respond(200, store.checkout(self.headers.get("X-Demo-User", "owner"), data))
            except PermissionError as exc:
                self.respond(403, {"error": str(exc)})
            except ConflictError as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="OpenMultiPOS · demo local ficticia")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--db", type=Path, default=Path.home() / ".openmultipos-demo" / "demo.sqlite3"
    )
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    server = make_server(DemoStore(args.db), args.port)
    print(f"Demo ficticia: http://127.0.0.1:{server.server_port} · Ctrl+C para salir", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
