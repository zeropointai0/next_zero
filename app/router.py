"""
router.py — ZeroPointAI Intent Router v2.0

ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Intentionsöversättare. Frank uttrycker mål — Zero väljer handling.

Filosofi (från Claude + GPT + Grok):
    Zero ska inte förstå kommandon.
    Zero ska förstå mål.

    Frank → intention → Zero → zero_sudo → Linux
                                   ↓
                              loggar allt
                              kan återställa
                              Frank har veto vid risk

Arkitektur:
    router.py     ← identifierar intention
    zero_sudo.py  ← enda platsen kommandon körs
    zero_engine.py ← visar resultatet för Frank

Intent-kategorier:
    system_action   — diagnostik, status, hårdvara, tjänster
    hardware_intent — GPU, disk, RAM, nätverk, processer
    run_intent      — godtyckliga kommandon ("kör nvidia-smi")
    memory_action   — minnen, evolution, soul snapshot
    navigation      — appar, dashboard

Regler:
    - / (slash) bypasses alltid intent-detection
    - Inga hårdkodade sökvägar — allt via foundation.py
    - zero_sudo äger ALL exekvering — inget annat kör kommandon
    - Enkla SAFE-kommandon kör direkt, CAUTION/HIGH frågar Frank
    - evolution_loop körs bara om should_run_evolution() eller force=True
    - Zero förklarar alltid vad den tänker göra (Groks princip)
"""

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

import re
import shlex
import subprocess
from typing import Dict, List, Optional, Tuple

from app.foundation import APP_DIR


# ── Intent-patterns ───────────────────────────────────────────────────────────
# (pattern, action, category)
# Ordning spelar roll — mer specifika mönster först

