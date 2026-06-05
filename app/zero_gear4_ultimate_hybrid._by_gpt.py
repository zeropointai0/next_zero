#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_gear4.py — ZeroPointAI Gear 4 Ultimate Hybrid v3.2

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: true
ZERO_ROLE:      Identitetsbevarande orkestrator: Goal → Decompose → Specialize → Guard → Route → Checkpoint
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_specialization_engine.py, zero_coherence_contract.py, zero_identity_anchor.py, zero_risk_policy.py, zero_task.py, zero_checkpoint.py, zero_entity_wizard.py
ZERO_USED_BY:   zero_web_server.py, zero_router.py, zero_night.py

Mental Model:
    Gear 4 är dirigenten.

    Den spelar inte alla instrument.
    Den äger inte all intelligens.
    Den är inte en task-runner.

    Gear 4 äger ordningen:
        1. förstå målet
        2. välj bästa långsiktiga väg
        3. kontrollera koherens/risk/identitet
        4. skapa rätt artefakt
        5. checkpointa state
        6. fråga Frank när autonomi inte är förtjänad

Non-Negotiables:
    - ENTITY betyder Draft Entity / Entity Wizard, aldrig ACTIVE agent direkt.
    - Risk check sker före state-changing route.
    - Coherence är min(), inte genomsnitt.
    - Layer 0 är hård grind.
    - Task är state machine, inte agent.
    - Gear 4 ska bli tunnare när subsystemen mognar.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

VERSION = "3.2"
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Root / imports
# ─────────────────────────────────────────────────────────────────────────────

def detect_zero_root() -> Path:
    env_root = os.getenv("ZERO_ROOT", "").strip()
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if (p / "app").exists():
            return p

    this_file = Path(__file__).resolve()
    if this_file.parent.name == "app":
        root = this_file.parent.parent
        if (root / "app").exists():
            return root

    for parent in [this_file.parent] + list(this_file.parents):
        if (parent / "app").exists() and ((parent / "docs").exists() or (parent / ".git").exists()):
            return parent

    cwd = Path.cwd().resolve()
    if (cwd / "app").exists():
        return cwd

    return Path("/opt/zeropointai").resolve()


try:
    from app.foundation import ZERO_ROOT as FOUNDATION_ZERO_ROOT
    ZERO_ROOT = Path(FOUNDATION_ZERO_ROOT)
except Exception:
    ZERO_ROOT = detect_zero_root()

if str(ZERO_ROOT) not in sys.path:
    sys.path.insert(0, str(ZERO_ROOT))

GEAR4_DIR = ZERO_ROOT / "data" / "gear4"
GEAR4_DIR.mkdir(parents=True, exist_ok=True)


def zimport(module_name: str):
    """Import app.<module> when installed, fallback to local module when run directly."""
    try:
        return __import__(f"app.{module_name}", fromlist=["*"])
    except Exception:
        return __import__(module_name, fromlist=["*"])


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DIRECT = "DIRECT"
FUNCTION = "FUNCTION"
TASK = "TASK"
ENTITY = "ENTITY"
VALID_ROUTES = {DIRECT, FUNCTION, TASK, ENTITY}

CONTINUE = "continue"
WARN = "warn"
PAUSE = "pause"
ABORT = "abort"

CONFIDENCE_AUTO = 0.90
CONFIDENCE_ASK = 0.65

STATUS_READY = "READY"
STATUS_DRAFT = "DRAFT"
STATUS_BLOCKED = "BLOCKED"
STATUS_FAILED = "FAILED"
STATUS_COMPLETE = "COMPLETE"


# ─────────────────────────────────────────────────────────────────────────────
# Data contracts
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Gear4Config:
    entity_id: str = "zero"

    # Gear 4 defaults to routing/drafting, not doing side-effectful execution.
    dry_run: bool = False
    allow_state_creation: bool = False

    # Entity and function autonomy must be earned.
    always_ask_for_entity: bool = True
    always_ask_for_function_code: bool = True

    # Guardrails.
    use_coherence_guard: bool = True
    use_identity_anchor: bool = True
    use_risk_policy: bool = True
    checkpoint_state_routes: bool = True

    # DIRECT should normally be handed back to engine/chat layer.
    execute_direct: bool = False


