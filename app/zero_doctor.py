#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_doctor.py — ZeroPointAI Medical Tricorder Deluxe v2.0

Linux-first Doctor.

Role:
  zero_map.py      = observes / maps / exports context
  zero_doctor.py   = diagnoses / creates repair plans / applies approved tasks
  foundation.py     = Layer 0, checksumma, sanningskällan

Doctor starts from zero_map context, then performs only targeted confirmation probes.
It does not randomly "fix everything".

Examples:
  python3 app/zero_doctor.py --check
  python3 app/zero_doctor.py --diagnose "ollama is slow"
  python3 app/zero_doctor.py --repair-plan "postgres memory seems broken"
  python3 app/zero_doctor.py --list-tasks
  python3 app/zero_doctor.py --apply clear-pycache
  python3 app/zero_doctor.py --apply restart-ollama --yes

ZERO_MODULE:    health
ZERO_LAYER:     2
ZERO_ESSENTIAL: false
ZERO_ROLE:      Diagnostik — analyserar systemhälsa och skapar reparationsplaner
ZERO_DEPENDS:   foundation.py, zero_map.py
ZERO_USED_BY:   router.py ('run doctor'), zero_engine.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

@dataclass
class Finding:
    severity: str
    subsystem: str
    code: str
    message: str
    recommendation: str = ""

@dataclass
class RepairTask:
    name: str
    risk: str
    description: str
    command_hint: str = ""
    requires_yes: bool = False
    implemented: bool = True

@dataclass
class DoctorReport:
    generated_at: str
    state: str
    problem: str
    map_profiles: list[str]
    findings: list[dict[str, Any]] = field(default_factory=list)
    repair_plan: list[dict[str, Any]] = field(default_factory=list)
    map_summary_path: str = ""
    notes: list[str] = field(default_factory=list)

def app_dir() -> Path:
    return Path(__file__).resolve().parent

def root_dir() -> Path:
    env = os.getenv("ZERO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    return here.parent.parent if here.parent.name == "app" else Path.cwd().resolve()

ROOT = root_dir()
APP = app_dir()
DATA_DOCTOR = ROOT / "data" / "doctor"

def run_cmd(cmd: list[str], timeout: int = 20, cwd: Path | None = None) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd or ROOT))
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if err:
            out = (out + "\n[stderr]\n" + err).strip()
        return p.returncode == 0, out or "(no output)"
    except Exception as e:
        return False, str(e)

def which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def load_json_from_cmd(cmd: list[str], timeout: int = 60) -> tuple[dict[str, Any] | None, str]:
    ok, out = run_cmd(cmd, timeout=timeout)
    if not ok:
        return None, out
    # Extrahera bara JSON-blocket — ignorera eventuell extra text före/efter
    # (t.ex. psql-lösenordspromptar eller andra stdout-meddelanden)
    json_start = out.find("{")
    json_end   = out.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        return None, f"Ingen JSON hittad i output\n{out[:500]}"
    json_str = out[json_start:json_end]
    try:
        return json.loads(json_str), ""
    except Exception as e:
        return None, f"JSON parse failed: {e}\n{json_str[:2000]}"

def zero_map_recommend(problem: str) -> list[str]:
    zm = APP / "zero_map.py"
    if not zm.exists():
        return ["fast"]
    data, _err = load_json_from_cmd(
        [sys.executable, str(zm), "--recommend", problem or "general health check", "--format", "json", "--quiet"],
        timeout=30,
    )
    if data and isinstance(data.get("recommended_profiles"), list):
        return data["recommended_profiles"][:4]
    return ["doctor-context" if problem else "fast"]

def run_zero_map_profile(profile: str) -> tuple[dict[str, Any] | None, str]:
    zm = APP / "zero_map.py"
    if not zm.exists():
        return None, "zero_map.py not found"
    return load_json_from_cmd(
        [sys.executable, str(zm), "--profile", profile, "--format", "json", "--quiet"],
        timeout=120,
    )

