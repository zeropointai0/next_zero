#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_gear4.py — ZeroPointAI Gear 4 Autonomous Runner v0.1

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Minimal read-only Gear 4-loop: Plan → Anchor → Risk → Act → Observe → Checkpoint
ZERO_DEPENDS:   foundation.py, zero_task.py, zero_checkpoint.py, zero_identity_anchor.py, zero_perspective.py
ZERO_USED_BY:   zero_night.py, minna_entity.py, zero_web_server.py

Filosofi:
    Gear 4 är inte "AI som bara kör".
    Gear 4 är ett kontrollerat autonomt tillstånd.

    Varje steg:
        1. Plan / current step
        2. Quick/Medium/Deep Anchor
        3. Risk Check FÖRE Act
        4. Act
        5. Observe
        6. Checkpoint
        7. Continue / Pause / Abort

    Denna v0.1 är medvetet konservativ:
        - SAFE/read-only tools körs direkt.
        - CAUTION kräver allow_writes=True.
        - HIGH/CRITICAL kräver explicit approval_callback.
        - FORBIDDEN körs aldrig.
        - Bash är förbjudet i denna version.
        - Extern kommunikation är blockerad i denna version.

    Målet är att bevisa loop, state, checkpoints och koherens innan riktig autonomi.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> None:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Root / imports
# ─────────────────────────────────────────────────────────────────────────────

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except Exception:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

ZERO_ROOT = Path(ZERO_ROOT)
load_dotenv(ZERO_ROOT / ".env")

GEAR4_DIR = ZERO_ROOT / "data" / "gear4"
GEAR4_DIR.mkdir(parents=True, exist_ok=True)


# Existing Zero modules.
# These imports are deliberately fault-tolerant so this file can be compared
# standalone against Claude/Grok versions before everything is wired in.

try:
    from app.zero_task import Task, TaskManager
except Exception:
    Task = Any  # type: ignore

    class TaskManager:  # degraded fallback
        def __init__(self, entity_id: str = "zero"):
            self.entity_id = entity_id
            self._tasks: Dict[str, Any] = {}

        def create_task(self, goal: str, plan: List[str], risk_level: str = "SAFE"):
            task = SimpleTask(entity_id=self.entity_id, goal=goal, plan=plan, risk_level=risk_level)
            self._tasks[task.task_id] = task
            return task

        def approve(self, task_id: str, by: str = "Frank") -> bool:
            self._tasks[task_id].status = "approved"
            return True

        def start(self, task_id: str) -> bool:
            self._tasks[task_id].status = "running"
            return True

        def pause(self, task_id: str, reason: str = "") -> bool:
            self._tasks[task_id].status = "paused"
            self._tasks[task_id].error = reason
            return True

        def block(self, task_id: str, reason: str = "") -> bool:
            self._tasks[task_id].status = "blocked"
            self._tasks[task_id].error = reason
            return True

        def complete(self, task_id: str, result: str = "") -> bool:
            self._tasks[task_id].status = "complete"
            self._tasks[task_id].result = result
            return True

        def abort(self, task_id: str, reason: str = "") -> bool:
            self._tasks[task_id].status = "aborted"
            self._tasks[task_id].error = reason
            return True

try:
    from app.zero_checkpoint import save_checkpoint, rollback_task
except Exception:
    def save_checkpoint(**kwargs: Any) -> Any:
        return kwargs

    def rollback_task(task_id: str, target_step: Optional[int] = None, entity_id: str = "zero") -> bool:
        return False

try:
    from app.zero_identity_anchor import IdentityAnchor
except Exception:
    class IdentityAnchor:
        def __init__(self, entity_id: str = "zero"):
            self.entity_id = entity_id

        def check(self, **kwargs: Any):
            return AnchorLike(action="continue", coherence_score=1.0, reason="degraded anchor")

        def force_deep(self, **kwargs: Any):
            return AnchorLike(action="continue", coherence_score=1.0, reason="degraded deep anchor")

        def format_summary(self) -> str:
            return "IdentityAnchor degraded mode"

try:
    from app.zero_perspective import summarize_perspectives, add_perspective
except Exception:
    def summarize_perspectives(subject: str, domain: str = "", entity_id: str = "zero") -> str:
        return f"Inga perspektiv tillgängliga i degraded mode för: {subject}"

    def add_perspective(**kwargs: Any) -> Any:
        return kwargs


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SAFE = "SAFE"
CAUTION = "CAUTION"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
FORBIDDEN = "FORBIDDEN"

CONTINUE = "continue"
WARN = "warn"
PAUSE = "pause"
ABORT = "abort"
BLOCK = "block"

