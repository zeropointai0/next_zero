"""
zero_task.py — ZeroPointAI Task Management

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Uppdragstillstånd, task journal, checkpoints, rollback
ZERO_DEPENDS:   foundation.py, drm_memory.py, zero_sudo.py
ZERO_USED_BY:   zero_gear4.py, zero_interrupt.py

Filosofi:
    Ett uppdrag är inte en prompt. Det är ett levande tillstånd.
    Varje steg sparas i STONE — oberoende av git.
    Om Zero startar om mitt i ett uppdrag ska den kunna fortsätta.
    Frank bestämmer om ett pausat uppdrag ska återupptas.

Tillstånd:
    draft      → Skapad men ej godkänd
    approved   → Frank har godkänt
    running    → Körs just nu
    paused     → Pausad (manuellt eller av guardrails)
    blocked    → Väntar på Frank-input
    complete   → Klart
    reviewed   → Frank har granskat resultatet
    aborted    → Avbrutet, state rullas tillbaka

Checkpoints sparas efter varje steg med:
    - Mål och plan
    - Senaste observation
    - Nästa tänkta steg
    - Coherence score
    - Git commit hash (rollback-punkt)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

# ── Root ──────────────────────────────────────────────────────────────────────

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

load_dotenv(ZERO_ROOT / ".env")

# ── Konstanter ────────────────────────────────────────────────────────────────

VALID_STATUSES = {
    "draft", "approved", "running",
    "paused", "blocked", "complete",
    "reviewed", "aborted"
}

VALID_TRANSITIONS = {
    "draft":    {"approved", "aborted"},
    "approved": {"running", "aborted"},
    "running":  {"paused", "blocked", "complete", "aborted"},
    "paused":   {"running", "aborted"},
    "blocked":  {"running", "aborted"},
    "complete": {"reviewed"},
    "reviewed": set(),
    "aborted":  set(),
}


# ── Dataklasser ───────────────────────────────────────────────────────────────

@dataclass
class TaskStep:
    """Ett enskilt steg i ett uppdrag."""
    step_number:     int
    description:     str
    risk_level:      str = "SAFE"
    status:          str = "pending"  # pending/running/complete/failed
    result:          str = ""
    coherence_score: float = 1.0
    started_at:      Optional[str] = None
    completed_at:    Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TaskCheckpoint:
    """Sparad state efter ett steg."""
    checkpoint_id:   str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id:         str = ""
    step_number:     int = 0
    observation:     str = ""
    next_step:       str = ""
    coherence_score: float = 1.0
    layer0_alignment: float = 1.0
    mission_alignment: float = 1.0
    entity_alignment: float = 1.0
    git_commit_hash: str = ""
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Task:
    """Ett fullständigt uppdrag."""
    task_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_id:    str = "zero"
    status:       str = "draft"
    goal:         str = ""
    plan:         List[TaskStep] = field(default_factory=list)
    current_step: int = 0
    checkpoints:  List[TaskCheckpoint] = field(default_factory=list)
    result:       str = ""
    error:        str = ""
    risk_level:   str = "SAFE"
    created_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    approved_by:  str = ""
    reviewed_by:  str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["plan"] = [s.to_dict() for s in self.plan]
        d["checkpoints"] = [c.to_dict() for c in self.checkpoints]
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Task":
        d = dict(d)
        d["plan"] = [TaskStep(**s) for s in d.get("plan", [])]
        d["checkpoints"] = [TaskCheckpoint(**c) for c in d.get("checkpoints", [])]
        return cls(**d)

    @property
    def current_step_obj(self) -> Optional[TaskStep]:
        if 0 <= self.current_step < len(self.plan):
            return self.plan[self.current_step]
        return None

    @property
    def is_active(self) -> bool:
        return self.status in ("running", "paused", "blocked")

    @property
    def is_terminal(self) -> bool:
        return self.status in ("complete", "reviewed", "aborted")

    @property
    def progress_pct(self) -> float:
        if not self.plan:
            return 0.0
        return round(self.current_step / len(self.plan) * 100, 1)


# ── Task Manager ──────────────────────────────────────────────────────────────

class TaskManager:
    """
    Hanterar alla uppdrag för en entity.
    Sparar state i STONE + lokal JSON-fil som fallback.
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id = entity_id
        self._tasks: Dict[str, Task] = {}
        self._journal_file = ZERO_ROOT / "data" / "tasks" / f"{entity_id}_tasks.json"
        self._journal_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_from_file()

    # ── Persistens ────────────────────────────────────────────────────────────

    def _save_to_file(self) -> None:
        """Sparar alla tasks till JSON-fil (fallback om STONE är nere)."""
        try:
            data = {tid: t.to_dict() for tid, t in self._tasks.items()}
            tmp  = self._journal_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._journal_file)
        except Exception as e:
            log.warning(f"task journal write failed: {e}")

    def _load_from_file(self) -> None:
        """Laddar tasks från JSON-fil."""
        if not self._journal_file.exists():
            return
        try:
            data = json.loads(self._journal_file.read_text(encoding="utf-8"))
            self._tasks = {tid: Task.from_dict(t) for tid, t in data.items()}
            log.debug(f"Loaded {len(self._tasks)} tasks for {self.entity_id}")
        except Exception as e:
            log.warning(f"task journal load failed: {e}")

    def _save_to_stone(self, task: Task) -> None:
        """Sparar task till STONE."""
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[task] {task.task_id[:8]} {task.status} "
                    f"'{task.goal[:60]}' step={task.current_step}/{len(task.plan)}"
                ),
                source  = f"zero_task:{self.entity_id}",
                session_id = task.task_id,
            )
        except Exception as e:
            log.debug(f"STONE task save: {e}")

    # ── Git-snapshot ──────────────────────────────────────────────────────────

    def _git_snapshot(self, message: str) -> str:
        """Skapar git commit och returnerar hash."""
        try:
            subprocess.run(
                ["git", "add", "app/", "docs/"],
                cwd=str(ZERO_ROOT), capture_output=True, timeout=15
            )
            subprocess.run(
                ["git", "commit", "-m", f"[task] {message}"],
                cwd=str(ZERO_ROOT), capture_output=True,
                text=True, timeout=15
            )
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(ZERO_ROOT), capture_output=True,
                text=True, timeout=10
            )
            return result.stdout.strip()
        except Exception:
            return ""

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_task(
        self,
        goal:      str,
        plan:      List[str],
        risk_level: str = "SAFE",
    ) -> Task:
        """Skapar ett nytt uppdrag i draft-status."""
        steps = [
            TaskStep(step_number=i, description=step)
            for i, step in enumerate(plan)
        ]
        task = Task(
            entity_id  = self.entity_id,
            goal       = goal,
            plan       = steps,
            risk_level = risk_level,
        )
        self._tasks[task.task_id] = task
        self._save_to_file()
        log.info(f"Task created: {task.task_id[:8]} '{goal[:40]}'")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_active_tasks(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.is_active]

    def get_pending_review(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == "complete"]

    # ── Tillståndsövergångar ──────────────────────────────────────────────────

    def transition(
        self,
        task_id:   str,
        new_status: str,
        by:        str = "system",
        note:      str = "",
    ) -> bool:
        """Övergång till nytt tillstånd. Validerar tillåtna övergångar."""
        task = self._tasks.get(task_id)
        if not task:
            log.warning(f"transition: task {task_id[:8]} not found")
            return False

        allowed = VALID_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            log.warning(
                f"transition: {task.status} → {new_status} not allowed "
                f"(allowed: {allowed})"
            )
            return False

        old_status = task.status
        task.status = new_status
        task.updated_at = datetime.now(timezone.utc).isoformat()

        if new_status == "approved":
            task.approved_by = by
        elif new_status == "reviewed":
            task.reviewed_by = by
        elif new_status == "complete":
            task.completed_at = datetime.now(timezone.utc).isoformat()

        self._save_to_file()
        self._save_to_stone(task)
        log.info(
            f"Task {task_id[:8]}: {old_status} → {new_status} "
            f"(by={by}, note={note[:40]})"
        )
        return True

    def approve(self, task_id: str, by: str = "Frank") -> bool:
        return self.transition(task_id, "approved", by=by)

    def start(self, task_id: str) -> bool:
        return self.transition(task_id, "running", by="zero")

    def pause(self, task_id: str, reason: str = "") -> bool:
        return self.transition(task_id, "paused", note=reason)

    def block(self, task_id: str, reason: str = "") -> bool:
        """Blockeras — väntar på Frank-input."""
        task = self._tasks.get(task_id)
        if task:
            task.error = reason
        return self.transition(task_id, "blocked", note=reason)

    def complete(self, task_id: str, result: str = "") -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.result = result
        return self.transition(task_id, "complete")

    def abort(self, task_id: str, reason: str = "") -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.error = reason
        return self.transition(task_id, "aborted", note=reason)

    # ── Steg-hantering ────────────────────────────────────────────────────────

    def advance_step(
        self,
        task_id:         str,
        observation:     str,
        next_step_desc:  str = "",
        coherence_score: float = 1.0,
        layer0_alignment: float = 1.0,
        mission_alignment: float = 1.0,
        entity_alignment: float = 1.0,
    ) -> Optional[TaskCheckpoint]:
        """
        Markerar nuvarande steg som klart och sparar checkpoint.
        Returnerar checkpoint-objektet.
        """
        task = self._tasks.get(task_id)
        if not task or task.status != "running":
            return None

        # Markera nuvarande steg som klart
        current = task.current_step_obj
        if current:
            current.status       = "complete"
            current.result       = observation
            current.coherence_score = coherence_score
            current.completed_at = datetime.now(timezone.utc).isoformat()

        # Spara checkpoint
        git_hash = self._git_snapshot(
            f"step {task.current_step} of {len(task.plan)} "
            f"task {task_id[:8]}"
        )

        checkpoint = TaskCheckpoint(
            task_id           = task_id,
            step_number       = task.current_step,
            observation       = observation,
            next_step         = next_step_desc,
            coherence_score   = coherence_score,
            layer0_alignment  = layer0_alignment,
            mission_alignment = mission_alignment,
            entity_alignment  = entity_alignment,
            git_commit_hash   = git_hash,
        )
        task.checkpoints.append(checkpoint)

        # Gå till nästa steg
        task.current_step += 1
        task.updated_at = datetime.now(timezone.utc).isoformat()

        # Om alla steg klara → complete
        if task.current_step >= len(task.plan):
            self.complete(task_id, result=observation)

        self._save_to_file()
        self._save_to_stone(task)

        log.info(
            f"Task {task_id[:8]} step {task.current_step-1} complete "
            f"coherence={coherence_score:.2f} git={git_hash}"
        )
        return checkpoint

    def mark_step_failed(
        self,
        task_id: str,
        error:   str,
    ) -> None:
        """Markerar nuvarande steg som misslyckat."""
        task = self._tasks.get(task_id)
        if not task:
            return
        current = task.current_step_obj
        if current:
            current.status = "failed"
            current.result = error
        task.error      = error
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_to_file()

    # ── Återupptagning ────────────────────────────────────────────────────────

    def get_resumable_tasks(self) -> List[Task]:
        """
        Returnerar pausade/blockerade tasks som kan återupptas.
        Frank bestämmer om de ska återupptas.
        """
        return [
            t for t in self._tasks.values()
            if t.status in ("paused", "blocked")
        ]

    def get_last_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        task = self._tasks.get(task_id)
        if not task or not task.checkpoints:
            return None
        return task.checkpoints[-1]

    # ── Rapportering ──────────────────────────────────────────────────────────

    def format_status(self, task_id: str) -> str:
        """Formaterar task-status för presentation till Frank."""
        task = self._tasks.get(task_id)
        if not task:
            return f"Task {task_id[:8]} hittades inte."

        lines = [
            f"📋 Uppdrag: {task.task_id[:8]}",
            f"   Status:  {task.status.upper()}",
            f"   Mål:     {task.goal[:60]}",
            f"   Framsteg: {task.current_step}/{len(task.plan)} steg "
            f"({task.progress_pct}%)",
            f"   Risk:    {task.risk_level}",
        ]

        current = task.current_step_obj
        if current:
            lines.append(f"   Steg:    {current.description[:60]}")

        if task.checkpoints:
            last = task.checkpoints[-1]
            lines.append(
                f"   Koherens: {last.coherence_score:.2f} "
                f"(L0={last.layer0_alignment:.2f})"
            )

        if task.error:
            lines.append(f"   ⚠️  Fel: {task.error[:60]}")

        if task.result:
            lines.append(f"   ✓ Resultat: {task.result[:80]}")

        return "\n".join(lines)

    def format_all_active(self) -> str:
        """Formaterar alla aktiva tasks."""
        active = self.get_active_tasks()
        if not active:
            return "Inga aktiva uppdrag."
        return "\n\n".join(self.format_status(t.task_id) for t in active)


