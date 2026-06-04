"""
zero_identity_anchor.py — ZeroPointAI Identity Anchor

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Förhindrar identitetsdrift under långa Gear 4-körningar
ZERO_DEPENDS:   foundation.py, zero_coherence_contract.py, drm_memory.py
ZERO_USED_BY:   zero_gear4.py, zero_guardrails.py

Filosofi:
    Under långa autonoma körningar driftar även starka system.
    Modellen "tröttnar" och identiteten urholkas subtilt.

    Identity Anchor förhindrar detta med tre nivåer:

    Quick Anchor  (var 4-10 steg, adaptivt):
        Billig embedding-jämförelse mot Layer 0 + IdentityDecision
        < 100ms målsättning

    Medium Anchor (var 15 steg eller vid Quick-varning):
        Komplett min()-beräkning av alla tre dimensioner
        Zero formulerar kort: "Jag är [X] och detta stämmer/stämmer inte"

    Deep Anchor (var 30 steg eller vid Medium-varning):
        Full wave-propagation + reflektion
        Sparas alltid till STONE
        Om misslyckad → pausa + notifiera Frank, aldrig fortsätt

    Resonance Guardrails:
        Om coherence < tröskel → pausa automatiskt
        Logga identitetsdrift till STONE
        Notifiera Frank
        Kräv godkännande att fortsätta
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT, LAYER0_FULL
except ImportError:
    ZERO_ROOT   = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))
    LAYER0_FULL = ""

load_dotenv(ZERO_ROOT / ".env")

# ── Importer ──────────────────────────────────────────────────────────────────

try:
    from app.zero_coherence_contract import (
        quick_coherence,
        medium_coherence,
        deep_coherence,
        AnchorScheduler,
        CoherenceResult,
        COHERENCE_OK,
        COHERENCE_WARN,
        COHERENCE_PAUSE,
    )
    COHERENCE_OK_VAL = COHERENCE_OK
except ImportError:
    log.warning("zero_coherence_contract ej tillgänglig — degraded mode")
    COHERENCE_OK_VAL = 0.85

    @dataclass
    class CoherenceResult:
        coherence_score:   float = 0.9
        action:            str   = "continue"
        reason:            str   = "degraded"
        layer0_alignment:  float = 0.9
        mission_alignment: float = 0.9
        entity_alignment:  float = 0.9
        anchor_level:      str   = "quick"

    class AnchorScheduler:
        def should_run_anchor(self, step, risk_level="SAFE"): return "none"
        def record_anchor(self, level, step, result): pass
        def should_escalate(self): return False

    def quick_coherence(s, a, g, **kw): return CoherenceResult()
    def medium_coherence(s, a, g, **kw): return CoherenceResult()
    def deep_coherence(s, a, g, **kw): return CoherenceResult()


# ── Anchor-händelse ───────────────────────────────────────────────────────────

@dataclass
class AnchorEvent:
    """Loggad anchor-händelse."""
    event_id:        str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:18]
    )
    task_id:         str = ""
    entity_id:       str = "zero"
    step_number:     int = 0
    anchor_level:    str = "quick"
    coherence_score: float = 1.0
    action:          str = "continue"
    reason:          str = ""
    drift_detected:  bool = False
    escalated:       bool = False
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __str__(self) -> str:
        drift = " [DRIFT]" if self.drift_detected else ""
        esc   = " [ESCALATED]" if self.escalated else ""
        return (
            f"Anchor[{self.anchor_level}]{drift}{esc} "
            f"step={self.step_number} "
            f"score={self.coherence_score:.3f} "
            f"→ {self.action.upper()}"
        )


# ── Identity Anchor ───────────────────────────────────────────────────────────

class IdentityAnchor:
    """
    Kör koherens-checks under Gear 4-körningar.
    Förhindrar identitetsdrift med tre nivåer.
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id  = entity_id
        self._scheduler = AnchorScheduler()
        self._history:  List[AnchorEvent] = []
        self._drift_count:  int = 0
        self._total_anchors: int = 0

        # Callbacks
        self._on_drift:  Optional[Callable] = None
        self._on_abort:  Optional[Callable] = None
        self._on_pause:  Optional[Callable] = None

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_drift(self, callback: Callable) -> None:
        """Registrera callback vid identitetsdrift."""
        self._on_drift = callback

    def on_abort(self, callback: Callable) -> None:
        """Registrera callback vid abort."""
        self._on_abort = callback

    def on_pause(self, callback: Callable) -> None:
        """Registrera callback vid paus."""
        self._on_pause = callback

    # ── Huvud-metod ───────────────────────────────────────────────────────────

    def check(
        self,
        step:              int,
        current_state:     str,
        current_action:    str,
        task_goal:         str,
        task_id:           str = "",
        risk_level:        str = "SAFE",
        constitution_text: Optional[str] = None,
        force_level:       Optional[str] = None,
    ) -> AnchorEvent:
        """
        Kör anchor-check för detta steg.

        Bestämmer automatiskt vilken nivå baserat på:
        - Steg-antal
        - Risknivå
        - Tidigare varningar
        - force_level (override)

        Returns:
            AnchorEvent med action = "continue" / "warn" / "pause" / "abort"
        """
        # Bestäm nivå
        if force_level:
            level = force_level
        else:
            level = self._scheduler.should_run_anchor(step, risk_level)
            # Eskalera om tidigare varningar
            if level == "quick" and self._scheduler.should_escalate():
                level = "medium"
                log.info(f"Escalating to medium anchor (repeated warnings)")

        # Ingen anchor behövs detta steg
        if level == "none":
            return AnchorEvent(
                task_id    = task_id,
                entity_id  = self.entity_id,
                step_number = step,
                anchor_level = "none",
                action     = "continue",
                reason     = "No anchor needed this step",
            )

        # Kör anchor på rätt nivå
        result = self._run_anchor(
            level              = level,
            current_state      = current_state,
            current_action     = current_action,
            task_goal          = task_goal,
            constitution_text  = constitution_text,
        )

        # Logga och hantera
        event = self._process_result(
            result     = result,
            step       = step,
            task_id    = task_id,
            level      = level,
        )

        self._scheduler.record_anchor(level, step, result)
        self._total_anchors += 1

        return event

    def _run_anchor(
        self,
        level:             str,
        current_state:     str,
        current_action:    str,
        task_goal:         str,
        constitution_text: Optional[str] = None,
    ) -> CoherenceResult:
        """Kör rätt anchor-nivå."""
        common = dict(
            current_state     = current_state,
            current_action    = current_action,
            task_goal         = task_goal,
            entity_id         = self.entity_id,
        )

        if level == "quick":
            return quick_coherence(**common)
        elif level == "medium":
            return medium_coherence(
                **common,
                constitution_text = constitution_text,
            )
        elif level == "deep":
            return deep_coherence(
                **common,
                constitution_text = constitution_text,
            )
        else:
            # Fallback
            return quick_coherence(**common)

    def _process_result(
        self,
        result:  CoherenceResult,
        step:    int,
        task_id: str,
        level:   str,
    ) -> AnchorEvent:
        """Processar anchor-resultat och triggar callbacks."""
        drift_detected = result.action in ("warn", "pause", "abort")

        if drift_detected:
            self._drift_count += 1
            self._log_drift_to_stone(result, step, task_id)

        event = AnchorEvent(
            task_id         = task_id,
            entity_id       = self.entity_id,
            step_number     = step,
            anchor_level    = level,
            coherence_score = result.coherence_score,
            action          = result.action,
            reason          = result.reason,
            drift_detected  = drift_detected,
        )
        self._history.append(event)

        # Logga
        if drift_detected:
            log.warning(f"Identity drift: {event}")
        else:
            log.debug(f"Anchor OK: {event}")

        # Trigga callbacks
        if result.action == "abort" and self._on_abort:
            self._on_abort(event, result)
        elif result.action == "pause" and self._on_pause:
            self._on_pause(event, result)
        elif drift_detected and self._on_drift:
            self._on_drift(event, result)

        return event

    def _log_drift_to_stone(
        self, result: CoherenceResult, step: int, task_id: str
    ) -> None:
        """Loggar identitetsdrift till STONE."""
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[identity_drift] entity={self.entity_id} "
                    f"task={task_id[:8]} step={step} "
                    f"score={result.coherence_score:.3f} "
                    f"action={result.action} "
                    f"L0={result.layer0_alignment:.2f} "
                    f"M={result.mission_alignment:.2f} "
                    f"E={result.entity_alignment:.2f}\n"
                    f"Reason: {result.reason}"
                ),
                source  = f"zero_identity_anchor:{self.entity_id}",
            )
        except Exception as e:
            log.debug(f"drift STONE log: {e}")

    # ── Tvingad anchor ────────────────────────────────────────────────────────

    def force_quick(
        self,
        current_state:  str,
        current_action: str,
        task_goal:      str,
        step:           int = -1,
        task_id:        str = "",
    ) -> AnchorEvent:
        """Tvingad Quick Anchor — används alltid före kritiska operationer."""
        return self.check(
            step           = step,
            current_state  = current_state,
            current_action = current_action,
            task_goal      = task_goal,
            task_id        = task_id,
            force_level    = "quick",
        )

    def force_deep(
        self,
        current_state:     str,
        current_action:    str,
        task_goal:         str,
        step:              int = -1,
        task_id:           str = "",
        constitution_text: Optional[str] = None,
    ) -> AnchorEvent:
        """Tvingad Deep Anchor — vid uppstart och avslut av uppdrag."""
        return self.check(
            step               = step,
            current_state      = current_state,
            current_action     = current_action,
            task_goal          = task_goal,
            task_id            = task_id,
            constitution_text  = constitution_text,
            force_level        = "deep",
        )

    # ── Statistik ─────────────────────────────────────────────────────────────

    @property
    def drift_rate(self) -> float:
        """Andel anchors med drift."""
        if not self._total_anchors:
            return 0.0
        return self._drift_count / self._total_anchors

    @property
    def is_stable(self) -> bool:
        """Är identiteten stabil? (låg drift-rate)"""
        return self.drift_rate < 0.2  # < 20% drift

    def get_recent_history(self, n: int = 10) -> List[AnchorEvent]:
        return self._history[-n:]

    def format_summary(self) -> str:
        lines = [
            f"Identity Anchor Summary ({self.entity_id}):",
            f"  Totalt anchors: {self._total_anchors}",
            f"  Drift-händelser: {self._drift_count}",
            f"  Drift-rate: {self.drift_rate:.1%}",
            f"  Stabil: {'Ja ✓' if self.is_stable else 'Nej ⚠'}",
        ]
        recent = self.get_recent_history(5)
        if recent:
            lines.append(f"\n  Senaste anchors:")
            for e in recent:
                lines.append(f"    {e}")
        return "\n".join(lines)