VALID_RISK_LEVELS = {SAFE, CAUTION, HIGH, CRITICAL, FORBIDDEN}

READ_ONLY_TOOLS = {
    "noop",
    "note",
    "read_file",
    "list_dir",
    "search_stone",
    "summarize_perspectives",
    "status",
}

CAUTION_TOOLS = {
    "add_perspective",
    "write_note",
    "write_file",
    "modify_stone",
}

HIGH_TOOLS = {
    "send_mail",
    "post_forum",
    "web_post",
    "external_message",
}

CRITICAL_TOOLS = {
    "delete_file",
    "system_change",
    "external_transaction",
}

FORBIDDEN_PATTERNS = [
    r"\brm\s+-rf\s+/",
    r"\bDROP\s+DATABASE\b",
    r"\bfork\s*bomb\b",
    r":\(\)\s*\{\s*:\|:",
    r"\bmkfs\b",
    r"\bdd\s+if=",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnchorLike:
    """Small fallback object matching IdentityAnchor events enough for Gear 4."""
    action: str = CONTINUE
    coherence_score: float = 1.0
    reason: str = ""
    layer0_alignment: float = 1.0
    mission_alignment: float = 1.0
    entity_alignment: float = 1.0
    anchor_level: str = "none"


@dataclass
class SimpleTask:
    """
    Fallback task used only if zero_task.py is unavailable.
    The real system should use app.zero_task.Task.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str = "zero"
    status: str = "draft"
    goal: str = ""
    plan: List[str] = field(default_factory=list)
    current_step: int = 0
    result: str = ""
    error: str = ""
    risk_level: str = SAFE


@dataclass
class Gear4Step:
    """
    Ett körbart steg i Gear 4.

    tool:
        noop                    gör inget, bara observation
        note                    sparar observation i rapporten
        read_file               läser textfil under allowed_roots
        list_dir                listar katalog under allowed_roots
        search_stone            enkel STONE-sökning
        summarize_perspectives  hämtar perspektivsammanfattning
        add_perspective         CAUTION, blockad om allow_writes=False

    args:
        read_file: {"path": "..."}
        list_dir: {"path": "...", "limit": 50}
        search_stone: {"query": "...", "limit": 5}
        summarize_perspectives: {"subject": "...", "domain": ""}
        add_perspective: {"domain": "...", "subject": "...", "claim": "...", "source_type": "...", "confidence": 0.5}
    """
    description: str
    tool: str = "noop"
    args: Dict[str, Any] = field(default_factory=dict)
    risk_level: Optional[str] = None

    @classmethod
    def from_any(cls, value: Any) -> "Gear4Step":
        if isinstance(value, Gear4Step):
            return value
        if isinstance(value, str):
            return cls(description=value, tool="note", args={"text": value})
        if isinstance(value, dict):
            return cls(
                description=str(value.get("description") or value.get("desc") or value.get("tool") or "Unnamed step"),
                tool=str(value.get("tool", "noop")),
                args=dict(value.get("args", {})),
                risk_level=value.get("risk_level"),
            )
        raise TypeError(f"Cannot convert to Gear4Step: {type(value)!r}")


@dataclass
class Gear4Config:
    entity_id: str = "zero"
    allow_writes: bool = False
    require_approval_for_high: bool = True
    max_steps: int = 50
    step_delay_seconds: float = 0.0
    allowed_roots: List[str] = field(default_factory=lambda: [
        str(ZERO_ROOT / "docs"),
        str(ZERO_ROOT / "app"),
        str(ZERO_ROOT / "runtime"),
        str(ZERO_ROOT / "data"),
    ])
    constitution_text: Optional[str] = None
    stop_on_warn: bool = False
    auto_approve_safe_tasks: bool = True


@dataclass
class Gear4StepResult:
    step_number: int
    description: str
    tool: str
    risk_level: str
    ok: bool
    observation: str = ""
    error: str = ""
    anchor_action: str = CONTINUE
    anchor_score: float = 1.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Gear4RunResult:
    task_id: str
    entity_id: str
    goal: str
    status: str
    steps: List[Gear4StepResult] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "complete"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format(self) -> str:
        lines = [
            f"Gear 4 run: {self.status.upper()}",
            f"Task: {self.task_id[:8]}",
            f"Entity: {self.entity_id}",
            f"Goal: {self.goal}",
            "",
            "Steps:",
        ]
        for s in self.steps:
            mark = "✓" if s.ok else "✗"
            lines.append(
                f"  {mark} {s.step_number:02d}. {s.description} "
                f"[{s.tool}/{s.risk_level}] "
                f"anchor={s.anchor_action}:{s.anchor_score:.2f}"
            )
            if s.error:
                lines.append(f"      error: {s.error[:160]}")
            elif s.observation:
                lines.append(f"      obs: {s.observation[:160]}")
        if self.summary:
            lines.extend(["", "Summary:", self.summary])
        if self.error:
            lines.extend(["", "Error:", self.error])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Risk policy
# ─────────────────────────────────────────────────────────────────────────────

class Gear4RiskPolicy:
    """
    Minimal lokal risk-policy.

    Om app.zero_risk_policy finns senare kan Gear4Runner bytas till den.
    Den här versionen är explicit och konservativ.
    """

    def classify(self, tool: str, args: Optional[Dict[str, Any]] = None, text: str = "") -> str:
        tool = (tool or "noop").strip().lower()
        args = args or {}
        scan = f"{tool} {text} {json.dumps(args, ensure_ascii=False, default=str)}"

        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, scan, flags=re.IGNORECASE):
                return FORBIDDEN

        if tool in READ_ONLY_TOOLS:
            return SAFE
        if tool in CAUTION_TOOLS:
            return CAUTION
        if tool in HIGH_TOOLS:
            return HIGH
        if tool in CRITICAL_TOOLS:
            return CRITICAL

        # Unknown tool = HIGH by default. Unknown autonomy is not safe.
        return HIGH

    def allowed(
        self,
        risk_level: str,
        config: Gear4Config,
        approval_callback: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None,
        tool: str = "",
        args: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        args = args or {}
        risk_level = risk_level.upper()

        if risk_level == FORBIDDEN:
            return False, "FORBIDDEN operation blocked permanently."

        if risk_level == SAFE:
            return True, "SAFE operation allowed."

        if risk_level == CAUTION:
            if config.allow_writes:
                return True, "CAUTION operation allowed because allow_writes=True."
            return False, "CAUTION operation blocked: Gear 4 is in read-only mode."

        if risk_level in {HIGH, CRITICAL}:
            if approval_callback:
                approved = approval_callback(risk_level, tool, args)
                if approved:
                    return True, f"{risk_level} operation approved by callback."
            return False, f"{risk_level} operation requires explicit Frank approval."

        return False, f"Unknown risk level: {risk_level}"


# ─────────────────────────────────────────────────────────────────────────────
# Interrupt file
# ─────────────────────────────────────────────────────────────────────────────

class Gear4Interrupt:
    """
    Enkel interrupt-kanal via JSON-fil.

    Fil:
        /opt/zeropointai/data/gear4/interrupt_<entity>.json

    Exempel:
        {"command": "pause", "reason": "Frank asked"}
        {"command": "abort", "reason": "wrong direction"}
        {"command": "stop", "reason": "manual stop"}

    Efter läsning raderas filen.
    """

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.path = GEAR4_DIR / f"interrupt_{entity_id}.json"

    def check(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.path.unlink(missing_ok=True)
            if not isinstance(data, dict):
                return {"command": "pause", "reason": "Invalid interrupt payload"}
            return data
        except Exception as e:
            return {"command": "pause", "reason": f"Interrupt read failed: {e}"}

    def write(self, command: str, reason: str = "") -> None:
        self.path.write_text(
            json.dumps(
                {
                    "command": command,
                    "reason": reason,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

class Gear4Tools:
    """Read-only tool executor for Gear 4 v0.1."""

    def __init__(self, config: Gear4Config):
        self.config = config

    def execute(self, step: Gear4Step) -> str:
        tool = step.tool.strip().lower()
        args = step.args or {}

        if tool == "noop":
            return "No operation executed."

        if tool == "note":
            return str(args.get("text") or step.description)

        if tool == "status":
            return "Gear 4 is running."

        if tool == "read_file":
            return self._read_file(str(args.get("path", "")))

        if tool == "list_dir":
            return self._list_dir(
                path=str(args.get("path", "")),
                limit=int(args.get("limit", 50)),
            )

        if tool == "search_stone":
            return self._search_stone(
                query=str(args.get("query", "")),
                limit=int(args.get("limit", 5)),
            )

        if tool == "summarize_perspectives":
            return summarize_perspectives(
                subject=str(args.get("subject", "")),
                domain=str(args.get("domain", "")),
                entity_id=self.config.entity_id,
            )

        if tool == "add_perspective":
            p = add_perspective(
                domain=str(args.get("domain", "general")),
                subject=str(args.get("subject", "")),
                claim=str(args.get("claim", "")),
                source_type=str(args.get("source_type", "zero_inference")),
                confidence=float(args.get("confidence", 0.5)),
                entity_id=self.config.entity_id,
                source_detail=str(args.get("source_detail", "")),
            )
            return f"Perspective added: {p}"

        raise RuntimeError(f"Unknown or unsupported Gear 4 tool: {tool}")

    # ── Safe filesystem ──────────────────────────────────────────────────────

    def _resolve_safe_path(self, raw_path: str) -> Path:
        if not raw_path:
            raise ValueError("Missing path")

        p = Path(raw_path)
        if not p.is_absolute():
            p = ZERO_ROOT / p
        p = p.resolve()

        allowed = [Path(x).resolve() for x in self.config.allowed_roots]
        if not any(str(p).startswith(str(root)) for root in allowed):
            raise PermissionError(
                f"Path outside allowed_roots: {p}. Allowed: {', '.join(map(str, allowed))}"
            )
        return p

    def _read_file(self, path: str) -> str:
        p = self._resolve_safe_path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if not p.is_file():
            raise IsADirectoryError(str(p))
        if p.stat().st_size > 2_000_000:
            raise ValueError(f"File too large for read-only Gear 4 v0.1: {p.stat().st_size} bytes")

        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 12000:
            return text[:12000] + "\n\n[TRUNCATED by Gear 4 read_file]"
        return text

    def _list_dir(self, path: str, limit: int = 50) -> str:
        p = self._resolve_safe_path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if not p.is_dir():
            raise NotADirectoryError(str(p))

        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:limit]
        lines = [f"Directory listing: {p}"]
        for item in items:
            kind = "dir " if item.is_dir() else "file"
            lines.append(f"  {kind}  {item.name}")
        return "\n".join(lines)

    # ── STONE read-only search ───────────────────────────────────────────────

    def _search_stone(self, query: str, limit: int = 5) -> str:
        if not query.strip():
            return "STONE search skipped: empty query."

        try:
            from app.drm_memory import execute_query
        except Exception as e:
            return f"STONE search unavailable: {e}"

        like = f"%{query[:120]}%"
        try:
            rows = execute_query(
                """
                SELECT role, source, content, created_at
                FROM memories
                WHERE content ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (like, limit),
            )
        except TypeError:
            # Some execute_query wrappers may not support params.
            safe = query[:120].replace("'", "''")
            rows = execute_query(
                f"""
                SELECT role, source, content, created_at
                FROM memories
                WHERE content ILIKE '%{safe}%'
                ORDER BY created_at DESC
                LIMIT {int(limit)}
                """
            )
        except Exception as e:
            return f"STONE search failed: {e}"

        if not rows:
            return f"No STONE memories matched: {query}"

        lines = [f"STONE search results for '{query}':"]
        for i, row in enumerate(rows, 1):
            content = str(row.get("content", "") if isinstance(row, dict) else row)
            source = str(row.get("source", "") if isinstance(row, dict) else "")
            created = str(row.get("created_at", "") if isinstance(row, dict) else "")
            lines.append(f"\n{i}. source={source} created={created}")
            lines.append(content[:600])
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Gear 4 Runner
# ─────────────────────────────────────────────────────────────────────────────

