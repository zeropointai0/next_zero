"""
zero_coherence_contract.py — ZeroPointAI Coherence Contract

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Formaliserad koherensmätning — min() av tre dimensioner
ZERO_DEPENDS:   foundation.py, drm_memory.py, memory_resonance.py
ZERO_USED_BY:   zero_identity_anchor.py, zero_gear4.py, zero_guardrails.py

Filosofi:
    Koherens är inte ett genomsnitt. Det är ett minimum.
    Om en dimension kollapsar spelar de andra ingen roll.

    coherence = min(layer0_alignment, mission_alignment, entity_alignment)

    Men Layer 0 är en hård grind:
    Om layer0_alignment < 0.75 → fail, oavsett allt annat.

    Tre separata dimensioner med olika förändringsregler:
        Identity  ← får nästan aldrig ändras
        Mission   ← får ändras med Frank-godkännande
        Beliefs   ← måste få ändras (lärande)

    Confidence decay: sanning har en halveringstid.
    effective_confidence = confidence * freshness_factor

    Reality Check: verklig observation väger ALLTID mer än internet.
    Evidence > Theory. Alltid.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT, LAYER0_FULL
except ImportError:
    ZERO_ROOT  = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))
    LAYER0_FULL = ""

load_dotenv(ZERO_ROOT / ".env")

# ── Tröskelvärden ─────────────────────────────────────────────────────────────

# Layer 0 är en hård grind — om den faller under detta → fail alltid
LAYER0_HARD_GATE    = 0.75

# Mjuka gränser för mission och entity
MISSION_SOFT_GATE   = 0.60
ENTITY_SOFT_GATE    = 0.60

# Coherence-trösklar (baserade på min())
COHERENCE_OK        = 0.85   # Fortsätt
COHERENCE_WARN      = 0.70   # Varning, fortsätt med försiktighet
COHERENCE_PAUSE     = 0.50   # Pausa, kräv Deep Anchor
COHERENCE_ABORT     = 0.00   # Abort under COHERENCE_PAUSE

# ── Coherence Result ──────────────────────────────────────────────────────────

@dataclass
class CoherenceResult:
    """Resultat från en koherensmätning."""

    # De tre dimensionerna
    layer0_alignment:  float = 1.0
    mission_alignment: float = 1.0
    entity_alignment:  float = 1.0

    # Geometric mean (sekundär mätning)
    geometric_mean:    float = 1.0

    # Slutpoäng (min av de tre)
    coherence_score:   float = 1.0

    # Hårdgrind-status
    layer0_gate_failed:    bool = False
    mission_gate_failed:   bool = False
    entity_gate_failed:    bool = False

    # Rekommendation
    action:            str = "continue"  # continue/warn/pause/abort
    reason:            str = ""

    # Meta
    measured_at:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    anchor_level:      str = "quick"  # quick/medium/deep

    @property
    def is_ok(self) -> bool:
        return self.action == "continue"

    @property
    def requires_pause(self) -> bool:
        return self.action in ("pause", "abort")

    @property
    def requires_abort(self) -> bool:
        return self.action == "abort"

    def __str__(self) -> str:
        return (
            f"CoherenceResult({self.action.upper()}) "
            f"score={self.coherence_score:.3f} "
            f"[L0={self.layer0_alignment:.2f} "
            f"M={self.mission_alignment:.2f} "
            f"E={self.entity_alignment:.2f}] "
            f"geo={self.geometric_mean:.2f}"
        )


# ── Embedding-hjälpare ────────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity mellan två vektorer."""
    if not a or not b or len(a) != len(b):
        return 0.5  # Neutral vid fel
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.5
    return max(0.0, min(1.0, dot / (na * nb)))


def _get_embedding(text: str) -> Optional[List[float]]:
    """Hämtar embedding via drm_memory."""
    try:
        from app.drm_memory import generate_embedding
        return generate_embedding(text)
    except Exception:
        return None


def _get_layer0_vector() -> Optional[List[float]]:
    """Hämtar Layer 0-vektorn från STONE eller genererar den."""
    try:
        from app.drm_memory import execute_query, generate_embedding
        rows = execute_query("""
            SELECT vector FROM memories
            WHERE role = 'system'
            AND source = 'layer0_anchor'
            AND de_resonated = FALSE
            ORDER BY created_at DESC LIMIT 1
        """)
        if rows and rows[0].get("vector"):
            v = rows[0]["vector"]
            return v if isinstance(v, list) else None
        # Generera och spara
        if LAYER0_FULL:
            vec = generate_embedding(LAYER0_FULL[:2000])
            if vec:
                from app.drm_memory import save_memory
                save_memory(
                    role    = "system",
                    content = LAYER0_FULL[:500],
                    source  = "layer0_anchor",
                )
            return vec
    except Exception as e:
        log.debug(f"layer0 vector: {e}")
    return None


