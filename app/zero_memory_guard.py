"""
zero_memory_guard — ZeroPointAI

ZERO_MODULE:    memory
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Minnesskydd — rate limiting, read-only guard, session budgets
ZERO_DEPENDS:   drm_memory.py, foundation.py
ZERO_USED_BY:   zero_engine.py
"""
from __future__ import annotations


# Canonical blocks injected by inject_foundation_laws.py.
# Do not edit manually. ZERO_SYSTEM.md is the source of truth.




import datetime as dt
import json
import os
from pathlib import Path
from typing import Dict, Optional

def _default_state_path() -> Path:
    """Resolve state path — Linux/H9 default, Windows fallback, env override."""
    env = os.getenv("ZERO_MEMORY_GUARD_STATE")
    if env:
        return Path(env)
    zero_root = os.getenv("ZERO_ROOT")
    if zero_root:
        return Path(zero_root) / "data" / "status" / "memory_guard_state.json"
    if os.name == "nt":
        return Path(r"D:\ZeroPointAI\data\status\memory_guard_state.json")
    return Path("/opt/zeropointai/data/status/memory_guard_state.json")

STATE_PATH = _default_state_path()

PER_REQUEST_ROW_LIMIT = int(os.getenv("ZERO_MEMORY_PER_REQUEST_ROW_LIMIT", "1000"))
PER_REQUEST_TOKEN_LIMIT = int(os.getenv("ZERO_MEMORY_PER_REQUEST_TOKEN_LIMIT", "30000"))
PER_REQUEST_BYTES_LIMIT = int(os.getenv("ZERO_MEMORY_PER_REQUEST_BYTES_LIMIT", str(3 * 1024 * 1024)))

SESSION_REQUESTS_PER_MINUTE = int(os.getenv("ZERO_MEMORY_SESSION_REQUESTS_PER_MINUTE", "8"))
SESSION_ROW_LIMIT = int(os.getenv("ZERO_MEMORY_SESSION_ROW_LIMIT", "12000"))
SESSION_TOKEN_LIMIT = int(os.getenv("ZERO_MEMORY_SESSION_TOKEN_LIMIT", "240000"))
SESSION_BYTES_LIMIT = int(os.getenv("ZERO_MEMORY_SESSION_BYTES_LIMIT", str(25 * 1024 * 1024)))
SESSION_RELATIVE_DB_LIMIT_PCT = float(os.getenv("ZERO_MEMORY_SESSION_RELATIVE_DB_LIMIT_PCT", "5.0"))

DEFAULT_STATE = {
    "read_only": False,
    "read_only_reason": "",
    "read_only_since": "",
    "sessions": {},
    "incidents": [],
}

def _ensure_parent():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

def _utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _load_state() -> Dict:
    _ensure_parent()
    if not STATE_PATH.exists():
        _save_state(DEFAULT_STATE.copy())
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Backup corrupt file for forensic inspection before reset
        try:
            import shutil as _shutil
            corrupt_backup = STATE_PATH.with_suffix(
                f".corrupt.{_utc_now().replace(':', '-')}.json"
            )
            _shutil.copy2(STATE_PATH, corrupt_backup)
        except Exception:
            pass
        backup = {
            **DEFAULT_STATE,
            "incidents": [{"ts": _utc_now(), "event": "STATE_CORRUPT_RESET"}],
        }
        _save_state(backup)
        return backup

def _save_state(data: Dict):
    """Write state atomically to prevent corruption on crash."""
    _ensure_parent()
    tmp = STATE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise

def _get_session_bucket(state: Dict, session_id: str) -> Dict:
    sessions = state.setdefault("sessions", {})
    bucket = sessions.get(session_id)
    now = dt.datetime.utcnow()

    if not bucket:
        bucket = {
            "minute_window_started_at": _utc_now(),
            "requests_this_minute": 0,
            "rows_total": 0,
            "tokens_total": 0,
            "bytes_total": 0,
            "db_rows_seen_hint": 0,
        }
        sessions[session_id] = bucket
        return bucket

    try:
        start = dt.datetime.fromisoformat(bucket["minute_window_started_at"].replace("Z", ""))
    except Exception:
        start = now

    if (now - start).total_seconds() >= 60:
        bucket["minute_window_started_at"] = _utc_now()
        bucket["requests_this_minute"] = 0

    return bucket

def enable_read_only(reason: str):
    state = _load_state()
    state["read_only"] = True
    state["read_only_reason"] = reason
    state["read_only_since"] = _utc_now()
    state.setdefault("incidents", []).append({
        "ts": _utc_now(),
        "event": "READ_ONLY_ENABLED",
        "reason": reason,
    })
    _save_state(state)

def disable_read_only(reason: str = ""):
    state = _load_state()
    state["read_only"] = False
    state["read_only_reason"] = ""
    state["read_only_since"] = ""
    state.setdefault("incidents", []).append({
        "ts": _utc_now(),
        "event": "READ_ONLY_DISABLED",
        "reason": reason,
    })
    _save_state(state)