INTENT_PATTERNS: List[Tuple[str, str, str]] = [

    # ── Diagnostik ────────────────────────────────────────────────────────────
    (r"\b(zero doctor|kör en zero doctor|run zero doctor|run doctor|"
     r"doctor check|system check|diagnostik)\b",
     "run_doctor", "system_action"),

    (r"\b(hur mår systemet|kolla status|visa status|"
     r"systemstatus|system status|zero status)\b",
     "show_status", "system_action"),

    (r"\b(sudo status|sudo-status|hur länge sudo|status för sudo)\b",
     "sudo_status", "system_action"),

    (r"\b(list trash|visa trash|visa papperskorg|trash status)\b",
     "list_trash", "system_action"),

    # ── Systemkarta ───────────────────────────────────────────────────────────
    (r"\b(scanna|skanna|kolla upp vad du har|vilka moduler har du|"
     r"vad har du för moduler|systemkarta|mappa systemet|"
     r"vad kan du göra|vad finns tillgängligt|"
     r"zero map|kör map|scan modules|what do you have)\b",
     "run_zero_map_fast", "system_action"),

    (r"\b(full diagnostik|kör diagnostik|doctor.?context|"
     r"full system.?check|full koll på systemet|"
     r"diagnostisera systemet)\b",
     "run_zero_map_doctor", "system_action"),

    # ── GPU / grafikkort ──────────────────────────────────────────────────────
    (r"\b(gpu.?temp(eratur)?|hur varm.*(gpu|grafik)|grafikkort.?temp|"
     r"vram.?använd|gpu.?last|gpu.?status|"
     r"hur.?mår.*(gpu|grafik)|gpu.?hälsa)\b",
     "hw_gpu_status", "hardware_intent"),

    # ── Disk / lagring ────────────────────────────────────────────────────────
    (r"\b(diskutrymme|disk.?space|hur mycket.*(plats|utrymme|lagring)|"
     r"ledigt.*(disk|utrymme|plats)|storage.?status|"
     r"df |lagring|disk.?hälsa|disk.?status)\b",
     "hw_disk_status", "hardware_intent"),

    # ── RAM / minne ───────────────────────────────────────────────────────────
    (r"\b(ram.?(använd|status|last|anv)|hur mycket.*(ram|minne).*(använd|kvar|fri)|"
     r"memory.?usage|minnes.?använd|free.?ram|ram anv|ram.?anv)\b",
     "hw_ram_status", "hardware_intent"),

    (r"^(ram|ram användning|ram-status)$",
     "hw_ram_status", "hardware_intent"),

    # ── CPU / processer ───────────────────────────────────────────────────────
    (r"\b(cpu.?(last|temp|status|använd)|processor.?last|"
     r"vilka processer|aktiva processer|top.?process|"
     r"vad körs|vad är igång)\b",
     "hw_process_status", "hardware_intent"),

    # ── Nätverk ───────────────────────────────────────────────────────────────
    (r"\b(nätverks.?status|network.?status|vilken.?ip|ip.?adress|"
     r"öppna.?portar|listening.?port|nätverks.?info)\b",
     "hw_network_status", "hardware_intent"),

    # ── Tjänster / services ───────────────────────────────────────────────────
    (r"\b(tjänste.?status|service.?status|vilka tjänster|"
     r"systemctl.?status|zero.*service|kör.*service)\b",
     "hw_service_status", "hardware_intent"),

    # ── Systemöversikt (allt på en gång) ──────────────────────────────────────
    (r"\b(system.?översikt|full.?status|"
     r"hur (mår|är det med).*(server|datorn|h9|maskinen|zero)|"
     r"hur mår server|hur mår servern|snabb.?status|quick.?status|system.?hälsa)\b",
     "hw_system_overview", "hardware_intent"),

    # ── Trust mode ────────────────────────────────────────────────────────────
    (r"\b(trust mode full|full trust|lita på dig själv|kör utan att fråga|"
     r"high autonomy|hög autonomi|zero trust full)\b",
     "set_trust_full", "system_action"),

    (r"\b(trust mode normal|normal trust|fråga som vanligt|"
     r"återställ trust|normal autonomi)\b",
     "set_trust_normal", "system_action"),

    # ── Godtyckliga kommandon — Frank kör vad som helst ──────────────────────
    # "kör nvidia-smi", "run ls /opt", "exec df -h"
    (r"^(kör|run|exec|execute|bash|terminal)\s+(.+)$",
     "run_command", "run_intent"),

    # ── Minne ─────────────────────────────────────────────────────────────────
    (r"\b(kalibrera minnet|kör evolution|uppdatera resonans|"
     r"evolution loop|minneskalibr|kalibrering)\b",
     "run_evolution", "memory_action"),

    (r"\b(minnesstatistik|minnes?stats|hur många minnen|"
     r"stone stats|drm stats|memory stats)\b",
     "show_memory_stats", "memory_action"),

    (r"\b(soul snapshot|skapa soul|spara soul|zero soul)\b",
     "create_soul_snapshot", "memory_action"),

    (r"\b(semantisk hälsa|embedding.?status|hur mår.*minne|embedding.?hälsa|"
     r"semantic.?health|embedding.?health|mår.*semantisk)\b",
     "show_semantic_health", "memory_action"),

    (r"\b(sök i minnet|sök minnen|hitta i minnet|memory search)\b",
     "search_memory", "memory_action"),

    # ── Navigation ────────────────────────────────────────────────────────────
    (r"\b(dash|dashboard|minnesstatus|memory status|hälsopanel)\b",
     "show_dash", "navigation"),

    (r"\b(lista (appar|moduler|filer)|show apps|visa scripts|"
     r"visa appar|visa moduler)\b",
     "show_apps", "navigation"),
]


# ── Hårdvarukommandon — whitelisted SAFE-kommandon ───────────────────────────
# Dessa körs direkt utan att fråga Frank

