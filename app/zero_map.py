#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_map.py — ZeroPointAI System Map Generator

One-file observability/context exporter for ZeroPointAI.
It maps system state into Markdown or JSON so Zero, an assistant, or Zero Doctor
can understand the machine without leaking secrets.

Examples:
    cd /opt/zeropointai
    python3 app/zero_map.py --list-profiles
    python3 app/zero_map.py --profile ai
    python3 app/zero_map.py --profile gpu --out /tmp/zero_gpu.md
    python3 app/zero_map.py --profile doctor-context --format json --out /tmp/zero_doctor_context.json
    python3 app/zero_map.py --auto --out /tmp/zero_auto.md

Design:
    zero_map.py    = observes / maps / exports context
    zero_doctor.py = diagnoses / recommends / repairs
    foundation.py  = Layer 0, checksumma, sökvägar — sanningskällan

ZERO / AI STARTUP GUIDE:
    If a potential problem is detected, start by asking zero_map.py what context is needed.

    Recommended flow:
        1. Run: python3 app/zero_map.py --recommend "<problem description>"
        2. Run the recommended profile(s).
        3. Give the resulting map/context to Zero Doctor.
        4. Zero Doctor may then diagnose, propose, or perform repairs according to its permissions.
        5. foundation.py verifierar Layer 0-integritet vid varje uppstart.

    Important:
        zero_map.py must not repair anything.
        zero_map.py must not mutate system files.
        zero_map.py is a safe observer and context exporter.

PROFILE GUIDE:
    fast            -> small general status snapshot.
    ai              -> providers, routing, Ollama, models, AI modules.
    gpu             -> NVIDIA, CUDA, VRAM, PyTorch, GPU runtime.
    memory          -> PostgreSQL, pgvector, STONE memory, DB size, memory logs.
    security        -> secrets status, permissions, exposed ports, foundation status.
    runtime         -> live processes, RAM, load, resources.
    dependencies    -> Python packages, pip check, pip freeze, dependency tree.
    docker          -> Docker containers, Postgres/Ollama containers, stats.
    network         -> ports, sockets, interfaces, listening services.
    logs            -> recent systemd/project logs.
    doctor-context  -> patient journal for Zero Doctor. Broad diagnostic context.
    full            -> everything guarded/truncated.

DOCTOR HANDOFF:
    Zero can give Zero Doctor task-specific assignments such as:
        - "Diagnose why Ollama is slow. Use ai+gpu+runtime context."
        - "Check whether memory/Postgres is unhealthy. Use memory context."
        - "Find broken Python dependencies. Use dependencies context."
        - "Check if security is at risk. Use security context."
        - "Use doctor-context as the full patient journal before proposing repairs."

Examples:
    python3 app/zero_map.py --recommend "ollama is slow and gpu seems unused"
    python3 app/zero_map.py --profile gpu --out /tmp/zero_gpu.md
    python3 app/zero_map.py --profile doctor-context --format json --out /tmp/zero_doctor_context.json

ZERO_MODULE:    health
ZERO_LAYER:     2
ZERO_ESSENTIAL: false
ZERO_ROLE:      Systemkarta — observerar och exporterar kontext för Zero Doctor
ZERO_DEPENDS:   foundation.py
ZERO_USED_BY:   zero_doctor.py, router.py, zero_gear4.py
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Paths / constants
# ─────────────────────────────────────────────────────────────────────────────

THIS_FILE = Path(__file__).resolve()
APP = THIS_FILE.parent
ROOT = APP.parent if APP.name == "app" else THIS_FILE.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
LOGS = ROOT / "logs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
except Exception:
    pass

