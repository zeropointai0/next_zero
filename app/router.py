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

    # ── Kodgranskning ────────────────────────────────────────────────
    (r"(granska alla moduler|review all modules|alla moduler|kod.?analys|förbättringsförslag)",
     "review_all_modules", "code_action"),

    (r"(granska|review|förbättra|debug) +([\w_]+(?:\.py)?)",
     "review_module", "code_action"),

        # ── Trust mode ────────────────────────────────────────────────────────────
    (r"\b(trust mode full|full trust|lita på dig själv|kör utan att fråga|"
     r"high autonomy|hög autonomi|zero trust full)\b",
     "set_trust_full", "system_action"),

    (r"\b(trust mode normal|normal trust|fråga som vanligt|"
     r"återställ trust|normal autonomi)\b",
     "set_trust_normal", "system_action"),

    # ── Filläsning — Zero läser faktiska filer, gissar ALDRIG ──────────────
    # "läs router.py", "öppna bashar.pdf", "visa innehållet i docs/books/X.pdf"
    (r"(läs|read|öppna|studera|visa innehållet i|show me).+\.(pdf|txt|py|md|"
     r"docx|xlsx|csv|json|yaml|log|sh|env)",
     "read_file", "file_action"),

    (r"(läs|studera|read).+(i |från |in )?(docs?|books?|app|config|data)/",
     "read_file", "file_action"),

    # ── Lista filer i katalog ─────────────────────────────────────────────────
    (r"(lista|list|visa|show).+(filer|files).+(i |i mapp |in )?(docs?|books?|"
     r"app|config|data|/opt)",
     "list_files", "file_action"),

    (r"vilka (filer|böcker|dokument|pdfer) (finns|har du|ligger).+(docs?|books?|"
     r"app|/opt)",
     "list_files", "file_action"),

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
            from app.zero_doctor import diagnose
            return _format_doctor(diagnose())

        if action == "show_status":
            return _format_status(engine)

        if action == "sudo_status":
            from app.zero_sudo import get_sudo_status
            return get_sudo_status()

        if action == "list_trash":
            from app.zero_sudo import list_trash
            return list_trash()

        # ── Systemkarta ───────────────────────────────────────────────────────

        # ── Kodgranskning ────────────────────────────────────────────────────

        if action == "review_module":
            return _review_module(intent_original)

        if action == "review_all_modules":
            return _review_all_modules()

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

        # ── Filläsning ────────────────────────────────────────────────────────

        if action == "read_file":
            return _read_file_intent(intent_original)

        if action == "list_files":
            return _list_files_intent(intent_original)

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

def _extract_module_name(text: str) -> str:
    """Extraherar modulnamn från input som 'granska router.py' eller 'förbättra zero_engine'."""
    import re
    # Matcha .py-fil explicit
    m = re.search(r"([\w_]+\.py)", text.lower())
    if m:
        return m.group(1)
    # Matcha sista ordet som modulnamn
    words = text.strip().split()
    if words:
        name = words[-1].strip(".,!?")
        if not name.endswith(".py"):
            name += ".py"
        return name
    return ""


