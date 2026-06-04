"""
router.py — ZeroPointAI Intent Router

Mål:
  - Naturligt språk triggar riktiga systemkommandon
  - Systemstatus hallucinerar aldrig
  - Providerbyte påverkar inte systemåtgärder
  - Zero kan trigga evolution on-demand när systemet behöver det

Intent-kategorier:
  system_action  — doctor, status, sudo, trash
  memory_action  — sök minnen, evolution, soul snapshot, statistik
  navigation     — visa appar, dashboard

Regler:
  - Kommandot / (slash) bypasses alltid intent-detection
  - Inga hårdkodade sökvägar — allt via foundation.py
  - evolution_loop körs bara om should_run_evolution() säger OK
    eller Frank ger explicit godkännande (force=True)

ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Intent-detection. Naturligt språk → systemkommandon.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from app.foundation import APP_DIR


# ── Intent-patterns ───────────────────────────────────────────────────────────
# (pattern, action, category)

INTENT_PATTERNS: list[Tuple[str, str, str]] = [

    # ── System ────────────────────────────────────────────────────────────────
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

    # ── Systemkarta / zero_map ────────────────────────────────────────────────
    # Naturliga fraser Frank skulle säga
    (r"\b(scanna|skanna|kolla upp vad du har|vilka moduler har du|"
     r"vad har du för moduler|systemkarta|mappa systemet|"
     r"vad kan du göra|vad finns tillgängligt|"
     r"zero map|kör map|scan modules|what do you have)\b",
     "run_zero_map_fast", "system_action"),

    (r"\b(full diagnostik|kör diagnostik|doctor.?context|"
     r"full system.?check|full koll på systemet|"
     r"diagnostisera systemet)\b",
     "run_zero_map_doctor", "system_action"),
]


# ── Intent-detection ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_intent(text: str) -> Optional[Dict]:
    """
    Analyserar text och returnerar intent-dict om en systemåtgärd känns igen.
    Returnerar None om Zero ska svara normalt.

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
    return None


# ── Exekvering ────────────────────────────────────────────────────────────────

def execute_system_action(action: str,
                           engine=None,
                           force: bool = False) -> Optional[str]:
    """
    Kör en systemåtgärd och returnerar ett svar som Zero kan presentera.

    force=True: används bara för evolution (Frank-override av cooldown).
    """
    try:

        # ── System ────────────────────────────────────────────────────────────

        if action == "run_doctor":
            from app.zero_doctor import run_doctor
            report = run_doctor()
            return _format_doctor(report)

        if action == "show_status":
            return _format_status(engine)

        if action == "sudo_status":
            from app.zero_sudo import get_sudo_status
            return get_sudo_status()

        if action == "list_trash":
            from app.zero_sudo import list_trash
            return list_trash()

        # ── Minne ─────────────────────────────────────────────────────────────

        if action == "run_evolution":
            return _run_evolution(force=force)

        if action == "show_memory_stats":
            from app.drm_memory import get_memory_stats, get_embedding_provider
            stats = get_memory_stats()
            lines = ["📊 STONE-statistik:"]
            for key, value in stats.items():
                lines.append(f"  {key}: {value:,}" if isinstance(value, int)
                             else f"  {key}: {value}")
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
            names = sorted(p.name for p in APP_DIR.glob("*.py")
                           if not p.name.startswith("__"))
            return "Zero moduler:\n" + "\n".join(f"  {n}" for n in names[:60])

        if action == "run_zero_map_fast":
            return _run_zero_map("fast")

        if action == "run_zero_map_doctor":
            return _run_zero_map("doctor-context")

    except Exception as e:
        return f"Systemåtgärd '{action}' misslyckades: {e}"

    return None


# ── Formatering ───────────────────────────────────────────────────────────────

def _format_doctor(report) -> str:
    parts = [
        "🔬 Zero Doctor körd.",
        f"State: {report.state}",
        f"Root cause: {report.root_cause}",
        f"Recommended action: {report.recommended_action}",
    ]
    if getattr(report, 'memory_read_only', False):
        parts.append("⚠️ Memory guard är i READ_ONLY.")
    if getattr(report, 'sherlock_started', False):
        parts.append("🕵️ Sherlock Mode aktiverades.")
    return "\n".join(parts)


def _format_status(engine) -> str:
    if not engine:
        return "Engine-status är inte tillgänglig i detta läge."
    provider = getattr(engine, "provider", "?")
    db_ok    = getattr(engine, "db_ok", False)
    mem      = getattr(engine, "memory_count", 0)
    cost     = getattr(engine, "session_cost", 0)
    return (
        f"⚡ Zero status\n"
        f"  Provider : {provider}\n"
        f"  Databas  : {'OK ✓' if db_ok else 'Inte ansluten ✗'}\n"
        f"  Minnen   : {mem:,}\n"
        f"  Session  : ~{cost:.3f} kr"
    )