DEFAULT_TIMEOUT = 10
DEEP_TIMEOUT = 25
MAX_CMD_CHARS = 30_000
MAX_LIST_ITEMS = 600
MAX_FILE_TREE_ITEMS = 900

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|pwd|bearer|authorization)\s*[:=]\s*([^\s'\"]+)"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{16,})"),
    re.compile(r"(?i)(xox[baprs]-[A-Za-z0-9\-]{20,})"),
    re.compile(r"(?i)(gh[pousr]_[A-Za-z0-9_]{20,})"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Safe utilities
# ─────────────────────────────────────────────────────────────────────────────

def mask_secrets(text: Any) -> Any:
    """Mask likely secrets in strings/lists/dicts."""
    if isinstance(text, dict):
        return {k: mask_secrets(v) for k, v in text.items()}
    if isinstance(text, list):
        return [mask_secrets(v) for v in text]
    if not isinstance(text, str):
        return text

    out = text
    for pat in SECRET_PATTERNS:
        def repl(m: re.Match) -> str:
            if len(m.groups()) >= 2:
                return f"{m.group(1)}=***MASKED***"
            return "***MASKED_SECRET***"
        out = pat.sub(repl, out)

    # Mask common env-style assignment lines.
    lines = []
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if re.search(r"(?i)(key|token|secret|password|passwd|pwd)", k):
                lines.append(f"{k}=***MASKED***")
            else:
                lines.append(line)
        else:
            lines.append(line)
    return "\n".join(lines)

def truncate(value: Any, limit: int = MAX_CMD_CHARS) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"\n\n... TRUNCATED ({len(value):,} chars total) ..."
    if isinstance(value, list) and len(value) > MAX_LIST_ITEMS:
        return value[:MAX_LIST_ITEMS] + [f"... TRUNCATED ({len(value):,} items total) ..."]
    if isinstance(value, dict):
        return {k: truncate(v, limit) for k, v in value.items()}
    return value

def safe_text(value: Any) -> Any:
    return truncate(mask_secrets(value))

def which(cmd: str) -> str | None:
    return shutil.which(cmd)

def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    shell: bool = False,
) -> str:
    """Run a command safely and return stdout/stderr combined, masked and truncated."""
    try:
        if shell:
            proc = subprocess.run(
                " ".join(cmd),
                shell=True,
                cwd=str(cwd) if cwd else None,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        else:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                text=True,
                capture_output=True,
                timeout=timeout,
            )

        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if err:
            output = f"{output}\n[stderr]\n{err}".strip()
        if proc.returncode != 0:
            output = f"[exit {proc.returncode}]\n{output}".strip()
        return safe_text(output or "(no output)")
    except FileNotFoundError:
        return f"(command not found: {cmd[0]})"
    except subprocess.TimeoutExpired:
        return f"(timeout after {timeout}s: {' '.join(cmd)})"
    except Exception as e:
        return f"(error running {' '.join(cmd)}: {e})"

def import_status(module: str) -> dict[str, Any]:
    try:
        m = importlib.import_module(module)
        return {
            "installed": True,
            "version": getattr(m, "__version__", "ok"),
            "error": None,
        }
    except Exception as e:
        return {
            "installed": False,
            "version": None,
            "error": str(e),
        }

def bytes_gb(n: int | float) -> float:
    return round(float(n) / 1024 / 1024 / 1024, 2)

# ─────────────────────────────────────────────────────────────────────────────
# Collectors
# ─────────────────────────────────────────────────────────────────────────────

def collect_identity() -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "app": str(APP),
        "hostname": socket.gethostname(),
        "user": os.getenv("USER", "(unknown)"),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "working_directory": os.getcwd(),
    }

def collect_hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "os": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "(unknown)",
        "cpu_count": os.cpu_count(),
        "ram_gb": None,
        "disk_root": None,
    }

    try:
        mem = Path("/proc/meminfo").read_text(errors="ignore")
        for line in mem.splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                info["ram_gb"] = round(kb / 1024 / 1024, 1)
                break
    except Exception:
        pass

    try:
        du = shutil.disk_usage(ROOT)
        info["disk_root"] = {
            "total_gb": bytes_gb(du.total),
            "used_gb": bytes_gb(du.used),
            "free_gb": bytes_gb(du.free),
        }
    except Exception as e:
        info["disk_root_error"] = str(e)

    if which("lscpu"):
        info["lscpu_summary"] = "\n".join(run_cmd(["lscpu"]).splitlines()[:35])
    return safe_text(info)

def collect_runtime() -> dict[str, Any]:
    return safe_text({
        "uptime": run_cmd(["uptime"]),
        "memory": run_cmd(["free", "-h"]) if which("free") else "(free not found)",
        "load_processes_cpu": run_cmd(["ps", "-eo", "pid,ppid,%cpu,%mem,cmd", "--sort=-%cpu"], timeout=DEFAULT_TIMEOUT),
        "load_processes_mem": run_cmd(["ps", "-eo", "pid,ppid,%cpu,%mem,cmd", "--sort=-%mem"], timeout=DEFAULT_TIMEOUT),
    })

def collect_environment() -> dict[str, Any]:
    interesting_keys = [
        "DEFAULT_PROVIDER", "ZERO_ROOT", "UI_PORT",
        "OLLAMA_MODEL", "OLLAMA_BASE_URL",
        "ANTHROPIC_MODEL", "GEMINI_MODEL", "MISTRAL_MODEL",
        "XAI_MODEL", "GROQ_MODEL", "OPENROUTER_MODEL",
        "CEREBRAS_MODEL", "COHERE_MODEL", "DEEPSEEK_MODEL",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
        "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER",
        "ZERO_REFLECTION_PROVIDER", "CUDA_VISIBLE_DEVICES",
    ]

    key_markers = ("API", "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PWD")
    api_status = {}
    for k, v in os.environ.items():
        if any(marker in k.upper() for marker in key_markers):
            api_status[k] = "SET" if v else "EMPTY"

    return safe_text({
        "selected_values": {k: os.getenv(k, "(not set)") for k in interesting_keys},
        "secret_like_variables_status_only": dict(sorted(api_status.items())),
    })

def collect_providers() -> dict[str, Any]:
    try:
        from app.providers import PROVIDER_SPECS, LOCAL_FIRST_PROVIDER_ORDER  # type: ignore
        specs = {}
        for name, s in PROVIDER_SPECS.items():
            specs[name] = {
                "display": getattr(s, "display_name", None),
                "local": getattr(s, "is_local", None),
                "tool_use": getattr(s, "supports_tool_use", None),
                "context_limit": getattr(s, "context_limit", None),
            }
        return safe_text({
            "defined": specs,
            "priority_order": list(LOCAL_FIRST_PROVIDER_ORDER),
            "default": os.getenv("DEFAULT_PROVIDER", "(not set)"),
        })
    except Exception as e:
        return {"error": str(e)}

