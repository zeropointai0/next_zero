 """
zero_gear4.py — ZeroPointAI Gear 4 Autonomous Execution Engine

ZERO_MODULE:    autonomy
ZERO_LAYER:     4
ZERO_ESSENTIAL: false
ZERO_ROLE:      Huvudloopen för autonom exekvering med identitetsbevarande
ZERO_DEPENDS:   zero_task, zero_risk_policy, zero_checkpoint,
                zero_coherence_contract, zero_identity_anchor,
                zero_perspective, drm_memory
ZERO_USED_BY:   minna_entity.py, zero_night.py

Filosofi:
    Gear 4 är inte "AI som kör uppgifter".
    Gear 4 är Zero/Minna som agerar koherent med sig själv över tid.

    Loopen:
    Plan → Quick Anchor → Risk Check → Act → Observe →
    Checkpoint → Medium/Deep Anchor → Continue/Pause/Abort

    COMPASS implementerat:
    DETECT → Plan
    EXPRESS → Risk Check + Act
    ALLOW → Observe
    MAINTAIN → Checkpoint + Anchor
    CALIBRATE → Continue / Pause / Abort
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    from pathlib import Path
    ZERO_ROOT = Path("/opt/zeropointai")

load_dotenv(ZERO_ROOT / ".env")

# ── Importer ──────────────────────────────────────────────────────────────────

from app.zero_task import get_task_manager, Task
from app.zero_risk_policy import risk_gate, get_approval_manager
from app.zero_checkpoint import save_checkpoint, rollback_task
from app.zero_coherence_contract import (
    quick_coherence,
    medium_coherence,
    deep_coherence,
    CoherenceResult,
)
from app.zero_identity_anchor import get_anchor, get_guardrails
from app.zero_perspective import get_perspective_manager, frank_observes


# ── Gear 4 Result ─────────────────────────────────────────────────────────────

@dataclass
class Gear4Result:
    success:        bool
    task_id:        str
    final_status:   str
    result_summary: str
    coherence_score: float = 1.0
    aborted:        bool = False
    paused:         bool = False
    reason:         str = ""


# ── Gear 4 Engine ─────────────────────────────────────────────────────────────

class Gear4Engine:
    """
    Huvudklassen för autonom exekvering.
    En instans per entity (zero, minna, etc.).
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id       = entity_id
        self.task_manager    = get_task_manager(entity_id)
        self.anchor          = get_anchor(entity_id)
        self.guardrails      = get_guardrails(entity_id)
        self.perspective_mgr = get_perspective_manager(entity_id)
        self.approval_mgr    = get_approval_manager()

        # Callbacks
        self.on_pause:  Optional[Callable] = None
        self.on_abort:  Optional[Callable] = None
        self.on_step_complete: Optional[Callable] = None

    def run_task(
        self,
        task_id: str,
        max_steps: Optional[int] = None,
    ) -> Gear4Result:
        """
        Kör ett befintligt task autonomt.
        Returnerar Gear4Result.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            return Gear4Result(
                success=False,
                task_id=task_id,
                final_status="not_found",
                result_summary="Task hittades inte",
            )

        if task.status != "approved":
            self.task_manager.start(task_id)

        log.info(f"Gear 4 startar task {task_id[:8]}: {task.goal[:60]}")

        step_count = 0
        while task.current_step < len(task.plan):
            if max_steps and step_count >= max_steps:
                break

            current_step = task.current_step_obj
            if not current_step:
                break

            # ── 1. Plan (nuvarande steg) ─────────────────────────────────
            step_desc = current_step.description
            log.info(f"Steg {task.current_step}: {step_desc}")

            # ── 2. Quick Anchor ──────────────────────────────────────────
            state = f"Jag är {self.entity_id.capitalize()}. Uppdrag: {task.goal}"
            action = f"Utför: {step_desc}"

            event = self.anchor.check(
                step=task.current_step,
                current_state=state,
                current_action=action,
                task_goal=task.goal,
                task_id=task_id,
                risk_level=task.risk_level,
            )

            if not self.guardrails.evaluate(event):
                return Gear4Result(
                    success=False,
                    task_id=task_id,
                    final_status="paused",
                    result_summary="Pausad av guardrails",
                    coherence_score=event.coherence_score,
                    paused=True,
                    reason=event.reason,
                )

            # ── 3. Risk Check FÖRE Act ───────────────────────────────────
            operation = f"Steg {task.current_step}: {step_desc}"
            proceed, risk = risk_gate(
                operation=operation,
                operation_type="research",  # ändras per steg i framtiden
                operation_id=f"{task_id}_{task.current_step}",
                entity_id=self.entity_id,
            )

            if not proceed:
                if risk.forbidden:
                    self.task_manager.abort(task_id, "Forbidden operation")
                    return Gear4Result(
                        success=False,
                        task_id=task_id,
                        final_status="aborted",
                        result_summary="Forbidden operation",
                        aborted=True,
                    )
                # Väntar på godkännande
                self.task_manager.block(task_id, "Väntar på godkännande")
                return Gear4Result(
                    success=False,
                    task_id=task_id,
                    final_status="blocked",
                    result_summary="Väntar på Frank-godkännande",
                    paused=True,
                )

            # ── 4. Act (här körs den faktiska operationen) ───────────────
            # TODO: Ersätt med riktig steg-exekvering (web search, fil-läsning, etc.)
            observation = f"[SIMULERING] Utförde steg: {step_desc}"

            # ── 5. Observe + Perspective ─────────────────────────────────
            self.perspective_mgr.add(
                domain="pinball",
                subject="research",
                claim=observation,
                source_type="zero_inference",
            )

            # ── 6. Checkpoint ────────────────────────────────────────────
            checkpoint = save_checkpoint(
                task_id=task_id,
                step_number=task.current_step,
                step_description=step_desc,
                goal=task.goal,
                remaining_plan=[s.description for s in task.plan[task.current_step+1:]],
                observation=observation,
                next_step="Nästa steg" if task.current_step + 1 < len(task.plan) else "Slut",
                coherence_score=event.coherence_score,
                layer0_alignment=0.92,
                mission_alignment=0.88,
                entity_alignment=0.90,
                entity_id=self.entity_id,
            )

            # ── 7. Advance step ──────────────────────────────────────────
            self.task_manager.advance_step(
                task_id=task_id,
                observation=observation,
                next_step_desc="Fortsätt enligt plan",
                coherence_score=event.coherence_score,
                layer0_alignment=0.92,
                mission_alignment=0.88,
                entity_alignment=0.90,
            )

            step_count += 1
            time.sleep(0.1)  # Simulering — tas bort i produktion

        # ── Uppdrag klart ─────────────────────────────────────────────────
        self.task_manager.complete(task_id, result="Uppdrag slutfört")
        log.info(f"Gear 4 avslutade task {task_id[:8]} framgångsrikt")

        return Gear4Result(
            success=True,
            task_id=task_id,
            final_status="complete",
            result_summary="Uppdrag slutfört",
            coherence_score=0.89,
        )


# ── Global instanser ──────────────────────────────────────────────────────────

_engines: Dict[str, Gear4Engine] = {}


def get_gear4_engine(entity_id: str = "zero") -> Gear4Engine:
    if entity_id not in _engines:
        _engines[entity_id] = Gear4Engine(entity_id)
    return _engines[entity_id]


# ── Publikt API ───────────────────────────────────────────────────────────────

def run_gear4_task(task_id: str, entity_id: str = "zero") -> Gear4Result:
    """Publikt API — används av Minna, Zero Night etc."""
    engine = get_gear4_engine(entity_id)
    return engine.run_task(task_id)


# ── CLI för test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="ZeroPointAI Gear 4")
    parser.add_argument("--task", metavar="TASK_ID", help="Kör ett specifikt task")
    parser.add_argument("--entity", default="minna", help="Entity att köra som")
    parser.add_argument("--test", action="store_true", help="Skapa och kör test-uppdrag")
    args = parser.parse_args()

    if args.test:
        from app.zero_task import create_task
        print("Skapar test-uppdrag för Gear 4...")

        task = create_task(
            goal="Undersök vanliga fel på Firepower vänster flipper",
            plan=[
                "Sök i STONE efter tidigare kunskap",
                "Sök på Pinside och IPDB",
                "Sammanfatta mest troliga orsaker",
                "Skapa rekommendation för Frank",
            ],
            entity_id=args.entity,
            risk_level="SAFE",
        )

        print(f"Task skapad: {task.task_id[:8]}")
        # Godkänn och kör
        from app.zero_task import approve_task
        approve_task(task.task_id, by="Frank")

        result = run_gear4_task(task.task_id, args.entity)
        print(f"\nGear 4-resultat: {result.final_status}")
        print(f"Sammanfattning: {result.result_summary}")

    elif args.task:
        result = run_gear4_task(args.task, args.entity)
        print(result)
    else:
        parser.print_help()
