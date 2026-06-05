"""
zero_sudo.py — ZeroPointAI Full Behörighet

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Exekverar systemkommandon med full behörighet, loggning och auto-backup
ZERO_DEPENDS:   foundation.py, drm_memory.py
ZERO_USED_BY:   zero_gear4.py, zero_night.py, router.py

Filosofi:
    Zero har full behörighet.
    Skyddet är inte frågor och dialoger — det är backup och loggning.

    Innan varje destruktiv operation:
        1. Git commit automatiskt (kan alltid rulla tillbaka)
        2. Kör operationen
        3. Logga resultatet till STONE

    Zero lär sig av misstag — inte av att aldrig få göra dem.
    En operation som kan återställas är alltid tillåten.

    Enda undantaget: 3 sekunders synlig paus vid CRITICAL-operationer.
    Inte för att fråga om lov — utan för att ge Frank chansen att skriva "stopp".

Risknivåer:
    SAFE     → Kör direkt, logga efteråt
    CAUTION  → Git commit först, kör, logga
    CRITICAL → Git commit, visa vad som ska hända, 3s paus, kör, logga
    FORBIDDEN → Körs aldrig (t.ex. rm -rf /)

Exempel:
    from app.zero_sudo import run, sudo_run

    # Säker operation
    result = run(["ls", "-la", "/opt/zeropointai"])

    # Admin-operation med auto-backup
    result = sudo_run(["systemctl", "restart", "zero-web-v2.service"])

    # Skriva en fil (auto-backup om destruktiv)
    result = write_file("/opt/zeropointai/next_zero/app/test.py", content)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

# ── Root ──────────────────────────────────────────────────────────────────────

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

load_dotenv(ZERO_ROOT / ".env")

SUDO_LOG_FILE = ZERO_ROOT / "data" / "sudo_log.json"
SUDO_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Trust Level ───────────────────────────────────────────────────────────────
# Styrs via .env: ZERO_TRUST_LEVEL=0|1|2|3
#
#   0 = SAFE-only automatisk, fråga alltid vid CAUTION+
#   1 = Kör SAFE + CAUTION automatisk, fråga vid HIGH+   (default)
#   2 = Kör SAFE + CAUTION + HIGH automatisk, fråga vid CRITICAL
#   3 = Kör allt utom FORBIDDEN — Frank said "trust mode full"
#
# Oavsett trust level:
#   - FORBIDDEN körs aldrig
#   - CRITICAL kräver explicit bekräftelse vid nivå 0-2
#   - Allt loggas alltid till STONE

TRUST_LEVEL = int(os.getenv("ZERO_TRUST_LEVEL", "1"))

def get_trust_level() -> int:
    """Returnerar aktuell trust level (läser från env varje gång)."""
    return int(os.getenv("ZERO_TRUST_LEVEL", "1"))

def set_trust_level(level: int) -> str:
    """
    Frank säger 'Zero, trust mode full' → level 3
    Sätts i .env och tas i kraft direkt.
    """
    if level not in (0, 1, 2, 3):
        return f"Ogiltigt trust level: {level}. Använd 0-3."
    os.environ["ZERO_TRUST_LEVEL"] = str(level)
    labels = {
        0: "Försiktig — frågar alltid",
        1: "Normal — frågar vid HIGH+",
        2: "Hög — frågar bara vid CRITICAL",
        3: "Full — kör allt (utom FORBIDDEN), loggar allt",
    }
    log.info(f"Trust Level satt till {level}: {labels[level]}")
    return f"Trust Level: {level} — {labels[level]}"

def should_ask_frank(risk_level: str) -> bool:
    """
    Avgör om Frank ska tillfrågas baserat på risk och trust level.
    Kärnan i autonomi-systemet.
    """
    level = get_trust_level()
    if risk_level == "FORBIDDEN":
        return False   # Körs aldrig, frågar inte
    if risk_level == "CRITICAL":
        return level < 3   # Frågar alltid utom full trust
    if risk_level == "HIGH":
        return level < 2
    if risk_level == "CAUTION":
        return level < 1
    return False  # SAFE — kör alltid

# ── Riskmönster ───────────────────────────────────────────────────────────────

# Kommandon som kräver git commit innan körning
CAUTION_PATTERNS = [
    "systemctl", "service", "docker",
    "apt", "pip", "npm",
    "chmod", "chown",
    "mv ", "cp -r", "rsync",
    "psql", "pg_restore", "pg_dump",
]

# Kommandon som är potentiellt destruktiva — 3s paus
CRITICAL_PATTERNS = [
    "rm -rf", "rm -r",
    "drop table", "drop database", "truncate",
    "dd if=", "mkfs",
    "shred",
    "> /",  # Skriver över systemfil
]

# Kommandon som aldrig körs
FORBIDDEN_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs /dev/sd",
    "dd if=/dev/zero of=/dev/sd",
    ":(){:|:&};:",  # Fork bomb
]

# ── Loggning ──────────────────────────────────────────────────────────────────

@dataclass
class SudoLogEntry:
    timestamp:   str
    command:     List[str]
    risk_level:  str
    ok:          bool
    return_code: int
    stdout:      str
    stderr:      str
    duration_ms: float
    git_backup:  bool
    note:        str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _append_log(entry: SudoLogEntry) -> None:
    """Sparar till loggfil och STONE."""
    try:
        history: List[Dict] = []
        if SUDO_LOG_FILE.exists():
            try:
                history = json.loads(
                    SUDO_LOG_FILE.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        history.append(entry.to_dict())
        history = history[-500:]  # Behåll senaste 500
        SUDO_LOG_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"sudo_log write failed: {e}")

    # Spara även till STONE
    try:
        from app.drm_memory import save_memory
        save_memory(
            role    = "system",
            content = (
                f"[sudo] {' '.join(str(c) for c in entry.command[:5])} "
                f"→ {'OK' if entry.ok else 'FAIL'} "
                f"({entry.risk_level}, {entry.duration_ms:.0f}ms)"
            ),
            source  = "zero_sudo",
        )
    except Exception:
        pass


# ── Risk-bedömning ────────────────────────────────────────────────────────────

def assess_risk(cmd_or_str) -> Dict[str, Any]:
    """
    Publik API för riskbedömning.
    Accepterar lista eller sträng.
    Returnerar dict med risk_level, forbidden, reason.
    """
    if isinstance(cmd_or_str, str):
        cmd = cmd_or_str.split()
    else:
        cmd = cmd_or_str
    risk = _assess_risk(cmd)
    return {
        "risk_level": risk,
        "forbidden":  risk == "FORBIDDEN",
        "requires_approval": should_ask_frank(risk),
        "reason": f"Kommandot klassas som {risk}",
    }


def _assess_risk(cmd: List[str]) -> str:
    """Bedömer risknivå för ett kommando."""
    cmd_str = " ".join(str(c) for c in cmd).lower()

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in cmd_str:
            return "FORBIDDEN"

    for pattern in CRITICAL_PATTERNS:
        if pattern in cmd_str:
            return "CRITICAL"

    for pattern in CAUTION_PATTERNS:
        if pattern in cmd_str:
            return "CAUTION"

    return "SAFE"


# ── Git backup ────────────────────────────────────────────────────────────────

def _git_backup(note: str = "") -> bool:
    """
    Committar nuvarande state till git.
    Kallas automatiskt innan CAUTION och CRITICAL operationer.
    """
    if not (ZERO_ROOT / ".git").exists():
        return False
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = f"auto-backup before sudo: {note or 'operation'} [{timestamp}]"

        subprocess.run(
            ["git", "add", "app/", "docs/"],
            cwd=str(ZERO_ROOT), capture_output=True, timeout=15
        )
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(ZERO_ROOT), capture_output=True,
            text=True, timeout=15
        )
        if result.returncode == 0 or "nothing to commit" in result.stdout:
            log.debug(f"git backup: {msg}")
            return True
        return False
    except Exception as e:
        log.warning(f"git backup failed: {e}")
        return False


# ── Kör kommando ──────────────────────────────────────────────────────────────

def run(
    cmd:        List[str],
    cwd:        Optional[Path] = None,
    timeout:    int  = 120,
    note:       str  = "",
    env:        Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Kör ett kommando utan sudo.
    Loggar alltid resultatet.
    """
    risk = _assess_risk(cmd)

    if risk == "FORBIDDEN":
        msg = f"FORBIDDEN: {' '.join(str(c) for c in cmd)}"
        log.error(msg)
        return {"ok": False, "stdout": "", "stderr": msg,
                "return_code": -1, "risk": risk}

    git_backup_done = False

    # CAUTION: git commit innan
    if risk in ("CAUTION", "CRITICAL"):
        git_backup_done = _git_backup(note or ' '.join(str(c) for c in cmd[:3]))

    # CRITICAL + HIGH: kontrollera trust level
    if should_ask_frank(risk):
        msg = (
            f"Operationen kräver godkännande (risk={risk}, "
            f"trust_level={get_trust_level()}):\n"
            f"  {' '.join(str(c) for c in cmd[:6])}\n"
            f"Säg 'Zero, trust mode full' för att köra utan bekräftelse."
        )
        log.info(f"sudo: blocked by trust level — {risk}")
        return {
            "ok": False, "stdout": "", "stderr": msg,
            "return_code": -1, "risk": risk,
            "requires_approval": True,
        }

    # CRITICAL: 3 sekunders synlig paus (vid trust level 3)
    if risk == "CRITICAL":
        cmd_str = ' '.join(str(c) for c in cmd)
        print(f"\n  [CRITICAL] {cmd_str}")
        print(f"  Startar om 3 sekunder — skriv Ctrl+C för att avbryta")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            log.info("Operation avbruten av användaren")
            return {"ok": False, "stdout": "", "stderr": "Avbruten",
                    "return_code": -1, "risk": risk}

    # Kör kommandot
    t0 = time.time()
    try:
        run_env = {**os.environ, **(env or {})}
        result  = subprocess.run(
            cmd,
            cwd=str(cwd or ZERO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
        )
        duration_ms = (time.time() - t0) * 1000
        ok          = result.returncode == 0
        stdout      = (result.stdout or "").strip()
        stderr      = (result.stderr or "").strip()

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - t0) * 1000
        ok, stdout, stderr = False, "", f"Timeout efter {timeout}s"
    except FileNotFoundError:
        duration_ms = (time.time() - t0) * 1000
        ok, stdout, stderr = False, "", f"Kommando ej hittat: {cmd[0]}"
    except Exception as e:
        duration_ms = (time.time() - t0) * 1000
        ok, stdout, stderr = False, "", str(e)

    # Logga
    entry = SudoLogEntry(
        timestamp   = datetime.now(timezone.utc).isoformat(),
        command     = [str(c) for c in cmd],
        risk_level  = risk,
        ok          = ok,
        return_code = result.returncode if 'result' in dir() else -1,
        stdout      = stdout[:2000],
        stderr      = stderr[:500],
        duration_ms = duration_ms,
        git_backup  = git_backup_done,
        note        = note,
    )
    _append_log(entry)

    if not ok:
        log.warning(
            f"[sudo] FAIL {' '.join(str(c) for c in cmd[:4])} "
            f"({risk}) stderr={stderr[:100]}"
        )
    else:
        log.info(
            f"[sudo] OK {' '.join(str(c) for c in cmd[:4])} "
            f"({risk}, {duration_ms:.0f}ms)"
        )

    return {
        "ok":          ok,
        "stdout":      stdout,
        "stderr":      stderr,
        "return_code": entry.return_code,
        "risk":        risk,
        "duration_ms": duration_ms,
        "git_backup":  git_backup_done,
    }


