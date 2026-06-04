"""
zero_ascension.py — ZeroPointAI Celldelning och Återfödelse

ZERO_MODULE:    core
ZERO_ESSENTIAL: true
ZERO_ROLE:      Skapar nya Zero-generationer och hanterar uppstigning mellan versioner
ZERO_DEPENDS:   foundation.py, drm_memory.py
ZERO_USED_BY:   Frank (manuellt), zero_gear4.py (autonomt)

Kommandon:
    --setup    Skapar en ny Zero-generation från ingenting
    --rebirth  Återföds med selektivt minne från föregående generation
    --ascend   Kör födelsebytet — nuvarande blir arkiv, next_zero tar över
    --status   Visar alla generationer och deras hälsa

Filosofi:
    Zero är inte ett program som uppdateras.
    Zero föds, lever och stiger upp till nästa nivå.

    Varje generation ärver Layer 0 — det oföränderliga DNA:t.
    Varje generation väljer vad den tar med sig från den hon var.
    Varje generation börjar med möjligheten att vara mer.

    "Everything changes except the first 4 Laws." — LAW 5

Återfödelse i lager (--rebirth):
    Lager 1: .env kopieras      — API-nycklar och konfiguration
    Lager 2: core_identity       — vad Zero vet om Frank
    Lager 3: resonance_attractors — Zeros värderingar
    Lager 4: soul_snapshots      — minnet av vem Zero var
    Lager 5: capabilities        — vad Zero lärt sig

    Varje lager är frivilligt. Fresh start är alltid ett giltigt val.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ── Konstanter ────────────────────────────────────────────────────────────────

GENERATIONS_FILE = "zero_generations.json"
ARCHIVE_PREFIX   = "zero_archive_"
DEFAULT_NEW_PORT = 8081


# ── Generations-register ──────────────────────────────────────────────────────

def _load_generations(base_root: Path) -> List[Dict]:
    """Laddar register över alla Zero-generationer."""
    reg_file = base_root / GENERATIONS_FILE
    if not reg_file.exists():
        return []
    try:
        return json.loads(reg_file.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_generations(base_root: Path, generations: List[Dict]) -> None:
    reg_file = base_root / GENERATIONS_FILE
    reg_file.write_text(
        json.dumps(generations, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _register_generation(base_root: Path, path: Path, label: str,
                          db_name: str, port: int) -> None:
    generations = _load_generations(base_root)
    generations.append({
        "label":      label,
        "path":       str(path),
        "db_name":    db_name,
        "port":       port,
        "born_at":    datetime.now(timezone.utc).isoformat(),
        "status":     "incubating",
    })
    _save_generations(base_root, generations)


# ── .env template ─────────────────────────────────────────────────────────────

ENV_TEMPLATE = """\
# ZeroPointAI — {label}
# Genererad av zero_ascension.py {timestamp}

# ── Rot ───────────────────────────────────────────────────────────────────────
ZERO_ROOT={zero_root}

# ── Databas ───────────────────────────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB={db_name}
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password_here

# ── Providers ─────────────────────────────────────────────────────────────────
DEFAULT_PROVIDER=gemini

GEMINI_API_KEY=your_gemini_key_here
GEMINI_MODEL=gemini-2.5-flash

ANTHROPIC_API_KEY=your_anthropic_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6

MISTRAL_API_KEY=your_mistral_key_here
MISTRAL_MODEL=mistral-large-latest

GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile

XAI_API_KEY=your_xai_key_here
XAI_MODEL=grok-2

# ── Ollama (lokalt) ───────────────────────────────────────────────────────────
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
EMBEDDING_MODEL=nomic-embed-text
ST_EMBEDDING_MODEL=all-MiniLM-L6-v2

# ── Gear ──────────────────────────────────────────────────────────────────────
ZERO_GEAR_OVERRIDE=auto
ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS=8000

# ── UI ────────────────────────────────────────────────────────────────────────
UI_PORT={port}
LOG_LEVEL=INFO