def collect_modules() -> dict[str, Any]:
    known = [
        # ── Lager 1 — Kärnan ─────────────────────────────────────────
        "app.foundation",
        "app.drm_memory",
        "app.memory_resonance",
        "app.providers",
        "app.router",
        "app.zero_gear",
        "app.zero_engine",
        "app.zero_web_server",
        "app.zero_boot",
        "app.self_reflection",
        "app.zero_ascension",
        "app.zero_memory_guard",
        "app.zero_memory_search",
        "app.zero_self_knowledge",
        # ── Lager 2 — Hälsa ──────────────────────────────────────────
        "app.zero_doctor",
        "app.zero_monitor",
        "app.zero_map",
        # ── Lager 3 — Autonomi (planerade) ───────────────────────────
        "app.zero_gear4",
        "app.zero_sudo",
        "app.zero_night",
        "app.zero_inventor",
        # ── Lager 4 — Integration (planerade) ────────────────────────
        "app.zero_telegram",
        "app.zero_mail_watcher",
        "app.pinball_social_entity",
    ]
    result = {}
    for mod in known:
        rel = mod.replace(".", "/") + ".py"
        candidates = [ROOT / rel, APP / (mod.split(".")[-1] + ".py")]
        exists = any(p.exists() for p in candidates)
        entry: dict[str, Any] = {"exists": exists, "importable": False, "error": None}
        if exists:
            try:
                import io, contextlib
                # Suppress stdout during import — some modules print banners/warnings on import
                with contextlib.redirect_stdout(io.StringIO()):
                    importlib.import_module(mod)
                entry["importable"] = True
            except Exception as e:
                entry["error"] = str(e)
        result[mod] = entry
    return safe_text(result)

def collect_python_packages(deep: bool = False) -> dict[str, Any]:
    critical = [
        "dotenv", "anthropic", "openai", "mistralai",
        "google.genai", "google.generativeai",
        "psycopg", "psycopg2", "pgvector",
        "pypdf", "PIL", "pytesseract",
        "websockets", "httpx", "fastapi", "uvicorn",
        "numpy", "torch", "transformers", "sentence_transformers",
    ]
    result: dict[str, Any] = {
        "python": sys.version,
        "executable": sys.executable,
        "critical_imports": {pkg: import_status(pkg) for pkg in critical},
        "pip_check": run_cmd([sys.executable, "-m", "pip", "check"], timeout=DEEP_TIMEOUT),
    }

    if deep:
        result["pip_freeze"] = run_cmd([sys.executable, "-m", "pip", "freeze"], timeout=DEEP_TIMEOUT).splitlines()
        result["pip_list_outdated"] = run_cmd([sys.executable, "-m", "pip", "list", "--outdated"], timeout=DEEP_TIMEOUT)
        if which("pipdeptree"):
            result["pipdeptree"] = run_cmd(["pipdeptree"], timeout=DEEP_TIMEOUT)
        else:
            result["pipdeptree"] = "pipdeptree not installed. Install with: python3 -m pip install pipdeptree"
        if which("pip-audit"):
            result["pip_audit"] = run_cmd(["pip-audit"], timeout=DEEP_TIMEOUT)
        else:
            result["pip_audit"] = "pip-audit not installed. Optional: python3 -m pip install pip-audit"

    return safe_text(result)

def collect_gpu() -> dict[str, Any]:
    result: dict[str, Any] = {
        "nvidia_smi_found": bool(which("nvidia-smi")),
        "nvcc_found": bool(which("nvcc")),
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES", "(not set)"),
    }
    if which("nvidia-smi"):
        result["nvidia_smi_query"] = run_cmd([
            "nvidia-smi",
            "--query-gpu=index,name,uuid,driver_version,memory.total,memory.used,memory.free,temperature.gpu,power.draw,power.limit,pcie.link.gen.current,pcie.link.width.current",
            "--format=csv,noheader,nounits",
        ])
        result["nvidia_smi_full"] = run_cmd(["nvidia-smi"])
    else:
        result["nvidia_smi"] = "nvidia-smi not found"

    if which("nvcc"):
        result["nvcc_version"] = run_cmd(["nvcc", "--version"])
    else:
        result["nvcc_version"] = "nvcc not found"

    try:
        import torch  # type: ignore
        result["torch"] = {
            "version": getattr(torch, "__version__", None),
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": getattr(torch.version, "cuda", None),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "devices": [
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "capability": torch.cuda.get_device_capability(i),
                    "memory_allocated_gb": bytes_gb(torch.cuda.memory_allocated(i)),
                    "memory_reserved_gb": bytes_gb(torch.cuda.memory_reserved(i)),
                }
                for i in range(torch.cuda.device_count())
            ] if torch.cuda.is_available() else [],
        }
    except Exception as e:
        result["torch"] = {"error": str(e)}

    return safe_text(result)

def collect_ollama() -> dict[str, Any]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    result: dict[str, Any] = {
        "base_url": base_url,
        "ollama_binary": which("ollama") or "(not found)",
        "processes": run_cmd(["pgrep", "-af", "ollama"]),
    }
    if which("ollama"):
        result["version"] = run_cmd(["ollama", "--version"])
        result["models"] = run_cmd(["ollama", "list"], timeout=DEEP_TIMEOUT)
        result["running_models"] = run_cmd(["ollama", "ps"], timeout=DEEP_TIMEOUT)
    else:
        result["version"] = "ollama command not found"

    if which("curl"):
        result["api_tags"] = run_cmd(["curl", "-sS", f"{base_url}/api/tags"], timeout=DEFAULT_TIMEOUT)
        result["api_ps"] = run_cmd(["curl", "-sS", f"{base_url}/api/ps"], timeout=DEFAULT_TIMEOUT)
    else:
        result["api"] = "curl not found"
    return safe_text(result)