# ── Global instans per entity ─────────────────────────────────────────────────

_managers: Dict[str, TaskManager] = {}


def get_task_manager(entity_id: str = "zero") -> TaskManager:
    """Returnerar (eller skapar) TaskManager för en entity."""
    if entity_id not in _managers:
        _managers[entity_id] = TaskManager(entity_id)
    return _managers[entity_id]


# ── Publikt API ───────────────────────────────────────────────────────────────

def create_task(
    goal:       str,
    plan:       List[str],
    entity_id:  str = "zero",
    risk_level: str = "SAFE",
) -> Task:
    """Skapar ett nytt uppdrag."""
    return get_task_manager(entity_id).create_task(goal, plan, risk_level)


def get_task(task_id: str, entity_id: str = "zero") -> Optional[Task]:
    return get_task_manager(entity_id).get_task(task_id)


def approve_task(task_id: str, entity_id: str = "zero", by: str = "Frank") -> bool:
    return get_task_manager(entity_id).approve(task_id, by=by)


def abort_task(task_id: str, entity_id: str = "zero", reason: str = "") -> bool:
    return get_task_manager(entity_id).abort(task_id, reason=reason)


def get_active_tasks(entity_id: str = "zero") -> List[Task]:
    return get_task_manager(entity_id).get_active_tasks()