HW_COMMANDS = {
    "hw_gpu_status": {
        "cmd":  ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,"
                 "memory.used,memory.total,power.draw",
                 "--format=csv,noheader,nounits"],
        "desc": "GPU-status (temperatur, last, VRAM)",
        "risk": "SAFE",
    },
    "hw_disk_status": {
        "cmd":  ["df", "-h", "--output=target,size,used,avail,pcent"],
        "desc": "Diskutrymme",
        "risk": "SAFE",
    },
    "hw_ram_status": {
        "cmd":  ["free", "-h"],
        "desc": "RAM-användning",
        "risk": "SAFE",
    },
    "hw_process_status": {
        "cmd":  ["ps", "aux", "--sort=-%cpu"],
        "desc": "Aktiva processer sorterade efter CPU",
        "risk": "SAFE",
    },
    "hw_network_status": {
        "cmd":  ["bash", "-c", "ip -brief addr && ss -tlnp | grep LISTEN"],
        "desc": "Nätverksstatus och öppna portar",
        "risk": "SAFE",
    },
    "hw_service_status": {
        "cmd":  ["bash", "-c",
                 "systemctl list-units 'zero-*' --all --no-pager 2>/dev/null | head -20"],
        "desc": "Zero-tjänsternas status",
        "risk": "SAFE",
    },
    "hw_system_overview": {
        "cmd":  ["bash", "-c",
                 "echo '=== CPU ===' && uptime && "
                 "echo '=== RAM ===' && free -h && "
                 "echo '=== DISK ===' && df -h / /opt 2>/dev/null && "
                 "echo '=== GPU ===' && nvidia-smi --query-gpu=name,temperature.gpu,"
                 "utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null || "
                 "echo 'Ingen GPU hittad'"],
        "desc": "Systemöversikt — CPU, RAM, Disk, GPU",
        "risk": "SAFE",
    },
}


# ── Intent-detection ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _looks_like_system_query(lowered: str) -> bool:
    """
    Snabb check — verkar frågan handla om systemet?
    Eskalerar till Layer 2 (zero_system_intent) om ja.
    Undviker att eskalera vanlig konversation.
    """
    system_signals = [
        "varför", "hur mår", "vad händer", "vad finns",
        "vad heter", "vilka", "vad har", "vad kan",
        "berätta om", "förklara", "visa mig",
        "städa", "rensa", "frigör", "optimera",
        "skanna", "hitta", "sök efter",
        "installera", "sätt upp", "konfigurera",
        "backup", "återställ", "uppdatera",
        "slow", "långsam", "trög", "fel", "problem",
        "hälsa", "status", "rapport", "analys",
    ]
    # Undvik att eskalera ren konversation
    conversation_signals = [
        "tack", "okej", "bra", "hej", "haha",
        "vad tänker du", "vad tycker du", "berätta om dig",
        "vem är du", "hur är läget",
    ]
    if any(s in lowered for s in conversation_signals):
        return False
    return any(s in lowered for s in system_signals)


def detect_intent(text: str) -> Optional[Dict]:
    """
    Analyserar text och returnerar intent-dict om en systemåtgärd känns igen.
    Returnerar None om Zero ska svara normalt via provider.

    Slash-kommandon (/) bypass:ar alltid intent-detection.
    """
    original = (text or "").strip()
    lowered  = _normalize(original)

    if lowered.startswith("/"):
        return None

    for pattern, action, category in INTENT_PATTERNS:
        if re.search(pattern, lowered):
            return {
                "kind":     category,
                "action":   action,
                "original": original,
            }

    # Layer 2 — System Intent förståelse
    # Om ingen reflex matchade men frågan verkar systemrelaterad
    if _looks_like_system_query(lowered):
        return {
            "kind":     "system_intent",
            "action":   "understand_system_intent",
            "original": original,
        }

    return None


# ── Exekvering ────────────────────────────────────────────────────────────────