def collect_docker() -> dict[str, Any]:
    result: dict[str, Any] = {"docker_binary": which("docker") or "(not found)"}
    if not which("docker"):
        return result

    result["docker_version"] = run_cmd(["docker", "--version"])
    result["docker_ps"] = run_cmd(["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"], timeout=DEEP_TIMEOUT)
    result["docker_compose_files"] = [str(p.relative_to(ROOT)) for p in ROOT.rglob("docker-compose*.yml")]
    result["docker_stats_no_stream"] = run_cmd(["docker", "stats", "--no-stream"], timeout=DEEP_TIMEOUT)

    # Only inspect likely Zero/Postgres containers to avoid huge output.
    names = run_cmd(["docker", "ps", "--format", "{{.Names}}"], timeout=DEFAULT_TIMEOUT).splitlines()
    inspect_targets = [n for n in names if re.search(r"zero|postgres|pgvector|ollama", n, re.I)]
    if inspect_targets:
        result["inspect_selected"] = run_cmd(["docker", "inspect", *inspect_targets], timeout=DEEP_TIMEOUT)
    return safe_text(result)

def collect_postgres() -> dict[str, Any]:
    result: dict[str, Any] = {
        "env_host": os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST") or "localhost",
        "env_port": os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT") or "5432",
        "env_db": os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or "(not set)",
        "env_user": os.getenv("DB_USER") or os.getenv("POSTGRES_USER") or "(not set)",
    }

    # Prefer project-native stats if available.
    try:
        from app.zero_memory_search import get_zero_stats  # type: ignore
        stats = get_zero_stats()
        result["zero_memory_stats"] = stats if isinstance(stats, dict) else {"raw": str(stats)}
    except Exception as e:
        result["zero_memory_stats_error"] = str(e)

    # Best-effort psql if available. Avoid password output. Uses env/.pgpass if configured.
    if which("psql"):
        db = result["env_db"]
        user = result["env_user"]
        host = result["env_host"]
        port = result["env_port"]
        if db != "(not set)" and user != "(not set)":
            # -w = aldrig fråga efter lösenord, PGPASSWORD från env
            import os as _os
            pg_env = {**_os.environ, "PGPASSWORD": _os.getenv("POSTGRES_PASSWORD", "")}
            base = ["psql", "-h", str(host), "-p", str(port), "-U", str(user), "-d", str(db), "-Atc", "-w"]
            result["postgres_version"] = run_cmd(base + ["select version();"], timeout=DEFAULT_TIMEOUT)
            result["database_size"] = run_cmd(base + ["select pg_size_pretty(pg_database_size(current_database()));"], timeout=DEFAULT_TIMEOUT)
            result["extensions"] = run_cmd(base + ["select extname, extversion from pg_extension order by extname;"], timeout=DEFAULT_TIMEOUT)
            result["table_sizes"] = run_cmd(base + [
                "select schemaname||'.'||relname||' | '||pg_size_pretty(pg_total_relation_size(relid)) "
                "from pg_catalog.pg_statio_user_tables order by pg_total_relation_size(relid) desc limit 30;"
            ], timeout=DEFAULT_TIMEOUT)
        else:
            result["psql"] = "psql found, but DB_NAME/DB_USER not set"
    else:
        result["psql"] = "psql not found"

    return safe_text(result)

def collect_network() -> dict[str, Any]:
    result: dict[str, Any] = {}
    if which("ss"):
        result["listening_ports"] = run_cmd(["ss", "-tulpn"], timeout=DEFAULT_TIMEOUT)
    elif which("netstat"):
        result["listening_ports"] = run_cmd(["netstat", "-tulpn"], timeout=DEFAULT_TIMEOUT)
    else:
        result["listening_ports"] = "ss/netstat not found"

    if which("ip"):
        result["ip_addr"] = run_cmd(["ip", "-brief", "addr"], timeout=DEFAULT_TIMEOUT)
        result["ip_route"] = run_cmd(["ip", "route"], timeout=DEFAULT_TIMEOUT)
    return safe_text(result)

def collect_git() -> dict[str, Any]:
    if not (ROOT / ".git").exists() and not which("git"):
        return {"git": "not a git repo or git not installed"}

    return safe_text({
        "branch": run_cmd(["git", "branch", "--show-current"], cwd=ROOT),
        "status_short": run_cmd(["git", "status", "--short"], cwd=ROOT),
        "last_commit": run_cmd(["git", "log", "-1", "--oneline"], cwd=ROOT),
        "remotes": run_cmd(["git", "remote", "-v"], cwd=ROOT),
    })

def collect_security() -> dict[str, Any]:
    result: dict[str, Any] = {
        "env_file": {},
        "sensitive_files": [],
        "sudo": None,
        "firewall": None,
    }

    env_file = ROOT / ".env"
    if env_file.exists():
        st = env_file.stat()
        result["env_file"] = {
            "exists": True,
            "mode": oct(st.st_mode & 0o777),
            "owner_uid": st.st_uid,
            "size_bytes": st.st_size,
            "recommendation": "Prefer 600 permissions: chmod 600 .env" if (st.st_mode & 0o077) else "permissions look restricted",
        }
    else:
        result["env_file"] = {"exists": False}

    for pattern in ["*.env", "*.key", "*.pem", "*secret*", "*token*", "*password*"]:
        for p in ROOT.rglob(pattern):
            if any(skip in p.parts for skip in ("venv", "__pycache__", ".git", "node_modules")):
                continue
            if p.is_file():
                try:
                    st = p.stat()
                    result["sensitive_files"].append({
                        "path": str(p.relative_to(ROOT)),
                        "mode": oct(st.st_mode & 0o777),
                        "size_bytes": st.st_size,
                    })
                except Exception:
                    pass

    if which("sudo"):
        result["sudo"] = run_cmd(["sudo", "-n", "true"], timeout=DEFAULT_TIMEOUT)
        if result["sudo"] == "(no output)":
            result["sudo"] = "passwordless sudo appears available for this command"
    if which("ufw"):
        result["firewall"] = run_cmd(["ufw", "status", "verbose"], timeout=DEFAULT_TIMEOUT)
    return safe_text(result)