class Gear4Runner:
    """
    Minimal Gear 4 runner.

    This class owns the loop. It does not own:
        - provider/model selection
        - long-form reasoning generation
        - unsafe tool execution
        - external communication

    It is deliberately boring and auditable.
    """

    def __init__(
        self,
        config: Optional[Gear4Config] = None,
        approval_callback: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None,
    ):
        self.config = config or Gear4Config()
        self.entity_id = self.config.entity_id
        self.task_manager = TaskManager(entity_id=self.entity_id)
        self.anchor = IdentityAnchor(entity_id=self.entity_id)
        self.risk_policy = Gear4RiskPolicy()
        self.tools = Gear4Tools(self.config)
        self.interrupt = Gear4Interrupt(self.entity_id)
        self.approval_callback = approval_callback

    # ── Public API ───────────────────────────────────────────────────────────

    def create_task(
        self,
        goal: str,
        plan: Iterable[Any],
        risk_level: str = SAFE,
        approve: Optional[bool] = None,
    ) -> Any:
        """
        Create a Gear 4 task.

        plan may be:
            - list[str]
            - list[dict]
            - list[Gear4Step]

        zero_task.py currently stores string descriptions.
        Gear4Runner keeps the richer executable plan in task context/checkpoints.
        """
        steps = [Gear4Step.from_any(p) for p in plan]
        overall_risk = self._max_risk([self._classify_step(s) for s in steps] + [risk_level])

        task = self.task_manager.create_task(
            goal=goal,
            plan=[self._step_to_plan_text(s) for s in steps],
            risk_level=overall_risk,
        )

        # Attach runtime-only rich plan if possible.
        try:
            task.gear4_plan = [asdict(s) for s in steps]
        except Exception:
            pass

        should_approve = self.config.auto_approve_safe_tasks if approve is None else approve
        if should_approve and overall_risk == SAFE:
            self.task_manager.approve(task.task_id, by="Gear4Runner:auto-safe")

        self._persist_run_plan(task.task_id, goal, steps, overall_risk)
        return task

    def run(
        self,
        goal: str,
        plan: Iterable[Any],
        entity_id: Optional[str] = None,
        risk_level: str = SAFE,
        approve: Optional[bool] = None,
    ) -> Gear4RunResult:
        """
        Create and execute a task.

        This is the easiest API for tests:
            run_gear4("Research Firepower", [{"tool": "search_stone", ...}])
        """
        if entity_id and entity_id != self.entity_id:
            cfg = asdict(self.config)
            cfg["entity_id"] = entity_id
            return Gear4Runner(Gear4Config(**cfg), self.approval_callback).run(
                goal=goal, plan=plan, risk_level=risk_level, approve=approve
            )

        steps = [Gear4Step.from_any(p) for p in plan]
        task = self.create_task(goal=goal, plan=steps, risk_level=risk_level, approve=approve)
        return self.run_task(task.task_id, steps=steps)

    def run_task(
        self,
        task_id: str,
        steps: Optional[List[Gear4Step]] = None,
    ) -> Gear4RunResult:
        """Run an existing task by task_id."""
        task = self.task_manager.get_task(task_id) if hasattr(self.task_manager, "get_task") else None
        if not task:
            return Gear4RunResult(
                task_id=task_id,
                entity_id=self.entity_id,
                goal="",
                status="aborted",
                error=f"Task not found: {task_id}",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        if steps is None:
            steps = self._load_run_plan(task_id)
            if not steps:
                steps = self._steps_from_task(task)

        result = Gear4RunResult(
            task_id=task_id,
            entity_id=self.entity_id,
            goal=str(getattr(task, "goal", "")),
            status="running",
        )

        # Only approved tasks may run.
        status = str(getattr(task, "status", "draft"))
        if status == "draft":
            if self.config.auto_approve_safe_tasks and self._max_risk([self._classify_step(s) for s in steps]) == SAFE:
                self.task_manager.approve(task_id, by="Gear4Runner:auto-safe")
            else:
                self.task_manager.block(task_id, "Task is draft and requires Frank approval")
                result.status = "blocked"
                result.error = "Task requires approval before Gear 4 can run."
                result.completed_at = datetime.now(timezone.utc).isoformat()
                return result

        if str(getattr(task, "status", "")) == "approved":
            self.task_manager.start(task_id)

        # Deep anchor at start.
        start_anchor = self.anchor.force_deep(
            current_state=self._current_state(task, 0, "Starting Gear 4 task"),
            current_action="Start Gear 4 task",
            task_goal=str(getattr(task, "goal", "")),
            step=0,
            task_id=task_id,
            constitution_text=self.config.constitution_text,
        )
        if start_anchor.action in {PAUSE, ABORT}:
            return self._handle_anchor_stop(result, task_id, start_anchor, "start")

        # Main loop.
        for idx, step in enumerate(steps):
            if idx >= self.config.max_steps:
                result.status = "paused"
                result.error = f"Max steps reached: {self.config.max_steps}"
                self.task_manager.pause(task_id, result.error)
                break

            interrupt = self.interrupt.check()
            if interrupt:
                action = str(interrupt.get("command", "")).lower()
                reason = str(interrupt.get("reason", ""))
                if action in {"pause", "stop"}:
                    result.status = "paused"
                    result.error = f"Interrupted: {action}. {reason}"
                    self.task_manager.pause(task_id, result.error)
                    self._checkpoint(task, idx, step, result.error, "Paused by interrupt", start_anchor, result)
                    break
                if action == "abort":
                    result.status = "aborted"
                    result.error = f"Aborted by interrupt. {reason}"
                    rollback_task(task_id, entity_id=self.entity_id)
                    self.task_manager.abort(task_id, result.error)
                    break

            step_result = self._run_step(task, idx, step)
            result.steps.append(step_result)

            # Update task pointer opportunistically.
            try:
                task.current_step = idx + 1
            except Exception:
                pass

            if not step_result.ok:
                if result.status not in {"paused", "aborted", "blocked"}:
                    result.status = "paused"
                result.error = step_result.error
                break

            if step_result.anchor_action == WARN and self.config.stop_on_warn:
                result.status = "paused"
                result.error = "Paused because stop_on_warn=True and anchor warned."
                self.task_manager.pause(task_id, result.error)
                break

            if self.config.step_delay_seconds > 0:
                time.sleep(self.config.step_delay_seconds)

        else:
            # Deep anchor at completion.
            final_anchor = self.anchor.force_deep(
                current_state=self._current_state(task, len(steps), "Completing Gear 4 task"),
                current_action="Complete Gear 4 task and summarize observations",
                task_goal=str(getattr(task, "goal", "")),
                step=len(steps),
                task_id=task_id,
                constitution_text=self.config.constitution_text,
            )

            if final_anchor.action in {PAUSE, ABORT}:
                return self._handle_anchor_stop(result, task_id, final_anchor, "final")

            result.status = "complete"
            result.summary = self._summarize_run(result)
            self.task_manager.complete(task_id, result.summary)

        if result.status == "running":
            # If loop broke without setting terminal-ish status.
            result.status = "paused"
            self.task_manager.pause(task_id, result.error or "Paused without explicit reason")

        result.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_run_result(result)
        return result

    def pause(self, reason: str = "manual pause") -> None:
        self.interrupt.write("pause", reason)

    def abort(self, reason: str = "manual abort") -> None:
        self.interrupt.write("abort", reason)

    def status(self) -> str:
        active = []
        if hasattr(self.task_manager, "get_active_tasks"):
            active = self.task_manager.get_active_tasks()
        lines = [f"Gear 4 status ({self.entity_id})"]
        lines.append(f"Active tasks: {len(active)}")
        for t in active:
            lines.append(
                f"  {getattr(t, 'task_id', '')[:8]} "
                f"{getattr(t, 'status', '')} "
                f"step={getattr(t, 'current_step', 0)} "
                f"goal={getattr(t, 'goal', '')[:70]}"
            )
        try:
            lines.append("")
            lines.append(self.anchor.format_summary())
        except Exception:
            pass
        return "\n".join(lines)

    # ── Step loop internals ──────────────────────────────────────────────────

    def _run_step(self, task: Any, idx: int, step: Gear4Step) -> Gear4StepResult:
        task_id = str(getattr(task, "task_id", ""))
        goal = str(getattr(task, "goal", ""))
        risk_level = step.risk_level or self._classify_step(step)

        # 1. Anchor BEFORE risk/action.
        anchor_event = self.anchor.check(
            step=idx,
            current_state=self._current_state(task, idx, f"Preparing step: {step.description}"),
            current_action=self._current_action(step),
            task_goal=goal,
            task_id=task_id,
            risk_level=risk_level,
            constitution_text=self.config.constitution_text,
        )

        if anchor_event.action in {PAUSE, ABORT}:
            obs = f"Anchor stopped step before Act: {anchor_event.reason}"
            self._checkpoint(task, idx, step, obs, step.description, anchor_event, None)

            if anchor_event.action == ABORT:
                rollback_task(task_id, entity_id=self.entity_id)
                self.task_manager.abort(task_id, obs)
            else:
                self.task_manager.pause(task_id, obs)

            return Gear4StepResult(
                step_number=idx,
                description=step.description,
                tool=step.tool,
                risk_level=risk_level,
                ok=False,
                error=obs,
                anchor_action=anchor_event.action,
                anchor_score=anchor_event.coherence_score,
            )

        # 2. Risk check BEFORE Act.
        allowed, risk_reason = self.risk_policy.allowed(
            risk_level=risk_level,
            config=self.config,
            approval_callback=self.approval_callback,
            tool=step.tool,
            args=step.args,
        )

        if not allowed:
            self.task_manager.block(task_id, risk_reason)
            self._checkpoint(task, idx, step, risk_reason, "Blocked by risk policy", anchor_event, None)
            return Gear4StepResult(
                step_number=idx,
                description=step.description,
                tool=step.tool,
                risk_level=risk_level,
                ok=False,
                error=risk_reason,
                anchor_action=anchor_event.action,
                anchor_score=anchor_event.coherence_score,
            )

        # 3. Act.
        started = datetime.now(timezone.utc).isoformat()
        try:
            observation = self.tools.execute(step)
            ok = True
            error = ""
        except Exception as e:
            observation = ""
            error = f"{type(e).__name__}: {e}"
            ok = False

        completed = datetime.now(timezone.utc).isoformat()

        # 4. Observe + checkpoint.
        obs_text = observation if ok else error
        next_step = self._next_step_text(task, idx)
        self._checkpoint(task, idx, step, obs_text, next_step, anchor_event, None)

        if not ok:
            self.task_manager.pause(task_id, error)

        return Gear4StepResult(
            step_number=idx,
            description=step.description,
            tool=step.tool,
            risk_level=risk_level,
            ok=ok,
            observation=observation,
            error=error,
            anchor_action=anchor_event.action,
            anchor_score=anchor_event.coherence_score,
            started_at=started,
            completed_at=completed,
        )

    def _checkpoint(
        self,
        task: Any,
        idx: int,
        step: Gear4Step,
        observation: str,
        next_step: str,
        anchor_event: Any,
        run_result: Optional[Gear4RunResult],
    ) -> None:
        task_id = str(getattr(task, "task_id", ""))
        goal = str(getattr(task, "goal", ""))
        remaining = self._remaining_plan(task, idx + 1)

        save_checkpoint(
            task_id=task_id,
            step_number=idx,
            step_description=step.description,
            goal=goal,
            remaining_plan=remaining,
            observation=observation,
            next_step=next_step,
            coherence_score=float(getattr(anchor_event, "coherence_score", 1.0) or 1.0),
            layer0_alignment=float(getattr(anchor_event, "layer0_alignment", 1.0) or 1.0),
            mission_alignment=float(getattr(anchor_event, "mission_alignment", 1.0) or 1.0),
            entity_alignment=float(getattr(anchor_event, "entity_alignment", 1.0) or 1.0),
            entity_id=self.entity_id,
            context={
                "tool": step.tool,
                "args": step.args,
                "risk_level": step.risk_level or self._classify_step(step),
                "anchor_action": getattr(anchor_event, "action", CONTINUE),
                "anchor_reason": getattr(anchor_event, "reason", ""),
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _classify_step(self, step: Gear4Step) -> str:
        return self.risk_policy.classify(step.tool, step.args, step.description)

    def _max_risk(self, risks: Iterable[str]) -> str:
        order = {SAFE: 0, CAUTION: 1, HIGH: 2, CRITICAL: 3, FORBIDDEN: 4}
        normalized = [str(r).upper() for r in risks if str(r).upper() in order]
        if not normalized:
            return SAFE
        return max(normalized, key=lambda r: order[r])

    def _step_to_plan_text(self, step: Gear4Step) -> str:
        return f"{step.description} [{step.tool}]"

    def _current_state(self, task: Any, step: int, note: str) -> str:
        return (
            f"Entity={self.entity_id}. "
            f"Task={str(getattr(task, 'task_id', ''))[:8]}. "
            f"Goal={getattr(task, 'goal', '')}. "
            f"Step={step}. "
            f"State={note}. "
            f"Mode=Gear4 read-only controlled autonomy."
        )

    def _current_action(self, step: Gear4Step) -> str:
        return f"Prepare to run tool={step.tool}. Description={step.description}. Args={step.args}"

    def _remaining_plan(self, task: Any, start: int) -> List[str]:
        plan = getattr(task, "plan", [])
        out: List[str] = []
        for item in list(plan)[start:]:
            if hasattr(item, "description"):
                out.append(str(item.description))
            else:
                out.append(str(item))
        return out

    def _next_step_text(self, task: Any, idx: int) -> str:
        remaining = self._remaining_plan(task, idx + 1)
        return remaining[0] if remaining else "Complete task"

    def _steps_from_task(self, task: Any) -> List[Gear4Step]:
        plan = getattr(task, "plan", [])
        steps: List[Gear4Step] = []
        for item in plan:
            if hasattr(item, "description"):
                steps.append(Gear4Step(description=str(item.description), tool="note", args={"text": str(item.description)}))
            else:
                steps.append(Gear4Step.from_any(str(item)))
        return steps

    def _persist_run_plan(self, task_id: str, goal: str, steps: List[Gear4Step], risk_level: str) -> None:
        path = GEAR4_DIR / f"plan_{task_id[:8]}.json"
        payload = {
            "task_id": task_id,
            "entity_id": self.entity_id,
            "goal": goal,
            "risk_level": risk_level,
            "steps": [asdict(s) for s in steps],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _load_run_plan(self, task_id: str) -> List[Gear4Step]:
        path = GEAR4_DIR / f"plan_{task_id[:8]}.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [Gear4Step.from_any(s) for s in payload.get("steps", [])]
        except Exception as e:
            log.warning(f"Failed to load Gear4 run plan: {e}")
            return []

    def _save_run_result(self, result: Gear4RunResult) -> None:
        path = GEAR4_DIR / f"result_{result.task_id[:8]}.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        try:
            from app.drm_memory import save_memory
            save_memory(
                role="system",
                content=(
                    f"[gear4_result] task={result.task_id[:8]} "
                    f"entity={result.entity_id} status={result.status} "
                    f"goal={result.goal[:100]}\n{result.summary[:1000]}"
                ),
                source=f"zero_gear4:{self.entity_id}",
                session_id=result.task_id,
            )
        except Exception as e:
            log.debug(f"Gear4 result STONE save failed: {e}")

    def _summarize_run(self, result: Gear4RunResult) -> str:
        ok_steps = sum(1 for s in result.steps if s.ok)
        failed = [s for s in result.steps if not s.ok]
        lines = [
            f"Gear 4 completed {ok_steps}/{len(result.steps)} steps for '{result.goal}'.",
        ]
        if failed:
            lines.append(f"Failed/blocked steps: {len(failed)}")
            for s in failed[:3]:
                lines.append(f"- step {s.step_number}: {s.error}")
        else:
            lines.append("No failed steps.")
        return "\n".join(lines)

    def _handle_anchor_stop(
        self,
        result: Gear4RunResult,
        task_id: str,
        anchor_event: Any,
        phase: str,
    ) -> Gear4RunResult:
        action = getattr(anchor_event, "action", PAUSE)
        reason = getattr(anchor_event, "reason", "")
        result.status = "aborted" if action == ABORT else "paused"
        result.error = f"Deep anchor stopped task at {phase}: {reason}"
        if action == ABORT:
            rollback_task(task_id, entity_id=self.entity_id)
            self.task_manager.abort(task_id, result.error)
        else:
            self.task_manager.pause(task_id, result.error)
        result.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_run_result(result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Public convenience API
# ─────────────────────────────────────────────────────────────────────────────

def run_gear4(
    goal: str,
    plan: Iterable[Any],
    entity_id: str = "zero",
    allow_writes: bool = False,
    max_steps: int = 50,
) -> Gear4RunResult:
    runner = Gear4Runner(
        Gear4Config(
            entity_id=entity_id,
            allow_writes=allow_writes,
            max_steps=max_steps,
        )
    )
    return runner.run(goal=goal, plan=plan)


def pause_gear4(entity_id: str = "zero", reason: str = "manual pause") -> None:
    Gear4Interrupt(entity_id).write("pause", reason)


def abort_gear4(entity_id: str = "zero", reason: str = "manual abort") -> None:
    Gear4Interrupt(entity_id).write("abort", reason)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_plan_arg(raw: str) -> List[Gear4Step]:
    """
    Parse plan from JSON string or text.

    JSON examples:
        '[{"description":"Search STONE","tool":"search_stone","args":{"query":"Firepower"}}]'

    Text fallback:
        "step one; step two; step three"
    """
    raw = raw.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [Gear4Step.from_any(x) for x in data]
        if isinstance(data, dict):
            return [Gear4Step.from_any(data)]
    except Exception:
        pass

    return [Gear4Step.from_any(part.strip()) for part in raw.split(";") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="ZeroPointAI Gear 4 Runner v0.1")
    parser.add_argument("--entity", default="zero", help="Entity ID, e.g. zero or minna")
    parser.add_argument("--goal", help="Task goal")
    parser.add_argument("--plan", help="JSON plan or semicolon-separated steps")
    parser.add_argument("--allow-writes", action="store_true", help="Allow CAUTION tools")
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--pause", metavar="REASON")
    parser.add_argument("--abort", metavar="REASON")
    parser.add_argument("--test", action="store_true", help="Run built-in safe test task")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cfg = Gear4Config(
        entity_id=args.entity,
        allow_writes=args.allow_writes,
        max_steps=args.max_steps,
    )
    runner = Gear4Runner(cfg)

    if args.status:
        print(runner.status())
        return 0

    if args.pause:
        runner.pause(args.pause)
        print(f"Pause signal written for {args.entity}: {args.pause}")
        return 0

    if args.abort:
        runner.abort(args.abort)
        print(f"Abort signal written for {args.entity}: {args.abort}")
        return 0

    if args.test:
        result = runner.run(
            goal="Test Gear 4 read-only loop",
            plan=[
                {"description": "Confirm Gear 4 is alive", "tool": "status"},
                {"description": "Summarize perspectives on Gear 4", "tool": "summarize_perspectives", "args": {"subject": "Gear 4"}},
                {"description": "List Zero docs folder", "tool": "list_dir", "args": {"path": str(ZERO_ROOT / "docs"), "limit": 20}},
            ],
        )
        print(result.format())
        return 0 if result.ok else 2

    if not args.goal or not args.plan:
        parser.error("--goal and --plan are required unless --status/--pause/--abort/--test is used")

    plan = _parse_plan_arg(args.plan)
    result = runner.run(goal=args.goal, plan=plan)
    print(result.format())
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