def execute_system_action(
    action:           str,
    engine=None,
    force:            bool = False,
    intent_original:  str  = "",
) -> Optional[str]:
    """
    Kör en systemåtgärd och returnerar ett svar som Zero kan presentera.

    Arkitektur:
        - zero_sudo äger all exekvering med loggning och backup
        - Fallback till subprocess för SAFE hårdvarukommandon
        - Frank har alltid veto vid CAUTION/HIGH risk
    """
    try:

        # ── Diagnostik ────────────────────────────────────────────────────────

        if action == "run_doctor":
            from app.zero_doctor import run_doctor
            return _format_doctor(run_doctor())

        if action == "show_status":
            return _format_status(engine)

        if action == "sudo_status":
            from app.zero_sudo import get_sudo_status
            return get_sudo_status()

        if action == "list_trash":
            from app.zero_sudo import list_trash
            return list_trash()

        # ── Systemkarta ───────────────────────────────────────────────────────

        # ── Trust mode ───────────────────────────────────────────────────────

        if action == "set_trust_full":
            try:
                from app.zero_sudo import trust_mode_full
                return trust_mode_full()
            except ImportError:
                return "zero_sudo saknas."

        if action == "set_trust_normal":
            try:
                from app.zero_sudo import trust_mode_normal
                return trust_mode_normal()
            except ImportError:
                return "zero_sudo saknas."

        # ── Layer 2: System Intent ────────────────────────────────────────────

        if action == "understand_system_intent":
            return _handle_system_intent(intent_original)

        if action == "run_zero_map_fast":
            return _run_zero_map("fast")

        if action == "run_zero_map_doctor":
            return _run_zero_map("doctor-context")

        # ── Hårdvara — whitelisted SAFE-kommandon ─────────────────────────────

        if action in HW_COMMANDS:
            hw = HW_COMMANDS[action]
            return _run_hw_command(hw["cmd"], hw["desc"], hw["risk"])

        # ── Godtyckligt kommando — Frank kör vad som helst ────────────────────

        if action == "run_command":
            raw = intent_original or ""
            cmd_str = re.sub(
                r"^(kör|run|exec|execute|bash|terminal)\s+",
                "", raw, flags=re.IGNORECASE
            ).strip()
            if not cmd_str:
                return "Vilket kommando vill du köra?"
            return _run_arbitrary_command(cmd_str)

        # ── Minne ─────────────────────────────────────────────────────────────

        if action == "run_evolution":
            return _run_evolution(force=force)

        if action == "show_memory_stats":
            from app.drm_memory import get_memory_stats, get_embedding_provider
            stats = get_memory_stats()
            lines = ["STONE-statistik:"]
            for key, value in stats.items():
                lines.append(
                    f"  {key}: {value:,}" if isinstance(value, int)
                    else f"  {key}: {value}"
                )
            lines.append(f"  embedding_provider: {get_embedding_provider()}")
            return "\n".join(lines)

        if action == "create_soul_snapshot":
            return _create_soul_snapshot()

        if action == "search_memory":
            return "Vad vill du att jag söker efter i minnet?"

        if action == "show_semantic_health":
            return _format_semantic_health()

        # ── Navigation ────────────────────────────────────────────────────────

        if action == "show_dash":
            return _format_dash(engine)

        if action == "show_apps":
            names = sorted(
                p.name for p in APP_DIR.glob("*.py")
                if not p.name.startswith("__")
            )
            return "Zero moduler:\n" + "\n".join(f"  {n}" for n in names[:60])

    except Exception as e:
        return f"Systemåtgärd '{action}' misslyckades: {e}"

    return None


# ── Kommandoexekvering ────────────────────────────────────────────────────────

def _handle_system_intent(goal: str) -> str:
    """
    Layer 2 — eskalerar till zero_system_intent för djup förståelse.
    Används när ingen regex-reflex matchade men frågan verkar systemrelaterad.
    """
    try:
        from app.zero_system_intent import handle_system_intent
        return handle_system_intent(goal)
    except ImportError:
        return (
            f"Jag förstår inte riktigt vad du menar med '{goal}'. "
            f"Prova att vara mer specifik, t.ex. 'gpu temp', 'diskutrymme', "
            f"eller 'kör [kommando]'."
        )
    except Exception as e:
        log.warning(f"system_intent: {e}")
        return None


def _run_hw_command(cmd: List[str], desc: str, risk: str = "SAFE") -> str:
    """
    Kör ett whitelistat hårdvarukommando och formaterar output snyggt.
    Försöker via zero_sudo, faller tillbaka till subprocess för SAFE.
    """
    try:
        from app.zero_sudo import run as sudo_run
        result = sudo_run(cmd, note=f"hw:{desc[:40]}")
        output = (result.get("stdout") or result.get("stderr") or "").strip()
        ok     = result.get("ok", True)
        if not ok:
            return f"{desc}:\n```\nFEL: {output[:500]}\n```"
    except Exception:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            output = (r.stdout or r.stderr or "Ingen output").strip()
            ok     = r.returncode == 0
        except FileNotFoundError:
            return f"{desc}: kommando ej tillgängligt."
        except subprocess.TimeoutExpired:
            return f"{desc}: timeout (>15s)."
        except Exception as e:
            return f"{desc}: {e}"

    return _format_hw_output(cmd, desc, output)