def get_memory_guard_status() -> Dict:
    return _load_state()

def can_write_memory() -> Dict:
    state = _load_state()
    if state.get("read_only"):
        return {
            "ok": False,
            "reason": state.get("read_only_reason") or "READ_ONLY_MODE is active",
        }
    return {"ok": True, "reason": ""}

def _record_incident(state: Dict, event: str, detail: Dict):
    state.setdefault("incidents", []).append({
        "ts": _utc_now(),
        "event": event,
        "detail": detail,
    })
    # Håll filen rimlig
    state["incidents"] = state["incidents"][-200:]

def authorize_memory_read(
    session_id: str,
    requested_rows: int,
    requested_tokens: int = 0,
    requested_bytes: int = 0,
    db_total_rows_hint: Optional[int] = None,
    actor: str = "internal",
    local_with_sudo: bool = False,
) -> Dict:
    state = _load_state()

    if local_with_sudo:
        _record_incident(state, "MEMORY_READ_OVERRIDE", {
            "session_id": session_id,
            "actor": actor,
            "requested_rows": requested_rows,
            "requested_tokens": requested_tokens,
            "requested_bytes": requested_bytes,
            "db_total_rows_hint": db_total_rows_hint,
        })
        _save_state(state)
        return {"ok": True, "reason": "Local sudo override active."}

    bucket = _get_session_bucket(state, session_id)

    if requested_rows > PER_REQUEST_ROW_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "PER_REQUEST_ROW_LIMIT",
            "session_id": session_id,
            "requested_rows": requested_rows,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Begärt uttag överskrider per-request radgräns ({PER_REQUEST_ROW_LIMIT})."}

    if requested_tokens > PER_REQUEST_TOKEN_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "PER_REQUEST_TOKEN_LIMIT",
            "session_id": session_id,
            "requested_tokens": requested_tokens,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Begärt uttag överskrider per-request tokengräns ({PER_REQUEST_TOKEN_LIMIT})."}

    if requested_bytes > PER_REQUEST_BYTES_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "PER_REQUEST_BYTES_LIMIT",
            "session_id": session_id,
            "requested_bytes": requested_bytes,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Begärt uttag överskrider per-request bytesgräns ({PER_REQUEST_BYTES_LIMIT})."}

    if bucket["requests_this_minute"] >= SESSION_REQUESTS_PER_MINUTE:
        _record_incident(state, "MEMORY_READ_THROTTLED", {
            "reason": "SESSION_REQUESTS_PER_MINUTE",
            "session_id": session_id,
            "requests_this_minute": bucket["requests_this_minute"],
        })
        _save_state(state)
        return {"ok": False, "reason": "För många minnesuttag denna minut."}

    next_rows = bucket["rows_total"] + requested_rows
    next_tokens = bucket["tokens_total"] + requested_tokens
    next_bytes = bucket["bytes_total"] + requested_bytes

    if next_rows > SESSION_ROW_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "SESSION_ROW_LIMIT",
            "session_id": session_id,
            "rows_total": next_rows,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Sessionen överskrider radbudget ({SESSION_ROW_LIMIT})."}

    if next_tokens > SESSION_TOKEN_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "SESSION_TOKEN_LIMIT",
            "session_id": session_id,
            "tokens_total": next_tokens,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Sessionen överskrider tokenbudget ({SESSION_TOKEN_LIMIT})."}

    if next_bytes > SESSION_BYTES_LIMIT:
        _record_incident(state, "MEMORY_READ_BLOCKED", {
            "reason": "SESSION_BYTES_LIMIT",
            "session_id": session_id,
            "bytes_total": next_bytes,
        })
        _save_state(state)
        return {"ok": False, "reason": f"Sessionen överskrider bytesbudget ({SESSION_BYTES_LIMIT})."}

    if db_total_rows_hint and db_total_rows_hint > 0:
        relative_pct = (next_rows / db_total_rows_hint) * 100
        if relative_pct > SESSION_RELATIVE_DB_LIMIT_PCT:
            _record_incident(state, "MEMORY_READ_BLOCKED", {
                "reason": "SESSION_RELATIVE_DB_LIMIT_PCT",
                "session_id": session_id,
                "relative_pct": relative_pct,
                "db_total_rows_hint": db_total_rows_hint,
            })
            _save_state(state)
            return {"ok": False, "reason": f"Sessionen överskrider {SESSION_RELATIVE_DB_LIMIT_PCT:.1f}% av databasen."}
        bucket["db_rows_seen_hint"] = db_total_rows_hint

    bucket["requests_this_minute"] += 1
    bucket["rows_total"] = next_rows
    bucket["tokens_total"] = next_tokens
    bucket["bytes_total"] = next_bytes

    _save_state(state)
    return {"ok": True, "reason": "Authorized."}
