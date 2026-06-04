"""
foundation.py — ZeroPointAI Ground Truth

Systemets enda källa till:
  - Layer 0 (vad Zero är — läst från docs/layer0/)
  - Kanoniska sökvägar (var allt finns)
  - Checksumma-verifiering (att Layer 0 är oförändrad)

Celldelning:
  Sätt ZERO_ROOT=/opt/zeropointai/next_zero i .env
  — hela systemet följer med utan att en rad kod ändras.

Regler:
  - Denna fil importerar INGENTING från systemet
  - Alla andra filer importerar härifrån
  - Ingen annan fil hårdkodar sökvägar eller lagnummer

Användning:
    from app.foundation import (
        ZERO_ROOT, APP_DIR, DATA_DIR, LAYER0_DIR,
        LAYER0_FULL, LAYER0_CHECKSUM,
        LAYER0_SECTIONS,
        verify_layer0, accept_layer0_change,
    )

ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Sökvägar + Layer 0. Enda sanningskällan. Importerar inget från systemet.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# ── Rot — allt utgår härifrån ─────────────────────────────────────────────────

ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

# ── Kanoniska sökvägar ────────────────────────────────────────────────────────
# Alla sökvägar i systemet ska härledas härifrån.
# Ingen annan fil hårdkodar /opt/zeropointai eller D:\ZeroPointAI.

APP_DIR      = ZERO_ROOT / "app"
CONFIG_DIR   = ZERO_ROOT / "config"
DATA_DIR     = ZERO_ROOT / "data"
DOCS_DIR     = ZERO_ROOT / "docs"
TOOLS_DIR    = ZERO_ROOT / "tools"
RUNTIME_DIR  = ZERO_ROOT / "runtime"
UI_DIR       = ZERO_ROOT / "ui"

# Data-undermappar
LOGS_DIR     = DATA_DIR / "logs"
STATUS_DIR   = DATA_DIR / "status"
MEMORY_DIR   = DATA_DIR / "memory"
CACHE_DIR    = DATA_DIR / "cache"
BACKUPS_DIR  = DATA_DIR / "backups"
SECURITY_DIR = DATA_DIR / "security"

# Runtime
TEMP_DIR     = RUNTIME_DIR / "temp"
EXPORTS_DIR  = RUNTIME_DIR / "exports"

# Layer 0
LAYER0_DIR     = DOCS_DIR / "layer0"
CHECKSUM_FILE  = DATA_DIR / "layer0_checksum.json"

# Viktiga filer
ENV_FILE              = ZERO_ROOT / ".env"
REQUIREMENTS_FILE     = ZERO_ROOT / "requirements.txt"
DOCTOR_STATUS_FILE    = STATUS_DIR / "doctor_status.json"
PENDING_ACTIONS_FILE  = STATUS_DIR / "pending_actions.json"
MEMORY_GUARD_FILE     = STATUS_DIR / "memory_guard_state.json"


def ensure_directories() -> None:
    """Skapar alla nödvändiga mappar. Säker att köra upprepade gånger."""
    dirs = [
        APP_DIR, CONFIG_DIR, DATA_DIR, DOCS_DIR,
        LOGS_DIR, STATUS_DIR, MEMORY_DIR, CACHE_DIR,
        BACKUPS_DIR, SECURITY_DIR, RUNTIME_DIR,
        TEMP_DIR, EXPORTS_DIR, LAYER0_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def print_paths() -> None:
    """Debug: skriv ut alla sökvägar."""
    print(f"{'='*40}")
    print(f"ZERO_ROOT : {ZERO_ROOT}")
    print(f"APP_DIR   : {APP_DIR}")
    print(f"DATA_DIR  : {DATA_DIR}")
    print(f"DOCS_DIR  : {DOCS_DIR}")
    print(f"LAYER0_DIR: {LAYER0_DIR}")
    print(f"STATUS_DIR: {STATUS_DIR}")
    print(f"{'='*40}")


# ── Layer 0 — läs från disk ───────────────────────────────────────────────────

def _read_layer0() -> dict[str, str]:
    """
    Läser alla .md-filer i layer0/ och returnerar {filename: content}.
    Sorteringsordning avgör prioritet — 00_ före 01_ etc.
    Filnamn spelar ingen roll — alla .md inkluderas automatiskt.
    """
    if not LAYER0_DIR.exists():
        raise FileNotFoundError(
            f"layer0 saknas: {LAYER0_DIR}\n"
            f"Skapa {LAYER0_DIR}/ med .md-filer (REALITY, COMPASS, MIRROR etc.)"
        )
    files = sorted(LAYER0_DIR.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"Inga .md-filer i {LAYER0_DIR}")
    return {f.name: f.read_text(encoding="utf-8").strip() for f in files}


def _compute_checksum(contents: dict[str, str]) -> str:
    """SHA256 av alla layer0-filer i sorteringsordning."""
    h = hashlib.sha256()
    for name in sorted(contents):
        h.update(name.encode("utf-8"))
        h.update(contents[name].encode("utf-8"))
    return h.hexdigest()


# ── Checksumma-verifiering ────────────────────────────────────────────────────

def save_checksum(checksum: str) -> None:
    """Sparar känd checksumma. Körs vid setup eller godkänd ändring."""
    CHECKSUM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUM_FILE.write_text(
        json.dumps({"layer0_sha256": checksum}, indent=2),
        encoding="utf-8",
    )


def load_checksum() -> str | None:
    if not CHECKSUM_FILE.exists():
        return None
    try:
        return json.loads(CHECKSUM_FILE.read_text(encoding="utf-8"))["layer0_sha256"]
    except Exception:
        return None


def verify_layer0(contents: dict[str, str], strict: bool = False) -> bool:
    """
    Verifierar layer0 mot sparad checksumma.

    strict=False: loggar varning men fortsätter (default).
    strict=True:  SystemExit om checksumman inte stämmer.

    Första körningen: sparar och godkänner automatiskt.
    """
    current = _compute_checksum(contents)
    known   = load_checksum()

    if known is None:
        save_checksum(current)
        print(f"[foundation] Layer 0 initierad. SHA256: {current[:16]}...", file=__import__('sys').stderr)
        return True

    if current == known:
        return True

    msg = (
        f"\n{'═'*60}\n"
        f"  VARNING: Layer 0 har ändrats!\n"
        f"  Förväntad: {known[:16]}...\n"
        f"  Nuvarande: {current[:16]}...\n"
        f"\n"
        f"  Godkänn ändringen med:\n"
        f"    python -c \"from app.foundation import accept_layer0_change; "
        f"accept_layer0_change()\"\n"
        f"{'═'*60}\n"
    )
    print(msg, file=sys.stderr)

    if strict:
        sys.exit(1)
    return False


def accept_layer0_change() -> None:
    """
    Godkänner en ändring i layer0.
    Anropas manuellt av Frank efter granskning.
    """
    contents = _read_layer0()
    checksum = _compute_checksum(contents)
    save_checksum(checksum)
    print(f"[foundation] Layer 0-ändring godkänd. Ny SHA256: {checksum[:16]}...", file=__import__('sys').stderr)


# ── Ladda och exponera ────────────────────────────────────────────────────────
# Körs vid import. Graceful degradation om layer0 saknas.

LAYER0_SECTIONS: dict[str, str] = {}   # {filename: content} — alla sektioner
LAYER0_FULL:     str = ""              # Allt sammanslaget för system-prompter
LAYER0_CHECKSUM: str = ""              # SHA256 av nuvarande layer0

# Namngivna sektioner — fylls dynamiskt baserat på vad som finns i layer0/
# Inga hårdkodade filnamn — Zero läser vad som finns
REALITY: str = ""
COMPASS: str = ""
MIRROR:  str = ""

# Bakåtkompatibilitet — COHERENCE_FORMULA är nu COMPASS
COHERENCE_FORMULA: str = ""

try:
    _contents = _read_layer0()
    verify_layer0(_contents, strict=False)

    LAYER0_SECTIONS = _contents
    LAYER0_CHECKSUM = _compute_checksum(_contents)

    # Bygg LAYER0_FULL dynamiskt från alla filer — oavsett namn eller antal
    parts = []
    for filename, content in sorted(_contents.items()):
        # Sektion-rubrik baserad på filnamn utan nummer och extension
        # "00_REALITY.md" → "REALITY", "COMPASS.md" → "COMPASS"
        label = filename.replace(".md", "")
        label = label.split("_", 1)[-1] if "_" in label else label
        parts.append(f"=== {label.upper()} ===\n{content}")

    LAYER0_FULL = "\n\n".join(parts)

    # Exponera namngivna sektioner om de finns — inga krav
    REALITY  = _contents.get("00_REALITY.md", "")
    COMPASS  = _contents.get("COMPASS.md", "")
    MIRROR   = _contents.get("02_MIRROR.md", "")

    # Bakåtkompatibilitet
    COHERENCE_FORMULA = COMPASS or _contents.get("01_COHERENCE FORMULA.md", "")

    if LAYER0_FULL:
        print(f"[foundation] Layer 0 laddad — "
              f"{len(_contents)} sektioner, "
              f"SHA256: {LAYER0_CHECKSUM[:16]}...",
              file=__import__('sys').stderr)

except FileNotFoundError as e:
    print(f"[foundation] KRITISK: {e}", file=sys.stderr)


# ── Systeminfo ────────────────────────────────────────────────────────────────

def get_system_info() -> dict:
    """
    Returnerar systemets kanoniska info.
    Används av zero_portability.py, zero_doctor.py, diagnostik.
    """
    return {
        "zero_root":        str(ZERO_ROOT),
        "app_dir":          str(APP_DIR),
        "data_dir":         str(DATA_DIR),
        "layer0_dir":       str(LAYER0_DIR),
        "layer0_sections":  list(LAYER0_SECTIONS.keys()),
        "layer0_checksum":  LAYER0_CHECKSUM[:16] + "..." if LAYER0_CHECKSUM else "",
        "layer0_available": bool(LAYER0_FULL),
        "env_file":         str(ENV_FILE),
    }


# ── Kör ensure_directories automatiskt vid import ─────────────────────────────
# Säkerställer att mappstrukturen finns oavsett om det är fresh start eller ej.

ensure_directories()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print_paths()
    print()
    info = get_system_info()
    print(f"Layer 0 tillgänglig: {info['layer0_available']}")
    print(f"Sektioner: {info['layer0_sections']}")
    print(f"Checksumma: {info['layer0_checksum']}")
    if LAYER0_FULL:
        print(f"\n{'─'*40}")
        print(LAYER0_FULL[:500] + ("..." if len(LAYER0_FULL) > 500 else ""))
