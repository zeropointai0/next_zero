"""
zero_monitor.py — ZeroPointAI System Monitor

Realtidsövervakning av hela Zero-stacken.
Uppdateras var 2:a sekund.

Kör direkt: python scripts/zero_monitor.py
Avsluta:    Ctrl+C

ZERO_MODULE:    health
ZERO_LAYER:     2
ZERO_ESSENTIAL: false
ZERO_ROLE:      Realtidsövervakning — CPU, RAM, GPU, databas, Ollama, Docker
ZERO_DEPENDS:   foundation.py
ZERO_USED_BY:   Frank (manuellt), zero_gear4.py
"""

import os
from pathlib import Path
import sys
import json
import time
import shutil
import socket
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import psycopg2
import psycopg2.extras
import psutil

# ── Konfiguration ──────────────────────────────────────────────────────────────

VERSION        = "2.0"
try:
    from app.foundation import ZERO_ROOT, STATUS_DIR
    STATUS_FILE = STATUS_DIR / "zero_status.json"
except ImportError:
    ZERO_ROOT   = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    STATUS_DIR  = ZERO_ROOT / "data" / "status"
    STATUS_FILE = STATUS_DIR / "zero_status.json"
ZERO_ROOT = str(ZERO_ROOT)

DB_HOST        = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT        = int(os.getenv("POSTGRES_PORT", 5432))
DB_NAME        = os.getenv("POSTGRES_DB", "zeropointai")
DB_USER        = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD    = os.getenv("POSTGRES_PASSWORD", "")
DB_TIMEOUT     = 3

OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen3:4b")
PROVIDER       = os.getenv("DEFAULT_PROVIDER", "ollama")
REFRESH        = 2.0

# ── Helpers ────────────────────────────────────────────────────────────────────

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def fmt_s(v):
    try:    return f"{float(v):.3f}s" if v is not None else "n/a"
    except: return "n/a"

def fmt_pct(v):
    try:    return f"{float(v):.1f}%" if v is not None else "n/a"
    except: return "n/a"

def fmt_gb(b):
    try:    return f"{b / (1024**3):.2f} GB" if b is not None else "n/a"
    except: return "n/a"

def truncate(text, n=100):
    if not text: return "n/a"
    text = str(text).replace("\n", " ").strip()
    return text[:n-3] + "..." if len(text) > n else text

def port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except: return False

def run_cmd(cmd, timeout=4):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return (r.returncode == 0), (out or err or f"exit {r.returncode}")
    except FileNotFoundError: return False, "command not found"
    except subprocess.TimeoutExpired: return False, "timeout"
    except Exception as e: return False, str(e)

def safe_json(path):
    try:
        if not os.path.exists(path): return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

# ── Data-insamling ─────────────────────────────────────────────────────────────

def get_system():
    cpu = psutil.cpu_percent(interval=0.2)
    vm  = psutil.virtual_memory()
    drive = ZERO_ROOT if os.path.exists(ZERO_ROOT) else os.sep
    try:    disk = shutil.disk_usage(drive)
    except: disk = None
    return {
        "cpu": cpu,
        "ram_pct": vm.percent,
        "ram_used": vm.used,
        "ram_total": vm.total,
        "disk_free": disk.free if disk else None,
        "disk_total": disk.total if disk else None,
        "disk_path": drive,
    }

def get_gpu():
    ok, out = run_cmd([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits"
    ], timeout=3)
    if not ok or not out:
        return {"available": False, "error": out or "nvidia-smi ej tillgänglig"}
    try:
        p = [x.strip() for x in out.splitlines()[0].split(",")]
        return {
            "available": True,
            "name": p[0],
            "util": float(p[1]),
            "mem_used": int(p[2]),
            "mem_total": int(p[3]),
            "temp": int(p[4]),
        }
    except:
        return {"available": False, "error": "parse-fel"}

def get_ollama():
    port_ok = port_open("localhost", 11434)
    ps_ok, ps_out = run_cmd(["ollama", "ps"], timeout=4)

    loaded = None
    if ps_ok and ps_out:
        for line in ps_out.splitlines()[1:]:
            if line.strip():
                loaded = line.split()[0]
                break

    # Kolla om konfigurerad modell är installerad
    list_ok, list_out = run_cmd(["ollama", "list"], timeout=4)
    model_installed = OLLAMA_MODEL in list_out if list_ok else None

    return {
        "port_ok": port_ok,
        "ps_ok": ps_ok,
        "loaded": loaded,
        "configured_model": OLLAMA_MODEL,
        "model_installed": model_installed,
    }

def get_docker():
    ok, out = run_cmd(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=4)
    if not ok:
        return {"ok": False, "containers": [], "error": out}
    containers = []
    for line in out.splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            containers.append({"name": name.strip(), "status": status.strip()})
    return {"ok": True, "containers": containers, "error": None}