def summarize_map(data: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    services = data.get("services", {})
    service_blob = json.dumps(services, ensure_ascii=False).lower()
    # zero-engine.service is intentionally disabled (CLI mode, not a daemon).
    # Only flag if zero-web.service or other critical services are inactive.
    KNOWN_DISABLED = {"zero-engine", "zeropointai", "zero_engine", "zero-web-v2"}
    if "inactive" in service_blob or "failed" in service_blob:
        # Check if the inactive service is one we know is intentionally disabled
        active_concern = False
        for svc_name, svc_data in (services.items() if isinstance(services, dict) else {}.items()):
            svc_str = json.dumps(svc_data).lower()
            if ("inactive" in svc_str or "failed" in svc_str):
                if not any(disabled in svc_name.lower() for disabled in KNOWN_DISABLED):
                    active_concern = True
                    break
        if active_concern:
            findings.append(Finding("warning", "services", "SERVICE_NOT_ACTIVE",
                                    "One or more critical services appear inactive/failed.",
                                    "Inspect service logs: sudo journalctl -u zero-web.service -n 30"))

    gpu = data.get("gpu", {})
    torch_info = gpu.get("torch", {}) if isinstance(gpu, dict) else {}
    if isinstance(torch_info, dict) and torch_info.get("cuda_available") is False:
        findings.append(Finding("warning", "gpu", "TORCH_CUDA_FALSE",
                                "PyTorch reports CUDA unavailable.",
                                "Check NVIDIA driver, CUDA-compatible torch build, and nvidia-smi."))

    deps = data.get("dependencies_deep") or data.get("dependencies_fast") or {}
    pip_check = str(deps.get("pip_check", "")) if isinstance(deps, dict) else ""
    if pip_check and "No broken requirements found" not in pip_check and "(no output)" not in pip_check:
        findings.append(Finding("warning", "dependencies", "PIP_CHECK_WARNINGS",
                                "pip check returned dependency warnings/errors.",
                                "Run dependencies profile and repair exact package conflicts."))

    sec = data.get("security", {})
    env_file = sec.get("env_file", {}) if isinstance(sec, dict) else {}
    if isinstance(env_file, dict) and env_file.get("mode") not in (None, "0o600", "0o400"):
        findings.append(Finding("warning", "security", "ENV_PERMISSIONS_LOOSE",
                                f".env permissions are {env_file.get('mode')}.",
                                "Use chmod 600 .env if appropriate."))

    foundation = data.get("foundation", {})
    foundation_blob = json.dumps(foundation, ensure_ascii=False)
    foundation_lower = foundation_blob.lower()

    # foundation.py är sanningskällan för Layer 0 — inte zero_guardian
    layer0_available = foundation.get("layer0_available") if isinstance(foundation, dict) else None
    layer0_sections  = foundation.get("layer0_sections", []) if isinstance(foundation, dict) else []
    foundation_error = foundation.get("foundation_error") if isinstance(foundation, dict) else None

    if foundation_error:
        findings.append(Finding("critical", "foundation", "FOUNDATION_UNAVAILABLE",
                                f"foundation.py kunde inte ladda Layer 0: {foundation_error}",
                                "Kontrollera att /docs/layer0/ finns och innehåller .md-filer."))
    elif layer0_available is False:
        findings.append(Finding("critical", "foundation", "LAYER0_EMPTY",
                                "Layer 0 är tillgänglig men tom.",
                                "Lägg till 00_REALITY.md, COMPASS.md och 02_MIRROR.md i docs/layer0/."))
    elif layer0_sections and len(layer0_sections) < 2:
        findings.append(Finding("warning", "foundation", "LAYER0_INCOMPLETE",
                                f"Layer 0 har bara {len(layer0_sections)} sektion(er). Förväntar minst 3.",
                                "Lägg till saknade .md-filer i docs/layer0/."))

    # Moduler med ZERO_MODULE-header
    modules_without = foundation.get("modules_without_zero_header", []) if isinstance(foundation, dict) else []
    if modules_without:
        findings.append(Finding("info", "foundation", "MODULES_MISSING_HEADER",
                                f"{len(modules_without)} moduler saknar ZERO_MODULE-header: {', '.join(modules_without[:5])}",
                                "Lägg till ZERO_MODULE/ZERO_LAYER-header i varje .py-fil."))

    pg_blob = json.dumps(data.get("postgres", {}), ensure_ascii=False).lower()
    # Only flag if real connection errors — not password prompts or psql warnings
    # "password for user" appears in zero_map stdout when .pgpass is not set
    pg_real_error = (
        ("error" in pg_blob or "connection refused" in pg_blob or "not found" in pg_blob)
        and "password for user" not in pg_blob
        and "password for user" not in pg_blob.split("error")[0][-80:] if "error" in pg_blob else False
    )
    # Also skip if Docker container is confirmed running
    docker_blob = json.dumps(data.get("docker", {}), ensure_ascii=False).lower()
    postgres_container_up = "zeropoint-postgres" in docker_blob and "up" in docker_blob
    if pg_real_error and not postgres_container_up:
        findings.append(Finding("warning", "memory", "POSTGRES_ATTENTION",
                                "Postgres/memory context indicates possible issue.",
                                "Run memory profile, inspect Docker/Postgres and memory_guard."))

    if not findings:
        findings.append(Finding("info", "general", "NO_MAJOR_FINDINGS",
                                "No obvious major issue detected from zero_map context.",
                                "Use targeted scan if symptoms persist."))
    return findings

def _tasks() -> dict[str, RepairTask]:
    """Bygger TASKS dynamiskt med rätt sökvägar från ZERO_ROOT."""
    root_str = str(ROOT)
    return {
        "clear-pycache": RepairTask(
            "clear-pycache", "SAFE",
            "Ta bort __pycache__-mappar och .pyc-filer under projektroten.",
            f"find {root_str} -name __pycache__ -type d -prune -exec rm -rf {{}} +"),
        "fix-env-permissions": RepairTask(
            "fix-env-permissions", "CAUTION",
            "Sätt .env-rättigheter till 600.",
            f"chmod 600 {root_str}/.env", True),
        "restart-ollama": RepairTask(
            "restart-ollama", "CAUTION",
            "Starta om Ollama-service via systemd.",
            "sudo systemctl restart ollama", True),
        "restart-zero": RepairTask(
            "restart-zero", "CAUTION",
            "Starta om Zero web-service (hittar rätt service automatiskt).",
            "sudo systemctl restart zero-web.service", True),
        "restart-zero-v2": RepairTask(
            "restart-zero-v2", "CAUTION",
            "Starta om Zero v2 web-service.",
            "sudo systemctl restart zero-web-v2.service", True),
        "restart-postgres-container": RepairTask(
            "restart-postgres-container", "CAUTION",
            "Starta om PostgreSQL Docker-container.",
            "docker restart zeropoint-postgres", True),
        "run-evolution": RepairTask(
            "run-evolution", "SAFE",
            "Kör evolution-loop — kalibrerar resonansvikter och genererar embeddings.",
            f"ZERO_ROOT={root_str} python3 {root_str}/app/drm_memory.py", False),
        "check-embeddings": RepairTask(
            "check-embeddings", "SAFE",
            "Kör semantisk hälsokoll — testar embedding-kedjan.",
            f"ZERO_ROOT={root_str} python3 app/zero_doctor.py --semantic"),
        "accept-layer0-change": RepairTask(
            "accept-layer0-change", "CAUTION",
            "Godkänn en Layer 0-ändring (uppdaterar checksumma).",
            f"ZERO_ROOT={root_str} python3 app/zero_doctor.py --apply accept-layer0-change --yes", True),
        "db-restore": RepairTask(
            "db-restore", "CRITICAL",
            "Återställ databas från backup.",
            "Manuellt only. Kräver verifierad backup och explicit Frank-godkännande.", True, False),
    }

TASKS: dict[str, RepairTask] = _tasks()

def build_repair_plan(problem: str, findings: list[Finding]) -> list[RepairTask]:
    text = (problem + " " + " ".join(f.code + " " + f.subsystem for f in findings)).lower()
    plan: list[RepairTask] = []
    if "pycache" in text or "import" in text or "dependency" in text:
        plan.append(TASKS["clear-pycache"])
    if "env_permissions" in text or ".env" in text:
        plan.append(TASKS["fix-env-permissions"])
    if "ollama" in text or "inference" in text:
        plan.append(TASKS["restart-ollama"])
    if "zero service" in text or "service_not_active" in text:
        plan.append(TASKS["restart-zero"])
    if "postgres" in text or "memory" in text or "database" in text:
        plan.append(TASKS["restart-postgres-container"])
    if "foundation" in text or "layer0" in text:
        plan.append(TASKS["accept-layer0-change"])
    if "embedding" in text or "semantic" in text or "resonans" in text:
        plan.append(TASKS["check-embeddings"])
    if "evolution" in text or "kalibrering" in text:
        plan.append(TASKS["run-evolution"])
    if not plan and any(f.severity in ("warning", "critical") for f in findings):
        plan.append(TASKS["clear-pycache"])
    seen, out = set(), []
    for task in plan:
        if task.name not in seen:
            out.append(task); seen.add(task.name)
    return out

def diagnose(problem: str = "", profile: str | None = None) -> DoctorReport:
    # --check använder fast som default (snabb, < 5s)
    # --diagnose med problem-text väljer profil intelligentare
    if profile:
        profiles = [profile]
    elif not problem or problem == "general health check":
        profiles = ["fast"]
    else:
        profiles = zero_map_recommend(problem)
        if "broken" in problem.lower() or "trasig" in problem.lower():
            profiles = ["doctor-context"]

    all_findings: list[Finding] = []
    map_paths: list[str] = []
    DATA_DOCTOR.mkdir(parents=True, exist_ok=True)

    for p in profiles:
        data, err = run_zero_map_profile(p)
        if not data:
            all_findings.append(Finding("warning", "zero_map", "ZERO_MAP_FAILED", err, "Check zero_map.py."))
            continue
        path = DATA_DOCTOR / f"zero_map_{p}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        map_paths.append(str(path))
        all_findings.extend(summarize_map(data))

    state = "CRITICAL" if any(f.severity == "critical" for f in all_findings) else ("WOUNDED" if any(f.severity == "warning" for f in all_findings) else "STABLE")
    plan = build_repair_plan(problem, all_findings)
    report = DoctorReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        state=state,
        problem=problem or "general health check",
        map_profiles=profiles,
        findings=[asdict(f) for f in all_findings],
        repair_plan=[asdict(t) for t in plan],
        map_summary_path=", ".join(map_paths),
        notes=[
            "zero_doctor used zero_map as primary sensor source.",
            "Apply tasks only with explicit --apply TASK and --yes when required.",
            "Foundation Layer 0 verifieras av foundation.py vid varje uppstart.",
        ],
    )
    save_report(report)
    return report