@dataclass
class Gear4Decision:
    route: str = DIRECT
    confidence: float = 0.75
    reason: str = ""
    next_action: str = "answer_directly"
    ask_frank: bool = True

    reasons: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    suggested_steps: List[str] = field(default_factory=list)

    entity_name: str = ""
    entity_domain: str = ""
    entity_purpose: str = ""

    function_name: str = ""
    function_purpose: str = ""

    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardResult:
    allowed: bool = True
    action: str = CONTINUE
    risk_level: str = "SAFE"

    coherence_score: float = 1.0
    layer0_alignment: float = 1.0
    mission_alignment: float = 1.0
    entity_alignment: float = 1.0

    reason: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class Gear4Artifact:
    kind: str
    title: str
    status: str = STATUS_READY
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Gear4Result:
    run_id: str = field(default_factory=lambda: "gear4_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    version: str = VERSION
    entity_id: str = "zero"
    goal: str = ""
    status: str = STATUS_READY
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    decomposition: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    guard: Dict[str, Any] = field(default_factory=dict)
    artifact: Optional[Gear4Artifact] = None
    checkpoint_id: str = ""

    ask_frank: bool = False
    frank_question: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        return self.status not in {STATUS_FAILED, STATUS_BLOCKED}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["ok"] = self.ok()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    def format_for_frank(self) -> str:
        route = self.decision.get("route", "?")
        confidence = safe_float(self.decision.get("confidence", 0.0), 0.0)
        lines = [
            f"## Gear 4 v{self.version}",
            "",
            f"**Goal:** {self.goal}",
            f"**Route:** {route} ({confidence:.0%})",
            f"**Status:** {self.status}",
        ]

        if self.decision.get("reason"):
            lines += ["", f"**Reason:** {self.decision['reason']}"]

        if self.artifact:
            lines += ["", f"### {self.artifact.title}", self.artifact.message]

        reasons = self.decision.get("reasons") or []
        if reasons:
            lines += ["", "### Varför", *[f"- {r}" for r in reasons[:5]]]

        if self.frank_question:
            lines += ["", "### Fråga till Frank", self.frank_question]

        if self.warnings:
            lines += ["", "### Varningar", *[f"- {w}" for w in self.warnings]]

        if self.errors:
            lines += ["", "### Fel", *[f"- {e}" for e in self.errors]]

        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────────────────────────────────────

def plain(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return {k: plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [plain(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "__dict__"):
        try:
            return {k: plain(v) for k, v in vars(obj).items() if not k.startswith("_")}
        except Exception:
            pass
    return str(obj)


def getv(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)] if str(value).strip() else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def first_nonempty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Gear 4 conductor
# ─────────────────────────────────────────────────────────────────────────────

class Gear4Conductor:
    """
    Ultimate hybrid Gear 4.

    Keeps:
        - Claude's loop intuition: decompose → anchor/risk → act → checkpoint → learn.
        - GPT's normalization/artifact/result contracts.
        - Grok's strict conductor purity and pre/post guard ordering.

    Avoids:
        - putting provider/tool execution inside Gear 4
        - creating active entities directly
        - treating tasks as agents
        - proceeding through unknown risk silently
    """

    def __init__(self, config: Optional[Gear4Config] = None):
        self.config = config or Gear4Config()
        self.entity_id = self.config.entity_id
        self._running = False
        self._interrupt = False

    # ── Public controls ──────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def interrupt(self) -> None:
        self._interrupt = True
        log.info("Gear 4 interrupt requested")

    def run(self, goal: str, context: Optional[str] = None) -> Gear4Result:
        goal = (goal or "").strip()
        result = Gear4Result(entity_id=self.entity_id, goal=goal)

        if not goal:
            result.status = STATUS_FAILED
            result.errors.append("Empty goal.")
            return result

        self._running = True
        self._interrupt = False

        try:
            # 1. Understand.
            decomposition = self.decompose(goal, context)
            result.decomposition = plain(decomposition)

            # 2. Decide route.
            decision = self.specialize(decomposition, context)
            result.decision = plain(decision)

            # 3. Guard before any state-changing route.
            guard = self.guard(goal, decomposition, decision)
            result.guard = plain(guard)
            result.warnings.extend(guard.warnings)

            if not guard.allowed:
                result.status = STATUS_BLOCKED
                result.ask_frank = True
                result.frank_question = guard.reason or "Gear 4 guard stoppade routingen. Vill du granska?"
                self.persist(result)
                return result

            # 4. Route to artifact/request.
            artifact = self.route(goal, context, decomposition, decision)
            result.artifact = artifact
            result.status = artifact.status

            # 5. Ask Frank when autonomy is not earned.
            result.ask_frank = bool(decision.ask_frank or artifact.status == STATUS_DRAFT)
            if result.ask_frank:
                result.frank_question = self.make_frank_question(decision, artifact)

            # 6. Checkpoint state-bearing routes.
            if self.config.checkpoint_state_routes and artifact.kind != "direct":
                result.checkpoint_id = self.checkpoint(result)

            # 7. Medium anchor after route, if state-bearing.
            if artifact.kind != "direct":
                post_guard = self.post_route_anchor(goal, decision, artifact)
                result.warnings.extend(post_guard.warnings)
                if not post_guard.allowed:
                    result.status = STATUS_BLOCKED
                    result.ask_frank = True
                    result.frank_question = post_guard.reason or "Post-route anchor pausade Gear 4."

            self.persist(result)
            return result

        except Exception as exc:
            result.status = STATUS_FAILED
            result.errors.append(f"{type(exc).__name__}: {exc}")
            result.errors.append(traceback.format_exc(limit=8))
            self.persist(result)
            return result

        finally:
            self._running = False

    # ────────────────────────────────────────────────────────────────────────
    # Step 1 — Decompose
    # ────────────────────────────────────────────────────────────────────────

    def decompose(self, goal: str, context: Optional[str]) -> Any:
        try:
            mod = zimport("zero_decomposer")

            fn = getattr(mod, "decompose", None)
            if callable(fn):
                for args in (
                    lambda: fn(goal, context=context, entity_id=self.entity_id),
                    lambda: fn(goal, context, self.entity_id),
                    lambda: fn(goal, context=context),
                    lambda: fn(goal),
                ):
                    try:
                        return args()
                    except TypeError:
                        continue

            cls = getattr(mod, "GoalDecomposer", None)
            if cls:
                inst = cls()
                analyze = getattr(inst, "analyze", None)
                if callable(analyze):
                    return analyze(goal, context=context, entity_id=self.entity_id)

        except Exception as exc:
            log.warning("zero_decomposer unavailable, fallback used: %s", exc)

        return self.fallback_decomposition(goal, context)

    # ────────────────────────────────────────────────────────────────────────
    # Step 2 — Specialize
    # ────────────────────────────────────────────────────────────────────────

    def specialize(self, decomposition: Any, context: Optional[str]) -> Gear4Decision:
        raw = None
        try:
            mod = zimport("zero_specialization_engine")

            fn = getattr(mod, "evaluate", None)
            if callable(fn):
                for args in (
                    lambda: fn(decomposition, entity_id=self.entity_id, context=context),
                    lambda: fn(decomposition, entity_id=self.entity_id),
                    lambda: fn(decomposition),
                ):
                    try:
                        raw = args()
                        break
                    except TypeError:
                        continue

            if raw is None:
                cls = getattr(mod, "SpecializationEngine", None)
                if cls:
                    raw = cls().evaluate(decomposition, entity_id=self.entity_id, context=context)

        except Exception as exc:
            log.warning("zero_specialization_engine unavailable, fallback used: %s", exc)

        if raw is None:
            raw = self.fallback_recommendation(decomposition)

        return self.normalize_decision(raw, decomposition)

    def normalize_decision(self, raw: Any, decomposition: Any) -> Gear4Decision:
        route = str(getv(raw, "path", getv(raw, "route", DIRECT)) or DIRECT).upper()
        if route not in VALID_ROUTES:
            route = DIRECT

        confidence = max(0.0, min(1.0, safe_float(getv(raw, "confidence", 0.75), 0.75)))

        ask_frank = bool(getv(raw, "ask_frank", False))
        if confidence < CONFIDENCE_AUTO:
            ask_frank = True
        if route == ENTITY and self.config.always_ask_for_entity:
            ask_frank = True
        if route == FUNCTION and self.config.always_ask_for_function_code:
            ask_frank = True

        domain = first_nonempty(getv(raw, "entity_domain", ""), getv(decomposition, "domain", ""))

        return Gear4Decision(
            route=route,
            confidence=confidence,
            reason=first_nonempty(getv(raw, "reason", ""), getv(raw, "thinking", ""), self.default_reason(route)),
            next_action=first_nonempty(getv(raw, "next_action", ""), self.default_next_action(route)),
            ask_frank=ask_frank,
            reasons=as_list(getv(raw, "reasons", [])),
            alternatives=as_list(getv(raw, "alternatives", [])),
            suggested_steps=as_list(getv(raw, "suggested_steps", [])) or self.plan_from_decomposition(decomposition),
            entity_name=first_nonempty(getv(raw, "entity_name", ""), self.suggest_entity_name(domain)) if route == ENTITY else "",
            entity_domain=domain if route == ENTITY else "",
            entity_purpose=first_nonempty(getv(raw, "entity_purpose", ""), f"Specialist inom {domain}") if route == ENTITY else "",
            function_name=first_nonempty(getv(raw, "function_name", ""), self.suggest_function_name(decomposition)) if route == FUNCTION else "",
            function_purpose=first_nonempty(getv(raw, "function_purpose", ""), getv(decomposition, "intent", ""), getv(decomposition, "core_problem", "")) if route == FUNCTION else "",
            raw=plain(raw),
        )

    # ────────────────────────────────────────────────────────────────────────
    # Step 3 — Guards
    # ────────────────────────────────────────────────────────────────────────

    def guard(self, goal: str, decomposition: Any, decision: Gear4Decision) -> GuardResult:
        warnings: List[str] = []

        # A. Coherence: min-based contract where available.
        coherence = self.coherence_guard(goal, decomposition, decision)
        warnings.extend(coherence.warnings)
        if not coherence.allowed:
            return coherence

        # B. Identity anchor: quick pre-route anchor.
        anchor = self.identity_anchor(goal, decision, mode="quick", step=0)
        warnings.extend(anchor.warnings)
        if not anchor.allowed:
            anchor.warnings = warnings
            return anchor

        # C. Risk: before Act.
        risk = self.risk_guard(goal, decision)
        warnings.extend(risk.warnings)
        if not risk.allowed:
            risk.warnings = warnings
            return risk

        return GuardResult(
            allowed=True,
            action=CONTINUE,
            risk_level=risk.risk_level,
            coherence_score=coherence.coherence_score,
            layer0_alignment=coherence.layer0_alignment,
            mission_alignment=coherence.mission_alignment,
            entity_alignment=coherence.entity_alignment,
            warnings=warnings,
        )

    def coherence_guard(self, goal: str, decomposition: Any, decision: Gear4Decision) -> GuardResult:
        if not self.config.use_coherence_guard:
            return GuardResult()

        state = f"Gear4 goal: {goal}"
        action = f"Route as {decision.route}"

        try:
            mod = zimport("zero_coherence_contract")

            # Prefer quick_coherence because identity_anchor imports it from this module.
            for name in ("quick_coherence", "measure_coherence", "check_coherence", "medium_coherence"):
                fn = getattr(mod, name, None)
                if not callable(fn):
                    continue

                try:
                    result = fn(state, action, goal, entity_id=self.entity_id)
                except TypeError:
                    try:
                        result = fn(current_state=state, current_action=action, task_goal=goal, entity_id=self.entity_id)
                    except TypeError:
                        result = fn(state)

                return self.coherence_result_to_guard(result)

        except Exception as exc:
            return GuardResult(
                allowed=True,
                warnings=[f"Coherence guard degraded: {type(exc).__name__}: {exc}"],
            )

        return GuardResult()

    def coherence_result_to_guard(self, result: Any) -> GuardResult:
        action = str(getv(result, "action", CONTINUE) or CONTINUE).lower()
        score = safe_float(getv(result, "coherence_score", getv(result, "score", 1.0)), 1.0)
        layer0 = safe_float(getv(result, "layer0_alignment", 1.0), 1.0)
        mission = safe_float(getv(result, "mission_alignment", 1.0), 1.0)
        entity = safe_float(getv(result, "entity_alignment", 1.0), 1.0)
        reason = str(getv(result, "reason", "") or "")

        allowed = action not in {PAUSE, ABORT} and layer0 >= 0.75
        if layer0 < 0.75 and not reason:
            reason = "Layer 0 hard gate failed."

        return GuardResult(
            allowed=allowed,
            action=action,
            risk_level="SAFE",
            coherence_score=score,
            layer0_alignment=layer0,
            mission_alignment=mission,
            entity_alignment=entity,
            reason=reason,
        )

    def identity_anchor(self, goal: str, decision: Gear4Decision, mode: str, step: int) -> GuardResult:
        if not self.config.use_identity_anchor:
            return GuardResult()

        try:
            mod = zimport("zero_identity_anchor")

            fn = getattr(mod, "anchor_check", None)
            if callable(fn):
                try:
                    result = fn(
                        step=step,
                        current_state=f"Gear4 routing: {goal}",
                        current_action=f"Route as {decision.route}",
                        task_goal=goal,
                        entity_id=self.entity_id,
                        risk_level=self.route_risk(decision),
                        mode=mode,
                    )
                except TypeError:
                    result = fn(
                        step=step,
                        current_state=f"Gear4 routing: {goal}",
                        current_action=f"Route as {decision.route}",
                        task_goal=goal,
                        entity_id=self.entity_id,
                        risk_level=self.route_risk(decision),
                    )
                return self.anchor_result_to_guard(result)

            cls = getattr(mod, "IdentityAnchor", None)
            if cls:
                anchor = cls(entity_id=self.entity_id)
                result = anchor.check(
                    step=step,
                    current_state=f"Gear4 routing: {goal}",
                    current_action=f"Route as {decision.route}",
                    task_goal=goal,
                    risk_level=self.route_risk(decision),
                    force_level=mode,
                )
                return self.anchor_result_to_guard(result)

        except Exception as exc:
            return GuardResult(
                allowed=True,
                warnings=[f"Identity anchor degraded: {type(exc).__name__}: {exc}"],
            )

        return GuardResult()

    def anchor_result_to_guard(self, result: Any) -> GuardResult:
        action = str(getv(result, "action", CONTINUE) or CONTINUE).lower()
        score = safe_float(getv(result, "coherence_score", 1.0), 1.0)
        reason = str(getv(result, "reason", "") or "")
        return GuardResult(
            allowed=action not in {PAUSE, ABORT},
            action=action,
            coherence_score=score,
            reason=reason,
            warnings=[] if action == CONTINUE else [reason or f"Anchor action: {action}"],
        )

    def risk_guard(self, goal: str, decision: Gear4Decision) -> GuardResult:
        if not self.config.use_risk_policy:
            return GuardResult(risk_level=self.route_risk(decision))

        risk_level = self.route_risk(decision)

        try:
            mod = zimport("zero_risk_policy")

            fn = getattr(mod, "risk_gate", None)
            if callable(fn):
                allowed, assessment = fn(
                    operation=f"Gear4 route {decision.route}: {goal[:160]}",
                    operation_type="gear4_route",
                    entity_id=self.entity_id,
                )
                level = str(getv(assessment, "risk_level", risk_level) or risk_level)
                reason = str(getv(assessment, "reason", "") or "")
                return GuardResult(allowed=bool(allowed), action=CONTINUE if allowed else PAUSE, risk_level=level, reason=reason)

            fn = getattr(mod, "assess_risk", None)
            if callable(fn):
                assessment = fn(f"Gear4 route {decision.route}: {goal[:160]}", "gear4_route")
                level = str(getv(assessment, "risk_level", risk_level) or risk_level)
                forbidden = bool(getv(assessment, "forbidden", False))
                requires_approval = bool(getv(assessment, "requires_approval", False))
                reason = str(getv(assessment, "reason", "") or "")
                allowed = not forbidden and not (requires_approval and decision.confidence < CONFIDENCE_AUTO)
                return GuardResult(allowed=allowed, action=CONTINUE if allowed else PAUSE, risk_level=level, reason=reason)

        except Exception as exc:
            # Conservative around ENTITY when risk system is unavailable.
            if decision.route == ENTITY:
                return GuardResult(
                    allowed=False,
                    action=PAUSE,
                    risk_level="CAUTION",
                    reason="Risk policy unavailable for ENTITY route.",
                    warnings=[f"Risk policy degraded: {type(exc).__name__}: {exc}"],
                )
            return GuardResult(
                allowed=True,
                risk_level=risk_level,
                warnings=[f"Risk policy degraded: {type(exc).__name__}: {exc}"],
            )

        return GuardResult(risk_level=risk_level)

    def post_route_anchor(self, goal: str, decision: Gear4Decision, artifact: Gear4Artifact) -> GuardResult:
        if artifact.kind == "direct":
            return GuardResult()
        return self.identity_anchor(goal, decision, mode="medium", step=1)

    # ────────────────────────────────────────────────────────────────────────
    # Step 4 — Route adapters
    # ────────────────────────────────────────────────────────────────────────

    def route(self, goal: str, context: Optional[str], decomposition: Any, decision: Gear4Decision) -> Gear4Artifact:
        if self._interrupt:
            return Gear4Artifact(
                kind="interrupt",
                title="INTERRUPTED",
                status=STATUS_BLOCKED,
                message="Gear 4 avbröts innan routing.",
            )

        if decision.route == DIRECT:
            return self.route_direct(goal, decomposition, decision)
        if decision.route == FUNCTION:
            return self.route_function(goal, decomposition, decision)
        if decision.route == TASK:
            return self.route_task(goal, decomposition, decision)
        if decision.route == ENTITY:
            return self.route_entity(goal, decomposition, decision)

        return Gear4Artifact(
            kind="unknown",
            title="UNKNOWN ROUTE",
            status=STATUS_FAILED,
            message=f"Unknown route: {decision.route}",
        )

    def route_direct(self, goal: str, decomposition: Any, decision: Gear4Decision) -> Gear4Artifact:
        # Direct is explicitly handed back to the chat/engine layer.
        return Gear4Artifact(
            kind="direct",
            title="DIRECT — svara direkt",
            status=STATUS_COMPLETE if self.config.execute_direct else STATUS_READY,
            message="Gear 4 bedömer att målet ska lösas direkt av normal chat/engine utan extra autonomi.",
            data={
                "next_action": "answer_directly",
                "goal": goal,
                "decomposition": plain(decomposition),
            },
        )

    def route_function(self, goal: str, decomposition: Any, decision: Gear4Decision) -> Gear4Artifact:
        brief = {
            "function_name": decision.function_name or self.suggest_function_name(decomposition),
            "purpose": decision.function_purpose or goal,
            "input_contract": "Define before coding.",
            "output_contract": "Define before coding.",
            "test_required": True,
            "suggested_steps": decision.suggested_steps,
        }

        return Gear4Artifact(
            kind="function",
            title=f"FUNCTION — {brief['function_name']}",
            status=STATUS_DRAFT,
            message="Gear 4 rekommenderar återanvändbar funktion/modul. Den skriver inte kod förrän briefet är godkänt.",
            data={"function_brief": brief},
        )

    def route_task(self, goal: str, decomposition: Any, decision: Gear4Decision) -> Gear4Artifact:
        plan = decision.suggested_steps or self.plan_from_decomposition(decomposition)
        task_request = {
            "goal": goal,
            "plan": plan,
            "entity_id": self.entity_id,
            "risk_level": self.route_risk(decision),
            "status": "draft",
        }

        task_id = ""
        task_obj = None

        if self.config.allow_state_creation and not self.config.dry_run:
            try:
                mod = zimport("zero_task")
                create_task = getattr(mod, "create_task", None)
                if callable(create_task):
                    task_obj = create_task(**task_request)
                else:
                    manager_cls = getattr(mod, "TaskManager", None)
                    if manager_cls:
                        manager = manager_cls(entity_id=self.entity_id)
                        task_obj = manager.create_task(goal=goal, plan=plan, risk_level=self.route_risk(decision))

                task_id = str(getv(task_obj, "task_id", "") or "")
            except Exception as exc:
                return Gear4Artifact(
                    kind="task",
                    title="TASK — creation failed",
                    status=STATUS_FAILED,
                    message=f"Task creation failed: {type(exc).__name__}: {exc}",
                    data={"task_request": task_request},
                )

        return Gear4Artifact(
            kind="task",
            title="TASK — strukturerat uppdrag",
            status=STATUS_READY if task_id else STATUS_DRAFT,
            message="Gear 4 rekommenderar ett finite task med state, checkpoints och review.",
            data={
                "task_id": task_id,
                "task_request": task_request,
                "task": plain(task_obj),
                "state_created": bool(task_id),
            },
        )

    def route_entity(self, goal: str, decomposition: Any, decision: Gear4Decision) -> Gear4Artifact:
        draft = {
            "name": decision.entity_name or self.suggest_entity_name(decision.entity_domain),
            "domain": decision.entity_domain or str(getv(decomposition, "domain", "general") or "general"),
            "purpose": decision.entity_purpose or goal,
            "status": "DRAFT",
            "source_goal": goal,
            "confidence": decision.confidence,
            "created_by": "Gear4",
            "non_negotiables": [
                "Starts as DRAFT.",
                "Shares Layer 0 with Zero.",
                "No ACTIVE autonomy without Frank approval.",
            ],
        }

        wizard_request = {
            "action": "start_entity_wizard",
            "draft": draft,
            "first_questions": [
                "Vad ska denna Entity bli bättre på än Zero generalist?",
                "Vilka källor, mentorer eller dokument ska den studera?",
                "Vilka beslut måste alltid gå via Frank?",
            ],
        }

        # Intentionally do not call Entity Manager here. Entity Wizard owns the design conversation.
        return Gear4Artifact(
            kind="entity",
            title=f"ENTITY — Draft: {draft['name']}",
            status=STATUS_DRAFT,
            message="Gear 4 rekommenderar Draft Entity / Entity Wizard. Detta skapar inte en aktiv agent.",
            data={
                "draft_entity": draft,
                "wizard_request": wizard_request,
            },
        )

    # ────────────────────────────────────────────────────────────────────────
    # Step 5 — Checkpoint / persistence
    # ────────────────────────────────────────────────────────────────────────

    def checkpoint(self, result: Gear4Result) -> str:
        if not result.artifact or result.artifact.kind == "direct":
            return ""

        try:
            mod = zimport("zero_checkpoint")
            save_checkpoint = getattr(mod, "save_checkpoint", None)
            if callable(save_checkpoint):
                cp = save_checkpoint(
                    task_id=result.run_id,
                    step_number=0,
                    step_description=f"Gear4 routed as {result.decision.get('route')}",
                    goal=result.goal,
                    remaining_plan=[],
                    observation=result.artifact.message,
                    next_step=result.decision.get("next_action", ""),
                    coherence_score=safe_float(result.guard.get("coherence_score", 1.0), 1.0),
                    layer0_alignment=safe_float(result.guard.get("layer0_alignment", 1.0), 1.0),
                    mission_alignment=safe_float(result.guard.get("mission_alignment", 1.0), 1.0),
                    entity_alignment=safe_float(result.guard.get("entity_alignment", 1.0), 1.0),
                    entity_id=self.entity_id,
                    context=result.to_dict(),
                )
                return str(getv(cp, "checkpoint_id", "") or "")
        except Exception as exc:
            result.warnings.append(f"Checkpoint failed: {type(exc).__name__}: {exc}")

        return ""

    def persist(self, result: Gear4Result) -> None:
        try:
            path = GEAR4_DIR / f"{result.run_id}.json"
            path.write_text(result.to_json(), encoding="utf-8")
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────────────────
    # Fallbacks and small helpers
    # ────────────────────────────────────────────────────────────────────────

    def fallback_decomposition(self, goal: str, context: Optional[str]) -> Dict[str, Any]:
        text = f"{goal}\n{context or ''}".lower()

        domain = "general"
        if any(w in text for w in ("flipper", "pinball", "stern", "williams", "bally", "gottlieb")):
            domain = "pinball"
        elif any(w in text for w in ("trading", "trade", "market", "tradingview")):
            domain = "trading"
        elif any(w in text for w in ("python", "kod", "script", "modul", "api", "server", "funktion")):
            domain = "programming"

        recurring = any(w in text for w in ("återkommande", "varje", "långsiktig", "över tid", "specialist", "entity", "entitet"))
        research = any(w in text for w in ("analysera", "research", "undersök", "jämför", "gå igenom"))
        learning = any(w in text for w in ("lära", "studera", "förbättras", "över tid", "mentor"))

        return {
            "raw_goal": goal,
            "core_problem": goal,
            "intent": goal,
            "domain": domain,
            "complexity": "moderate" if research or recurring else "simple",
            "is_recurring": recurring,
            "requires_research": research,
            "requires_learning": learning,
            "requires_memory": recurring,
            "estimated_steps": 3 if research else 1,
            "sub_goals": [],
            "missing_context": [],
        }

    def fallback_recommendation(self, decomposition: Any) -> Gear4Decision:
        domain = str(getv(decomposition, "domain", "general") or "general")
        recurring = bool(getv(decomposition, "is_recurring", False))
        learning = bool(getv(decomposition, "requires_learning", False))
        research = bool(getv(decomposition, "requires_research", False))
        complexity = str(getv(decomposition, "complexity", "simple") or "simple")

        if recurring and (learning or domain not in {"general", "programming"}):
            route = ENTITY
            confidence = 0.72
            reason = "Fallback: recurring + learning/domain signal suggests Draft Entity."
        elif domain == "programming" and not learning:
            route = FUNCTION
            confidence = 0.70
            reason = "Fallback: technical bounded problem suggests reusable function/module."
        elif research or complexity in {"moderate", "complex"}:
            route = TASK
            confidence = 0.70
            reason = "Fallback: multi-step/research signal suggests task."
        else:
            route = DIRECT
            confidence = 0.78
            reason = "Fallback: simple goal suggests direct answer."

        return Gear4Decision(
            route=route,
            confidence=confidence,
            reason=reason,
            reasons=[reason],
            next_action=self.default_next_action(route),
            ask_frank=True,
        )

    def default_next_action(self, route: str) -> str:
        return {
            DIRECT: "answer_directly",
            FUNCTION: "create_function_brief",
            TASK: "create_task_request",
            ENTITY: "start_entity_wizard",
        }.get(route, "answer_directly")

    def default_reason(self, route: str) -> str:
        return {
            DIRECT: "This appears best handled as a direct answer.",
            FUNCTION: "This appears best handled as reusable code/functionality.",
            TASK: "This appears best handled as a finite multi-step task.",
            ENTITY: "This appears best handled as a long-term specialist/Draft Entity.",
        }.get(route, "")

    def route_risk(self, decision: Gear4Decision) -> str:
        if decision.route == DIRECT:
            return "SAFE"
        if decision.route in {FUNCTION, TASK, ENTITY}:
            return "CAUTION"
        return "SAFE"

    def plan_from_decomposition(self, decomposition: Any) -> List[str]:
        sub_goals = as_list(getv(decomposition, "sub_goals", []))
        if sub_goals:
            return sub_goals

        missing = as_list(getv(decomposition, "missing_context", []))
        plan = ["Förstå målet och samla relevant kontext"]
        if missing:
            plan.append("Hämta saknad kontext: " + "; ".join(missing[:3]))
        plan.extend(["Analysera möjliga vägar", "Sammanfatta rekommendation och nästa steg"])
        return plan

    def suggest_entity_name(self, domain: str) -> str:
        d = (domain or "").lower()
        if "pinball" in d:
            return "Minna"
        if "trading" in d:
            return "Master Trader Assistant"
        if "social" in d:
            return "Pinball Social Entity"
        if "system" in d:
            return "Zero Systems Apprentice"
        if "programming" in d:
            return "Zero Builder"
        if d and d != "general":
            return d.replace("_", " ").title() + " Assistant"
        return "Draft Specialist"

    def suggest_function_name(self, decomposition: Any) -> str:
        domain = str(getv(decomposition, "domain", "zero") or "zero").lower()
        intent = first_nonempty(
            getv(decomposition, "intent", ""),
            getv(decomposition, "core_problem", ""),
            getv(decomposition, "raw_goal", ""),
            "helper",
        )
        slug = "".join(ch if ch.isalnum() else "_" for ch in intent.lower()).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        slug = slug[:40] or "helper"
        return f"{domain}_{slug}"

    def make_frank_question(self, decision: Gear4Decision, artifact: Gear4Artifact) -> str:
        if decision.route == ENTITY:
            return f"Jag rekommenderar Draft Entity: **{decision.entity_name or 'specialist'}**. Vill du starta Entity Wizard och designa den tillsammans?"
        if decision.route == FUNCTION:
            return "Jag rekommenderar en återanvändbar funktion/modul. Vill du godkänna briefet och skriva implementation?"
        if decision.route == TASK:
            return "Jag rekommenderar ett strukturerat task. Vill du godkänna plan/state creation?"
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_engines: Dict[str, Gear4Conductor] = {}


def get_gear4(entity_id: str = "zero", config: Optional[Gear4Config] = None) -> Gear4Conductor:
    if config is not None:
        return Gear4Conductor(config)
    if entity_id not in _engines:
        _engines[entity_id] = Gear4Conductor(Gear4Config(entity_id=entity_id))
    return _engines[entity_id]


def process_goal(
    goal: str,
    context: Optional[str] = None,
    entity_id: str = "zero",
    dry_run: bool = False,
    allow_state_creation: bool = False,
) -> Gear4Result:
    conductor = Gear4Conductor(Gear4Config(
        entity_id=entity_id,
        dry_run=dry_run,
        allow_state_creation=allow_state_creation,
    ))
    return conductor.run(goal, context=context)


def route_goal(goal: str, context: Optional[str] = None, entity_id: str = "zero") -> Gear4Result:
    return process_goal(goal, context=context, entity_id=entity_id, dry_run=True, allow_state_creation=False)


def interrupt(entity_id: str = "zero") -> None:
    if entity_id in _engines:
        _engines[entity_id].interrupt()


def status(entity_id: str = "zero") -> str:
    running = _engines.get(entity_id).is_running if entity_id in _engines else False
    return f"Gear 4 v{VERSION} — entity={entity_id} — running={running} — root={ZERO_ROOT}"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=f"ZeroPointAI Gear 4 Ultimate Hybrid v{VERSION}")
    parser.add_argument("--goal", help="Goal to route through Gear 4")
    parser.add_argument("--context", default=None)
    parser.add_argument("--entity", default="zero")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-state-creation", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.status:
        print(status(entity_id=args.entity))
        return 0

    if args.test:
        goals = [
            "Vad betyder OSError address already in use?",
            "Skriv en funktion som skapar specs för viktiga moduler",
            "Analysera varför Firepower-flippern inte svarar",
            "Skapa en Master Trader Assistant som lär sig över tid",
        ]
        ok = True
        for goal in goals:
            result = process_goal(goal, entity_id=args.entity, dry_run=True)
            print("=" * 90)
            print(result.format_for_frank())
            ok = ok and result.ok()
        return 0 if ok else 2

    if not args.goal:
        parser.error("--goal krävs om du inte använder --status eller --test")

    result = process_goal(
        goal=args.goal,
        context=args.context,
        entity_id=args.entity,
        dry_run=args.dry_run,
        allow_state_creation=args.allow_state_creation,
    )

    print(result.to_json() if args.json else result.format_for_frank())
    return 0 if result.ok() else 2


if __name__ == "__main__":
    raise SystemExit(main())