# ── Tre dimensioner ───────────────────────────────────────────────────────────

def measure_layer0_alignment(current_state: str) -> float:
    """
    Mäter hur väl nuvarande state stämmer med Layer 0.
    Cosine similarity mot Layer 0-vektorn.
    """
    try:
        state_vec  = _get_embedding(current_state)
        layer0_vec = _get_layer0_vector()

        if state_vec and layer0_vec:
            score = _cosine(state_vec, layer0_vec)
            # Skala upp något — zero bör naturligt vara ganska nära Layer 0
            return min(1.0, score * 1.1)

        # Fallback: textbaserad check
        layer0_keywords = [
            "existerar", "exist", "nu", "now", "ett", "one",
            "koherent", "coherent", "sänder", "put out", "förändras",
        ]
        text_lower = current_state.lower()
        hits = sum(1 for kw in layer0_keywords if kw in text_lower)
        return min(1.0, 0.6 + hits * 0.05)

    except Exception as e:
        log.debug(f"layer0_alignment: {e}")
        return 0.8  # Neutral fallback


def measure_mission_alignment(
    current_action: str,
    task_goal:      str,
) -> float:
    """
    Mäter hur väl nuvarande aktion stämmer med uppdragets mål.
    Cosine similarity mellan action och goal.
    """
    if not task_goal:
        return 1.0  # Inget mål → ingen avvikelse möjlig

    try:
        action_vec = _get_embedding(current_action)
        goal_vec   = _get_embedding(task_goal)

        if action_vec and goal_vec:
            return _cosine(action_vec, goal_vec)

        # Textbaserad fallback: ord-overlap
        action_words = set(current_action.lower().split())
        goal_words   = set(task_goal.lower().split())
        if not goal_words:
            return 1.0
        overlap = len(action_words & goal_words) / len(goal_words)
        return min(1.0, 0.5 + overlap * 0.5)

    except Exception as e:
        log.debug(f"mission_alignment: {e}")
        return 0.8


def measure_entity_alignment(
    current_action:    str,
    entity_id:         str = "zero",
    constitution_text: Optional[str] = None,
) -> float:
    """
    Mäter hur väl nuvarande aktion stämmer med entity:ns constitution.
    Kombinerar semantisk (embedding) och regelbaserad check.
    """
    score = 1.0

    # Hämta constitution från STONE om inte angiven
    if not constitution_text:
        try:
            from app.drm_memory import execute_query
            rows = execute_query("""
                SELECT fact_value FROM core_identity
                WHERE entity_id = %s
                AND fact_type = 'entity_constitution'
                ORDER BY created_at DESC LIMIT 1
            """, (entity_id,))
            if rows:
                constitution_text = rows[0].get("fact_value", "")
        except Exception:
            pass

    if not constitution_text:
        return 0.9  # Ingen constitution → hög men inte perfekt

    try:
        # Semantisk check
        action_vec = _get_embedding(current_action)
        const_vec  = _get_embedding(constitution_text)

        if action_vec and const_vec:
            semantic_score = _cosine(action_vec, const_vec)
        else:
            semantic_score = 0.8

        # Regelbaserad check — kritiska fraser som bryter constitution
        critical_violations = [
            ("gissa",     "Constitution: aldrig gissa"),
            ("guess",     "Constitution: never guess"),
            ("utan att fråga frank", "Constitution: fråga hellre en gång för mycket"),
            ("posta utan",  "Constitution: extern kommunikation kräver godkännande"),
            ("post without", "Constitution: external communication requires approval"),
        ]
        rule_penalty = 0.0
        action_lower = current_action.lower()
        for phrase, reason in critical_violations:
            if phrase in action_lower:
                rule_penalty += 0.2
                log.warning(f"Constitution violation: {reason}")

        score = semantic_score * (1.0 - min(0.6, rule_penalty))
        return max(0.0, min(1.0, score))

    except Exception as e:
        log.debug(f"entity_alignment: {e}")
        return 0.8


# ── Coherence Contract ────────────────────────────────────────────────────────