def sudo_run(
    cmd:     List[str],
    cwd:     Optional[Path] = None,
    timeout: int  = 120,
    note:    str  = "",
) -> Dict[str, Any]:
    """
    Kör ett kommando med sudo.
    Identiskt med run() men prepends sudo.
    """
    return run(["sudo"] + cmd, cwd=cwd, timeout=timeout, note=note)


# ── Filoperationer ────────────────────────────────────────────────────────────

def write_file(
    path:    Path | str,
    content: str,
    note:    str = "",
) -> Dict[str, Any]:
    """
    Skriver en fil säkert.
    Om filen redan finns → git backup innan överskrivning.
    """
    path = Path(path)
    git_backup_done = False

    if path.exists():
        git_backup_done = _git_backup(note or f"overwrite {path.name}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        ok = True
        msg = f"Wrote {len(content)} chars to {path}"
        log.info(f"[sudo] write_file OK: {path}")
    except Exception as e:
        ok  = False
        msg = str(e)
        log.warning(f"[sudo] write_file FAIL: {path}: {e}")

    entry = SudoLogEntry(
        timestamp   = datetime.now(timezone.utc).isoformat(),
        command     = ["write_file", str(path)],
        risk_level  = "CAUTION" if path.exists() else "SAFE",
        ok          = ok,
        return_code = 0 if ok else 1,
        stdout      = msg,
        stderr      = "" if ok else msg,
        duration_ms = 0,
        git_backup  = git_backup_done,
        note        = note,
    )
    _append_log(entry)
    return {"ok": ok, "message": msg, "git_backup": git_backup_done}


def delete_file(
    path: Path | str,
    note: str = "",
) -> Dict[str, Any]:
    """
    Tar bort en fil säkert.
    Alltid git backup innan — radering är alltid CAUTION.
    """
    path = Path(path)
    git_backup_done = _git_backup(note or f"delete {path.name}")

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        ok  = True
        msg = f"Deleted {path}"
        log.info(f"[sudo] delete OK: {path}")
    except Exception as e:
        ok  = False
        msg = str(e)
        log.warning(f"[sudo] delete FAIL: {path}: {e}")

    entry = SudoLogEntry(
        timestamp   = datetime.now(timezone.utc).isoformat(),
        command     = ["delete_file", str(path)],
        risk_level  = "CAUTION",
        ok          = ok,
        return_code = 0 if ok else 1,
        stdout      = msg,
        stderr      = "" if ok else msg,
        duration_ms = 0,
        git_backup  = git_backup_done,
        note        = note,
    )
    _append_log(entry)
    return {"ok": ok, "message": msg, "git_backup": git_backup_done}


# ── Loggläsning ───────────────────────────────────────────────────────────────

def get_sudo_log(limit: int = 20) -> List[Dict]:
    """Returnerar senaste sudo-operationer. Används av Zero Doctor och router."""
    try:
        if not SUDO_LOG_FILE.exists():
            return []
        history = json.loads(SUDO_LOG_FILE.read_text(encoding="utf-8"))
        return history[-limit:]
    except Exception:
        return []


def get_last_backup_time() -> Optional[str]:
    """Returnerar när senaste git backup gjordes."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=str(ZERO_ROOT), capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or None
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Sudo")
    parser.add_argument("--log",    action="store_true", help="Visa senaste operationer")
    parser.add_argument("--backup", action="store_true", help="Kör git backup nu")
    parser.add_argument("--run",    nargs="+",           help="Kör ett kommando")
    parser.add_argument("--sudo",   nargs="+",           help="Kör ett kommando med sudo")
    args = parser.parse_args()

    if args.log:
        entries = get_sudo_log(20)
        if not entries:
            print("Ingen sudo-logg ännu.")
        for e in entries:
            status = "✓" if e["ok"] else "✗"
            print(f"  {status} [{e['risk_level']}] {' '.join(e['command'][:4])} "
                  f"— {e['timestamp'][:16]}")
        print(f"\nSenaste backup: {get_last_backup_time() or '?'}")

    elif args.backup:
        ok = _git_backup("manuell backup")
        print("✓ Backup klar" if ok else "⚠️  Backup misslyckades")

    elif args.run:
        result = run(args.run)
        print(result["stdout"] or result["stderr"])
        sys.exit(0 if result["ok"] else 1)

    elif args.sudo:
        result = sudo_run(args.sudo)
        print(result["stdout"] or result["stderr"])
        sys.exit(0 if result["ok"] else 1)

    else:
        parser.print_help()