def collect_foundation() -> dict[str, Any]:
    """
    Verifierar Layer 0 via foundation.py.
    zero_guardian.py är ej en kärnmodul — foundation.py är sanningskällan.
    """
    result: dict[str, Any] = {}
    try:
        from app.foundation import LAYER0_FULL, LAYER0_CHECKSUM, LAYER0_SECTIONS
        result["layer0_available"] = bool(LAYER0_FULL)
        result["layer0_sections"] = list(LAYER0_SECTIONS.keys())
        result["layer0_checksum"] = LAYER0_CHECKSUM[:16] + "..." if LAYER0_CHECKSUM else "?"
        result["layer0_chars"] = len(LAYER0_FULL)
    except Exception as e:
        result["foundation_error"] = str(e)

    # Skanna moduler efter ZERO_MODULE-header (nytt system)
    py_files = list(APP.glob("*.py"))
    modules_with_header = []
    modules_without_header = []
    for f in sorted(py_files):
        if f.name.startswith("_"):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")[:500]
            if "ZERO_MODULE:" in txt:
                modules_with_header.append(f.name)
            else:
                modules_without_header.append(f.name)
        except Exception:
            pass

    result["modules_with_zero_header"] = modules_with_header
    result["modules_without_zero_header"] = modules_without_header
    return safe_text(result)

def collect_file_tree(deep: bool = False) -> dict[str, Any]:
    sections = {
        "root": ROOT,
        "app": APP,
        "config": CONFIG,
        "data": DATA,
        "logs": LOGS,
    }
    tree: dict[str, Any] = {}
    max_depth = 5 if deep else 3

    for name, base in sections.items():
        if not base.exists():
            tree[name] = "(missing)"
            continue

        items = []
        for p in sorted(base.rglob("*")):
            if any(skip in p.parts for skip in ("venv", "__pycache__", ".git", "node_modules", ".mypy_cache")):
                continue
            try:
                rel = p.relative_to(ROOT)
                depth = len(rel.parts)
                if depth > max_depth:
                    continue
                if p.is_file():
                    items.append(f"{rel} ({round(p.stat().st_size / 1024, 1)} kB)")
                elif p.is_dir() and deep:
                    items.append(f"{rel}/")
            except Exception:
                continue
            if len(items) >= MAX_FILE_TREE_ITEMS:
                items.append(f"... TRUNCATED after {MAX_FILE_TREE_ITEMS} items ...")
                break
        tree[name] = items
    return safe_text(tree)

def collect_ui() -> dict[str, Any]:
    ui_files = []
    if CONFIG.exists():
        ui_files = sorted(CONFIG.glob("zero_ui_v*.html"))
    port = os.getenv("UI_PORT", "8080")
    return safe_text({
        "latest": ui_files[-1].name if ui_files else "(none found)",
        "all": [p.name for p in ui_files],
        "port": port,
        "url": f"http://localhost:{port}",
    })

def collect_logs(deep: bool = False) -> dict[str, Any]:
    lines = "300" if deep else "80"
    result: dict[str, Any] = {}

    if which("journalctl"):
        result["systemd_zeropointai"] = run_cmd(["journalctl", "-u", "zero-web", "-n", lines, "--no-pager"], timeout=DEEP_TIMEOUT)
        result["systemd_ollama"] = run_cmd(["journalctl", "-u", "ollama", "-n", "80", "--no-pager"], timeout=DEEP_TIMEOUT)
    else:
        result["journalctl"] = "journalctl not found"

    if LOGS.exists():
        log_files = sorted(LOGS.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:8]
        result["log_files"] = []
        for f in log_files:
            try:
                result["log_files"].append({
                    "file": str(f.relative_to(ROOT)),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "tail": "\n".join(f.read_text(errors="ignore").splitlines()[-int(lines):]),
                })
            except Exception as e:
                result["log_files"].append({"file": str(f), "error": str(e)})
    return safe_text(result)

def collect_services() -> dict[str, Any]:
    return safe_text({
        "zero_web_v1": run_cmd(["systemctl", "is-active", "zero-web.service"]) if which("systemctl") else "systemctl not found",
        "zeropointai_process": run_cmd(["pgrep", "-af", "zero_web_server|zeropoint|zero_"], timeout=DEFAULT_TIMEOUT),
        "ollama_process": run_cmd(["pgrep", "-af", "ollama"], timeout=DEFAULT_TIMEOUT),
        "postgres_process": run_cmd(["pgrep", "-af", "postgres"], timeout=DEFAULT_TIMEOUT),
    })

def collect_disk() -> dict[str, Any]:
    result: dict[str, Any] = {
        "root_usage": None,
        "project_usage": None,
        "large_dirs": None,
    }
    try:
        du = shutil.disk_usage(ROOT)
        result["root_usage"] = {
            "total_gb": bytes_gb(du.total),
            "used_gb": bytes_gb(du.used),
            "free_gb": bytes_gb(du.free),
        }
    except Exception as e:
        result["root_usage_error"] = str(e)

    if which("du"):
        result["project_usage"] = run_cmd(["du", "-sh", str(ROOT)], timeout=DEEP_TIMEOUT)
        result["large_dirs"] = run_cmd(["du", "-h", "--max-depth=2", str(ROOT)], timeout=DEEP_TIMEOUT)
    if which("df"):
        result["df"] = run_cmd(["df", "-h"], timeout=DEFAULT_TIMEOUT)
    return safe_text(result)

