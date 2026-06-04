"""
zero_web_server.py — ZeroPointAI HTTP Server

ZERO_MODULE:    core
ZERO_ESSENTIAL: true
ZERO_ROLE:      HTTP-server — tar emot requests, delegerar till zero_engine.py
ZERO_DEPENDS:   foundation.py, zero_engine.py
ZERO_USED_BY:   zero-web.service (systemd), användaren via webbläsare

Ansvar:
  - Servar UI (zero_ui_vX.html från config/)
  - Tar emot /chat POST och delegerar till ZeroEngine
  - Hanterar /status, /memory, /health endpoints
  - Hanterar filuppladdningar och bilagor
  - Kör på port UI_PORT (default 8080)

Denna fil innehåller INGEN AI-logik.
Denna fil innehåller INGA provider-anrop.
Denna fil innehåller INGEN system-prompt-logik.
Allt sådant lever i zero_engine.py.
"""

from __future__ import annotations

import os
import sys
import json
import logging
import re
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.foundation import ZERO_ROOT, CONFIG_DIR
from app.zero_engine import get_engine, ZeroEngine

log = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

PORT = int(os.getenv("UI_PORT", 8080))


# ── UI-filhantering ───────────────────────────────────────────────────────────

def get_latest_ui() -> str:
    """Hittar automatiskt den senaste zero_ui_vX.html i config/."""
    best_version, best_file = -1, "zero_ui_v1.html"
    try:
        for f in os.listdir(CONFIG_DIR):
            m = re.match(r"zero_ui_v(\d+)\.html$", f)
            if m:
                v = int(m.group(1))
                if v > best_version:
                    best_version, best_file = v, f
    except Exception:
        pass
    return best_file


def _read_ui() -> bytes:
    ui_file = CONFIG_DIR / get_latest_ui()
    try:
        return ui_file.read_bytes()
    except FileNotFoundError:
        return b"<h1>UI saknas</h1><p>Placera zero_ui_vX.html i config/</p>"


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class ZeroHandler(BaseHTTPRequestHandler):

    _engine: ZeroEngine = None  # Delas av alla handler-instanser

    def log_message(self, fmt, *args):
        log.debug(f"{self.address_string()} — {fmt % args}")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._send_html(_read_ui())
            return

        if path == "/health":
            engine = self._get_engine()
            self._send_json({
                "status":       "ok",
                "db":           engine.db_ok,
                "health_score": engine.get_health_score(),
                "provider":     engine.provider,
                "uptime_s":     int((datetime.now() - engine.start_time).total_seconds()),
                "memories":     engine.memory_count,
            })
            return

        if path == "/status":
            engine = self._get_engine()
            self._send_json({
                "provider":       engine.provider,
                "db_ok":          engine.db_ok,
                "memory_count":   engine.memory_count,
                "session_calls":  engine.session_calls,
                "session_cost":   round(engine.session_cost, 4),
                "last_latency":   engine.last_latency,
                "health_score":   engine.get_health_score(),
                "gear4_active":   engine.gear4_active,
            })
            return

        if path == "/memory/stats":
            try:
                from app.drm_memory import get_memory_stats
                self._send_json(get_memory_stats())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/memory/soul":
            try:
                from app.drm_memory import get_latest_soul_snapshot
                snap = get_latest_soul_snapshot()
                self._send_json(snap or {"message": "Inga soul snapshots ännu"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path == "/gear/status":
            try:
                from app.zero_gear import get_gear_status
                self._send_json(get_gear_status())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": f"Okänd endpoint: {path}"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/chat":
            self._handle_chat()
            return

        if path == "/memory/search":
            self._handle_memory_search()
            return

        if path == "/memory/upsert":
            self._handle_memory_upsert()
            return

        if path == "/evolution":
            self._handle_evolution()
            return

        if path == "/provider/set":
            self._handle_set_provider()
            return

        self._send_json({"error": f"Okänd endpoint: {path}"}, 404)

    # ── Endpoint-handlers ─────────────────────────────────────────────────────

    def _handle_chat(self):
        body = self._read_body()
        user_input  = body.get("message", "").strip()
        attachments = body.get("attachments", [])
        session_id  = body.get("session_id")

        if not user_input and not attachments:
            self._send_json({"error": "Tomt meddelande"}, 400)
            return

        engine = self._get_engine()

        # Sätt session om skickad
        if session_id and session_id != engine.session_id:
            engine.session_id = session_id

        try:
            result = engine.chat(user_input, attachments=attachments or None)
            self._send_json({
                "response":   result["response"],
                "provider":   result.get("provider", engine.provider),
                "gear":       result.get("gear", "?"),
                "in_tok":     result.get("in_tok", 0),
                "out_tok":    result.get("out_tok", 0),
                "cost_sek":   result.get("cost_sek", 0.0),
                "latency":    result.get("latency", 0.0),
                "thinking":   result.get("thinking", []),
                "session_id": engine.session_id,
            })
        except Exception as e:
            log.error(f"/chat fel: {e}", exc_info=True)
            self._send_json({"error": str(e), "response": f"Fel: {e}"}, 500)

    def _handle_memory_search(self):
        body  = self._read_body()
        query = body.get("query", "").strip()
        if not query:
            self._send_json({"error": "query saknas"}, 400)
            return
        try:
            from app.zero_memory_search import search_zero_memory
            result = search_zero_memory(
                query=query,
                memory_types=body.get("types", "all"),
                limit=body.get("limit", 10),
            )
            self._send_json({"result": result})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_memory_upsert(self):
        body = self._read_body()
        try:
            from app.drm_memory import upsert_core_identity
            upsert_core_identity(
                fact_type  = body.get("fact_type", "fact"),
                fact_key   = body.get("fact_key", ""),
                fact_value = body.get("fact_value", ""),
                source     = body.get("source", "api"),
            )
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_evolution(self):
        body  = self._read_body()
        force = body.get("force", False)
        try:
            from app.drm_memory import run_evolution_loop
            result = run_evolution_loop(force=force)
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_set_provider(self):
        body     = self._read_body()
        provider = body.get("provider", "").strip()
        if not provider:
            self._send_json({"error": "provider saknas"}, 400)
            return
        engine = self._get_engine()
        from app.providers import normalize_provider_name, provider_exists
        canonical = normalize_provider_name(provider)
        if not provider_exists(canonical):
            self._send_json({"error": f"Okänd provider: {canonical}"}, 400)
            return
        engine.provider = canonical
        self._send_json({"ok": True, "provider": canonical})

    # ── Hjälp ─────────────────────────────────────────────────────────────────

    def _get_engine(self) -> ZeroEngine:
        if ZeroHandler._engine is None:
            ZeroHandler._engine = get_engine()
        return ZeroHandler._engine


# ── Serverstart ───────────────────────────────────────────────────────────────

def run():
    import atexit

    engine = get_engine()
    ZeroHandler._engine = engine
    atexit.register(engine.shutdown)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), ZeroHandler)

    print(f"\n{'='*50}")
    print(f"  ZeroPointAI — Web Server")
    print(f"  http://localhost:{PORT}")
    print(f"  Provider : {engine.provider}")
    print(f"  Databas  : {'OK ✓' if engine.db_ok else 'Inte ansluten ✗'}")
    print(f"  Minnen   : {engine.memory_count:,}")
    print(f"  UI       : {get_latest_ui()}")
    print(f"{'='*50}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStänger Zero...")
    finally:
        server.shutdown()
        engine.shutdown()


if __name__ == "__main__":
    run()
