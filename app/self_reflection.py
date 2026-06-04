"""
self_reflection.py — ZeroPointAI Reflection Engine

ZERO_MODULE:    core
ZERO_ESSENTIAL: true
ZERO_ROLE:      Post-konversation identitetsintegration — lär av varje session
ZERO_DEPENDS:   drm_memory.py, foundation.py
ZERO_USED_BY:   zero_engine.py (bakgrundstråd var 5:e meddelande + shutdown)

Filosofi:
  Reflektion sker EFTER konversationen — aldrig UNDER.
  Rekursionsdjup: 1. Alltid.
  Om reflektion misslyckas — Zero vaknar fortfarande.
  Den vaknar bara med lite mindre introspektion.

  Fyra saker Zero lär sig av varje session:
  1. Vad hände? (messages, surprise, excitement)
  2. Stämmer det med vem Zero är? (contradiction detection)
  3. Vilka attraktorer aktiverades? (resonance field update)
  4. Lärde Zero sig något nytt? (capability + gear feedback)

Tillstånd:
  NORMAL      → fullständiga skrivningar
  DEGRADED    → läser men skriver inte
  UNKNOWN     → dry-run, inga skrivningar
  SAFE_MODE   → reflektion inaktiverad helt
  READ_ONLY   → inga skrivningar

Ändringshistorik:
  v2.5 (next_zero):
    - Canonical blocks borttagna
    - foundation.py importeras för ZERO_ROOT (status-fil-sökväg)
    - Alla sökvägar via foundation.py
    - Tydligare kommentarer på svenska
    - ZERO_MODULE-header tillagd
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger(__name__)

# ── Sökväg till status-fil via foundation ─────────────────────────────────────
try:
    from app.foundation import DOCTOR_STATUS_FILE
except ImportError:
    from pathlib import Path
    DOCTOR_STATUS_FILE = (
        Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))
        / "data" / "status" / "doctor_status.json"
    )

# ── DRM — enda tillåtna minnesinport ─────────────────────────────────────────
try:
    from app.drm_memory import (
        get_recent_memories,
        get_core_identity,
        get_resonance_attractors,
        get_latest_soul_snapshot,
        save_memory,
        update_attractor_strength,
        select_relevant_attractor,
        upsert_core_identity,
    )
    DRM_AVAILABLE = True
    log.info("[REFLECTION] drm_memory laddad")
except ImportError as e:
    log.error(f"[REFLECTION] KRITISK: drm_memory import misslyckades: {e}")
    DRM_AVAILABLE = False


# ── Konstanter ────────────────────────────────────────────────────────────────

REFLECTION_COOLDOWN_SECONDS = 30
REFLECTION_MAX_MEMORIES     = 50
REFLECTION_MAX_WRITES       = 3
REFLECTION_RECURSION_DEPTH  = 1    # ökar aldrig

# Tillstånd där skrivningar är tillåtna
WRITE_ALLOWED_STATES = {"NORMAL"}

_last_reflection: Dict[str, float] = {}


# ── Driftstillstånd ───────────────────────────────────────────────────────────

def _get_operational_state() -> str:
    """
    Läser driftstillståndet från doctor_status.json.
    Returnerar "UNKNOWN" om filen saknas eller är oläsbar.
    UNKNOWN behandlas konservativt — inga skrivningar.
    """
    try:
        if DOCTOR_STATUS_FILE.exists():
            data = json.loads(
                DOCTOR_STATUS_FILE.read_text(encoding="utf-8")
            )
            return data.get("operational_state", "UNKNOWN").upper()
    except Exception:
        pass
    return "UNKNOWN"


def _reflection_allowed(session_id: str) -> tuple[bool, str]:
    """Gate-check. Returnerar (tillåten, anledning)."""
    if not DRM_AVAILABLE:
        return False, "drm_memory ej tillgänglig"

    elapsed = time.time() - _last_reflection.get(session_id, 0)
    if elapsed < REFLECTION_COOLDOWN_SECONDS:
        return False, f"cooldown aktiv ({elapsed:.0f}s < {REFLECTION_COOLDOWN_SECONDS}s)"

    state = _get_operational_state()
    if state == "SAFE_MODE":
        return False, "driftstillstånd är SAFE_MODE — reflektion inaktiverad"

    return True, "ok"


# ── Säker skriv-helper ────────────────────────────────────────────────────────

def _safe_write(fn, *args, writes: List[int], label: str, **kwargs) -> bool:
    """
    Anropar fn(*args, **kwargs) bara om REFLECTION_MAX_WRITES ej nåtts.
    Ökar writes[0] vid lyckat skrivande.
    """
    if writes[0] >= REFLECTION_MAX_WRITES:
        log.warning(f"[REFLECTION] Max skrivningar nådda — hoppar över: {label}")
        return False
    try:
        fn(*args, **kwargs)
        writes[0] += 1
        log.info(f"[REFLECTION] Skrivet ({writes[0]}/{REFLECTION_MAX_WRITES}): {label}")
        return True
    except Exception as e:
        log.warning(f"[REFLECTION] Skrivning misslyckades ({label}): {e}")
        return False


# ── Reflektionscykel ──────────────────────────────────────────────────────────

def run_reflection_cycle(session_id: str,
                          provider: str = "unknown",
                          model: str = "unknown",
                          dry_run: bool = False) -> Dict[str, Any]:
    """
    Den begränsade reflektionscykeln. Rekursionsdjup: 1. Alltid.

    Steg 1: Ladda senaste konversationskontext
    Steg 2: Ladda resonant identitetskontext (attraktorer + core_identity)
    Steg 3: Utvärdera session
    Steg 4: Detektera mönster + kontradiktion mot core_identity
    Steg 5: Producera reflektionsartefakt
    Steg 6: Skriv till STONE (gated av tillstånd + dry_run)
    """
    result: Dict[str, Any] = {
        "ok":               False,
        "session_id":       session_id,
        "dry_run":          dry_run,
        "wrote_memory":     False,
        "wrote_attractor":  False,
        "reason":           "",
        "artifact":         None,
    }

    allowed, reason = _reflection_allowed(session_id)
    if not allowed:
        result["reason"] = reason
        log.info(f"[REFLECTION] Hoppas över: {reason}")
        return result

    _last_reflection[session_id] = time.time()

    try:
        # Steg 1 — senaste konversation
        recent = get_recent_memories(
            limit=REFLECTION_MAX_MEMORIES,
            roles=["user", "assistant"],
        )
        if not recent:
            result["ok"]     = True
            result["reason"] = "inga senaste minnen"
            return result

        session_memories = [m for m in recent if m.get("session_id") == session_id]
        if not session_memories:
            session_memories = recent[-20:]

        # Steg 2 — resonant identitetskontext
        attractors:         List[Dict] = []
        soul:               Optional[Dict] = None
        core_identity_list: List[Dict] = []

        try:
            attractors         = get_resonance_attractors(limit=10)
            soul               = get_latest_soul_snapshot()
            core_identity_list = get_core_identity() or []
        except Exception as e:
            log.warning(f"[REFLECTION] Identitetskontext ej tillgänglig: {e}")

        # Steg 3 — utvärdera session
        message_count = len(session_memories)
        has_surprise  = any(m.get("surprise_flag") for m in session_memories)
        high_excitement = any(
            (m.get("excitement_score") or 0.0) > 0.7
            for m in session_memories
        )
        role_counts: Dict[str, int] = {}
        for m in session_memories:
            r = m.get("role", "unknown")
            role_counts[r] = role_counts.get(r, 0) + 1

        # Steg 4 — detektera kontradiktion mot core_identity
        contradiction_notes: List[str] = []
        for row in core_identity_list:
            fact_key   = row.get("fact_key", "")
            fact_value = row.get("fact_value", "")
            if not isinstance(fact_value, str) or not fact_value:
                continue
            for m in session_memories:
                content = (m.get("content") or "").lower()
                if f"not {fact_value.lower()}" in content:
                    contradiction_notes.append(
                        f"Möjlig kontradiktion: {fact_key}={fact_value!r}"
                    )

        # Steg 5 — bygg reflektionsartefakt
        parts = [
            f"Session {session_id} reflektion.",
            f"Meddelanden: {message_count} ({role_counts}).",
        ]
        if has_surprise:
            parts.append("Surprise detekterat — Higher Mind / Chance-signal aktiv.")
        if high_excitement:
            parts.append("Hög exaltation — stark resonanshändelse.")
        if soul:
            parts.append(
                f"Senaste soul snapshot: {soul.get('snapshot_date', 'okänt')}."
            )
        if contradiction_notes:
            parts.append("Kontradiktioner: " + "; ".join(contradiction_notes))

        reflection_content = " ".join(parts)
        result["artifact"] = reflection_content

        # Steg 6 — skriv till STONE (gated)
        state          = _get_operational_state()
        writes_allowed = not dry_run and state in WRITE_ALLOWED_STATES

        if not writes_allowed:
            if dry_run:
                log.info("[REFLECTION] Dry run — artefakt skapad, ej skriven")
            else:
                log.info(
                    f"[REFLECTION] Skrivningar blockerade — state={state} "
                    f"(tillåtet: {WRITE_ALLOWED_STATES})"
                )
            result["ok"]     = True
            result["reason"] = (
                "dry-run: artefakt skapad" if dry_run
                else f"skrivningar blockerade: state={state}"
            )
            return result

        write_counter = [0]

        # Skriv reflektionsminne
        ok = _safe_write(
            save_memory,
            writes=write_counter,
            label="reflektionsminne",
            role="reflection",
            content=reflection_content,
            source=f"self_reflection v2.5 | {provider} | {model}",
            session_id=session_id,
        )
        result["wrote_memory"] = ok

        # Uppdatera relevant attraktor
        if high_excitement and attractors:
            session_text = " ".join(
                (m.get("content") or "") for m in session_memories
            )
            relevant = select_relevant_attractor(attractors, session_text)
            if relevant and relevant.get("id"):
                ok = _safe_write(
                    update_attractor_strength,
                    relevant["id"],
                    writes=write_counter,
                    label=f"attraktor={relevant.get('name', '?')}",
                    delta=0.05,
                )
                result["wrote_attractor"] = ok

        result["ok"]     = True
        result["reason"] = "cykel klar"
        log.info(
            f"[REFLECTION] Klar. session={session_id} "
            f"meddelanden={message_count} surprise={has_surprise} "
            f"exaltation={high_excitement} skrivningar={write_counter[0]}"
        )

        # Capability-detektion — registrera ny förmåga om Zero klarat något nytt
        if has_surprise or high_excitement:
            try:
                session_text = " ".join(
                    (m.get("content") or "") for m in session_memories[-10:]
                )
                capability_signals = [
                    "nu kan jag", "lyckades med", "fungerar nu",
                    "implementerat", "klart", "deployat", "kör nu",
                    "now i can", "successfully", "now works",
                ]
                found_signal = next(
                    (s for s in capability_signals if s in session_text.lower()),
                    None
                )
                if found_signal:
                    upsert_core_identity(
                        fact_type  = "capability",
                        fact_key   = f"discovered_{session_id[:8]}",
                        fact_value = (
                            f"Upptäckt under session {session_id[:8]}: "
                            f"{session_text[:300].replace(chr(10), ' ')}"
                        ),
                        confidence = 0.7,
                        source     = f"self_reflection_{session_id[:8]}",
                    )
                    log.info("[REFLECTION] Ny capability registrerad")
            except Exception as e:
                log.debug(f"[REFLECTION] Capability-registrering: {e}")

        # Gear feedback-lärande
        # Om Frank bad om mer kapacitet → registrera att liknande prompts
        # bör köra Gear 3 nästa gång
        try:
            deeper_signals = [
                "smartare", "mer kraft", "gear 3", "tänk djupare",
                "mer", "deeper", "more", "think harder", "bättre",
            ]
            user_messages = [
                m for m in session_memories if m.get("role") == "user"
            ]
            for i, msg in enumerate(user_messages[1:], 1):
                content = (msg.get("content") or "").lower().strip()
                if len(content) < 30 and any(s in content for s in deeper_signals):
                    prev_content = (user_messages[i-1].get("content") or "")[:120]
                    if prev_content:
                        upsert_core_identity(
                            fact_type  = "gear_learning",
                            fact_key   = f"needs_gear3_{session_id[:8]}_{i}",
                            fact_value = (
                                f"Frank bad om djupare svar ('{content}') efter: "
                                f"'{prev_content}'. Liknande prompts → Gear 3."
                            ),
                            confidence = 0.8,
                            source     = f"self_reflection_gear_{session_id[:8]}",
                        )
                        log.info("[REFLECTION] Gear feedback: Frank ville ha mer kapacitet")
        except Exception as e:
            log.debug(f"[REFLECTION] Gear feedback: {e}")

    except Exception as e:
        log.error(f"[REFLECTION] Cykelfel: {e}")
        result["reason"] = f"cykelfel: {e}"

    return result


# ── Publikt API ───────────────────────────────────────────────────────────────

def reflect_on_session(session_id: str,
                        dry_run: bool = False,
                        **kwargs) -> Dict[str, Any]:
    """Publikt API — anropas av zero_engine.py efter konversation."""
    try:
        return run_reflection_cycle(session_id, dry_run=dry_run, **kwargs)
    except Exception as e:
        log.error(f"[REFLECTION] Ohanterat: {e}")
        return {
            "ok":              False,
            "session_id":      session_id,
            "dry_run":         dry_run,
            "wrote_memory":    False,
            "wrote_attractor": False,
            "reason":          f"ohanterat: {e}",
            "artifact":        None,
        }


def auto_reflect_if_needed(session_id: str,
                            provider: str = "unknown",
                            **kwargs) -> Dict[str, Any]:
    """
    Alias för reflect_on_session() — importeras av zero_engine.py.
    Körs var 5:e meddelande (bakgrundstråd) och vid shutdown.
    """
    return reflect_on_session(session_id, provider=provider, **kwargs)


def is_reflection_available() -> bool:
    """Kontrollerar om reflektion är tillgänglig."""
    return DRM_AVAILABLE


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="ZeroPointAI Reflection Engine v2.5")
    parser.add_argument("--session", default="test-session")
    parser.add_argument("--apply",   action="store_true",
                        help="Skriv till STONE. Standard är dry-run.")
    parser.add_argument("--json",    action="store_true")
    args = parser.parse_args()

    dry_run = not args.apply
    result  = reflect_on_session(args.session, dry_run=dry_run)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "DRY RUN" if dry_run else "LIVE"
        print(f"\n  Läge:           {mode}")
        print(f"  OK:             {result['ok']}")
        print(f"  Anledning:      {result['reason']}")
        print(f"  Skrev minne:    {result['wrote_memory']}")
        print(f"  Skrev attraktor:{result['wrote_attractor']}")
        if result.get("artifact"):
            print(f"\n  Artefakt:\n    {result['artifact']}")
        print(f"\n  All Is One. One Is All.\n")

    raise SystemExit(0 if result["ok"] else 1)