# ─────────────────────────────────────────────────────────────────────────────
# Profiles
# ─────────────────────────────────────────────────────────────────────────────

Collector = Callable[[], dict[str, Any]]

def c_python_fast() -> dict[str, Any]:
    return collect_python_packages(deep=False)

def c_python_deep() -> dict[str, Any]:
    return collect_python_packages(deep=True)

def c_file_tree_fast() -> dict[str, Any]:
    return collect_file_tree(deep=False)

def c_file_tree_deep() -> dict[str, Any]:
    return collect_file_tree(deep=True)

def c_logs_fast() -> dict[str, Any]:
    return collect_logs(deep=False)

def c_logs_deep() -> dict[str, Any]:
    return collect_logs(deep=True)

COLLECTORS: dict[str, Collector] = {
    "identity": collect_identity,
    "hardware": collect_hardware,
    "runtime": collect_runtime,
    "environment": collect_environment,
    "providers": collect_providers,
    "modules": collect_modules,
    "dependencies_fast": c_python_fast,
    "dependencies_deep": c_python_deep,
    "gpu": collect_gpu,
    "ollama": collect_ollama,
    "docker": collect_docker,
    "postgres": collect_postgres,
    "network": collect_network,
    "git": collect_git,
    "security": collect_security,
    "foundation": collect_foundation,
    "file_tree_fast": c_file_tree_fast,
    "file_tree_deep": c_file_tree_deep,
    "ui": collect_ui,
    "logs_fast": c_logs_fast,
    "logs_deep": c_logs_deep,
    "services": collect_services,
    "disk": collect_disk,
}

PROFILES: dict[str, list[str]] = {
    # Small, fast context.
    "fast": [
        "identity", "hardware", "services", "environment", "providers",
        "modules", "dependencies_fast", "gpu", "ollama", "ui", "git",
    ],

    # AI stack context.
    "ai": [
        "identity", "environment", "providers", "ollama", "gpu",
        "dependencies_fast", "modules", "ui", "services",
    ],

    # STONE/Postgres/memory context.
    "memory": [
        "identity", "postgres", "docker", "disk", "dependencies_fast",
        "services", "logs_fast",
    ],

    # Secrets/permissions/exposure/foundation.
    "security": [
        "identity", "security", "network", "environment", "foundation",
        "git", "dependencies_deep",
    ],

    # GPU/CUDA/Ollama inference.
    "gpu": [
        "identity", "hardware", "gpu", "ollama", "runtime", "services",
    ],

    # Live processes/resources.
    "runtime": [
        "identity", "runtime", "services", "network", "disk",
    ],

    # Python dependencies.
    "dependencies": [
        "identity", "dependencies_deep",
    ],

    # Containers.
    "docker": [
        "identity", "docker", "postgres", "ollama",
    ],

    # Ports/interfaces.
    "network": [
        "identity", "network", "services",
    ],

    # Logs only.
    "logs": [
        "identity", "logs_deep",
    ],

    # Context package for Zero Doctor. Does not repair anything.
    "doctor-context": [
        "identity", "hardware", "runtime", "services", "environment",
        "providers", "modules", "dependencies_deep", "gpu", "ollama",
        "docker", "postgres", "network", "git", "security", "foundation",
        "ui", "logs_fast", "disk",
    ],

    # Full but still guarded/truncated.
    "full": [
        "identity", "hardware", "runtime", "services", "environment",
        "providers", "modules", "dependencies_deep", "gpu", "ollama",
        "docker", "postgres", "network", "git", "security", "foundation",
        "file_tree_deep", "ui", "logs_deep", "disk",
    ],
}