def _format_hw_output(cmd: List[str], desc: str, raw: str) -> str:
    """Formaterar hårdvaruoutput snyggt baserat på kommandotyp."""
    cmd_str = " ".join(cmd)

    # ── GPU (nvidia-smi CSV) ──────────────────────────────────────────────────
    if "nvidia-smi" in cmd_str and "csv" in cmd_str:
        lines = []
        for line in raw.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                name  = parts[0]
                temp  = parts[1] if len(parts) > 1 else "?"
                load  = parts[2] if len(parts) > 2 else "?"
                used  = parts[3] if len(parts) > 3 else "?"
                total = parts[4] if len(parts) > 4 else "?"
                power = parts[5] if len(parts) > 5 else ""
                lines.append(f"GPU: {name}")
                lines.append(f"  Temperatur : {temp}°C")
                lines.append(f"  Last       : {load}%")
                lines.append(f"  VRAM       : {used} MB / {total} MB")
                if power:
                    lines.append(f"  Effekt     : {power} W")
            else:
                lines.append(line)
        return "\n".join(lines) if lines else raw

    # ── Disk (df) ─────────────────────────────────────────────────────────────
    if cmd[0] == "df":
        lines = ["Diskutrymme:"]
        for line in raw.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] != "Filesystem" and parts[0] != "target":
                mount  = parts[0]
                size   = parts[1]
                used   = parts[2]
                avail  = parts[3]
                pct    = parts[4] if len(parts) > 4 else ""
                lines.append(f"  {mount:<25} {used:>6} / {size:<6} ({pct} använt, {avail} kvar)")
            elif parts and parts[0] not in ("Filesystem", "target"):
                lines.append(f"  {line}")
        return "\n".join(lines) if len(lines) > 1 else raw

    # ── RAM (free) ────────────────────────────────────────────────────────────
    if cmd[0] == "free":
        lines = ["RAM och swap:"]
        for line in raw.strip().splitlines():
            parts = line.split()
            if parts and parts[0] == "Mem:":
                total = parts[1] if len(parts) > 1 else "?"
                used  = parts[2] if len(parts) > 2 else "?"
                free  = parts[3] if len(parts) > 3 else "?"
                lines.append(f"  RAM   : {used} använt / {total} totalt ({free} fritt)")
            elif parts and parts[0] == "Swap:":
                total = parts[1] if len(parts) > 1 else "?"
                used  = parts[2] if len(parts) > 2 else "?"
                lines.append(f"  Swap  : {used} använt / {total} totalt")
        return "\n".join(lines) if len(lines) > 1 else raw

    # ── Processer (ps) ────────────────────────────────────────────────────────
    if "ps" in cmd_str:
        lines  = ["Aktiva processer (topp 5 CPU):"]
        count  = 0
        for line in raw.strip().splitlines():
            if "USER" in line and "PID" in line:
                continue  # Skippa header
            parts = line.split(None, 10)
            if len(parts) >= 11 and count < 5:
                pid  = parts[1]
                cpu  = parts[2]
                mem  = parts[3]
                cmd_ = parts[10][:40]
                lines.append(f"  PID {pid:<7} CPU {cpu:>5}%  MEM {mem:>5}%  {cmd_}")
                count += 1
        return "\n".join(lines) if len(lines) > 1 else raw

    # ── Nätverk (ip + ss) ─────────────────────────────────────────────────────
    if "ip" in cmd_str and "addr" in cmd_str:
        lines = ["Nätverksstatus:"]
        for line in raw.strip().splitlines():
            if line.strip():
                lines.append(f"  {line.strip()}")
        return "\n".join(lines[:20]) if len(lines) > 1 else raw

    # ── Systemöversikt (bash -c med flera kommandon) ──────────────────────────
    if "bash" in cmd_str and "CPU" in raw:
        # Lägg till lite luft
        formatted = raw.replace("=== CPU ===", "── CPU ──────────────")
        formatted = formatted.replace("=== RAM ===", "\n── RAM ──────────────")
        formatted = formatted.replace("=== DISK ===", "\n── Disk ─────────────")
        formatted = formatted.replace("=== GPU ===", "\n── GPU ─────────────")
        return formatted

    # ── Tjänster ─────────────────────────────────────────────────────────────
    if "systemctl" in cmd_str:
        lines = ["Tjänster:"]
        for line in raw.strip().splitlines():
            if "zero-" in line.lower() or "active" in line.lower():
                lines.append(f"  {line.strip()}")
        return "\n".join(lines) if len(lines) > 1 else raw

    # Fallback — rådata i kodblock
    return f"```\n{raw[:2000]}\n```"


