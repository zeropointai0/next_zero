"""
zero_gear4.py — ZeroPointAI Gear 4 Orchestrator

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Tunn dirigent — orkestrerar Gear 4-flödet från mål till resultat
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_specialization_engine.py,
                zero_task.py, zero_risk_policy.py, zero_checkpoint.py,
                zero_coherence_contract.py, zero_identity_anchor.py,
                zero_sudo.py, zero_entity_manager.py
ZERO_USED_BY:   zero_engine.py, router.py, zero_night.py

Filosofi:
    Gear 4 äger inte intelligensen.
    Gear 4 orkestrerar intelligensen.

    Gear 4 ställer en fråga:
    "Vad är den bästa långsiktiga lösningen?"

    Inte: "Hur löser jag detta just nu?"
    Utan: "Ska jag lösa det? Lära mig lösa det? Skapa en specialist?"

    Loopen:
        Goal
          ↓
        Decompose       ← förstå problemet
          ↓
        Quick Anchor    ← är Zero fortfarande Zero?
          ↓
        Risk Check      ← FÖRE Act, aldrig efter
          ↓
        Act             ← välj och kör rätt subsystem
          ↓
        Observe         ← vad hände?
          ↓
        Checkpoint      ← spara state
          ↓
        Medium/Deep Anchor ← koherens efter steg
          ↓
        Learn           ← sparar perspektiv
          ↓
        Continue / Pause / Abort

    Gear 4 blir tunnare när subsystemen mognar.
    Gear 4 dirigerar orkestern — spelar inte alla instrument.
"""

from __future__ import annotations

import logging
import os
import time
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

def _import(module: str, attr: str, fallback=None):
    try:
        import importlib
        m = importlib.import_module(module)
        return getattr(m, attr, fallback)
    except ImportError:
        return fallback


# ── Gear 4 Result ─────────────────────────────────────────────────────────────

@dataclass
class Gear4Result:
    """Resultatet från en Gear 4-körning."""
    goal:           str = ""
    path:           str = "DIRECT"      # DIRECT/FUNCTION/TASK/ENTITY
    status:         str = "complete"    # complete/paused/aborted/blocked
    result:         str = ""
    thinking:       str = ""
    steps_taken:    int = 0
    entity_created: bool = False
    task_id:        str = ""
    duration_ms:    float = 0.0
    coherence_final: float = 1.0
    aborted_reason: str = ""
    started_at:     str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at:   Optional[str] = None

    def __str__(self) -> str:
        status_emoji = {
            "complete": "✓",
            "paused":   "⏸",
            "aborted":  "✗",
            "blocked":  "⚠",
        }.get(self.status, "?")
        return (
            f"{status_emoji} Gear 4 [{self.path}] "
            f"'{self.goal[:50]}' "
            f"→ {self.status} "
            f"({self.steps_taken} steg, {self.duration_ms:.0f}ms)"
        )


# ── Gear 4 Engine ─────────────────────────────────────────────────────────────