PROFILE_METADATA: dict[str, dict[str, Any]] = {
    "fast": {
        "purpose": "Small general status snapshot.",
        "best_for": ["unknown issue", "startup", "quick health check", "general status"],
        "doctor_handoff": "Use as first lightweight context before deeper diagnostics.",
    },
    "ai": {
        "purpose": "AI stack: providers, routing, Ollama, models, core AI modules.",
        "best_for": ["ollama", "provider", "model", "routing", "inference", "context", "tokens", "ai response"],
        "doctor_handoff": "Ask Zero Doctor to diagnose AI/provider/model routing issues using this context.",
    },
    "gpu": {
        "purpose": "GPU/CUDA/PyTorch/Ollama VRAM and inference runtime.",
        "best_for": ["gpu", "cuda", "vram", "nvidia", "3090", "torch", "slow inference", "thermal", "power", "pcie"],
        "doctor_handoff": "Ask Zero Doctor to diagnose GPU/CUDA/VRAM bottlenecks and propose safe fixes.",
    },
    "memory": {
        "purpose": "STONE memory, PostgreSQL, pgvector, database health and disk relation.",
        "best_for": ["memory", "stone", "postgres", "postgresql", "pgvector", "database", "embedding", "recall", "corruption"],
        "doctor_handoff": "Ask Zero Doctor to inspect memory/database health, backups, indexes and corruption risk.",
    },
    "security": {
        "purpose": "Secrets, permissions, ports, firewall, Foundation Laws status, dependency audit.",
        "best_for": ["security", "secret", "api key", "token", "permission", "chmod", "port", "firewall", "foundation", "breach"],
        "doctor_handoff": "Ask Zero Doctor for hardening recommendations only. foundation.py handles Layer 0 integrity.",
    },
    "runtime": {
        "purpose": "Live OS/process/RAM/load/disk/network resource snapshot.",
        "best_for": ["slow", "hang", "freeze", "cpu", "ram", "load", "process", "resource", "performance"],
        "doctor_handoff": "Ask Zero Doctor to identify resource bottlenecks and rogue processes.",
    },
    "dependencies": {
        "purpose": "Python packages, versions, broken dependencies, pip freeze, dependency tree.",
        "best_for": ["import error", "module not found", "dependency", "pip", "package", "version", "python error"],
        "doctor_handoff": "Ask Zero Doctor to propose dependency repair commands, but require permission before modifying packages.",
    },
    "docker": {
        "purpose": "Docker containers, compose files, container stats, selected inspect.",
        "best_for": ["docker", "container", "compose", "postgres container", "container unhealthy"],
        "doctor_handoff": "Ask Zero Doctor to inspect container health and propose restart/rebuild only with permission.",
    },
    "network": {
        "purpose": "Ports, sockets, interfaces, routes, listening services.",
        "best_for": ["port", "network", "localhost", "connection refused", "socket", "api not responding", "web server"],
        "doctor_handoff": "Ask Zero Doctor to identify port conflicts and dead services.",
    },
    "logs": {
        "purpose": "Recent systemd and project logs.",
        "best_for": ["log", "error", "traceback", "crash", "exception", "journalctl"],
        "doctor_handoff": "Ask Zero Doctor to summarize errors and map them to likely root causes.",
    },
    "doctor-context": {
        "purpose": "Broad patient journal for Zero Doctor. Observes only, does not repair.",
        "best_for": ["broken", "diagnose", "doctor", "health", "something wrong", "unknown problem", "system problem"],
        "doctor_handoff": "Give this whole map to Zero Doctor before it diagnoses or proposes repairs.",
    },
    "full": {
        "purpose": "Everything guarded/truncated.",
        "best_for": ["complete audit", "deep analysis", "full map", "everything"],
        "doctor_handoff": "Use only when broad context is needed; can be large.",
    },
}

def recommend_profiles(problem: str) -> dict[str, Any]:
    """Recommend profiles from a natural-language problem description.

    This is intentionally simple and transparent so Zero can understand it.
    Zero may override this recommendation if reasoning suggests better context.
    """
    msg = (problem or "").lower()
    scores: dict[str, int] = {name: 0 for name in PROFILES}

    for profile, meta in PROFILE_METADATA.items():
        for term in meta.get("best_for", []):
            if term.lower() in msg:
                scores[profile] += 3
        # Profile name direct mention.
        if profile in msg:
            scores[profile] += 5

    # Extra cross-profile heuristics.
    if any(x in msg for x in ["ollama", "model", "inference", "tokens", "provider"]):
        scores["ai"] += 4
        scores["gpu"] += 2
        scores["runtime"] += 1
    if any(x in msg for x in ["slow", "seg", "lag", "freeze", "hänger", "långsam"]):
        scores["runtime"] += 3
        scores["gpu"] += 2
        scores["ai"] += 1
    if any(x in msg for x in ["error", "traceback", "crash", "exception", "fel"]):
        scores["logs"] += 3
        scores["dependencies"] += 2
        scores["doctor-context"] += 2
    if any(x in msg for x in ["import", "module", "package", "pip", "dependency"]):
        scores["dependencies"] += 5
        scores["logs"] += 1
    if any(x in msg for x in ["postgres", "pgvector", "stone", "memory", "minne", "database", "db"]):
        scores["memory"] += 5
        scores["docker"] += 2
    if any(x in msg for x in ["secret", "api key", "token", "permission", "security", "breach", "foundation"]):
        scores["security"] += 5
    if any(x in msg for x in ["unknown", "trasigt", "broken", "doctor", "diagnose", "diagnostik", "problem"]):
        scores["doctor-context"] += 3

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    selected = [name for name, score in ranked if score > 0]

    if not selected:
        selected = ["fast"]

    # Keep output practical. doctor-context already includes broad context.
    selected = selected[:4]

    return {
        "problem": problem,
        "recommended_profiles": selected,
        "scores": {k: v for k, v in ranked if v > 0},
        "next_steps_for_zero": [
            "Run the recommended profile(s) with zero_map.py.",
            "Read the generated context.",
            "If repair may be needed, hand the context to zero_doctor.py with a specific task.",
            "Do not let zero_map.py mutate files; it is observer-only.",
            "foundation.py verifierar Layer 0-integritet automatiskt vid varje uppstart.",
        ],
        "doctor_task_examples": [
            "Zero Doctor: diagnose this issue using the attached zero_map context. Do not repair without permission.",
            "Zero Doctor: propose exact repair steps and classify them as safe, caution, or critical.",
            "Zero Doctor: if a service restart is needed, ask for explicit approval first.",
        ],
    }

def choose_auto_profile() -> str:
    """Simple heuristic. Zero can also call --list-profiles and decide externally."""
    if os.getenv("ZERO_MAP_AUTO_PROFILE"):
        return os.getenv("ZERO_MAP_AUTO_PROFILE", "fast")

    # If GPU exists and Ollama is installed, AI context is usually best.
    if which("nvidia-smi") or which("ollama"):
        return "ai"

    # If Docker/Postgres visible, memory context likely useful.
    if which("docker") or which("psql"):
        return "memory"

    return "fast"

# ─────────────────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────────────────