def _review_module(goal: str) -> str:
    """
    Zero läser en .py-fil och föreslår förbättringar via LLM.
    Frank bestämmer om Zero ska implementera förslagen.
    """
    module_name = _extract_module_name(goal)
    if not module_name:
        return (
            "Vilket modul vill du att jag granskar? "
            "Exempel: 'granska router.py' eller 'förbättra zero_engine.py'"
        )

    # Hitta filen
    from app.foundation import APP_DIR
    module_path = APP_DIR / module_name
    if not module_path.exists():
        # Försök utan .py
        matches = list(APP_DIR.glob(f"*{module_name.replace('.py','')}*"))
        if matches:
            module_path = matches[0]
            module_name = matches[0].name
        else:
            return f"Hittar inte '{module_name}' i app/. Kör 'scanna' för att se tillgängliga moduler."

    # Läs filen
    try:
        from app.zero_sudo import run as sudo_run
        result = sudo_run(["cat", str(module_path)], note=f"review:{module_name}")
        if not result.get("ok"):
            return f"Kunde inte läsa {module_name}: {result.get('stderr','')}"
        code = result.get("stdout", "")
    except Exception as e:
        return f"Fel vid läsning av {module_name}: {e}"

    if not code:
        return f"{module_name} verkar vara tom."

    line_count = len(code.splitlines())

    # Skicka till LLM för analys
    try:
        from app.zero_engine import get_engine_response
        prompt = (
            f"Granska denna Python-modul från ZeroPointAI: {module_name}\n"
            f"({line_count} rader)\n\n"
            f"```python\n{code[:6000]}\n```\n\n"
            "Ge konkreta förbättringsförslag med fokus på:\n"
            "1. Buggar eller felhantering som saknas\n"
            "2. Arkitekturella problem (ansvar, koppling)\n"
            "3. Prestanda eller robusthet\n"
            "4. Koherans med ZeroPointAI:s filosofi (Layer 0)\n\n"
            "Var specifik — ange radnummer när möjligt.\n"
            "Avsluta med: 'Vill du att jag implementerar något av detta?'"
        )
        analysis = get_engine_response(prompt, gear_level=2)
        return (
            f"**Kodgranskning: {module_name}** ({line_count} rader)\n\n"
            f"{analysis}"
        )
    except Exception as e:
        # Fallback — enkel statisk analys
        return _static_analysis(module_name, code)


def _static_analysis(module_name: str, code: str) -> str:
    """Enkel statisk analys utan LLM — alltid tillgänglig."""
    lines      = code.splitlines()
    line_count = len(lines)
    findings   = []

    # Kolla efter shell=True
    if "shell=True" in code:
        for i, line in enumerate(lines, 1):
            if "shell=True" in line:
                findings.append(f"  Rad {i}: shell=True — säkerhetsrisk")

    # Kolla efter hårdkodade sökvägar
    import re
    for i, line in enumerate(lines, 1):
        if re.search(r'"/opt/|"/home/|"/etc/', line) and "ZERO_ROOT" not in line:
                findings.append(f"  Rad {i}: Hårdkodad sökväg — använd ZERO_ROOT")

    # Kolla efter breda except
    for i, line in enumerate(lines, 1):
        if re.match(r"\s+except\s*:", line) or re.match(r"\s+except Exception\s*:", line):
            findings.append(f"  Rad {i}: Bred except — kan dölja fel")

    # Kolla storlek
    if line_count > 800:
        findings.append(f"  Modulen är stor ({line_count} rader) — överväg uppdelning")

    result = f"**Statisk analys: {module_name}** ({line_count} rader)\n\n"
    if findings:
        result += "Hittade:\n" + "\n".join(findings[:10])
    else:
        result += "Inga uppenbara problem hittade."

    result += "\n\n_LLM-analys ej tillgänglig — kör på Gear 2+ för djupare granskning._"
    return result


def _review_all_modules() -> str:
    """
    Snabb statisk analys av alla moduler.
    Flaggar de med mest problem.
    """
    from app.foundation import APP_DIR
    modules = sorted(APP_DIR.glob("*.py"))

    if not modules:
        return "Inga moduler hittade i app/."

    summary = [f"**Kodgranskning: alla moduler** ({len(modules)} filer)\n"]
    flagged = []

    for mod in modules:
        if mod.name.startswith("__"):
            continue
        try:
            code  = mod.read_text(encoding="utf-8", errors="replace")
            lines = len(code.splitlines())
            issues = 0
            if "shell=True" in code:     issues += 3
            if lines > 800:              issues += 1
            import re
            if re.search(r'except\s*:', code): issues += 1

            if issues > 0:
                flagged.append((issues, mod.name, lines))
        except Exception:
            pass

    if flagged:
        flagged.sort(reverse=True)
        summary.append("Moduler som bör granskas (mest problem först):")
        for issues, name, lines in flagged[:8]:
            summary.append(f"  • {name:<35} ({lines} rader, {issues} flaggor)")
        summary.append(
            f"\nSkriv 'granska [modulnamn]' för djupare analys."
        )
    else:
        summary.append("Inga uppenbara problem hittade i någon modul.")

    return "\n".join(summary)