def get_db():
    if not port_open(DB_HOST, DB_PORT):
        return {"ok": False, "error": f"Port {DB_HOST}:{DB_PORT} stängd", "counts": {}, "total": None, "last_user": None, "last_assistant": None}

    conn = cur = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD, connect_timeout=DB_TIMEOUT
        )
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM memories")
        total = cur.fetchone()[0]

        cur.execute("SELECT role, COUNT(*) FROM memories GROUP BY role ORDER BY role")
        counts = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("SELECT content, created_at FROM memories WHERE role='user' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        last_user = {"content": row[0], "at": row[1]} if row else None

        cur.execute("SELECT content, created_at FROM memories WHERE role='assistant' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        last_assistant = {"content": row[0], "at": row[1]} if row else None

        return {"ok": True, "error": None, "total": total, "counts": counts, "last_user": last_user, "last_assistant": last_assistant}

    except Exception as e:
        return {"ok": False, "error": str(e), "counts": {}, "total": None, "last_user": None, "last_assistant": None}
    finally:
        if cur:  cur.close()
        if conn: conn.close()

# ── Rendering ──────────────────────────────────────────────────────────────────

def bar(pct, width=20):
    """Enkel ASCII-bar för CPU/RAM."""
    try:
        filled = int(float(pct) / 100 * width)
        return "[" + "█" * filled + "░" * (width - filled) + f"] {pct:.1f}%"
    except:
        return "[" + "░" * width + "] n/a"

def status_dot(ok):
    return "●" if ok else "○"

def render(sys_s, gpu_s, ollama_s, docker_s, db_s):
    clear_screen()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"╔══════════════════════════════════════════════════════════════════════╗")
    print(f"║  Zero Monitor v{VERSION}                              {now}  ║")
    print(f"╚══════════════════════════════════════════════════════════════════════╝")
    print()

    # --- Tjänster ---
    db_dot     = status_dot(db_s["ok"])
    ollama_dot = status_dot(ollama_s["port_ok"])
    docker_dot = status_dot(docker_s["ok"])
    pg_str     = f"{db_dot} PostgreSQL"
    ol_str     = f"{ollama_dot} Ollama ({ollama_s['configured_model']})"
    dk_str     = f"{docker_dot} Docker"

    print(f"  TJÄNSTER    {pg_str:<28} {ol_str:<32} {dk_str}")
    print()

    # --- System ---
    print(f"  SYSTEM")
    print(f"  CPU   {bar(sys_s['cpu'])}")
    print(f"  RAM   {bar(sys_s['ram_pct'])}  ({fmt_gb(sys_s['ram_used'])} / {fmt_gb(sys_s['ram_total'])})")
    print(f"  Disk  {fmt_gb(sys_s['disk_free'])} ledigt på {sys_s['disk_path']}")

    if gpu_s.get("available"):
        print(f"  GPU   {gpu_s['name']}  |  {fmt_pct(gpu_s['util'])}  |  {gpu_s['mem_used']} / {gpu_s['mem_total']} MB  |  {gpu_s['temp']}°C")
    else:
        print(f"  GPU   ej tillgänglig")
    print()

    # --- Ollama ---
    print(f"  OLLAMA")
    loaded = ollama_s.get("loaded") or "ingen modell laddad"
    installed = "✓" if ollama_s.get("model_installed") else "✗ ej installerad"
    print(f"  Konfigurerad modell:  {ollama_s['configured_model']} ({installed})")
    print(f"  Aktiv i minnet:       {loaded}")
    print()

    # --- Docker containers ---
    print(f"  DOCKER CONTAINERS")
    containers = docker_s.get("containers", [])
    if containers:
        for c in containers[:6]:
            dot = "●" if "Up" in c["status"] else "○"
            print(f"  {dot} {c['name']:<35} {c['status']}")
    else:
        print(f"  ○ inga containers körande")
    print()

    # --- Minne ---
    print(f"  MINNESDATABAS")
    if db_s["ok"]:
        counts = db_s["counts"]
        total  = db_s["total"]
        parts  = [f"{role}: {n}" for role, n in sorted(counts.items())]
        print(f"  Totalt: {total}  |  {' | '.join(parts) if parts else 'tomt'}")
        if db_s["last_user"]:
            print(f"  Senaste user:      {truncate(db_s['last_user']['content'], 90)}")
        if db_s["last_assistant"]:
            print(f"  Senaste assistant: {truncate(db_s['last_assistant']['content'], 90)}")
    else:
        print(f"  Fel: {db_s['error']}")
    print()

    # --- Provider ---
    print(f"  AKTIV PROVIDER: {PROVIDER.upper()}")
    print()

    # --- Varningar ---
    notes = []
    if not db_s["ok"]:        notes.append(f"PostgreSQL: {db_s['error']}")
    if not ollama_s["port_ok"]: notes.append("Ollama svarar inte på port 11434")
    if not docker_s["ok"]:    notes.append(f"Docker: {docker_s['error']}")
    if ollama_s.get("model_installed") is False:
        notes.append(f"Modell '{OLLAMA_MODEL}' ej installerad — kör: ollama pull {OLLAMA_MODEL}")

    if notes:
        print(f"  VARNINGAR")
        for n in notes:
            print(f"  ⚠  {n}")
        print()

    print(f"  Ctrl+C för att avsluta  |  Uppdateras var {REFRESH}s")

# ── Huvudloop ──────────────────────────────────────────────────────────────────

def main():
    os.makedirs(STATUS_DIR, exist_ok=True)

    # Installera psutil om det saknas
    try:
        import psutil
    except ImportError:
        print("Installerar psutil...")
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], check=True)
        import psutil

    while True:
        try:
            render(
                sys_s    = get_system(),
                gpu_s    = get_gpu(),
                ollama_s = get_ollama(),
                docker_s = get_docker(),
                db_s     = get_db(),
            )
            time.sleep(REFRESH)
        except KeyboardInterrupt:
            print("\nZero Monitor stoppad.")
            break
        except Exception as e:
            clear_screen()
            print(f"Zero Monitor kraschade: {e}")
            print("Försöker igen om 3 sekunder...")
            time.sleep(3)

if __name__ == "__main__":
    main()