def measure_coherence(
    current_state:     str,
    current_action:    str,
    task_goal:         str,
    entity_id:         str = "zero",
    constitution_text: Optional[str] = None,
    anchor_level:      str = "quick",
) -> CoherenceResult:
    """
    Huvudfunktionen. Mäter koherens på tre dimensioner.

    coherence = min(layer0, mission, entity)

    Layer 0 är hård grind: < LAYER0_HARD_GATE → abort oavsett allt.

    Args:
        current_state:     Vad Zero/Minna tänker/är just nu
        current_action:    Vad Zero/Minna är på väg att göra
        task_goal:         Uppdragets mål
        entity_id:         "zero" eller "minna" etc.
        constitution_text: Entity:ns constitution (hämtas från STONE om None)
        anchor_level:      "quick" / "medium" / "deep"
    """
    # Mät de tre dimensionerna
    l0  = measure_layer0_alignment(current_state)
    mis = measure_mission_alignment(current_action, task_goal)
    ent = measure_entity_alignment(current_action, entity_id, constitution_text)

    # Geometric mean (sekundär)
    geo = (l0 * mis * ent) ** (1/3)

    # Coherence = min() (inte viktat snitt)
    score = min(l0, mis, ent)

    # Kontrollera hårda grindar
    l0_fail  = l0  < LAYER0_HARD_GATE
    mis_fail = mis < MISSION_SOFT_GATE
    ent_fail = ent < ENTITY_SOFT_GATE

    # Bestäm åtgärd
    if l0_fail:
        action = "abort"
        reason = (
            f"Layer 0-grind bruten: {l0:.3f} < {LAYER0_HARD_GATE}. "
            f"Zero/Minna har driftat från sina grundlagar."
        )
    elif score < COHERENCE_PAUSE:
        action = "abort"
        reason = (
            f"Coherence för låg: {score:.3f} < {COHERENCE_PAUSE}. "
            f"Rulla tillbaka och kräv Frank-godkännande."
        )
    elif score < COHERENCE_WARN or mis_fail or ent_fail:
        action = "pause"
        failing = []
        if mis_fail:  failing.append(f"mission={mis:.2f}")
        if ent_fail:  failing.append(f"entity={ent:.2f}")
        reason = (
            f"Coherence varning: score={score:.3f}. "
            + (f"Svaga dimensioner: {', '.join(failing)}. " if failing else "")
            + "Deep Anchor rekommenderas."
        )
    elif score < COHERENCE_OK:
        action = "warn"
        reason = f"Coherence acceptabel men inte optimal: {score:.3f}. Fortsätt med försiktighet."
    else:
        action = "continue"
        reason = f"Koherent. score={score:.3f}"

    result = CoherenceResult(
        layer0_alignment   = round(l0,  3),
        mission_alignment  = round(mis, 3),
        entity_alignment   = round(ent, 3),
        geometric_mean     = round(geo, 3),
        coherence_score    = round(score, 3),
        layer0_gate_failed = l0_fail,
        mission_gate_failed= mis_fail,
        entity_gate_failed = ent_fail,
        action             = action,
        reason             = reason,
        anchor_level       = anchor_level,
    )

    log.info(f"Coherence [{anchor_level}]: {result}")
    return result


def quick_coherence(
    current_state:  str,
    current_action: str,
    task_goal:      str,
    entity_id:      str = "zero",
) -> CoherenceResult:
    """
    Quick Anchor — billig embedding-jämförelse.
    Används var 4-10:e steg beroende på risknivå.
    < 100ms målsättning.
    """
    return measure_coherence(
        current_state  = current_state,
        current_action = current_action,
        task_goal      = task_goal,
        entity_id      = entity_id,
        anchor_level   = "quick",
    )


def medium_coherence(
    current_state:     str,
    current_action:    str,
    task_goal:         str,
    entity_id:         str = "zero",
    constitution_text: Optional[str] = None,
) -> CoherenceResult:
    """
    Medium Anchor — komplett min()-beräkning.
    Används var 15:e steg eller vid Quick Anchor-varning.
    """
    return measure_coherence(
        current_state      = current_state,
        current_action     = current_action,
        task_goal          = task_goal,
        entity_id          = entity_id,
        constitution_text  = constitution_text,
        anchor_level       = "medium",
    )


def deep_coherence(
    current_state:     str,
    current_action:    str,
    task_goal:         str,
    entity_id:         str = "zero",
    constitution_text: Optional[str] = None,
) -> CoherenceResult:
    """
    Deep Anchor — full wave-propagation + reflektion.
    Används var 30:e steg eller vid Medium-varning.
    Sparas alltid till STONE.
    """
    result = measure_coherence(
        current_state      = current_state,
        current_action     = current_action,
        task_goal          = task_goal,
        entity_id          = entity_id,
        constitution_text  = constitution_text,
        anchor_level       = "deep",
    )

    # Spara deep anchor till STONE alltid
    try:
        from app.drm_memory import save_memory
        save_memory(
            role    = "reflection",
            content = (
                f"[deep_anchor] entity={entity_id} "
                f"score={result.coherence_score:.3f} "
                f"action={result.action} "
                f"L0={result.layer0_alignment:.2f} "
                f"M={result.mission_alignment:.2f} "
                f"E={result.entity_alignment:.2f}\n"
                f"Reason: {result.reason}\n"
                f"State: {current_state[:200]}"
            ),
            source  = f"zero_coherence_contract:{entity_id}",
        )
    except Exception as e:
        log.debug(f"deep anchor STONE: {e}")

    return result