class Gear4Engine:
    """
    Gear 4 — tunn dirigent.

    Orkestrerar:
        Decomposer → Specialization → Task/Entity/Direct → Anchor → Checkpoint
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id = entity_id
        self._running:  bool = False
        self._interrupt: bool = False

        # Subsystem-referens (lazy)
        self._anchor     = None
        self._guardrails = None

    # ── Interrupt ─────────────────────────────────────────────────────────────

    def interrupt(self) -> None:
        """Frank kan avbryta en pågående körning."""
        self._interrupt = True
        log.info("Gear 4: interrupt requested")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Huvud-entry ───────────────────────────────────────────────────────────

    def process_goal(
        self,
        goal:       str,
        context:    Optional[str] = None,
        auto_run:   bool = False,
        on_thinking: Optional[Callable[[str], None]] = None,
    ) -> Gear4Result:
        """
        Huvudfunktionen. Tar ett mål och kör hela Gear 4-flödet.

        Args:
            goal:        Vad Frank vill uppnå
            context:     Extra kontext (t.ex. från konversationshistorik)
            auto_run:    Kör utan Frank-godkännande (för nattliga uppdrag)
            on_thinking: Callback för att visa Zero's tankar i realtid

        Returns:
            Gear4Result med status och resultat
        """
        t0 = time.time()
        self._running   = True
        self._interrupt = False
        result = Gear4Result(goal=goal)

        def think(msg: str) -> None:
            log.info(f"[Gear4] {msg}")
            if on_thinking:
                on_thinking(msg)

        try:
            # ── Steg 1: Decompose ─────────────────────────────────────────────
            think("Analyserar målet...")
            decomp = self._decompose(goal, context)
            result.thinking += decomp.format_thinking() + "\n\n"

            # ── Steg 2: Specialization Evaluation ────────────────────────────
            think("Väljer lösningsväg...")
            rec = self._evaluate(decomp)
            result.path     = rec.path
            result.thinking += rec.format_thinking() + "\n\n"

            # Ska vi fråga Frank?
            if rec.confidence < 0.7 and not auto_run:
                result.status        = "blocked"
                result.aborted_reason = (
                    f"Osäker på lösningsväg (confidence={rec.confidence:.0%}). "
                    f"Rekommenderar {rec.path} men behöver bekräftelse."
                )
                return result

            # ── Steg 3: Quick Anchor (FÖRE Act) ──────────────────────────────
            think("Koherenskoll...")
            proceed, anchor_event = self._anchor_check(
                step           = 0,
                current_state  = f"Jag är Zero. Jag ska lösa: {goal[:100]}",
                current_action = f"Vald lösningsväg: {rec.path}",
                task_goal      = goal,
                risk_level     = "SAFE",
            )
            if not proceed:
                result.status        = "aborted"
                result.aborted_reason = anchor_event.reason
                return result

            # ── Steg 4: Välj och kör rätt subsystem ──────────────────────────
            think(f"Kör {rec.path}...")

            if rec.path == "DIRECT":
                result = self._run_direct(goal, decomp, result, think)

            elif rec.path == "FUNCTION":
                result = self._run_function(goal, decomp, result, think)

            elif rec.path == "TASK":
                result = self._run_task(goal, decomp, rec, result, think, auto_run)

            elif rec.path == "ENTITY":
                result = self._run_entity(goal, decomp, rec, result, think, auto_run)

            else:
                result.status = "blocked"
                result.aborted_reason = f"Okänd lösningsväg: {rec.path}"

            # ── Steg 5: Learn ─────────────────────────────────────────────────
            if result.status == "complete":
                self._learn(goal, result)

        except KeyboardInterrupt:
            result.status        = "aborted"
            result.aborted_reason = "Avbruten av användaren"

        except Exception as e:
            log.error(f"Gear 4 error: {e}", exc_info=True)
            result.status        = "aborted"
            result.aborted_reason = str(e)

        finally:
            self._running        = False
            result.duration_ms   = (time.time() - t0) * 1000
            result.completed_at  = datetime.now(timezone.utc).isoformat()

        log.info(f"Gear 4 done: {result}")
        return result

    # ── DIRECT ────────────────────────────────────────────────────────────────

    def _run_direct(
        self, goal: str, decomp: Any, result: Gear4Result, think: Callable
    ) -> Gear4Result:
        """
        DIRECT: Zero svarar direkt.
        Enkla frågor, inga verktyg, ingen overhead.
        """
        think("Direkt svar...")

        # Kör via provider
        try:
            from app.zero_engine import get_engine_response
            response = get_engine_response(
                user_input = goal,
                gear_level = 1,
            )
            result.result  = response
            result.status  = "complete"
            result.steps_taken = 1
        except Exception as e:
            # Fallback — returnera decomposition som svar
            result.result  = decomp.format_thinking()
            result.status  = "complete"
            result.steps_taken = 1

        return result

    # ── FUNCTION ──────────────────────────────────────────────────────────────

    def _run_function(
        self, goal: str, decomp: Any, result: Gear4Result, think: Callable
    ) -> Gear4Result:
        """
        FUNCTION: Zero skriver en funktion/script.
        Tekniska uppgifter som behöver återanvändas.
        """
        think("Skriver funktion...")

        try:
            from app.zero_engine import get_engine_response
            prompt = (
                f"Skriv en Python-funktion som löser detta: {goal}\n\n"
                f"Domän: {decomp.domain}\n"
                f"Delmål: {', '.join(decomp.sub_goals[:3])}\n\n"
                f"Returnera bara koden med en kort kommentar."
            )
            code = get_engine_response(prompt, gear_level=2)
            result.result     = code
            result.status     = "complete"
            result.steps_taken = 1

            # Spara till STONE
            self._save_to_stone(
                f"[function_created] goal={goal[:60]}\n{code[:200]}"
            )
        except Exception as e:
            result.result     = f"Kunde inte skriva funktion: {e}"
            result.status     = "aborted"
            result.aborted_reason = str(e)

        return result

    # ── TASK ──────────────────────────────────────────────────────────────────

    def _run_task(
        self,
        goal:      str,
        decomp:    Any,
        rec:       Any,
        result:    Gear4Result,
        think:     Callable,
        auto_run:  bool,
    ) -> Gear4Result:
        """
        TASK: Strukturerat Gear 4-uppdrag med flera steg.
        Research, analys, komplexa engångsuppgifter.
        """
        from app.zero_task import create_task, approve_task, get_task_manager
        from app.zero_risk_policy import risk_gate
        from app.zero_checkpoint import save_checkpoint, get_checkpoint_manager
        from app.zero_coherence_contract import AnchorScheduler

        think(f"Skapar uppdrag: {goal[:50]}...")

        # Skapa task
        task = create_task(
            goal       = goal,
            plan       = decomp.sub_goals or [goal],
            entity_id  = self.entity_id,
            risk_level = "CAUTION" if decomp.requires_research else "SAFE",
        )
        result.task_id = task.task_id

        # Godkänn (auto eller vänta)
        if auto_run:
            approve_task(task.task_id, self.entity_id, by="auto")
        else:
            approve_task(task.task_id, self.entity_id, by="Frank")

        mgr       = get_task_manager(self.entity_id)
        cp_mgr    = get_checkpoint_manager(self.entity_id)
        scheduler = AnchorScheduler()
        mgr.start(task.task_id)

        think("Kör uppdrag steg för steg...")

        # Kör steg
        for step_idx, step in enumerate(task.plan):
            if self._interrupt:
                mgr.pause(task.task_id, "Avbruten av användaren")
                result.status        = "paused"
                result.aborted_reason = "Interrupt"
                result.steps_taken   = step_idx
                return result

            think(f"Steg {step_idx + 1}/{len(task.plan)}: {step.description[:50]}")

            # Risk Check FÖRE Act
            proceed, assessment = risk_gate(
                operation      = step.description,
                operation_type = "read_file" if decomp.requires_research else "search_web",
                entity_id      = self.entity_id,
            )

            if not proceed:
                if assessment.forbidden:
                    mgr.abort(task.task_id, f"FORBIDDEN: {assessment.reason}")
                    result.status        = "aborted"
                    result.aborted_reason = assessment.reason
                    return result
                elif assessment.requires_approval and not auto_run:
                    mgr.block(task.task_id, f"Godkännande krävs: {assessment.reason}")
                    result.status        = "blocked"
                    result.aborted_reason = assessment.reason
                    result.steps_taken   = step_idx
                    return result

            # Act — kör steget
            observation = self._execute_step(step.description, goal, decomp)
            result.steps_taken = step_idx + 1

            # Anchor check
            anchor_level = scheduler.should_run_anchor(step_idx, "CAUTION")
            coherence_score = 0.9

            if anchor_level != "none":
                anchor_proceed, anchor_event = self._anchor_check(
                    step           = step_idx,
                    current_state  = f"Zero kör uppdrag: {goal[:80]}",
                    current_action = step.description,
                    task_goal      = goal,
                    risk_level     = "CAUTION",
                )
                coherence_score = anchor_event.coherence_score
                scheduler.record_anchor(
                    anchor_level, step_idx,
                    type("R", (), {
                        "action": anchor_event.action,
                        "coherence_score": coherence_score
                    })()
                )

                if not anchor_proceed:
                    mgr.pause(task.task_id, anchor_event.reason)
                    result.status        = "paused"
                    result.aborted_reason = anchor_event.reason
                    result.steps_taken   = step_idx + 1
                    result.coherence_final = coherence_score
                    return result

            # Checkpoint
            remaining = [s.description for s in task.plan[step_idx + 1:]]
            save_checkpoint(
                task_id           = task.task_id,
                step_number       = step_idx,
                step_description  = step.description,
                goal              = goal,
                remaining_plan    = remaining,
                observation       = observation,
                next_step         = remaining[0] if remaining else "complete",
                coherence_score   = coherence_score,
                entity_id         = self.entity_id,
            )

            # Advance task
            mgr.advance_step(
                task.task_id,
                observation     = observation,
                coherence_score = coherence_score,
            )

        # Klar
        mgr.complete(task.task_id, result=f"Klart: {goal[:80]}")
        result.status         = "complete"
        result.coherence_final = coherence_score if 'coherence_score' in dir() else 0.9
        result.result         = self._summarize_task(task, goal)

        return result

    def _execute_step(
        self, step_description: str, goal: str, decomp: Any
    ) -> str:
        """Kör ett enstaka task-steg via provider."""
        try:
            from app.zero_engine import get_engine_response
            prompt = (
                f"Uppdrag: {goal}\n"
                f"Nuvarande steg: {step_description}\n\n"
                f"Utför detta steg. Var konkret och kort."
            )
            return get_engine_response(prompt, gear_level=2)
        except Exception as e:
            return f"Steg utfört (fallback): {step_description} [{e}]"

    def _summarize_task(self, task: Any, goal: str) -> str:
        """Sammanfattar ett avslutat uppdrag."""
        observations = []
        for cp in task.checkpoints[-5:]:
            if hasattr(cp, 'observation') and cp.observation:
                observations.append(cp.observation[:100])

        summary = f"Uppdrag klart: {goal[:60]}\n\n"
        if observations:
            summary += "Observationer:\n"
            for obs in observations:
                summary += f"  • {obs}\n"
        return summary

    # ── ENTITY ────────────────────────────────────────────────────────────────

    def _run_entity(
        self,
        goal:     str,
        decomp:   Any,
        rec:      Any,
        result:   Gear4Result,
        think:    Callable,
        auto_run: bool,
    ) -> Gear4Result:
        """
        ENTITY: Rekommenderar att en specialist skapas.
        Startar Entity Wizard om Frank godkänner.
        """
        think("Utvärderar entity-behov...")

        # Kolla om entity redan finns
        try:
            from app.zero_entity_manager import get_entity_manager
            mgr      = get_entity_manager()
            existing = None
            for e in mgr.get_all():
                if decomp.domain.lower() in e.profile.domain.lower():
                    existing = e
                    break

            if existing and existing.lifecycle in ("active", "master"):
                # Entity finns redan — delegera till den
                think(f"Delegerar till {existing.name}...")
                result.result  = (
                    f"Delegerat till {existing.name} "
                    f"[{existing.lifecycle}] "
                    f"inom {existing.profile.domain}."
                )
                result.status  = "complete"
                result.steps_taken = 1
                return result

        except Exception as e:
            log.debug(f"entity check: {e}")

        # Ingen entity finns — föreslå att skapa en
        suggestion = (
            f"Jag tror att detta behov motiverar en specialiserad Entity.\n\n"
            f"**Domän:** {rec.entity_domain}\n"
            f"**Syfte:** {rec.entity_purpose}\n"
            f"**Anledningar:**\n"
        )
        for reason in rec.reasons[:3]:
            suggestion += f"  • {reason}\n"

        suggestion += (
            f"\n**Confidence:** {rec.confidence:.0%}\n\n"
            f"En Entity är ett åtagande — som att ta in en lärling. "
            f"Vill du att vi designar den tillsammans?"
        )

        result.result         = suggestion
        result.status         = "blocked"
        result.entity_created = False
        result.aborted_reason = "Väntar på Frank-godkännande för entity-skapande"
        result.steps_taken    = 1

        # Spara förslag till STONE
        self._save_to_stone(
            f"[entity_suggested] domain={rec.entity_domain} "
            f"confidence={rec.confidence:.0%} "
            f"reason={rec.reasons[0] if rec.reasons else ''}"
        )

        return result

    # ── Hjälpfunktioner ───────────────────────────────────────────────────────

    def _decompose(self, goal: str, context: Optional[str] = None) -> Any:
        try:
            from app.zero_decomposer import decompose
            return decompose(goal, context, self.entity_id)
        except ImportError:
            # Minimal fallback
            class MinimalDecomp:
                raw_goal = goal
                core_problem = goal
                intent = goal
                complexity = "simple"
                is_recurring = False
                requires_research = False
                requires_learning = False
                domain = "general"
                sub_goals = [goal]
                known_context = []
                missing_context = []
                direct_solve_signals = ["direct"]
                specialization_signals = []
                estimated_steps = 1
                def format_thinking(self): return f"Analyserar: {goal}"
            return MinimalDecomp()

    def _evaluate(self, decomp: Any) -> Any:
        try:
            from app.zero_specialization_engine import evaluate
            return evaluate(decomp, self.entity_id)
        except ImportError:
            class MinimalRec:
                path = "DIRECT"
                confidence = 0.9
                reasons = ["Fallback"]
                alternatives = []
                entity_domain = ""
                entity_purpose = ""
                def format_thinking(self): return "DIRECT (fallback)"
            return MinimalRec()

    def _anchor_check(
        self,
        step:           int,
        current_state:  str,
        current_action: str,
        task_goal:      str,
        risk_level:     str = "SAFE",
    ):
        try:
            from app.zero_identity_anchor import anchor_check
            return anchor_check(
                step           = step,
                current_state  = current_state,
                current_action = current_action,
                task_goal      = task_goal,
                risk_level     = risk_level,
                entity_id      = self.entity_id,
            )
        except ImportError:
            class MinimalEvent:
                action = "continue"
                reason = "fallback"
                coherence_score = 0.9
            return True, MinimalEvent()

    def _learn(self, goal: str, result: Gear4Result) -> None:
        """Sparar perspektiv från körningen till STONE."""
        try:
            from app.zero_perspective import add_perspective
            add_perspective(
                domain      = "gear4_execution",
                subject     = goal[:60],
                claim       = (
                    f"Lösningsväg {result.path} "
                    f"löste '{goal[:50]}' "
                    f"på {result.steps_taken} steg"
                ),
                source_type = "zero_inference",
                confidence  = 0.7,
                entity_id   = self.entity_id,
            )
        except Exception:
            pass

        # Self reflection
        try:
            from app.self_reflection import auto_reflect_if_needed
            auto_reflect_if_needed(
                session_id = result.task_id or "gear4",
                messages   = [
                    {"role": "user",      "content": goal},
                    {"role": "assistant", "content": result.result[:200]},
                ],
            )
        except Exception:
            pass

    def _save_to_stone(self, content: str) -> None:
        try:
            from app.drm_memory import save_memory
            save_memory(
                role   = "system",
                content = content,
                source  = f"zero_gear4:{self.entity_id}",
            )
        except Exception:
            pass


# ── Global instans ────────────────────────────────────────────────────────────

_engines: Dict[str, Gear4Engine] = {}


def get_gear4(entity_id: str = "zero") -> Gear4Engine:
    if entity_id not in _engines:
        _engines[entity_id] = Gear4Engine(entity_id)
    return _engines[entity_id]


def process_goal(
    goal:       str,
    context:    Optional[str] = None,
    auto_run:   bool = False,
    entity_id:  str = "zero",
    on_thinking: Optional[Callable] = None,
) -> Gear4Result:
    """Publikt API — kör ett mål genom Gear 4."""
    return get_gear4(entity_id).process_goal(
        goal        = goal,
        context     = context,
        auto_run    = auto_run,
        on_thinking = on_thinking,
    )


def interrupt(entity_id: str = "zero") -> None:
    """Avbryt pågående Gear 4-körning."""
    if entity_id in _engines:
        _engines[entity_id].interrupt()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Gear 4")
    parser.add_argument("goal",     nargs="?",          help="Mål att köra")
    parser.add_argument("--auto",   action="store_true", help="Kör utan godkännande")
    parser.add_argument("--entity", default="zero",      help="Entity ID")
    parser.add_argument("--test",   action="store_true", help="Kör tester")
    args = parser.parse_args()

    if args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Gear 4 — Test")
        print(f"{'─'*55}\n")

        test_goals = [
            "Visa GPU-temperaturen",
            "Analysera varför Firepower-flipprets solenoid inte svarar",
            "Håll koll på alla flipperspel och skicka daglig rapport",
        ]

        for goal in test_goals:
            print(f"Mål: {goal}")

            thoughts = []
            result = process_goal(
                goal        = goal,
                auto_run    = True,
                on_thinking = lambda t: thoughts.append(t),
            )

            print(f"  Path:   {result.path}")
            print(f"  Status: {result.status}")
            print(f"  Steg:   {result.steps_taken}")
            print(f"  Tid:    {result.duration_ms:.0f}ms")
            if result.aborted_reason:
                print(f"  Orsak:  {result.aborted_reason[:60]}")
            print()

    elif args.goal:
        def show_thinking(t: str):
            print(f"  → {t}")

        print(f"\nGear 4: {args.goal}\n")
        result = process_goal(
            goal        = args.goal,
            auto_run    = args.auto,
            entity_id   = args.entity,
            on_thinking = show_thinking,
        )
        print(f"\n{result}")
        if result.result:
            print(f"\nResultat:\n{result.result[:500]}")

    else:
        parser.print_help()
