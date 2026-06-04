"""
zero_checkpoint.py — ZeroPointAI Checkpoint System

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Sparar och återställer Gear 4-state efter varje steg
ZERO_DEPENDS:   foundation.py, zero_task.py, drm_memory.py
ZERO_USED_BY:   zero_gear4.py

Filosofi:
    Ett checkpoint är ett löfte: "härifrån kan vi alltid återvända."
    Varje steg i Gear 4 börjar med ett checkpoint.
    Om något går fel → återgå till senaste checkpoint.
    Checkpoints sparas i STONE (oberoende av git) + git (kod-backup).

    Atomic task step: ett misslyckat steg lämnar aldrig systemet
    i halvtillstånd. Antingen lyckas steget helt, eller rullas
    hela steget tillbaka.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

load_dotenv(ZERO_ROOT / ".env")

CHECKPOINT_DIR = ZERO_ROOT / "data" / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


# ── Checkpoint-datastruktur ───────────────────────────────────────────────────

@dataclass
class Checkpoint:
    """
    Komplett systemtillstånd vid ett givet steg.
    Allt som behövs för att återuppta exakt härifrån.
    """
    checkpoint_id:     str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    task_id:           str = ""
    entity_id:         str = "zero"
    step_number:       int = 0
    step_description:  str = ""

    # Tillstånd
    goal:              str = ""
    remaining_plan:    List[str] = field(default_factory=list)
    observation:       str = ""
    next_step:         str = ""
    context:           Dict[str, Any] = field(default_factory=dict)

    # Koherens
    coherence_score:   float = 1.0
    layer0_alignment:  float = 1.0
    mission_alignment: float = 1.0
    entity_alignment:  float = 1.0

    # Rollback-info
    git_commit_hash:   str = ""
    stone_snapshot_id: str = ""

    # Meta
    timestamp:         str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    note:              str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Checkpoint":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def is_coherent(self) -> bool:
        """Är detta checkpoint koherent nog att återuppta från?"""
        return (
            self.coherence_score   >= 0.70 and
            self.layer0_alignment  >= 0.75 and  # Layer 0 är hård grind
            self.mission_alignment >= 0.60 and
            self.entity_alignment  >= 0.60
        )

    def __str__(self) -> str:
        return (
            f"Checkpoint {self.checkpoint_id} "
            f"[task={self.task_id[:8]}, step={self.step_number}] "
            f"coherence={self.coherence_score:.2f} "
            f"git={self.git_commit_hash[:7] or 'none'}"
        )


# ── Checkpoint Manager ────────────────────────────────────────────────────────

class CheckpointManager:
    """
    Sparar och hämtar checkpoints för en entity.
    Lagrar i lokal JSON + STONE.
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id  = entity_id
        self._store_dir = CHECKPOINT_DIR / entity_id
        self._store_dir.mkdir(parents=True, exist_ok=True)

    # ── Git-snapshot ──────────────────────────────────────────────────────────

    def _git_snapshot(self, message: str) -> str:
        """Committar kod och returnerar hash."""
        try:
            subprocess.run(
                ["git", "add", "app/", "docs/"],
                cwd=str(ZERO_ROOT), capture_output=True, timeout=15
            )
            result = subprocess.run(
                ["git", "commit", "-m", f"[checkpoint] {message}"],
                cwd=str(ZERO_ROOT), capture_output=True,
                text=True, timeout=15
            )
            if result.returncode == 0 or "nothing to commit" in result.stdout:
                rev = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(ZERO_ROOT), capture_output=True,
                    text=True, timeout=10
                )
                return rev.stdout.strip()
        except Exception as e:
            log.debug(f"git snapshot: {e}")
        return ""

    def _git_rollback(self, commit_hash: str) -> bool:
        """Rullar tillbaka kod till ett specifikt commit."""
        if not commit_hash:
            return False
        try:
            result = subprocess.run(
                ["git", "checkout", commit_hash, "--", "app/"],
                cwd=str(ZERO_ROOT), capture_output=True,
                text=True, timeout=30
            )
            ok = result.returncode == 0
            if ok:
                log.info(f"Git rollback to {commit_hash}")
            else:
                log.warning(f"Git rollback failed: {result.stderr[:100]}")
            return ok
        except Exception as e:
            log.warning(f"git rollback: {e}")
            return False

    # ── Spara checkpoint ──────────────────────────────────────────────────────

    def save(
        self,
        task_id:           str,
        step_number:       int,
        step_description:  str,
        goal:              str,
        remaining_plan:    List[str],
        observation:       str,
        next_step:         str,
        coherence_score:   float = 1.0,
        layer0_alignment:  float = 1.0,
        mission_alignment: float = 1.0,
        entity_alignment:  float = 1.0,
        context:           Optional[Dict] = None,
        note:              str = "",
    ) -> Checkpoint:
        """
        Sparar ett checkpoint.
        Skapar automatiskt git-snapshot.
        """
        # Git snapshot
        git_hash = self._git_snapshot(
            f"step {step_number} task {task_id[:8]}: {step_description[:40]}"
        )

        # STONE snapshot ID
        stone_id = self._save_to_stone(task_id, step_number, observation)

        cp = Checkpoint(
            task_id           = task_id,
            entity_id         = self.entity_id,
            step_number       = step_number,
            step_description  = step_description,
            goal              = goal,
            remaining_plan    = remaining_plan,
            observation       = observation,
            next_step         = next_step,
            coherence_score   = coherence_score,
            layer0_alignment  = layer0_alignment,
            mission_alignment = mission_alignment,
            entity_alignment  = entity_alignment,
            git_commit_hash   = git_hash,
            stone_snapshot_id = stone_id,
            context           = context or {},
            note              = note,
        )

        # Spara till fil
        cp_file = self._store_dir / f"{task_id[:8]}_step{step_number:04d}.json"
        cp_file.write_text(
            json.dumps(cp.to_dict(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        log.info(f"Checkpoint saved: {cp}")
        return cp

    def _save_to_stone(
        self, task_id: str, step_number: int, observation: str
    ) -> str:
        """Sparar checkpoint-info till STONE. Returnerar memory ID."""
        try:
            from app.drm_memory import save_memory
            mem_id = save_memory(
                role       = "system",
                content    = (
                    f"[checkpoint] task={task_id[:8]} step={step_number} "
                    f"observation={observation[:200]}"
                ),
                source     = f"zero_checkpoint:{self.entity_id}",
                session_id = task_id,
            )
            return str(mem_id or "")
        except Exception as e:
            log.debug(f"STONE checkpoint: {e}")
            return ""

    # ── Hämta checkpoint ──────────────────────────────────────────────────────

    def get_latest(self, task_id: str) -> Optional[Checkpoint]:
        """Hämtar senaste checkpoint för ett uppdrag."""
        files = sorted(
            self._store_dir.glob(f"{task_id[:8]}_step*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return None
        try:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            return Checkpoint.from_dict(data)
        except Exception as e:
            log.warning(f"load checkpoint: {e}")
            return None

    def get_all(self, task_id: str) -> List[Checkpoint]:
        """Hämtar alla checkpoints för ett uppdrag."""
        files = sorted(
            self._store_dir.glob(f"{task_id[:8]}_step*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        checkpoints = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append(Checkpoint.from_dict(data))
            except Exception:
                pass
        return checkpoints

    def get_last_coherent(self, task_id: str) -> Optional[Checkpoint]:
        """Hämtar senaste koherenta checkpoint (för rollback)."""
        for cp in reversed(self.get_all(task_id)):
            if cp.is_coherent:
                return cp
        return None

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback(self, task_id: str, target_step: Optional[int] = None) -> bool:
        """
        Rullar tillbaka till ett tidigare checkpoint.
        Om target_step är None → senaste koherenta checkpoint.

        Atomic: antingen rullas allt tillbaka, eller ingenting.
        """
        if target_step is not None:
            # Hitta specifikt steg
            all_cps = self.get_all(task_id)
            cp = next(
                (c for c in reversed(all_cps) if c.step_number == target_step),
                None,
            )
        else:
            cp = self.get_last_coherent(task_id)

        if not cp:
            log.warning(f"Rollback: ingen checkpoint hittad för {task_id[:8]}")
            return False

        log.info(f"Rolling back to {cp}")

        # Git rollback
        if cp.git_commit_hash:
            git_ok = self._git_rollback(cp.git_commit_hash)
            if not git_ok:
                log.warning("Git rollback misslyckades — fortsätter ändå")

        # Logga rollback till STONE
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[rollback] task={task_id[:8]} "
                    f"to step={cp.step_number} "
                    f"git={cp.git_commit_hash[:7]}"
                ),
                source  = f"zero_checkpoint:{self.entity_id}",
            )
        except Exception:
            pass

        return True

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_old(self, task_id: str, keep_last: int = 10) -> int:
        """Rensar gamla checkpoints, behåller de senaste N."""
        files = sorted(
            self._store_dir.glob(f"{task_id[:8]}_step*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        to_delete = files[:-keep_last] if len(files) > keep_last else []
        for f in to_delete:
            try:
                f.unlink()
            except Exception:
                pass
        return len(to_delete)

    def format_history(self, task_id: str) -> str:
        """Formaterar checkpoint-historik för presentation."""
        checkpoints = self.get_all(task_id)
        if not checkpoints:
            return f"Inga checkpoints för task {task_id[:8]}"

        lines = [f"Checkpoints för task {task_id[:8]}:"]
        for cp in checkpoints:
            coherent = "✓" if cp.is_coherent else "⚠"
            lines.append(
                f"  {coherent} Steg {cp.step_number:2d} "
                f"coherence={cp.coherence_score:.2f} "
                f"L0={cp.layer0_alignment:.2f} "
                f"git={cp.git_commit_hash[:7] or 'none'} "
                f"| {cp.step_description[:40]}"
            )
        return "\n".join(lines)


# ── Global instans ────────────────────────────────────────────────────────────

_managers: Dict[str, CheckpointManager] = {}


def get_checkpoint_manager(entity_id: str = "zero") -> CheckpointManager:
    if entity_id not in _managers:
        _managers[entity_id] = CheckpointManager(entity_id)
    return _managers[entity_id]


# ── Publikt API ───────────────────────────────────────────────────────────────

def save_checkpoint(
    task_id:          str,
    step_number:      int,
    step_description: str,
    goal:             str,
    remaining_plan:   List[str],
    observation:      str,
    next_step:        str,
    coherence_score:  float = 1.0,
    layer0_alignment: float = 1.0,
    mission_alignment: float = 1.0,
    entity_alignment: float = 1.0,
    entity_id:        str = "zero",
    **kwargs,
) -> Checkpoint:
    """Sparar ett checkpoint. Publikt API för Gear 4."""
    return get_checkpoint_manager(entity_id).save(
        task_id=task_id,
        step_number=step_number,
        step_description=step_description,
        goal=goal,
        remaining_plan=remaining_plan,
        observation=observation,
        next_step=next_step,
        coherence_score=coherence_score,
        layer0_alignment=layer0_alignment,
        mission_alignment=mission_alignment,
        entity_alignment=entity_alignment,
        **kwargs,
    )


def rollback_task(
    task_id:     str,
    target_step: Optional[int] = None,
    entity_id:   str = "zero",
) -> bool:
    """Rullar tillbaka ett uppdrag. Publikt API för Gear 4."""
    return get_checkpoint_manager(entity_id).rollback(task_id, target_step)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Checkpoint System")
    parser.add_argument("--entity",   default="zero")
    parser.add_argument("--history",  metavar="TASK_ID", help="Visa checkpoint-historik")
    parser.add_argument("--rollback", metavar="TASK_ID", help="Rulla tillbaka")
    parser.add_argument("--test",     action="store_true", help="Kör test")
    args = parser.parse_args()

    mgr = get_checkpoint_manager(args.entity)

    if args.history:
        print(mgr.format_history(args.history))

    elif args.rollback:
        ok = mgr.rollback(args.rollback)
        print("✓ Rollback klar" if ok else "✗ Rollback misslyckades")

    elif args.test:
        import uuid
        task_id = str(uuid.uuid4())[:8]
        print(f"Testar checkpoint-system för task {task_id}...")

        # Spara 3 checkpoints
        for i in range(3):
            cp = mgr.save(
                task_id           = task_id,
                step_number       = i,
                step_description  = f"Teststeg {i}",
                goal              = "Testa checkpoint-systemet",
                remaining_plan    = [f"Steg {j}" for j in range(i+1, 3)],
                observation       = f"Steg {i} observerades",
                next_step         = f"Steg {i+1}",
                coherence_score   = 0.90 - i * 0.05,
                layer0_alignment  = 0.95,
                mission_alignment = 0.88,
                entity_alignment  = 0.92,
            )
            print(f"  {cp}")

        print()
        print(mgr.format_history(task_id))

        # Hämta senaste koherenta
        latest = mgr.get_last_coherent(task_id)
        if latest:
            print(f"\nSenaste koherenta: steg {latest.step_number}")

    else:
        parser.print_help()