def save_report(report: DoctorReport) -> Path:
    DATA_DOCTOR.mkdir(parents=True, exist_ok=True)
    path = DATA_DOCTOR / "zero_doctor_report.json"
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def print_report(report: DoctorReport) -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  Zero Doctor v2.0 — Medical Tricorder Deluxe                       ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  State:       {report.state}")
    print(f"  Problem:     {report.problem}")
    print(f"  Profiles:    {', '.join(report.map_profiles)}")
    print(f"  Map files:   {report.map_summary_path or '(none)'}")
    print()
    print("  Findings:")
    for f in report.findings:
        print(f"   - [{f['severity'].upper()}] {f['subsystem']}::{f['code']} — {f['message']}")
        if f.get("recommendation"):
            print(f"       → {f['recommendation']}")
    print()
    print("  Repair plan:")
    if not report.repair_plan:
        print("   - No repair tasks recommended.")
    for t in report.repair_plan:
        print(f"   - {t['name']} [{t['risk']}] — {t['description']}")
        if t.get("command_hint"):
            print(f"       {t['command_hint']}")
    print()
    print(f"  Report saved: {ROOT / 'data' / 'doctor' / 'zero_doctor_report.json'}")
    print()

def apply_task(name: str, yes: bool = False) -> int:
    if name not in TASKS:
        print(f"Unknown task: {name}")
        return 2
    task = TASKS[name]
    if task.risk == "FORBIDDEN":
        print(f"FORBIDDEN: {task.description}")
        print(task.command_hint)
        return 3
    if not task.implemented:
        print(f"Not implemented automatically: {task.description}")
        print(task.command_hint)
        return 3
    if task.requires_yes and not yes:
        print(f"Task '{name}' is {task.risk} and requires --yes.")
        print(f"Hint: {task.command_hint}")
        return 1

    if name == "clear-pycache":
        removed = 0
        for p in ROOT.rglob("__pycache__"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True); removed += 1
        for p in ROOT.rglob("*.pyc"):
            try:
                p.unlink(); removed += 1
            except Exception:
                pass
        print(f"Removed pycache/pyc items: {removed}")
        return 0

    if name == "fix-env-permissions":
        env = ROOT / ".env"
        if not env.exists():
            print(".env not found"); return 1
        env.chmod(0o600); print("Set .env permissions to 600"); return 0

    if name == "restart-ollama":
        ok, out = run_cmd(["sudo", "systemctl", "restart", "ollama"], timeout=40); print(out); return 0 if ok else 1

    if name in ("restart-zero", "restart-zero-v2"):
        # Hitta rätt service automatiskt
        service = "zero-web-v2.service" if name == "restart-zero-v2" else "zero-web.service"
        ok, out = run_cmd(["sudo", "systemctl", "restart", service], timeout=40)
        print(out); return 0 if ok else 1

    if name == "run-evolution":
        try:
            from app.drm_memory import run_evolution_loop
            result = run_evolution_loop(force=True)
            print(f"Evolution: {result}")
            return 0
        except Exception as e:
            print(f"Evolution misslyckades: {e}"); return 1

    if name == "check-embeddings":
        try:
            from app.drm_memory import check_embedding_health, check_embedding_drift
            import json as _json
            health = check_embedding_health()
            drift  = check_embedding_drift()
            print(_json.dumps({"health": health, "drift": drift}, indent=2, ensure_ascii=False))
            return 0 if health["ok"] else 1
        except Exception as e:
            print(f"Embedding-check misslyckades: {e}"); return 1

    if name == "accept-layer0-change":
        try:
            from app.foundation import accept_layer0_change
            accept_layer0_change()
            return 0
        except Exception as e:
            print(f"Layer 0 accept misslyckades: {e}"); return 1

    if name == "restart-postgres-container":
        if not which("docker"):
            print("docker not found"); return 1
        ok, names = run_cmd(["docker", "ps", "--format", "{{.Names}}"], timeout=20)
        if not ok:
            print(names); return 1
        candidates = [n for n in names.splitlines() if any(x in n.lower() for x in ["postgres", "zero"])]
        if not candidates:
            print("No likely postgres/zero container found."); return 1
        ok, out = run_cmd(["docker", "restart", candidates[0]], timeout=60); print(out); return 0 if ok else 1

    print(f"No handler for task: {name}")
    return 2