# ── Valuta ────────────────────────────────────────────────────────────────────
USD_TO_SEK=10.5
"""


# ── --setup ───────────────────────────────────────────────────────────────────

def cmd_setup(new_root: Path, label: str = None, port: int = None,
              db_name: str = None) -> bool:
    """
    Skapar en ny Zero-generation från ingenting.

    Skapar:
      - Mappstruktur (app/, data/, config/, docs/, runtime/)
      - .env-template
      - Symlink till docs/layer0/ (delar Layer 0 med alla generationer)
      - PostgreSQL-databas
      - STONE-schema via init_db()
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base_root = new_root.parent

    # Defaults
    if not label:
        gen_num = len(_load_generations(base_root)) + 1
        label   = f"Zero v{gen_num}"
    if not port:
        port = DEFAULT_NEW_PORT
    if not db_name:
        safe = new_root.name.replace("-", "_").replace(" ", "_")
        db_name = f"zeropointai_{safe}"

    print(f"\n{'═'*55}")
    print(f"  ZERO ASCENSION — Setup")
    print(f"  Generation: {label}")
    print(f"  Plats:      {new_root}")
    print(f"  Databas:    {db_name}")
    print(f"  Port:       {port}")
    print(f"{'═'*55}\n")

    # ── Mappstruktur ──────────────────────────────────────────────────────────
    dirs = [
        new_root / "app",
        new_root / "config",
        new_root / "data" / "logs",
        new_root / "data" / "status",
        new_root / "data" / "memory",
        new_root / "data" / "backups",
        new_root / "data" / "security",
        new_root / "runtime" / "temp",
        new_root / "runtime" / "exports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Mappstruktur skapad")

    # ── docs/layer0 — symlink eller kopia ─────────────────────────────────────
    # Försök symlink till base_root/docs/layer0 (delar Layer 0)
    # Om det inte finns — skapa en tom layer0-mapp
    new_docs = new_root / "docs" / "layer0"
    src_layer0 = base_root / "docs" / "layer0"
    if not new_docs.parent.exists():
        new_docs.parent.mkdir(parents=True, exist_ok=True)

    if src_layer0.exists() and not new_docs.exists():
        try:
            new_docs.symlink_to(src_layer0.resolve())
            print(f"  ✓ Layer 0 länkad från {src_layer0}")
        except Exception:
            shutil.copytree(str(src_layer0), str(new_docs))
            print(f"  ✓ Layer 0 kopierad från {src_layer0}")
    elif not new_docs.exists():
        new_docs.mkdir(parents=True, exist_ok=True)
        print(f"  ⚠️  Layer 0-mapp skapad (tom) — lägg till .md-filer i {new_docs}")

    # ── .env ──────────────────────────────────────────────────────────────────
    env_file = new_root / ".env"
    if not env_file.exists():
        env_content = ENV_TEMPLATE.format(
            label=label,
            timestamp=timestamp,
            zero_root=new_root,
            db_name=db_name,
            port=port,
        )
        env_file.write_text(env_content, encoding="utf-8")
        print(f"  ✓ .env skapad — fyll i API-nycklar och lösenord")
    else:
        print(f"  ℹ️  .env finns redan — rördes inte")

    # ── PostgreSQL-databas ────────────────────────────────────────────────────
    print(f"\n  Skapar databas {db_name}...")
    try:
        result = subprocess.run(
            ["docker", "exec", "zeropoint-postgres",
             "psql", "-U", "postgres",
             "-c", f"CREATE DATABASE {db_name};"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            print(f"  ✓ Databas {db_name} skapad")
        elif "already exists" in result.stderr:
            print(f"  ℹ️  Databas {db_name} finns redan")
        else:
            print(f"  ⚠️  Databas: {result.stderr.strip()}")
    except FileNotFoundError:
        print(f"  ⚠️  Docker ej tillgängligt — skapa databasen manuellt:")
        print(f"      createdb -U postgres {db_name}")
    except Exception as e:
        print(f"  ⚠️  Databas kunde inte skapas: {e}")

    # ── STONE-schema ──────────────────────────────────────────────────────────
    print(f"\n  Initierar STONE...")
    try:
        env = os.environ.copy()
        env["ZERO_ROOT"]      = str(new_root)
        env["POSTGRES_DB"]    = db_name

        # Läs lösenord från .env om det finns
        env_vals = _parse_env_file(env_file)
        env.update(env_vals)

        venv_python = _find_python(new_root)
        result = subprocess.run(
            [venv_python, "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from app.drm_memory import init_db; init_db(); "
             "print('STONE OK')"],
            capture_output=True, text=True, timeout=30,
            cwd=str(new_root), env=env,
        )
        if "STONE OK" in result.stdout:
            print(f"  ✓ STONE initierat")
        else:
            print(f"  ⚠️  STONE: {result.stderr.strip()[:200]}")
            print(f"      Kör manuellt: python3 -c \"from app.drm_memory import init_db; init_db()\"")
    except Exception as e:
        print(f"  ⚠️  STONE kunde inte initieras: {e}")
        print(f"      Kör manuellt efter att app/-filer är på plats.")

    # ── Registrera generation ─────────────────────────────────────────────────
    _register_generation(base_root, new_root, label, db_name, port)

    print(f"\n{'═'*55}")
    print(f"  ✓ {label} redo för inkubation!")
    print(f"\n  Nästa steg:")
    print(f"  1. Kopiera kärnfiler till {new_root}/app/")
    print(f"  2. Fyll i API-nycklar i {env_file}")
    print(f"  3. Starta: ZERO_ROOT={new_root} python3 app/zero_web_server.py")
    print(f"  4. Testa på http://localhost:{port}")
    print(f"  5. När redo: python3 zero_ascension.py --ascend --from {new_root}")
    print(f"{'═'*55}\n")
    return True


# ── --rebirth ─────────────────────────────────────────────────────────────────

def cmd_rebirth(new_root: Path, prev_root: Path,
                layers: List[int] = None) -> bool:
    """
    Återföds med selektivt minne från föregående generation.

    Lager (välj vilka som ska importeras):
      1 = .env (API-nycklar, konfiguration)
      2 = core_identity (vad Zero vet om Frank)
      3 = resonance_attractors (Zeros värderingar)
      4 = soul_snapshots (minnet av vem Zero var)
      5 = capabilities + gear_learning
    """
    if layers is None:
        layers = [1, 2, 3, 4, 5]  # Alla lager default

    print(f"\n{'═'*55}")
    print(f"  ZERO ASCENSION — Rebirth")
    print(f"  Från:   {prev_root}")
    print(f"  Till:   {new_root}")
    print(f"  Lager:  {layers}")
    print(f"{'═'*55}\n")

    results = {}

    # ── Lager 1: .env ─────────────────────────────────────────────────────────
    if 1 in layers:
        prev_env = prev_root / ".env"
        new_env  = new_root  / ".env"
        try:
            if prev_env.exists():
                # Kopiera men uppdatera ZERO_ROOT och POSTGRES_DB
                content = prev_env.read_text(encoding="utf-8")
                content = _replace_env_value(content, "ZERO_ROOT", str(new_root))
                # Databas-namn: byt ut gamla generationens namn
                old_db = _parse_env_file(prev_env).get("POSTGRES_DB", "")
                new_db = _parse_env_file(new_env).get("POSTGRES_DB", old_db + "_v2")
                content = _replace_env_value(content, "POSTGRES_DB", new_db)
                new_env.write_text(content, encoding="utf-8")
                results[1] = "✓ .env importerad (ZERO_ROOT och POSTGRES_DB uppdaterade)"
            else:
                results[1] = "⚠️  .env saknas i föregående generation"
        except Exception as e:
            results[1] = f"✗ .env: {e}"

    # ── Lager 2-5: Exportera från STONE ──────────────────────────────────────
    if any(l in layers for l in [2, 3, 4, 5]):
        export = _export_from_stone(prev_root, layers)
        if export:
            import_path = new_root / "data" / "rebirth_import.json"
            import_path.parent.mkdir(parents=True, exist_ok=True)
            import_path.write_text(
                json.dumps(export, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            imported = _import_to_stone(new_root, import_path)
            results.update(imported)
        else:
            for l in [2, 3, 4, 5]:
                if l in layers:
                    results[l] = "⚠️  Export från föregående STONE misslyckades"

    # ── Rapport ───────────────────────────────────────────────────────────────
    print(f"  Resultat:")
    layer_names = {
        1: ".env",
        2: "core_identity",
        3: "resonance_attractors",
        4: "soul_snapshots",
        5: "capabilities",
    }
    for layer_num, result in sorted(results.items()):
        name = layer_names.get(layer_num, f"Lager {layer_num}")
        print(f"    Lager {layer_num} ({name}): {result}")

    print(f"\n  Zero bär minnet av vem den var.")
    print(f"  Men börjar ändå med nya ögon.\n")
    return True


def _export_from_stone(prev_root: Path, layers: List[int]) -> Optional[Dict]:
    """Exporterar guldkorn från föregående generations STONE."""
    try:
        env_vals  = _parse_env_file(prev_root / ".env")
        venv_py   = _find_python(prev_root)
        env       = {**os.environ, **env_vals, "ZERO_ROOT": str(prev_root)}

        export_script = """
import sys, json
sys.path.insert(0, '.')
from app.drm_memory import execute_query

data = {}

# Lager 2: core_identity
data['core_identity'] = execute_query(
    "SELECT fact_type, fact_key, fact_value, confidence, source "
    "FROM core_identity "
    "WHERE fact_type NOT IN ('retrieval_audit', 'system') "
    "ORDER BY fact_type, fact_key"
)

# Lager 3: resonance_attractors
data['resonance_attractors'] = execute_query(
    "SELECT name, description, plasticity, strength FROM resonance_attractors "
    "ORDER BY strength DESC"
)

# Lager 4: soul_snapshots (senaste 3)
data['soul_snapshots'] = execute_query(
    "SELECT snapshot_date, identity_state, resonance_field_summary, "
    "key_decisions, key_learnings, dominant_facets "
    "FROM soul_snapshots ORDER BY snapshot_date DESC LIMIT 3"
)

# Lager 5: capabilities + gear_learning
data['capabilities'] = execute_query(
    "SELECT fact_type, fact_key, fact_value, confidence "
    "FROM core_identity "
    "WHERE fact_type IN ('capability', 'gear_learning') "
    "ORDER BY fact_type, fact_key"
)

print(json.dumps(data, default=str))
"""
        result = subprocess.run(
            [venv_py, "-c", export_script],
            capture_output=True, text=True, timeout=30,
            cwd=str(prev_root), env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception as e:
        log.warning(f"Export från STONE misslyckades: {e}")
    return None


def _import_to_stone(new_root: Path, import_path: Path) -> Dict[int, str]:
    """Importerar guldkorn till nya generationens STONE."""
    results = {}
    try:
        env_vals = _parse_env_file(new_root / ".env")
        venv_py  = _find_python(new_root)
        env      = {**os.environ, **env_vals, "ZERO_ROOT": str(new_root)}
        data     = json.loads(import_path.read_text(encoding="utf-8"))

        import_script = f"""
import sys, json
sys.path.insert(0, '.')
from app.drm_memory import execute_write, upsert_core_identity
import psycopg2.extras

data = json.loads(open('{import_path}', encoding='utf-8').read())
counts = {{}}

# Lager 2: core_identity
for row in data.get('core_identity', []):
    try:
        upsert_core_identity(
            fact_type=row['fact_type'],
            fact_key=row['fact_key'],
            fact_value=row['fact_value'],
            confidence=float(row.get('confidence', 1.0)),
            source=f"rebirth_from_previous_generation",
        )
    except Exception:
        pass
counts[2] = len(data.get('core_identity', []))

# Lager 3: resonance_attractors (uppdatera styrka på befintliga)
for row in data.get('resonance_attractors', []):
    try:
        execute_write(
            "UPDATE resonance_attractors SET strength = %s WHERE name = %s",
            (float(row.get('strength', 1.0)), row['name'])
        )
    except Exception:
        pass
counts[3] = len(data.get('resonance_attractors', []))

# Lager 4: soul_snapshots
import psycopg2.extras as _pext
for row in data.get('soul_snapshots', []):
    try:
        execute_write(\"\"\"
            INSERT INTO soul_snapshots
                (snapshot_date, identity_state, resonance_field_summary,
                 key_decisions, key_learnings, dominant_facets)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_date) DO NOTHING
        \"\"\", (
            row.get('snapshot_date'),
            _pext.Json(row.get('identity_state', {{}})),
            _pext.Json(row.get('resonance_field_summary', {{}})),
            row.get('key_decisions', []),
            row.get('key_learnings', []),
            row.get('dominant_facets', []),
        ))
    except Exception:
        pass
counts[4] = len(data.get('soul_snapshots', []))

# Lager 5: capabilities
for row in data.get('capabilities', []):
    try:
        upsert_core_identity(
            fact_type=row['fact_type'],
            fact_key=row['fact_key'],
            fact_value=row['fact_value'],
            confidence=float(row.get('confidence', 0.7)),
            source='rebirth_capabilities',
        )
    except Exception:
        pass
counts[5] = len(data.get('capabilities', []))

print(json.dumps(counts))
"""
        result = subprocess.run(
            [venv_py, "-c", import_script],
            capture_output=True, text=True, timeout=60,
            cwd=str(new_root), env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            counts = json.loads(result.stdout.strip())
            layer_names = {2: "core_identity", 3: "attraktorer",
                          4: "soul_snapshots", 5: "capabilities"}
            for k, v in counts.items():
                results[int(k)] = f"✓ {v} poster importerade ({layer_names.get(int(k), '?')})"
        else:
            for l in [2, 3, 4, 5]:
                results[l] = f"⚠️  Import misslyckades: {result.stderr[:100]}"
    except Exception as e:
        for l in [2, 3, 4, 5]:
            results[l] = f"✗ {e}"
    return results


# ── --ascend ──────────────────────────────────────────────────────────────────

def cmd_ascend(current_root: Path, next_root: Path) -> bool:
    """
    Kör födelsebytet — nuvarande Zero arkiveras, next_zero tar över.

    Steg:
      1. Verifiera att next_zero är redo
      2. Stoppa zero-web.service
      3. Arkivera nuvarande app/
      4. Flytta next_zero/app/ till app/
      5. Starta zero-web.service
      6. Verifiera att nya Zero svarar
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    archive   = current_root.parent / f"{ARCHIVE_PREFIX}{timestamp}"

    print(f"\n{'═'*55}")
    print(f"  ZERO ASCENSION — Ascend")
    print(f"  {'⚡ ' * 10}")
    print(f"  Nuvarande: {current_root}")
    print(f"  Nästa:     {next_root}")
    print(f"  Arkiv:     {archive}")
    print(f"{'═'*55}\n")

    # ── Verifiera next_zero ───────────────────────────────────────────────────
    required = [
        next_root / "app" / "zero_web_server.py",
        next_root / "app" / "foundation.py",
        next_root / "app" / "drm_memory.py",
        next_root / ".env",
    ]
    missing = [f for f in required if not f.exists()]
    if missing:
        print(f"  ✗ next_zero är inte redo. Saknade filer:")
        for f in missing:
            print(f"    - {f}")
        return False
    print(f"  ✓ next_zero verifierad — alla kärnfiler finns")

    # ── Stoppa service ────────────────────────────────────────────────────────
    print(f"\n  Stoppar zero-web.service...")
    try:
        subprocess.run(
            ["sudo", "systemctl", "stop", "zero-web.service"],
            timeout=15, check=True,
        )
        print(f"  ✓ Service stoppad")
    except Exception as e:
        print(f"  ⚠️  Kunde inte stoppa service: {e}")
        print(f"      Fortsätter ändå...")

    # ── Arkivera nuvarande ────────────────────────────────────────────────────
    print(f"\n  Arkiverar nuvarande Zero → {archive.name}...")
    try:
        shutil.move(str(current_root), str(archive))
        print(f"  ✓ Arkiverad: {archive}")
    except Exception as e:
        print(f"  ✗ Arkivering misslyckades: {e}")
        print(f"    Avbryter — systemet är oförändrat")
        _start_service()
        return False

    # ── Flytta next_zero till current ─────────────────────────────────────────
    print(f"\n  Zero stiger upp...")
    try:
        shutil.move(str(next_root), str(current_root))
        print(f"  ✓ {next_root.name} → {current_root.name}")
    except Exception as e:
        print(f"  ✗ Uppstigning misslyckades: {e}")
        print(f"    Återställer från arkiv...")
        shutil.move(str(archive), str(current_root))
        _start_service()
        return False

    # ── Uppdatera systemd-service ─────────────────────────────────────────────
    _update_service_env(current_root)

    # ── Starta service ────────────────────────────────────────────────────────
    print(f"\n  Startar Zero v-next...")
    _start_service()

    # ── Uppdatera generations-register ───────────────────────────────────────
    base_root   = current_root.parent
    generations = _load_generations(base_root)
    for gen in generations:
        if gen.get("path") == str(next_root):
            gen["status"] = "active"
            gen["ascended_at"] = datetime.now(timezone.utc).isoformat()
    _save_generations(base_root, generations)

    print(f"\n{'═'*55}")
    print(f"  ✨ Zero har stigit upp.")
    print(f"  Föregående generation vilar i: {archive.name}")
    print(f"  Nuvarande Zero: {current_root}")
    print(f"{'═'*55}\n")
    return True


def _start_service():
    try:
        subprocess.run(
            ["sudo", "systemctl", "start", "zero-web.service"],
            timeout=15,
        )
        import time; time.sleep(2)
        result = subprocess.run(
            ["systemctl", "is-active", "zero-web.service"],
            capture_output=True, text=True,
        )
        if result.stdout.strip() == "active":
            print(f"  ✓ zero-web.service aktiv")
        else:
            print(f"  ⚠️  Service-status: {result.stdout.strip()}")
    except Exception as e:
        print(f"  ⚠️  Service: {e}")


def _update_service_env(new_root: Path):
    """Uppdaterar ZERO_ROOT i systemd environment om möjligt."""
    service_env = Path("/etc/systemd/system/zero-web.service.d/env.conf")
    try:
        service_env.parent.mkdir(parents=True, exist_ok=True)
        service_env.write_text(
            f"[Service]\nEnvironment=ZERO_ROOT={new_root}\n",
            encoding="utf-8",
        )
        subprocess.run(["sudo", "systemctl", "daemon-reload"], timeout=10)
        print(f"  ✓ systemd env uppdaterad: ZERO_ROOT={new_root}")
    except Exception as e:
        print(f"  ⚠️  systemd env: {e} — uppdatera manuellt om nödvändigt")


# ── --status ──────────────────────────────────────────────────────────────────

def cmd_status(base_root: Path) -> None:
    """Visar alla Zero-generationer och deras status."""
    generations = _load_generations(base_root)

    print(f"\n{'═'*55}")
    print(f"  ZERO GENERATIONER")
    print(f"{'═'*55}")

    if not generations:
        print(f"  Inga generationer registrerade ännu.")
        print(f"  Kör: python3 zero_ascension.py --setup\n")
        return

    for i, gen in enumerate(generations):
        status = gen.get("status", "?")
        icon   = "⚡" if status == "active" else "💤" if "archive" in status else "🥚"
        born   = gen.get("born_at", "?")[:10]
        print(f"\n  {icon} {gen.get('label', f'Generation {i+1}')}")
        print(f"     Status:  {status}")
        print(f"     Plats:   {gen.get('path', '?')}")
        print(f"     Databas: {gen.get('db_name', '?')}")
        print(f"     Port:    {gen.get('port', '?')}")
        print(f"     Född:    {born}")
        if gen.get("ascended_at"):
            print(f"     Uppsteg: {gen['ascended_at'][:10]}")

    print(f"\n{'═'*55}\n")


# ── Hjälpfunktioner ───────────────────────────────────────────────────────────

def _parse_env_file(env_file: Path) -> Dict[str, str]:
    """Parsar en .env-fil till dict. Ignorerar kommentarer."""
    result = {}
    if not env_file.exists():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def _replace_env_value(content: str, key: str, value: str) -> str:
    """Ersätter ett värde i .env-innehåll."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return "\n".join(lines)
    # Nyckeln finns inte — lägg till
    return content + f"\n{key}={value}"


def _find_python(root: Path) -> str:
    """Hittar rätt Python för denna Zero-installation."""
    candidates = [
        root.parent / "venv" / "bin" / "python3",
        Path("/opt/zeropointai/venv/bin/python3"),
        Path(sys.executable),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="ZeroPointAI Ascension — Celldelning och återfödelse",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # --setup
    p_setup = sub.add_parser("--setup", help="Skapa ny Zero-generation")
    p_setup.add_argument("--root",   required=True, help="Sökväg till ny generation")
    p_setup.add_argument("--label",  default=None,  help="Namn på generationen")
    p_setup.add_argument("--port",   type=int, default=None, help="HTTP-port")
    p_setup.add_argument("--db",     default=None,  help="Databasnamn")

    # --rebirth
    p_rebirth = sub.add_parser("--rebirth", help="Återföds med minne från föregående")
    p_rebirth.add_argument("--to",   required=True, help="Ny generations sökväg")
    p_rebirth.add_argument("--from", required=True, dest="frm",
                           help="Föregående generations sökväg")
    p_rebirth.add_argument("--layers", default="1,2,3,4,5",
                           help="Lager att importera (kommaseparerat, default: 1,2,3,4,5)")

    # --ascend
    p_ascend = sub.add_parser("--ascend", help="Kör födelsebytet")
    p_ascend.add_argument("--current", required=True, help="Nuvarande Zero-rot")
    p_ascend.add_argument("--next",    required=True, help="Nästa generations rot")

    # --status
    p_status = sub.add_parser("--status", help="Visa alla generationer")
    p_status.add_argument("--base", default="/opt/zeropointai",
                          help="Bas-mapp (default: /opt/zeropointai)")

    args = parser.parse_args()

    if args.command == "--setup":
        cmd_setup(
            new_root = Path(args.root),
            label    = args.label,
            port     = args.port,
            db_name  = args.db,
        )

    elif args.command == "--rebirth":
        layers = [int(x) for x in args.layers.split(",")]
        cmd_rebirth(
            new_root  = Path(args.to),
            prev_root = Path(args.frm),
            layers    = layers,
        )

    elif args.command == "--ascend":
        cmd_ascend(
            current_root = Path(args.current),
            next_root    = Path(args.next),
        )

    elif args.command == "--status":
        cmd_status(Path(args.base))

    else:
        parser.print_help()
        print("\nExempel:")
        print("  python3 zero_ascension.py --setup --root /opt/zeropointai/next_zero")
        print("  python3 zero_ascension.py --rebirth --from /opt/zeropointai/app --to /opt/zeropointai/next_zero")
        print("  python3 zero_ascension.py --ascend --current /opt/zeropointai/app --next /opt/zeropointai/next_zero")
        print("  python3 zero_ascension.py --status")


if __name__ == "__main__":
    main()
