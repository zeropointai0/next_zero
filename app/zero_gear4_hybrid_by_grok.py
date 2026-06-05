#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_gear4.py — ZeroPointAI Gear 4 Conductor v3.1

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: true
ZERO_ROLE:      Orkestrerar autonom exekvering medan identiteten hålls koherent
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_specialization_engine.py,
                zero_coherence_contract.py, zero_identity_anchor.py, zero_risk_policy.py,
                zero_task.py, zero_checkpoint.py
ZERO_USED_BY:   zero_web_server.py, zero_router.py, zero_night.py

Mental Model:
    Gear 4 är dirigenten — inte hela orkestern.
    Den förstår målet, väljer väg, bevakar identitet och skapar tydliga artefakter.
    Den exekverar inte själv utan delegerar till specialiserade moduler.
"""

import argparse
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)
VERSION = "3.1"

# Try to import core components
try:
    from app.foundation import ZERO_ROOT
    from app.zero_coherence_contract import measure_coherence
    from app.zero_identity_anchor import anchor_check
    from app.zero_risk_policy import risk_gate
except ImportError:
    ZERO_ROOT = Path(__file__).resolve().parent.parent


class Route:
    DIRECT = "DIRECT"
    FUNCTION = "FUNCTION"
    TASK = "TASK"
    ENTITY = "ENTITY"


@dataclass
class Gear4Context:
    goal: str
    context: Optional[str] = None
    entity_id: str = "zero"
    run_id: str = field(default_factory=lambda: f"gear4_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}")
    user_id: str = "frank"


@dataclass
class Gear4Decision:
    route: str
    confidence: float
    reason: str
    ask_frank: bool = False
    frank_question: str = ""
    suggested_steps: list[str] = field(default_factory=list)
    entity_draft: Optional[Dict[str, Any]] = None


@dataclass
class Gear4Result:
    run_id: str
    goal: str
    decision: Gear4Decision
    status: str = "ROUTED"
    artifact: Dict[str, Any] = field(default_factory=dict)
    coherence_score: float = 1.0
    checkpoint_id: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return len(self.errors) == 0 and self.status not in ("ABORTED", "BLOCKED")


class Gear4Conductor:
    """Gear 4 — Identitetsbevarande autonom orkestrator."""

    def __init__(self, entity_id: str = "zero"):
        self.entity_id = entity_id

    def run(self, goal: str, context: Optional[str] = None, execute: bool = False) -> Gear4Result:
        """Huvudentrypoint för Gear 4."""
        ctx = Gear4Context(goal=goal.strip(), context=context, entity_id=self.entity_id)
        result = Gear4Result(run_id=ctx.run_id, goal=ctx.goal)

        try:
            # 1. Decompose målet
            decomposition = self._decompose(ctx)

            # 2. Quick Anchor + Coherence (snabb check)
            coherence = self._quick_coherence_check(ctx, decomposition)
            if coherence and coherence.get("action") in ("PAUSE", "ABORT"):
                result.status = "PAUSED" if coherence.get("action") == "PAUSE" else "ABORTED"
                result.warnings.append(coherence.get("reason", "Identity drift detected"))
                return result

            # 3. Specialize → Route decision
            decision = self._specialize_and_decide(decomposition, ctx)
            result.decision = decision

            # 4. Risk Check FÖRE Act
            allowed, risk_msg = self._risk_check(decision, ctx)
            if not allowed:
                decision.ask_frank = True
                decision.frank_question = risk_msg or "Risk policy kräver godkännande."
                result.status = "BLOCKED"
                return result

            # 5. Execute chosen route
            artifact = self._execute_route(decision, ctx, execute=execute)
            result.artifact = artifact

            # 6. Checkpoint important state changes
            if decision.route in (Route.TASK, Route.ENTITY, Route.FUNCTION):
                result.checkpoint_id = self._create_checkpoint(ctx, decision, artifact)

            # 7. Medium Anchor efter handling
            self._medium_anchor_check(ctx, decision, artifact)

            result.status = "COMPLETED" if decision.route == Route.DIRECT else "ROUTED"
            return result

        except Exception as e:
            log.exception("Gear4 critical error")
            result.errors.append(f"{type(e).__name__}: {str(e)}")
            result.status = "FAILED"
            return result

    # ── Internal Steps ─────────────────────────────────────────────────────

    def _decompose(self, ctx: Gear4Context) -> Dict[str, Any]:
        """Förstår och bryter ner målet."""
        try:
            from app.zero_decomposer import decompose
            return decompose(ctx.goal, context=ctx.context, entity_id=ctx.entity_id)
        except Exception as e:
            log.warning(f"Decomposer unavailable: {e}")
            return {
                "core_problem": ctx.goal,
                "domain": "general",
                "complexity": "medium",
                "suggested_steps": ["Understand goal", "Gather context", "Execute"]
            }

    def _quick_coherence_check(self, ctx: Gear4Context, decomposition: Dict) -> Optional[Dict]:
        """Snabb identitets- och koherenskontroll."""
        try:
            return anchor_check(
                step=0,
                current_state=ctx.goal[:200],
                current_action="Gear4 initial routing",
                entity_id=ctx.entity_id,
                mode="quick"
            )
        except Exception:
            return None

    def _specialize_and_decide(self, decomposition: Dict, ctx: Gear4Context) -> Gear4Decision:
        """Väljer bästa väg via Specialization Engine."""
        try:
            from app.zero_specialization_engine import evaluate
            rec = evaluate(decomposition, entity_id=ctx.entity_id)
        except Exception:
            rec = {"path": Route.DIRECT, "confidence": 0.78, "reason": "Fallback recommendation"}

        route = rec.get("path", Route.DIRECT)
        confidence = float(rec.get("confidence", 0.75))

        ask_frank = confidence < 0.85 or route == Route.ENTITY

        entity_draft = None
        if route == Route.ENTITY and confidence >= 0.82:
            entity_draft = {
                "name": rec.get("entity_name", "Specialist"),
                "domain": rec.get("domain") or decomposition.get("domain", "general"),
                "purpose": rec.get("purpose") or ctx.goal,
                "status": "DRAFT",
                "confidence": confidence,
                "created_by": "Gear4"
            }

        return Gear4Decision(
            route=route,
            confidence=confidence,
            reason=rec.get("reason", "No specific reason given"),
            ask_frank=ask_frank,
            frank_question=self._make_frank_question(rec, route),
            suggested_steps=rec.get("suggested_steps", decomposition.get("suggested_steps", [])),
            entity_draft=entity_draft
        )

    def _risk_check(self, decision: Gear4Decision, ctx: Gear4Context) -> tuple[bool, str]:
        """Risk Check FÖRE någon state-ändrande action."""
        try:
            operation = f"Gear4 route {decision.route} for goal: {ctx.goal[:100]}"
            allowed, assessment = risk_gate(
                operation=operation,
                operation_type=decision.route.lower(),
                entity_id=ctx.entity_id
            )
            return allowed, assessment.get("reason", "")
        except Exception:
            # Degraded but continue with caution for non-entity routes
            return decision.route != Route.ENTITY, "Risk check unavailable — proceeding with caution"

    def _execute_route(self, decision: Gear4Decision, ctx: Gear4Context, execute: bool) -> Dict[str, Any]:
        """Delegerar till rätt hanterare."""
        if decision.route == Route.DIRECT:
            return {
                "type": "direct",
                "message": "Målet bedöms lämpligast hanteras direkt via chat/response layer."
            }

        elif decision.route == Route.FUNCTION:
            return {
                "type": "function",
                "brief": {
                    "function_name": decision.suggested_steps[0] if decision.suggested_steps else "helper_function",
                    "purpose": decision.reason,
                    "steps": decision.suggested_steps
                }
            }

        elif decision.route == Route.TASK:
            try:
                from app.zero_task import create_task
                task = create_task(
                    goal=ctx.goal,
                    plan=decision.suggested_steps,
                    entity_id=ctx.entity_id,
                    risk_level="CAUTION"
                )
                return {
                    "type": "task",
                    "task_id": getattr(task, "task_id", "unknown"),
                    "status": "DRAFT"
                }
            except Exception as e:
                return {"type": "task", "error": str(e), "status": "DRAFT"}

        elif decision.route == Route.ENTITY:
            return {
                "type": "entity",
                "draft": decision.entity_draft,
                "status": "DRAFT",
                "wizard_recommended": True
            }

        return {"type": "unknown", "route": decision.route}

    def _create_checkpoint(self, ctx: Gear4Context, decision: Gear4Decision, artifact: Dict) -> Optional[str]:
        """Skapar checkpoint efter state-förändring."""
        try:
            from app.zero_checkpoint import save_checkpoint
            return save_checkpoint(
                task_id=ctx.run_id,
                step_number=0,
                step_description=f"Gear4 routed as {decision.route}",
                goal=ctx.goal,
                observation=json.dumps(artifact, default=str)[:500],
                next_step=decision.route,
                entity_id=ctx.entity_id
            )
        except Exception as e:
            log.warning(f"Checkpoint failed: {e}")
            return None

    def _medium_anchor_check(self, ctx: Gear4Context, decision: Gear4Decision, artifact: Dict):
        """Medium anchor efter exekvering."""
        try:
            anchor_check(
                step=1,
                current_state=f"Completed Gear4 route: {decision.route}",
                current_action="Post-route maintenance",
                entity_id=ctx.entity_id,
                mode="medium"
            )
        except Exception:
            pass  # Graceful degradation

    def _make_frank_question(self, rec: Dict, route: str) -> str:
        if route == Route.ENTITY:
            name = rec.get("entity_name", "Specialist")
            return f"Jag rekommenderar starkt att skapa en **Draft Entity** kallad **{name}**. Vill du starta Entity Wizard för att designa den tillsammans?"
        if route == Route.TASK:
            return "Jag har föreslagit ett strukturerat Task. Vill du granska planen och godkänna innan vi kör?"
        return "Vill du granska beslutet innan jag fortsätter?"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def process_goal(goal: str, context: Optional[str] = None, entity_id: str = "zero", execute: bool = False) -> Gear4Result:
    """Bekväm toppnivå-funktion."""
    conductor = Gear4Conductor(entity_id=entity_id)
    return conductor.run(goal, context=context, execute=execute)


def status() -> str:
    return f"✅ Gear 4 v{VERSION} är aktiv och redo att orkestrera."


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=f"ZeroPointAI Gear 4 Conductor v{VERSION}")
    parser.add_argument("--goal", type=str, help="Målet som ska bearbetas")
    parser.add_argument("--context", type=str, help="Extra kontext")
    parser.add_argument("--entity", default="zero", help="Entity ID")
    parser.add_argument("--execute", action="store_true", help="Tillåt skapande av tasks/entities")
    parser.add_argument("--test", action="store_true", help="Kör smoke tests")
    args = parser.parse_args()

    if args.test:
        test_goals = [
            "Hur optimerar vi Pinball Inn's underhållsrutiner?",
            "Skriv en spec-generator för Zero-moduler",
            "Skapa en långsiktig specialist för flipper-reparationer"
        ]
        for goal in test_goals:
            print("\n" + "="*90)
            result = process_goal(goal, execute=False)
            print(f"Goal: {goal}")
            print(f"Route: {result.decision.route} ({result.decision.confidence:.0%})")
            print(f"Status: {result.status}")
            if result.decision.ask_frank:
                print(f"Frank Question: {result.decision.frank_question}")
        return

    if not args.goal:
        parser.error("--goal är obligatoriskt")

    result = process_goal(args.goal, args.context, entity_id=args.entity, execute=args.execute)

    print(json.dumps({
        "run_id": result.run_id,
        "goal": result.goal,
        "route": result.decision.route,
        "confidence": result.decision.confidence,
        "status": result.status,
        "ask_frank": result.decision.ask_frank,
        "frank_question": result.decision.frank_question,
        "artifact": result.artifact
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