def build_map(profile: str, verbose: bool = True) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")

    data: dict[str, Any] = {
        "_zero_map": {
            "profile": profile,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "root": str(ROOT),
            "script": str(THIS_FILE),
            "schema": "zero_map_v2_profiles",
            "note": "zero_map observes only. zero_doctor diagnoses/repairs. foundation.py verifies Layer 0.",
        }
    }

    for key in PROFILES[profile]:
        fn = COLLECTORS[key]
        if verbose:
            print(f"  collecting {key}...", file=sys.stderr)
        t0 = time.time()
        try:
            data[key] = fn()
        except Exception as e:
            data[key] = {"collector_error": str(e)}
        data.setdefault("_timing_seconds", {})[key] = round(time.time() - t0, 2)

    return safe_text(data)

def md_value(value: Any, level: int = 0) -> str:
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(f"- **{k}:**")
                nested = md_value(v, level + 1)
                lines.append(indent(nested, "  "))
            else:
                lines.append(f"- **{k}:** `{v}`")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append("-")
                lines.append(indent(md_value(item, level + 1), "  "))
            else:
                lines.append(f"- `{item}`")
        return "\n".join(lines)
    return f"`{value}`"

def indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in str(text).splitlines())

def render_markdown(data: dict[str, Any]) -> str:
    meta = data.get("_zero_map", {})
    lines: list[str] = []
    w = lines.append

    w("# ZERO_SYSTEM_MAP")
    w("")
    w(f"- **Profile:** `{meta.get('profile', '?')}`")
    w(f"- **Generated:** `{meta.get('generated_at', '?')}`")
    w(f"- **Root:** `{meta.get('root', '?')}`")
    w("")
    w("> Purpose: give Zero/AI/Zero Doctor accurate local context without exposing secrets.")
    w("")

    for section, value in data.items():
        if section == "_zero_map":
            continue
        w(f"## {section}")
        w("")
        if isinstance(value, str):
            w("```text")
            w(value)
            w("```")
        else:
            rendered = md_value(value)
            # If rendered is huge command output, still okay because values are truncated.
            w(rendered if rendered.strip() else "_No data_")
        w("")

    w("---")
    w("*All Is One. One Is All.*")
    return "\n".join(lines)

def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

def list_profiles_text() -> str:
    lines = ["Available zero_map profiles:", ""]
    for name in PROFILES:
        meta = PROFILE_METADATA.get(name, {})
        lines.append(f"  {name:15} {meta.get('purpose', '')}")
        best = ", ".join(meta.get("best_for", [])[:8])
        if best:
            lines.append(f"  {'':15} Best for: {best}")
        handoff = meta.get("doctor_handoff")
        if handoff:
            lines.append(f"  {'':15} Doctor handoff: {handoff}")
        lines.append("")
    lines.append("Recommendation mode:")
    lines.append('  python3 app/zero_map.py --recommend "ollama is slow and gpu seems unused"')
    lines.append("")
    lines.append("Auto mode:")
    lines.append("  python3 app/zero_map.py --auto")
    lines.append("")
    lines.append("Examples:")
    lines.append("  python3 app/zero_map.py --profile ai")
    lines.append("  python3 app/zero_map.py --profile gpu --out /tmp/zero_gpu.md")
    lines.append("  python3 app/zero_map.py --profile doctor-context --format json --out /tmp/zero_doctor_context.json")
    lines.append("")
    lines.append("Role separation:")
    lines.append("  zero_map.py observes and exports context.")
    lines.append("  zero_doctor.py diagnoses/proposes/repairs according to permission rules.")

    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ZeroPointAI system maps.")
    parser.add_argument("--profile", choices=sorted(PROFILES.keys()), default="fast", help="Map profile to run.")
    parser.add_argument("--auto", action="store_true", help="Let zero_map choose a useful profile.")
    parser.add_argument("--list-profiles", action="store_true", help="List available profiles.")
    parser.add_argument("--recommend", type=str, default=None, help="Recommend profile(s) from a problem description.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format.")
    parser.add_argument("--out", type=str, default=None, help="Write output to file instead of stdout.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output on stderr.")
    args = parser.parse_args()

    if args.list_profiles:
        print(list_profiles_text())
        return 0

    if args.recommend is not None:
        rec = recommend_profiles(args.recommend)
        if args.format == "json":
            output = render_json(rec)
        else:
            lines = ["# ZERO_MAP_RECOMMENDATION", "", f"**Problem:** {rec['problem']}", ""]
            lines.append("## Recommended profiles")
            for p in rec["recommended_profiles"]:
                purpose = PROFILE_METADATA.get(p, {}).get("purpose", "")
                lines.append(f"- `{p}` — {purpose}")
            lines.append("")
            lines.append("## Next steps for Zero")
            for step in rec["next_steps_for_zero"]:
                lines.append(f"- {step}")
            lines.append("")
            lines.append("## Zero Doctor handoff examples")
            for task in rec["doctor_task_examples"]:
                lines.append(f"- {task}")
            lines.append("")
            lines.append("## Scores")
            for k, v in rec["scores"].items():
                lines.append(f"- `{k}`: {v}")
            output = "\n".join(lines)

        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
            if not args.quiet:
                print(f"✅ Saved recommendation: {out_path}", file=sys.stderr)
            return 0

        print(output)
        return 0

    profile = choose_auto_profile() if args.auto else args.profile
    if not args.quiet:
        print(f"Building Zero System Map profile={profile} format={args.format}...", file=sys.stderr)

    data = build_map(profile, verbose=not args.quiet)
    output = render_json(data) if args.format == "json" else render_markdown(data)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        if not args.quiet:
            print(f"\n✅ Saved: {out_path}", file=sys.stderr)
            print(f"   Size: {len(output):,} chars", file=sys.stderr)
        return 0

    print(output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