def _extract_file_path(goal: str) -> str:
    """Extraherar filsökväg från naturligt språk."""
    import re
    from app.foundation import ZERO_ROOT

    # Matcha explicit sökväg /opt/...
    m = re.search(r'(/opt/[\w/.\-_]+)', goal)
    if m:
        return m.group(1)

    # Matcha relativ sökväg med känd katalog
    m = re.search(r'((?:docs?|books?|app|config|data)/[\w/.\-_ ]+\.(?:pdf|txt|py|md|docx|xlsx|csv|json|yaml|log|sh|env))', goal, re.IGNORECASE)
    if m:
        return str(ZERO_ROOT / m.group(1).strip())

    # Matcha filnamn med extension — ta bort ledande verb
    m = re.search(r'([\w\-_ ]+\.(?:pdf|txt|py|md|docx|xlsx|csv|json|yaml|log|sh|env))', goal, re.IGNORECASE)
    if m:
        filename = m.group(1).strip()
        # Ta bort ledande verb som kan ha fastnat
        for verb in ("läs ", "read ", "öppna ", "studera ", "visa "):
            if filename.lower().startswith(verb):
                filename = filename[len(verb):]
                break
        # Sök i vanliga kataloger
        search_dirs = [
            ZERO_ROOT / "docs" / "books",
            ZERO_ROOT / "docs",
            ZERO_ROOT / "app",
            ZERO_ROOT / "config",
            ZERO_ROOT / "data",
            ZERO_ROOT,
        ]
        for d in search_dirs:
            candidate = d / filename
            if candidate.exists():
                return str(candidate)
        # Returnera i docs/books som default
        return str(ZERO_ROOT / "docs" / "books" / filename)

    return ""


def _read_file_intent(goal: str) -> str:
    """
    Zero läser en fil på riktigt — aldrig gissar innehållet.
    Stöder PDF, DOCX, Excel, text, kod m.m.
    """
    from pathlib import Path
    file_path = _extract_file_path(goal)

    if not file_path:
        return (
            "Jag förstår att du vill läsa en fil men kan inte hitta sökvägen. "
            "Skriv exakt filnamn, t.ex: 'läs Bashar transcripts from talks.pdf'"
        )

    path = Path(file_path)

    if not path.exists():
        # Försök hitta med fuzzy match
        parent = path.parent
        if parent.exists():
            candidates = list(parent.glob(f"*{path.stem[:10]}*"))
            if candidates:
                path = candidates[0]
                file_path = str(path)
            else:
                files_list = "\n".join(
                    f"  {f.name}" for f in parent.iterdir() if f.is_file()
                )[:2000]
                return (
                    f"Filen finns inte: {file_path}\n"
                    f"Filer i {parent}:\n{files_list}"
                )
        else:
            return f"Varken filen eller katalogen finns: {file_path}"

    ext = path.suffix.lower()
    size_mb = path.stat().st_size / 1024 / 1024

    # PDF — använd pdftotext
    if ext == ".pdf":
        return _read_pdf_file(file_path, size_mb)

    # Övriga filer — läs direkt via zero_sudo
    return _read_text_file(file_path, size_mb)