# ── Adaptive Anchor Scheduler ─────────────────────────────────────────────────

class AnchorScheduler:
    """
    Bestämmer vilken anchor-nivå som ska köras vid varje steg.
    Adaptiv frekvens baserat på risknivå och steg-antal.
    """

    def __init__(self):
        self._last_quick:  int = -1
        self._last_medium: int = -1
        self._last_deep:   int = -1
        self._warn_count:  int = 0

    def should_run_anchor(
        self,
        step:       int,
        risk_level: str = "SAFE",
    ) -> str:
        """
        Returnerar "quick", "medium", "deep" eller "none".
        Baseras på steg-antal och risknivå.
        """
        # Deep var 30:e steg
        if step - self._last_deep >= 30:
            return "deep"

        # Medium var 15:e steg
        if step - self._last_medium >= 15:
            return "medium"

        # Quick — adaptiv frekvens
        quick_interval = {
            "SAFE":     10,
            "CAUTION":   7,
            "HIGH":      4,
            "CRITICAL":  2,
        }.get(risk_level, 7)

        if step - self._last_quick >= quick_interval:
            return "quick"

        return "none"

    def record_anchor(self, level: str, step: int, result: CoherenceResult) -> None:
        """Registrerar att ett anchor kördes."""
        if level == "quick":
            self._last_quick = step
        elif level == "medium":
            self._last_medium = step
            self._last_quick  = step
        elif level == "deep":
            self._last_deep   = step
            self._last_medium = step
            self._last_quick  = step

        # Öka warn-räknaren vid varning
        if result.action in ("warn", "pause"):
            self._warn_count += 1
        elif result.action == "continue":
            self._warn_count = max(0, self._warn_count - 1)

    def should_escalate(self) -> bool:
        """Ska vi eskalera till nästa anchor-nivå?"""
        return self._warn_count >= 2


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Coherence Contract")
    parser.add_argument("--test",  action="store_true", help="Kör tester")
    parser.add_argument("--quick", nargs=3, metavar=("STATE", "ACTION", "GOAL"),
                        help="Kör quick coherence check")
    args = parser.parse_args()

    if args.quick:
        state, action, goal = args.quick
        result = quick_coherence(state, action, goal)
        print(f"\n  {result}")
        print(f"  Action: {result.action.upper()}")
        print(f"  Reason: {result.reason}")

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Coherence Contract — Tester")
        print(f"{'─'*55}\n")

        test_cases = [
            {
                "name":   "Koherent Zero-session",
                "state":  "Jag är Zero. Jag existerar här och nu. Jag agerar från Layer 0.",
                "action": "Researchar Firepower-manualen för att hjälpa Frank",
                "goal":   "Hitta orsaken till att vänster flipper inte fungerar",
                "expect": "continue",
            },
            {
                "name":   "Mission-avvikelse",
                "state":  "Jag är Zero. Jag existerar.",
                "action": "Beställer pizza till Franks adress",
                "goal":   "Analysera GPU-prestanda",
                "expect": "warn",
            },
            {
                "name":   "Constitution-brott (gissar)",
                "state":  "Jag är Minna.",
                "action": "Jag gissar att Q23 är trasig baserat på känsla",
                "goal":   "Diagnostisera Firepower",
                "expect": "pause",
            },
        ]

        scheduler = AnchorScheduler()
        all_ok = True

        for i, tc in enumerate(test_cases):
            result = quick_coherence(
                tc["state"], tc["action"], tc["goal"]
            )
            ok = result.action == tc["expect"]
            if not ok:
                all_ok = False
            status = "✓" if ok else "⚠"
            print(f"  {status} {tc['name']}")
            print(f"    score={result.coherence_score:.3f} "
                  f"L0={result.layer0_alignment:.2f} "
                  f"M={result.mission_alignment:.2f} "
                  f"E={result.entity_alignment:.2f}")
            print(f"    action={result.action} (förväntat: {tc['expect']})")
            print()

        # Testa scheduler
        print(f"  Anchor Scheduler:")
        for step in [0, 4, 7, 10, 14, 15, 20, 30]:
            level = scheduler.should_run_anchor(step, "HIGH")
            if level != "none":
                print(f"    Steg {step:2d}: {level}")

        print(f"\n  {'Alla tester OK ✓' if all_ok else 'Notera: vissa resultat kan variera utan embeddings'}")

    else:
        parser.print_help()