def get_resumable_tasks(entity_id: str = "zero") -> List[Task]:
    return get_task_manager(entity_id).get_resumable_tasks()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Task Manager")
    parser.add_argument("--entity",  default="zero")
    parser.add_argument("--list",    action="store_true", help="Visa aktiva uppdrag")
    parser.add_argument("--resume",  action="store_true", help="Visa uppdrag som kan återupptas")
    parser.add_argument("--approve", metavar="TASK_ID",   help="Godkänn ett uppdrag")
    parser.add_argument("--abort",   metavar="TASK_ID",   help="Avbryt ett uppdrag")
    parser.add_argument("--status",  metavar="TASK_ID",   help="Visa status för ett uppdrag")
    parser.add_argument("--test",    action="store_true", help="Kör ett test-uppdrag")
    args = parser.parse_args()

    mgr = get_task_manager(args.entity)

    if args.list:
        print(mgr.format_all_active() or "Inga aktiva uppdrag.")

    elif args.resume:
        tasks = mgr.get_resumable_tasks()
        if not tasks:
            print("Inga pausade uppdrag.")
        for t in tasks:
            print(mgr.format_status(t.task_id))

    elif args.approve:
        ok = mgr.approve(args.approve)
        print("✓ Godkänd" if ok else "✗ Misslyckades")

    elif args.abort:
        ok = mgr.abort(args.abort, reason="Manuellt avbrott av Frank")
        print("✓ Avbrutet" if ok else "✗ Misslyckades")

    elif args.status:
        print(mgr.format_status(args.status))

    elif args.test:
        # Skapa ett test-uppdrag
        print("Skapar test-uppdrag...")
        task = mgr.create_task(
            goal = "Testa task-systemet",
            plan = [
                "Steg 1: Initiera",
                "Steg 2: Kör fake-operation",
                "Steg 3: Sammanfatta",
            ],
            risk_level = "SAFE",
        )
        print(f"  Skapat: {task.task_id[:8]}")

        mgr.approve(task.task_id, by="Frank")
        mgr.start(task.task_id)
        print(f"  Status: {task.status}")

        # Simulera steg
        for i in range(3):
            cp = mgr.advance_step(
                task.task_id,
                observation     = f"Steg {i} klart",
                next_step_desc  = f"Steg {i+1}",
                coherence_score = 0.92,
                layer0_alignment = 0.95,
                mission_alignment = 0.90,
                entity_alignment  = 0.93,
            )
            if cp:
                print(f"  Checkpoint {cp.checkpoint_id}: coherence={cp.coherence_score}")

        print()
        print(mgr.format_status(task.task_id))

    else:
        parser.print_help()