def _format_dash(engine) -> str:
    if not engine:
        return "Dashboard är inte tillgänglig utan aktiv engine."
    return (
        f"📊 Dashboard\n"
        f"  Health   : {engine.get_health_score()}/100\n"
        f"  Kontext  : {engine.get_context_usage_pct():.1f}%\n"
        f"  Anrop    : {engine.session_calls}\n"
        f"  Latens   : {engine.last_latency}s"
    )


def _run_evolution(force: bool = False) -> str:
    """
    Kör evolution-loop om systemet behöver det.
    Utan force: kontrollerar should_run_evolution() och cooldown.
    Med force: kör direkt (Frank-godkännande).
    """
    from app.drm_memory import run_evolution_loop, should_run_evolution

    if not force:
        ok, reason = should_run_evolution()
        if not ok:
            return (
                f"🔄 Evolution behövs inte just nu.\n"
                f"  {reason}\n\n"
                f"Vill du köra ändå? Säg 'kör evolution nu' för att tvinga."
            )

    result = run_evolution_loop(force=force)

    if result.get("status") == "skipped":
        return f"🔄 Evolution hoppades över: {result.get('reason', '')}"

    steps = result.get("steps", [])
    lines = ["🔄 Evolution loop klar:"]
    for step in steps:
        lines.append(f"  ✓ {step}")
    return "\n".join(lines)


def _create_soul_snapshot() -> str:
    """Skapar en soul snapshot manuellt."""
    from app.drm_memory import run_evolution_loop
    result = run_evolution_loop(days_back=30, force=True)
    steps = result.get("steps", [])
    snapshot_created = any("snapshot" in s.lower() for s in steps)
    if snapshot_created:
        return "✨ Soul snapshot skapad."
    return "Soul snapshot misslyckades — kör evolution loop och försök igen."


# ── Force-evolution helper ────────────────────────────────────────────────────

def _format_semantic_health() -> str:
    """Formaterar semantisk hälsostatus för Zero att presentera."""
    try:
        from app.drm_memory import (
            check_embedding_health, check_embedding_drift,
            get_re_embed_queue, get_retrieval_audit,
        )
        health = check_embedding_health()
        drift  = check_embedding_drift()
        queue  = get_re_embed_queue(limit=5)
        audit  = get_retrieval_audit()

        lines = ["🧠 Semantisk minneshälsa:"]
        lines.append(f"  Embedding:  {health['provider']} "
                     f"({'degraded' if health['degraded'] else 'OK'}, "
                     f"{health.get('dim', 0)} dim, {health.get('latency_ms', 0)}ms)")
        lines.append(f"  Drift:      {'⚠️ detekterad' if drift.get('drifted') else 'OK'} "
                     f"(likhet={drift.get('cosine', 0):.3f})")
        mixed = drift.get('mixed_universe_count', 0)
        if mixed > 0:
            lines.append(f"  Universum:  ⚠️ {mixed} minnen från annat embedding-universum")
        else:
            lines.append(f"  Universum:  OK — alla vektorer från {drift.get('current_model', '?')}")
        lines.append(f"  Re-embed:   {len(queue)} minnen saknar embeddings")

        if audit:
            lines.append(
                f"  Senaste retrieval: {audit.get('memory_count', 0)} minnen, "
                f"wave_depth={audit.get('wave_depth', 0)}, "
                f"top coherence={audit.get('top_coherence', 0):.2f}"
            )
            if audit.get('attractors_hit'):
                lines.append(f"  Attraktorer: {', '.join(audit['attractors_hit'])}")

        if not health['ok']:
            lines.append("  ⚠️  DEGRADED: Wave-sökning kör på keyword + recency")
        elif health['degraded']:
            lines.append("  ⚠️  FALLBACK: Ollama nere, sentence-transformers aktiv")

        return "\n".join(lines)
    except Exception as e:
        return f"Semantisk hälsokoll misslyckades: {e}"


def _run_zero_map(profile: str = "fast") -> str:
    """
    Kör zero_map.py med angiven profil och returnerar resultatet.
    Zero kan nu scanna och förstå sitt eget system.
    """
    try:
        from app.zero_map import build_map, render_markdown, PROFILES
        if profile not in PROFILES:
            profile = "fast"
        data   = build_map(profile, verbose=False)
        result = render_markdown(data)
        # Begränsa längden för chat-svar
        if len(result) > 8000:
            result = result[:8000] + "\n\n...[karta trunkerad — kör zero_map direkt för fullständig rapport]"
        return result
    except Exception as e:
        return f"zero_map misslyckades: {e}"


def detect_force_evolution(text: str) -> bool:
    """Känner igen explicit Frank-godkännande för tvingad evolution."""
    lowered = _normalize(text)
    return bool(re.search(
        r"\b(kör evolution nu|tvinga evolution|force evolution|"
        r"evolution nu|kalibrering nu)\b",
        lowered
    ))