def list_tasks() -> None:
    print("Available Doctor tasks:")
    for t in TASKS.values():
        print(f"  {t.name:28} [{t.risk}] {t.description}")

def main() -> int:
    ap = argparse.ArgumentParser(description="Zero Doctor v2.0")
    ap.add_argument("--check", action="store_true", help="General health check.")
    ap.add_argument("--diagnose", type=str, default=None, help="Diagnose a problem.")
    ap.add_argument("--repair-plan", type=str, default=None, help="Create repair plan for a problem.")
    ap.add_argument("--profile", type=str, default=None, help="Force a zero_map profile.")
    ap.add_argument("--list-tasks", action="store_true", help="List repair tasks.")
    ap.add_argument("--apply", type=str, default=None, help="Apply a specific task.")
    ap.add_argument("--yes", action="store_true", help="Approve CAUTION task.")
    ap.add_argument("--json", action="store_true", help="Print JSON report for diagnose/check.")
    ap.add_argument("--semantic", action="store_true", help="Kör semantisk hälsokoll (embedding health + drift).")
    args = ap.parse_args()

    if args.list_tasks:
        list_tasks(); return 0
    if args.apply:
        return apply_task(args.apply, yes=args.yes)
    if args.semantic:
        return apply_task("check-embeddings")

    problem = args.diagnose or args.repair_plan or ("general health check" if args.check else "")
    report = diagnose(problem, profile=args.profile)
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 2 if report.state == "CRITICAL" else (1 if report.state == "WOUNDED" else 0)

if __name__ == "__main__":
    raise SystemExit(main())
