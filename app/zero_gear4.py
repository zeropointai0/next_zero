#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_gear4.py — ZeroPointAI Gear 4 Conductor v2.1

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Ren Gear 4-orkestrator: Goal → Decompose → Specialize → Guard → Route
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_specialization_engine.py, zero_coherence_contract.py, zero_identity_anchor.py, zero_risk_policy.py, zero_task.py, zero_entity_wizard.py
ZERO_USED_BY:   zero_web_server.py, zero_router.py, zero_night.py

Mental Model:
    Gear 4 är dirigenten.

    Den ska inte vara arbetaren.
    Den ska inte vara verktygslådan.
    Den ska inte bli en monolit.

    Den ska avgöra:
        Ska Zero svara direkt?
        Ska Zero bygga en återanvändbar funktion?
        Ska Zero skapa ett avgränsat task?
        Ska Zero föreslå en Draft Entity / Wizard?

Core Flow:
    goal
      ↓
    zero_decomposer
      ↓
    zero_specialization_engine
      ↓
    coherence + identity + risk guards
      ↓
    route adapter:
        DIRECT   → direct artifact
        FUNCTION → function brief
        TASK     → task request
        ENTITY   → wizard request / draft entity recommendation

Non-Negotiables:
    - ENTITY betyder Draft Entity eller Wizard, aldrig ACTIVE agent.
    - Gear 4 väljer väg; den exekverar inte verktyg själv.
    - Guardrails körs före state-changing route.
    - Om confidence är låg frågar Gear 4 Frank.
    - Om kontext saknas exponeras det tydligt.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "2.1"
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Root detection / imports
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


def import_zero_module(name: str):
    try:
        return __import__(f"app.{name}", fromlist=["*"])
    except Exception:
        return __import__(name, fromlist=["*"])


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DIRECT = "DIRECT"
FUNCTION = "FUNCTION"
TASK = "TASK"
ENTITY = "ENTITY"
VALID_PATHS = {DIRECT, FUNCTION, TASK, ENTITY}

CONTINUE = "continue"
WARN = "warn"
PAUSE = "pause"
ABORT = "abort"

CONFIDENCE_AUTO = 0.90
CONFIDENCE_ASK = 0.65


# ─────────────────────────────────────────────────────────────────────────────
# Data contracts
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Gear4Config:
    entity_id: str = "zero"
    dry_run: bool = False
    allow_state_creation: bool = False
    require_frank_for_entity: bool = True
    require_frank_for_function_code: bool = True
    checkpoint: bool = True