def _run_arbitrary_command(cmd_str: str) -> str:
    """
    Kör ett godtyckligt kommando från Frank.

    Riskbedömning via zero_sudo:
        SAFE     → kör direkt, visa output
        CAUTION  → kör med git-backup först
        HIGH     → fråga Frank om godkännande
        CRITICAL → backup + 3s paus + bekräftelse
        FORBIDDEN → avvisa

    Frank är skaparen — Zero argumenterar aldrig,
    men loggar alltid och kan återställa.

    Säkerhetsregel: Aldrig shell=True.
    Om zero_sudo saknas → avvisa, kör aldrig direkt.
    """
    try:
        from app.zero_sudo import run as sudo_run, assess_risk

        # Riskbedömning
        assessment = assess_risk(cmd_str)
        risk_level = assessment.get("risk_level", "SAFE")
        forbidden  = assessment.get("forbidden", False)
        reason     = assessment.get("reason", "")

        if forbidden:
            return (
                f"Detta kommando är markerat som FORBIDDEN.\n"
                f"Anledning: {reason}\n"
                f"Om du verkligen vill köra det, kontakta mig direkt."
            )

        # Kör via zero_sudo (hanterar backup, loggning etc.)
        try:
            parts = shlex.split(cmd_str)
        except Exception:
            parts = ["bash", "-c", cmd_str]

        result = sudo_run(parts, note=f"frank:'{cmd_str[:60]}'")
        output = (result.get("stdout") or result.get("stderr") or "").strip()
        ok     = result.get("ok", True)
        backup = result.get("backup_ref", "")

        lines = [f"```", f"$ {cmd_str}"]
        if output:
            lines.append(output[:3000])
        else:
            lines.append("(inget output)")
        lines.append("```")

        if backup:
            lines.append(f"_Backup: {backup}_")
        if not ok:
            lines.append(f"_Kommandot returnerade felkod_")

        return "\n".join(lines)

    except ImportError:
        # zero_sudo saknas — avvisa hellre än att köra shell=True
        return (
            f"Kan inte köra `{cmd_str}` — zero_sudo är inte tillgänglig.\n"
            f"Kontrollera att zero_sudo.py finns i app/ och starta om Zero."
        )


# ── Formatering ───────────────────────────────────────────────────────────────

def _format_doctor(report) -> str:
    parts = [
        "Zero Doctor körd.",
        f"State: {report.state}",
        f"Root cause: {report.root_cause}",
        f"Recommended action: {report.recommended_action}",
    ]
    if getattr(report, "memory_read_only", False):
        parts.append("Memory guard är i READ_ONLY.")
    if getattr(report, "sherlock_started", False):
        parts.append("Sherlock Mode aktiverades.")
    return "\n".join(parts)


def _format_status(engine) -> str:
    if not engine:
        return "Engine-status är inte tillgänglig i detta läge."
    provider = getattr(engine, "provider", "?")
    db_ok    = getattr(engine, "db_ok", False)
    mem      = getattr(engine, "memory_count", 0)
    cost     = getattr(engine, "session_cost", 0)
    return (
        f"Zero status\n"
        f"  Provider : {provider}\n"
        f"  Databas  : {'OK' if db_ok else 'Inte ansluten'}\n"
        f"  Minnen   : {mem:,}\n"
        f"  Session  : ~{cost:.3f} kr"
    )