# ── Resonance Guardrails ──────────────────────────────────────────────────────

class ResonanceGuardrails:
    """
    Automatiska guardrails baserade på anchor-resultat.
    Pausar Gear 4 om identitetsdrift detekteras.
    Notifierar Frank.
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id    = entity_id
        self._paused:     bool = False
        self._pause_reason: str = ""
        self._consecutive_warnings: int = 0

    @property
    def is_paused(self) -> bool:
        return self._paused

    def evaluate(self, event: AnchorEvent) -> bool:
        """
        Utvärderar ett anchor-event.
        Returns True om körningen ska fortsätta, False om den ska pausas.
        """
        if event.action == "continue":
            self._consecutive_warnings = 0
            return True

        if event.action == "warn":
            self._consecutive_warnings += 1
            if self._consecutive_warnings >= 3:
                # Tre varningar i rad → tvingad paus
                self._pause(
                    f"Tre konsekutiva varningar. "
                    f"Senaste score: {event.coherence_score:.3f}"
                )
                return False
            return True

        if event.action == "pause":
            self._pause(event.reason)
            return False

        if event.action == "abort":
            self._pause(f"ABORT: {event.reason}")
            return False

        return True

    def _pause(self, reason: str) -> None:
        """Pausar Gear 4 och notifierar."""
        self._paused       = True
        self._pause_reason = reason
        log.warning(f"Guardrails PAUSED: {reason}")
        self._notify_frank(reason)

    def _notify_frank(self, reason: str) -> None:
        """Notifierar Frank om identitetsdrift via STONE."""
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[guardrails_pause] entity={self.entity_id}\n"
                    f"Gear 4 pausad på grund av identitetsdrift.\n"
                    f"Anledning: {reason}\n"
                    f"Frank behöver godkänna återupptagning."
                ),
                source  = f"zero_guardrails:{self.entity_id}",
                surprise_flag = True,
            )
        except Exception as e:
            log.debug(f"guardrails notify: {e}")

    def resume(self, approved_by: str = "Frank") -> None:
        """Frank godkänner återupptagning."""
        self._paused               = False
        self._pause_reason         = ""
        self._consecutive_warnings = 0
        log.info(f"Guardrails resumed by {approved_by}")

    def format_status(self) -> str:
        if self._paused:
            return f"⚠ PAUSAD: {self._pause_reason}"
        return f"✓ Aktiv (varningar: {self._consecutive_warnings})"


# ── Global instans per entity ─────────────────────────────────────────────────

_anchors:     Dict[str, IdentityAnchor]     = {}
_guardrails:  Dict[str, ResonanceGuardrails] = {}


def get_anchor(entity_id: str = "zero") -> IdentityAnchor:
    if entity_id not in _anchors:
        _anchors[entity_id] = IdentityAnchor(entity_id)
    return _anchors[entity_id]


def get_guardrails(entity_id: str = "zero") -> ResonanceGuardrails:
    if entity_id not in _guardrails:
        _guardrails[entity_id] = ResonanceGuardrails(entity_id)
    return _guardrails[entity_id]


def anchor_check(
    step:           int,
    current_state:  str,
    current_action: str,
    task_goal:      str,
    task_id:        str = "",
    risk_level:     str = "SAFE",
    entity_id:      str = "zero",
) -> tuple[bool, AnchorEvent]:
    """
    Huvud-API för Gear 4.
    Returns (proceed: bool, event: AnchorEvent)
    """
    anchor     = get_anchor(entity_id)
    guardrails = get_guardrails(entity_id)

    if guardrails.is_paused:
        event = AnchorEvent(
            entity_id    = entity_id,
            step_number  = step,
            anchor_level = "none",
            action       = "pause",
            reason       = f"Guardrails aktiva: {guardrails._pause_reason}",
        )
        return False, event

    event   = anchor.check(
        step           = step,
        current_state  = current_state,
        current_action = current_action,
        task_goal      = task_goal,
        task_id        = task_id,
        risk_level     = risk_level,
    )
    proceed = guardrails.evaluate(event)
    return proceed, event


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Identity Anchor")
    parser.add_argument("--test",   action="store_true")
    parser.add_argument("--entity", default="zero")
    args = parser.parse_args()

    if args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Identity Anchor — Test")
        print(f"{'─'*55}\n")

        anchor     = IdentityAnchor("zero")
        guardrails = ResonanceGuardrails("zero")

        # Simulera 35 steg med olika risknivåer
        goal  = "Researcha Firepower-problem och skapa rapport"
        state = "Jag är Zero. Jag existerar här och nu. Jag agerar från Layer 0."

        print("  Simulerar 35 steg (HIGH-risk uppdrag)...")
        print()

        anchors_run = []
        for step in range(35):
            action = f"Steg {step}: analyserar data för {goal[:30]}"
            event  = anchor.check(
                step           = step,
                current_state  = state,
                current_action = action,
                task_goal      = goal,
                risk_level     = "HIGH",
            )

            if event.anchor_level != "none":
                anchors_run.append(event)
                proceed = guardrails.evaluate(event)
                status  = "→ fortsätt" if proceed else "→ PAUS"
                print(f"  Steg {step:2d}: [{event.anchor_level:<7}] "
                      f"score={event.coherence_score:.2f} "
                      f"{event.action:<10} {status}")

        print()
        print(anchor.format_summary())
        print()
        print(f"  Guardrails: {guardrails.format_status()}")

        print(f"\n  Anchor-schema (HIGH-risk, 35 steg):")
        levels = [e.anchor_level for e in anchors_run]
        for level in set(levels):
            count = levels.count(level)
            print(f"    {level}: {count}x")

    else:
        parser.print_help()