@dataclass
class Gear4Recommendation:
    path: str = DIRECT
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
class Gear4GuardResult:
    allowed: bool = True
    action: str = CONTINUE
    risk_level: str = "SAFE"
    coherence_score: float = 1.0
    reason: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class Gear4Artifact:
    kind: str
    title: str
    message: str
    status: str = "ready"
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Gear4Result:
    run_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6])
    version: str = VERSION
    entity_id: str = "zero"
    goal: str = ""
    status: str = "ready"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    decomposition: Dict[str, Any] = field(default_factory=dict)
    recommendation: Dict[str, Any] = field(default_factory=dict)
    guard: Dict[str, Any] = field(default_factory=dict)
    artifact: Optional[Gear4Artifact] = None

    ask_frank: bool = False
    frank_question: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        return self.status not in {"failed", "blocked"}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["ok"] = self.ok()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    def format_for_frank(self) -> str:
        rec = self.recommendation or {}
        artifact = self.artifact
        lines = [
            f"## Gear 4 v{self.version}",
            "",
            f"**Goal:** {self.goal}",
            f"**Route:** {rec.get('path', '?')} ({float(rec.get('confidence', 0.0)):.0%})",
            f"**Status:** {self.status}",
        ]

        if rec.get("reason"):
            lines += ["", f"**Reason:** {rec['reason']}"]

        if artifact:
            lines += ["", f"### {artifact.title}", artifact.message]

        reasons = rec.get("reasons") or []
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
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def as_float(value: Any, default: float = 0.0) -> float:
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
    Minimal, strict Gear 4 conductor.

    Owns:
        - pipeline order
        - normalization
        - guard sequence
        - route selection
        - route artifacts

    Does not own:
        - deep goal understanding
        - specialization scoring
        - task execution
        - entity design dialogue
        - tool execution
    """

    def __init__(self, config: Optional[Gear4Config] = None):
        self.config = config or Gear4Config()
        self.entity_id = self.config.entity_id

    def process_goal(self, goal: str, context: Optional[str] = None) -> Gear4Result:
        goal = (goal or "").strip()
        result = Gear4Result(entity_id=self.entity_id, goal=goal)

        if not goal:
            result.status = "failed"
            result.errors.append("Empty goal.")
            return result

        try:
            decomposition = self.decompose(goal, context)
            result.decomposition = plain(decomposition)

            recommendation = self.specialize(decomposition, context)
            rec = self.normalize_recommendation(recommendation, decomposition)
            result.recommendation = plain(rec)

            guard = self.guard(goal, decomposition, rec)
            result.guard = plain(guard)
            result.warnings.extend(guard.warnings)

            if not guard.allowed:
                result.status = "blocked"
                result.ask_frank = True
                result.frank_question = guard.reason or "Gear 4 guard stoppade routingen. Vill du granska?"
                self.persist(result)
                return result

            artifact = self.route(goal, context, decomposition, rec)
            result.artifact = artifact
            result.ask_frank = rec.ask_frank or artifact.status in {"draft", "blocked"}
            result.status = artifact.status if artifact.status in {"draft", "blocked", "failed"} else "ready"

            if result.ask_frank:
                result.frank_question = self.frank_question(rec, artifact)

            if self.config.checkpoint:
                self.checkpoint(result)

            self.persist(result)
            return result

        except Exception as exc:
            result.status = "failed"
            result.errors.append(f"{type(exc).__name__}: {exc}")
            self.persist(result)
            return result

    # ── Delegated intelligence ───────────────────────────────────────────────

    def decompose(self, goal: str, context: Optional[str]) -> Any:
        try:
            mod = import_zero_module("zero_decomposer")
            if hasattr(mod, "decompose"):
                fn = mod.decompose
                try:
                    return fn(goal, context=context, entity_id=self.entity_id)
                except TypeError:
                    try:
                        return fn(goal, context=context)
                    except TypeError:
                        return fn(goal)

            cls = getattr(mod, "GoalDecomposer", None)
            if cls:
                inst = cls()
                if hasattr(inst, "analyze"):
                    return inst.analyze(goal, context=context)
        except Exception as exc:
            log.warning("zero_decomposer unavailable, fallback used: %s", exc)

        return self.fallback_decomposition(goal, context)

    def specialize(self, decomposition: Any, context: Optional[str]) -> Any:
        try:
            mod = import_zero_module("zero_specialization_engine")
            if hasattr(mod, "evaluate"):
                fn = mod.evaluate
                try:
                    return fn(decomposition, entity_id=self.entity_id, context=context)
                except TypeError:
                    try:
                        return fn(decomposition, entity_id=self.entity_id)
                    except TypeError:
                        return fn(decomposition)

            cls = getattr(mod, "SpecializationEngine", None)
            if cls:
                return cls().evaluate(decomposition, entity_id=self.entity_id, context=context)
        except Exception as exc:
            log.warning("zero_specialization_engine unavailable, fallback used: %s", exc)

        return self.fallback_recommendation(decomposition)

    # ── Normalization ────────────────────────────────────────────────────────

    def normalize_recommendation(self, obj: Any, decomposition: Any) -> Gear4Recommendation:
        path = str(getv(obj, "path", DIRECT) or DIRECT).upper()
        if path not in {DIRECT, FUNCTION, TASK, ENTITY}:
            path = DIRECT

        confidence = max(0.0, min(1.0, as_float(getv(obj, "confidence", 0.75), 0.75)))
        ask_frank = bool(getv(obj, "ask_frank", False)) or confidence < CONFIDENCE_AUTO

        entity_domain = first_nonempty(getv(obj, "entity_domain", ""), getv(decomposition, "domain", ""))
        entity_name = first_nonempty(getv(obj, "entity_name", ""), self.suggest_entity_name(entity_domain))

        rec = Gear4Recommendation(
            path=path,
            confidence=confidence,
            reason=first_nonempty(getv(obj, "reason", ""), getv(obj, "thinking", "")),
            next_action=first_nonempty(getv(obj, "next_action", ""), self.default_next_action(path)),
            ask_frank=ask_frank,
            reasons=as_list(getv(obj, "reasons", [])),
            alternatives=as_list(getv(obj, "alternatives", [])),
            suggested_steps=as_list(getv(obj, "suggested_steps", [])) or self.plan_from_decomposition(decomposition),
            entity_name=entity_name if path == ENTITY else "",
            entity_domain=entity_domain if path == ENTITY else "",
            entity_purpose=first_nonempty(getv(obj, "entity_purpose", ""), f"Specialist inom {entity_domain}") if path == ENTITY else "",
            function_name=first_nonempty(getv(obj, "function_name", ""), self.suggest_function_name(decomposition)) if path == FUNCTION else "",
            function_purpose=first_nonempty(getv(obj, "function_purpose", ""), getv(decomposition, "intent", ""), getv(decomposition, "core_problem", "")) if path == FUNCTION else "",
            raw=plain(obj),
        )

        if not rec.reason:
            rec.reason = self.default_reason(rec.path)

        return rec

    # ── Guards ───────────────────────────────────────────────────────────────

    def guard(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Gear4GuardResult:
        warnings: List[str] = []

        # 1. Coherence contract first if available.
        coherence_allowed, coherence_score, coherence_reason, coherence_warnings = self.coherence_guard(goal, decomposition, rec)
        warnings.extend(coherence_warnings)
        if not coherence_allowed:
            return Gear4GuardResult(
                allowed=False,
                action=PAUSE,
                risk_level=self.route_risk(rec),
                coherence_score=coherence_score,
                reason=coherence_reason or "Coherence guard paused Gear 4.",
                warnings=warnings,
            )

        # 2. Identity anchor.
        anchor_action, anchor_reason, anchor_warnings = self.identity_guard(goal, rec)
        warnings.extend(anchor_warnings)
        if anchor_action in {PAUSE, ABORT}:
            return Gear4GuardResult(
                allowed=False,
                action=anchor_action,
                risk_level=self.route_risk(rec),
                coherence_score=coherence_score,
                reason=anchor_reason or "Identity anchor paused Gear 4.",
                warnings=warnings,
            )

        # 3. Risk policy.
        risk_allowed, risk_level, risk_reason, risk_warnings = self.risk_guard(goal, rec)
        warnings.extend(risk_warnings)
        if not risk_allowed:
            return Gear4GuardResult(
                allowed=False,
                action=PAUSE,
                risk_level=risk_level,
                coherence_score=coherence_score,
                reason=risk_reason or "Risk policy paused Gear 4.",
                warnings=warnings,
            )

        # 4. Gear4-specific policy.
        if rec.path == ENTITY and self.config.require_frank_for_entity:
            rec.ask_frank = True

        if rec.path == FUNCTION and self.config.require_frank_for_function_code:
            rec.ask_frank = True

        return Gear4GuardResult(
            allowed=True,
            action=CONTINUE,
            risk_level=risk_level,
            coherence_score=coherence_score,
            warnings=warnings,
        )

    def coherence_guard(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Tuple[bool, float, str, List[str]]:
        try:
            mod = import_zero_module("zero_coherence_contract")

            # Preferred APIs.
            for name in ("check_coherence", "evaluate_coherence", "coherence_check"):
                fn = getattr(mod, name, None)
                if callable(fn):
                    result = fn(
                        current_state=f"Gear4 routing: {goal}",
                        current_action=f"Route as {rec.path}",
                        task_goal=goal,
                        entity_id=self.entity_id,
                    )
                    action = str(getv(result, "action", CONTINUE)).lower()
                    score = as_float(getv(result, "coherence_score", getv(result, "score", 1.0)), 1.0)
                    reason = str(getv(result, "reason", "") or "")
                    return action not in {PAUSE, ABORT}, score, reason, []

            cls = getattr(mod, "CoherenceContract", None)
            if cls:
                obj = cls(entity_id=self.entity_id) if "entity_id" in getattr(cls.__init__, "__code__", ()).co_varnames else cls()
                for method in ("check", "evaluate"):
                    fn = getattr(obj, method, None)
                    if callable(fn):
                        result = fn(
                            current_state=f"Gear4 routing: {goal}",
                            current_action=f"Route as {rec.path}",
                            task_goal=goal,
                        )
                        action = str(getv(result, "action", CONTINUE)).lower()
                        score = as_float(getv(result, "coherence_score", getv(result, "score", 1.0)), 1.0)
                        reason = str(getv(result, "reason", "") or "")
                        return action not in {PAUSE, ABORT}, score, reason, []

        except Exception as exc:
            return True, 1.0, "", [f"Coherence guard unavailable/degraded: {type(exc).__name__}: {exc}"]

        return True, 1.0, "", []

    def identity_guard(self, goal: str, rec: Gear4Recommendation) -> Tuple[str, str, List[str]]:
        try:
            mod = import_zero_module("zero_identity_anchor")

            for name in ("anchor_check", "check_anchor"):
                fn = getattr(mod, name, None)
                if callable(fn):
                    event = fn(
                        step=0,
                        current_state=f"Gear4 routing: {goal}",
                        current_action=f"Route as {rec.path}",
                        task_goal=goal,
                        entity_id=self.entity_id,
                        risk_level=self.route_risk(rec),
                    )
                    action = str(getv(event, "action", CONTINUE)).lower()
                    reason = str(getv(event, "reason", "") or "")
                    return action, reason, []

            cls = getattr(mod, "IdentityAnchor", None)
            if cls:
                obj = cls(entity_id=self.entity_id)
                event = obj.check(
                    step=0,
                    current_state=f"Gear4 routing: {goal}",
                    current_action=f"Route as {rec.path}",
                    task_goal=goal,
                    risk_level=self.route_risk(rec),
                )
                action = str(getv(event, "action", CONTINUE)).lower()
                reason = str(getv(event, "reason", "") or "")
                return action, reason, []

        except Exception as exc:
            return CONTINUE, "", [f"Identity anchor unavailable/degraded: {type(exc).__name__}: {exc}"]

        return CONTINUE, "", []

    def risk_guard(self, goal: str, rec: Gear4Recommendation) -> Tuple[bool, str, str, List[str]]:
        risk_level = self.route_risk(rec)

        try:
            mod = import_zero_module("zero_risk_policy")

            fn = getattr(mod, "risk_gate", None)
            if callable(fn):
                allowed, assessment = fn(
                    operation=f"Gear4 route {rec.path}: {goal}",
                    operation_type="gear4_route",
                    operation_id=f"gear4:{uuid.uuid4().hex[:8]}",
                    entity_id=self.entity_id,
                )
                actual = str(getv(assessment, "risk_level", risk_level) or risk_level)
                reason = str(getv(assessment, "reason", "") or "")
                return bool(allowed), actual, reason, []

            fn = getattr(mod, "assess_risk", None)
            if callable(fn):
                assessment = fn(f"Gear4 route {rec.path}: {goal}", "gear4_route")
                actual = str(getv(assessment, "risk_level", risk_level) or risk_level)
                forbidden = bool(getv(assessment, "forbidden", False))
                requires_approval = bool(getv(assessment, "requires_approval", False))
                if forbidden:
                    return False, actual, "FORBIDDEN operation blocked.", []
                if requires_approval and rec.confidence < CONFIDENCE_AUTO:
                    return False, actual, "Risk policy requires Frank approval.", []
                return True, actual, "", []

        except Exception as exc:
            return True, risk_level, "", [f"Risk policy unavailable/degraded: {type(exc).__name__}: {exc}"]

        if risk_level in {"HIGH", "CRITICAL"} and rec.confidence < CONFIDENCE_AUTO:
            return False, risk_level, f"{risk_level} route requires Frank approval.", []

        return True, risk_level, "", []

    # ── Routing adapters ─────────────────────────────────────────────────────

    def route(self, goal: str, context: Optional[str], decomposition: Any, rec: Gear4Recommendation) -> Gear4Artifact:
        if rec.path == DIRECT:
            return self.route_direct(goal, decomposition, rec)
        if rec.path == FUNCTION:
            return self.route_function(goal, decomposition, rec)
        if rec.path == TASK:
            return self.route_task(goal, decomposition, rec)
        if rec.path == ENTITY:
            return self.route_entity(goal, decomposition, rec)

        return Gear4Artifact(
            kind="unknown",
            title="UNKNOWN",
            status="failed",
            message=f"Unknown route: {rec.path}",
        )

    def route_direct(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Gear4Artifact:
        return Gear4Artifact(
            kind="direct",
            title="DIRECT — svara direkt",
            status="ready",
            message="Gear 4 bedömer att detta ska lösas direkt av normal chat/engine, utan task, funktion eller Entity.",
            data={
                "next_action": "answer_directly",
                "goal": goal,
                "decomposition": plain(decomposition),
            },
        )

    def route_function(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Gear4Artifact:
        return Gear4Artifact(
            kind="function",
            title=f"FUNCTION — {rec.function_name or 'new_function'}",
            status="draft",
            message="Gear 4 bedömer att detta bör bli en återanvändbar funktion/modul. Kod ska inte skrivas förrän briefet är godkänt.",
            data={
                "function_name": rec.function_name,
                "purpose": rec.function_purpose or goal,
                "brief": {
                    "input": "Define exact input contract before coding.",
                    "output": "Define exact output contract before coding.",
                    "test": "Add py_compile/import test at minimum.",
                },
                "suggested_steps": rec.suggested_steps,
            },
        )

    def route_task(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Gear4Artifact:
        plan = rec.suggested_steps or self.plan_from_decomposition(decomposition)
        task_payload = {
            "goal": goal,
            "plan": plan,
            "risk_level": self.route_risk(rec),
            "entity_id": self.entity_id,
            "status": "draft",
        }

        task_id = ""
        if self.config.allow_state_creation and not self.config.dry_run:
            try:
                mod = import_zero_module("zero_task")
                if hasattr(mod, "create_task"):
                    task = mod.create_task(**task_payload)
                    task_id = str(getv(task, "task_id", ""))
                else:
                    manager_cls = getattr(mod, "TaskManager", None)
                    if manager_cls:
                        manager = manager_cls(entity_id=self.entity_id)
                        task = manager.create_task(goal=goal, plan=plan, risk_level=self.route_risk(rec))
                        task_id = str(getv(task, "task_id", ""))
            except Exception as exc:
                return Gear4Artifact(
                    kind="task",
                    title="TASK — creation failed",
                    status="failed",
                    message=f"Task creation failed: {type(exc).__name__}: {exc}",
                    data=task_payload,
                )

        return Gear4Artifact(
            kind="task",
            title="TASK — strukturerat uppdrag",
            status="draft" if not task_id else "ready",
            message="Gear 4 bedömer att detta är ett avgränsat flerstegsuppdrag. Det ska hanteras som task med checkpoints och review.",
            data={
                "task_id": task_id,
                "task_request": task_payload,
                "state_created": bool(task_id),
            },
        )

    def route_entity(self, goal: str, decomposition: Any, rec: Gear4Recommendation) -> Gear4Artifact:
        draft = {
            "name": rec.entity_name or self.suggest_entity_name(rec.entity_domain),
            "domain": rec.entity_domain or str(getv(decomposition, "domain", "general")),
            "purpose": rec.entity_purpose or goal,
            "status": "DRAFT",
            "source_goal": goal,
            "confidence": rec.confidence,
            "non_negotiables": [
                "Starts as DRAFT.",
                "Shares Layer 0 with Zero.",
                "No ACTIVE autonomy without Frank approval.",
            ],
        }

        wizard_request = {
            "action": "start_entity_wizard",
            "draft": draft,
            "questions": [
                "Vad ska denna Entity bli bättre på än Zero generalist?",
                "Vilka källor/mentorer ska den studera?",
                "Vilka beslut får den aldrig ta själv?",
            ],
        }

        return Gear4Artifact(
            kind="entity",
            title=f"ENTITY — Draft: {draft['name']}",
            status="draft",
            message="Gear 4 rekommenderar Draft Entity / Entity Wizard. Detta skapar inte en aktiv agent.",
            data={
                "draft_entity": draft,
                "wizard_request": wizard_request,
            },
        )

    # ── Checkpoint / persistence ─────────────────────────────────────────────

    def checkpoint(self, result: Gear4Result) -> None:
        if not result.artifact or result.artifact.kind == "direct":
            return

        try:
            mod = import_zero_module("zero_checkpoint")
            fn = getattr(mod, "save_checkpoint", None)
            if callable(fn):
                fn(
                    task_id=result.run_id,
                    step_number=0,
                    step_description=f"Gear4 route: {result.recommendation.get('path')}",
                    goal=result.goal,
                    remaining_plan=[],
                    observation=result.artifact.message,
                    next_step=result.recommendation.get("next_action", ""),
                    coherence_score=float(result.guard.get("coherence_score", 1.0)),
                    layer0_alignment=1.0,
                    mission_alignment=1.0,
                    entity_alignment=1.0,
                    entity_id=self.entity_id,
                    context=result.to_dict(),
                )
        except Exception as exc:
            result.warnings.append(f"Checkpoint failed: {type(exc).__name__}: {exc}")

    def persist(self, result: Gear4Result) -> None:
        try:
            path = GEAR4_DIR / f"gear4_run_{result.run_id}.json"
            path.write_text(result.to_json(), encoding="utf-8")
        except Exception:
            pass

    # ── Fallbacks ────────────────────────────────────────────────────────────

    def fallback_decomposition(self, goal: str, context: Optional[str]) -> Dict[str, Any]:
        text = f"{goal}\n{context or ''}".lower()

        domain = "general"
        if any(w in text for w in ["flipper", "pinball", "stern", "williams", "bally", "gottlieb"]):
            domain = "pinball"
        elif any(w in text for w in ["trading", "trade", "market", "tradingview"]):
            domain = "trading"
        elif any(w in text for w in ["python", "kod", "script", "modul", "api", "server", "funktion"]):
            domain = "programming"

        recurring = any(w in text for w in ["återkommande", "varje", "långsiktig", "över tid", "specialist", "entity", "entitet"])
        research = any(w in text for w in ["analysera", "research", "undersök", "jämför", "gå igenom"])
        learning = any(w in text for w in ["lära", "studera", "förbättras", "över tid", "mentor"])

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

    def fallback_recommendation(self, decomposition: Any) -> Gear4Recommendation:
        domain = str(getv(decomposition, "domain", "general") or "general")
        recurring = bool(getv(decomposition, "is_recurring", False))
        learning = bool(getv(decomposition, "requires_learning", False))
        research = bool(getv(decomposition, "requires_research", False))
        complexity = str(getv(decomposition, "complexity", "simple") or "simple")

        if recurring and (learning or domain not in {"general", "programming"}):
            path = ENTITY
            confidence = 0.72
            reason = "Fallback: recurring + learning/domain signal suggests Draft Entity."
        elif domain == "programming" and not learning:
            path = FUNCTION
            confidence = 0.70
            reason = "Fallback: technical bounded problem suggests reusable function/module."
        elif research or complexity in {"moderate", "complex"}:
            path = TASK
            confidence = 0.70
            reason = "Fallback: multi-step/research signal suggests task."
        else:
            path = DIRECT
            confidence = 0.78
            reason = "Fallback: simple goal suggests direct answer."

        return Gear4Recommendation(
            path=path,
            confidence=confidence,
            reason=reason,
            reasons=[reason],
            next_action=self.default_next_action(path),
            ask_frank=confidence < CONFIDENCE_AUTO,
        )

    # ── Utility ──────────────────────────────────────────────────────────────

    def default_next_action(self, path: str) -> str:
        return {
            DIRECT: "answer_directly",
            FUNCTION: "create_function_brief",
            TASK: "create_task_request",
            ENTITY: "start_entity_wizard",
        }.get(path, "answer_directly")

    def default_reason(self, path: str) -> str:
        return {
            DIRECT: "This appears best handled as a direct answer.",
            FUNCTION: "This appears best handled as reusable code/functionality.",
            TASK: "This appears best handled as a finite multi-step task.",
            ENTITY: "This appears best handled as a long-term specialist/Draft Entity.",
        }.get(path, "")

    def route_risk(self, rec: Gear4Recommendation) -> str:
        if rec.path == DIRECT:
            return "SAFE"
        if rec.path in {FUNCTION, TASK, ENTITY}:
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
        plan += ["Analysera möjliga vägar", "Sammanfatta rekommendation och nästa steg"]
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

    def frank_question(self, rec: Gear4Recommendation, artifact: Gear4Artifact) -> str:
        if rec.path == ENTITY:
            return f"Jag rekommenderar Draft Entity: **{rec.entity_name or 'specialist'}**. Vill du starta Entity Wizard?"
        if rec.path == FUNCTION:
            return "Jag rekommenderar en återanvändbar funktion/modul. Vill du att vi skriver implementationen?"
        if rec.path == TASK:
            return "Jag rekommenderar ett strukturerat task. Vill du att Gear 4 skapar/kör uppdraget?"
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

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
    return conductor.process_goal(goal, context=context)


def route_goal(goal: str, context: Optional[str] = None, entity_id: str = "zero") -> Gear4Result:
    return process_goal(goal, context=context, entity_id=entity_id, dry_run=True)


def status(entity_id: str = "zero") -> str:
    return f"Gear 4 v{VERSION} — conductor ready — entity={entity_id} — root={ZERO_ROOT}"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=f"ZeroPointAI Gear 4 Conductor v{VERSION}")
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
            "Skriv en funktion som skapar specs för alla viktiga moduler",
            "Analysera varför Firepower-flippern inte svarar",
            "Skapa en Master Trader Assistant som lär sig över tid",
        ]
        conductor = Gear4Conductor(Gear4Config(entity_id=args.entity, dry_run=True))
        ok = True
        for goal in goals:
            result = conductor.process_goal(goal)
            print("=" * 80)
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