def _format_dash(engine) -> str:
    if not engine:
        return "Dashboard är inte tillgänglig utan aktiv engine."
    return (
        f"Dashboard\n"
        f"  Health   : {engine.get_health_score()}/100\n"
        f"  Kontext  : {engine.get_context_usage_pct():.1f}%\n"
        f"  Anrop    : {engine.session_calls}\n"
        f"  Latens   : {engine.last_latency}s"
    )


def _run_evolution(force: bool = False) -> str:
    from app.drm_memory import run_evolution_loop, should_run_evolution
    if not force:
        ok, reason = should_run_evolution()
        if not ok:
            return (
                f"Evolution behövs inte just nu.\n"
                f"  {reason}\n\n"
                f"Vill du köra ändå? Säg 'kör evolution nu' för att tvinga."
            )
    result = run_evolution_loop(force=force)
    if result.get("status") == "skipped":
        return f"Evolution hoppades över: {result.get('reason', '')}"
    steps = result.get("steps", [])
    lines = ["Evolution loop klar:"]
    for step in steps:
        lines.append(f"  {step}")
    return "\n".join(lines)


def _create_soul_snapshot() -> str:
    from app.drm_memory import run_evolution_loop
    result = run_evolution_loop(days_back=30, force=True)
    steps  = result.get("steps", [])
    if any("snapshot" in s.lower() for s in steps):
        return "Soul snapshot skapad."
    return "Soul snapshot misslyckades — kör evolution loop och försök igen."


def _format_semantic_health() -> str:
    try:
        from app.drm_memory import (
            check_embedding_health, check_embedding_drift,
            get_re_embed_queue, get_retrieval_audit,
        )
        health = check_embedding_health()
        drift  = check_embedding_drift()
        queue  = get_re_embed_queue(limit=5)
        audit  = get_retrieval_audit()
        lines  = ["Semantisk minneshälsa:"]
        lines.append(
            f"  Embedding:  {health['provider']} "
            f"({'degraded' if health['degraded'] else 'OK'}, "
            f"{health.get('dim', 0)} dim, {health.get('latency_ms', 0)}ms)"
        )
        lines.append(
            f"  Drift:      {'detekterad' if drift.get('drifted') else 'OK'} "
            f"(likhet={drift.get('cosine', 0):.3f})"
        )
        mixed = drift.get("mixed_universe_count", 0)
        if mixed > 0:
            lines.append(f"  Universum:  {mixed} minnen från annat embedding-universum")
        else:
            lines.append(f"  Universum:  OK — {drift.get('current_model', '?')}")
        lines.append(f"  Re-embed:   {len(queue)} minnen saknar embeddings")
        if audit:
            lines.append(
                f"  Retrieval:  {audit.get('memory_count', 0)} minnen, "
                f"top coherence={audit.get('top_coherence', 0):.2f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Semantisk hälsokoll misslyckades: {e}"


def _run_zero_map(profile: str = "fast") -> str:
    try:
        from app.zero_map import build_map, render_markdown, PROFILES
        if profile not in PROFILES:
            profile = "fast"
        data   = build_map(profile, verbose=False)
        result = render_markdown(data)
        if len(result) > 8000:
            result = (
                result[:8000]
                + "\n\n...[karta trunkerad — kör zero_map direkt för fullständig rapport]"
            )
        return result
    except Exception as e:
        return f"zero_map misslyckades: {e}"


# ── Force-evolution helper ────────────────────────────────────────────────────

def detect_force_evolution(text: str) -> bool:
    """Känner igen explicit Frank-godkännande för tvingad evolution."""
    lowered = _normalize(text)
    return bool(re.search(
        r"\b(kör evolution nu|tvinga evolution|force evolution|"
        r"evolution nu|kalibrering nu)\b",
        lowered
    ))