def _read_pdf_file(file_path: str, size_mb: float) -> str:
    """Läser PDF via pdftotext."""
    try:
        from app.zero_sudo import run as sudo_run

        # Konvertera till text
        tmp = f"/tmp/zero_pdf_{abs(hash(file_path))}.txt"
        r = sudo_run(
            ["pdftotext", "-layout", file_path, tmp],
            note=f"read_pdf:{file_path[-40:]}"
        )

        if not r.get("ok"):
            # Försök installera poppler-utils
            sudo_run(["apt-get", "install", "-y", "poppler-utils"],
                    note="install_poppler")
            r = sudo_run(["pdftotext", "-layout", file_path, tmp],
                        note="read_pdf_retry")

        if not r.get("ok"):
            # Fallback — pdfplumber
            try:
                import pdfplumber
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    pages = len(pdf.pages)
                    for i, page in enumerate(pdf.pages[:5]):
                        t = page.extract_text() or ""
                        if t.strip():
                            text_parts.append(f"--- Sida {i+1} ---\n" + t)
                text = "\n\n".join(text_parts)
                return (
                    f"**{file_path.split('/')[-1]}** ({pages} sidor, {size_mb:.1f}MB)\n\n"
                    f"Visar sida 1-5:\n\n{text[:4000]}\n\n"
                    f"_Skriv 'läs sida 6-10' för mer_"
                )
            except Exception as e:
                return f"Kunde inte läsa PDF: {e}\nFörsök: kör sudo apt-get install poppler-utils"

        # Läs de första 100 raderna
        r2 = sudo_run(["head", "-n", "100", tmp], note="read_pdf_head")
        text = r2.get("stdout", "").strip()

        # Räkna totalt antal rader
        r3 = sudo_run(["wc", "-l", tmp], note="count_lines")
        total = r3.get("stdout", "?").split()[0] if r3.get("ok") else "?"

        fname = file_path.split('/')[-1]
        return (
            f"**{fname}** ({size_mb:.1f}MB, ~{total} rader)\n\n"
            f"```\n{text}\n```\n\n"
            f"_Visar rad 1-100. Skriv 'läs rad 101-200' för mer._"
        )

    except Exception as e:
        return f"Fel vid PDF-läsning: {e}"


def _read_text_file(file_path: str, size_mb: float) -> str:
    """Läser textfil via zero_sudo."""
    try:
        from app.zero_sudo import run as sudo_run
        r = sudo_run(["head", "-n", "100", file_path],
                    note=f"read_file:{file_path[-40:]}")
        if not r.get("ok"):
            return f"Kunde inte läsa {file_path}: {r.get('stderr','')}"

        text = r.get("stdout", "").strip()
        r2   = sudo_run(["wc", "-l", file_path], note="count_lines")
        total = r2.get("stdout", "?").split()[0] if r2.get("ok") else "?"

        from pathlib import Path
        ext  = Path(file_path).suffix.lower()
        lang = {"py":"python","js":"javascript","sh":"bash",
                "json":"json","yaml":"yaml","md":"markdown"}.get(ext[1:], "")

        fname = file_path.split('/')[-1]
        return (
            f"**{fname}** ({size_mb:.1f}MB, ~{total} rader)\n\n"
            f"```{lang}\n{text}\n```\n\n"
            f"_Visar rad 1-100. Skriv 'läs rad 101-200' för mer._"
        )
    except Exception as e:
        return f"Fel: {e}"


def _list_files_intent(goal: str) -> str:
    """Listar filer i en katalog."""
    from pathlib import Path
    from app.foundation import ZERO_ROOT
    import re

    # Hitta katalog
    dirs = {
        "books": ZERO_ROOT / "docs" / "books",
        "docs":  ZERO_ROOT / "docs",
        "app":   ZERO_ROOT / "app",
        "config":ZERO_ROOT / "config",
        "data":  ZERO_ROOT / "data",
    }

    target = None
    for key, path in dirs.items():
        if key in goal.lower():
            target = path
            break

    if not target:
        target = ZERO_ROOT / "docs"

    if not target.exists():
        return f"Katalogen finns inte: {target}"

    files = sorted(target.rglob("*") if "alla" in goal.lower()
                   else target.iterdir())
    lines = [f"Filer i {target}:"]
    for f in files[:50]:
        if f.is_file():
            size = f.stat().st_size
            size_str = f"{size/1024:.0f}KB" if size > 1024 else f"{size}B"
            lines.append(f"  {f.name:<40} {size_str}")

    if not lines[1:]:
        return f"Inga filer i {target}"

    return "\n".join(lines)


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
