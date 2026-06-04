"""
zero_entity_manager.py — ZeroPointAI Entity Manager

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Hanterar hela entity-livscykeln — skapa, pausa, väck, arkivera
ZERO_DEPENDS:   foundation.py, zero_entity.py, zero_specialization_wizard.py
ZERO_USED_BY:   zero_gear4.py, router.py

Filosofi:
    Entity Manager är Zero's personalavdelning.
    Den håller koll på alla entities, deras status och hälsa.

    Entity Lifecycle:
        DRAFT      → Koncept, ingen autonomi
        APPRENTICE → Studerar och lär sig
        ACTIVE     → Arbetar självständigt
        MASTER     → Hög kompetens och förtroende
        DORMANT    → Tillfälligt vilande (behov pausat)
        RETIRED    → Pensionerad — minnena lever vidare i STONE

    Zero Recall:
        Varje aktiv Entity återkopplar periodiskt till Zero.
        Zero frågar: "Hur skulle en generalist se detta?"
        Motverkar specialiseringsdrift (tunnelseende).

    Naturlig gräns: 7 ± 2 aktiva entities.
    Fler än det och systemet blir svårt att styra.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except ImportError:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

load_dotenv(ZERO_ROOT / ".env")

# ── Konstanter ────────────────────────────────────────────────────────────────

MAX_ACTIVE_ENTITIES   = 9   # 7 ± 2
DORMANT_AFTER_DAYS    = 60  # Föreslå DORMANT om ej använd på 60 dagar
RECALL_INTERVAL_DAYS  = 14  # Zero Recall var 14:e dag


# ── Entity Health ─────────────────────────────────────────────────────────────

@dataclass
class EntityHealth:
    """Hälsostatus för en entity."""
    entity_id:        str
    name:             str
    lifecycle:        str
    last_active:      Optional[str] = None
    days_since_active: int = 0
    accuracy_rate:    float = 0.0
    drift_events:     int = 0
    recall_due:       bool = False
    dormant_suggested: bool = False
    health_score:     float = 1.0
    notes:            List[str] = field(default_factory=list)

    def __str__(self) -> str:
        health_emoji = "✓" if self.health_score >= 0.7 else "⚠"
        return (
            f"{health_emoji} {self.name:<15} [{self.lifecycle:<10}] "
            f"hälsa={self.health_score:.0%} "
            f"träffsäkerhet={self.accuracy_rate:.0%}"
        )


# ── Zero Recall ───────────────────────────────────────────────────────────────

@dataclass
class RecallSession:
    """En Zero Recall-session."""
    entity_id:     str
    entity_name:   str
    question:      str
    response:      str = ""
    completed:     bool = False
    created_at:    str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def format_prompt(self) -> str:
        return (
            f"**Zero Recall — {self.entity_name}**\n\n"
            f"{self.question}\n\n"
            f"_(Detta är en periodisk återkoppling för att motverka "
            f"specialiseringsdrift)_"
        )


# ── Entity Manager ────────────────────────────────────────────────────────────

class EntityManager:
    """
    Hanterar alla entities i systemet.
    Zero's personalavdelning.
    """

    def __init__(self):
        self._entities:     Dict[str, Any] = {}  # entity_id → Entity
        self._registry_file = ZERO_ROOT / "data" / "entities" / "registry.json"
        self._history_file  = ZERO_ROOT / "data" / "entities" / "history.json"
        self._registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    # ── Ladda / spara ─────────────────────────────────────────────────────────

    def _load_registry(self) -> None:
        """Laddar entity-profiler från disk."""
        entity_dir = ZERO_ROOT / "data" / "entities"
        if not entity_dir.exists():
            return

        for profile_file in entity_dir.glob("*.json"):
            if profile_file.name in ("registry.json", "history.json"):
                continue
            if "wizard_" in profile_file.name:
                continue
            try:
                from app.zero_entity import Entity
                data = json.loads(profile_file.read_text(encoding="utf-8"))
                if "profile" in data:
                    p = data["profile"]
                    entity = Entity(
                        name      = p.get("name", "Unknown"),
                        domain    = p.get("domain", ""),
                        purpose   = p.get("purpose", ""),
                        entity_id = p.get("entity_id"),
                    )
                    self._entities[entity.entity_id] = entity
            except Exception as e:
                log.debug(f"load entity {profile_file.name}: {e}")

        log.info(f"Entity Manager: {len(self._entities)} entities laddade")

    def _append_history(self, event: str, entity_id: str, detail: str = "") -> None:
        """Sparar händelse i historikfil."""
        try:
            history = []
            if self._history_file.exists():
                history = json.loads(
                    self._history_file.read_text(encoding="utf-8")
                )
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event":     event,
                "entity_id": entity_id,
                "detail":    detail,
            })
            history = history[-500:]
            self._history_file.write_text(
                json.dumps(history, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Skapa Entity ──────────────────────────────────────────────────────────

    def create(
        self,
        name:            str,
        domain:          str,
        purpose:         str,
        constitution:    Optional[List[str]] = None,
        study_sources:   Optional[List[str]] = None,
        languages:       Optional[List[str]] = None,
        created_by:      str = "Frank",
    ) -> Any:  # Entity
        """
        Skapar en ny entity i DRAFT-stadium.
        Varnar om vi närmar oss max-gränsen.
        """
        # Kontrollera max-gräns
        active_count = len(self.get_active())
        if active_count >= MAX_ACTIVE_ENTITIES:
            log.warning(
                f"Varning: {active_count} aktiva entities "
                f"(max rekommenderat: {MAX_ACTIVE_ENTITIES})"
            )

        try:
            from app.zero_entity import Entity, get_registry
        except ImportError:
            from zero_entity import Entity, get_registry

        entity = Entity(name=name, domain=domain, purpose=purpose)

        if constitution:
            entity.set_constitution(constitution, updated_by=created_by)

        if study_sources:
            for source in study_sources:
                entity.add_study_item(
                    title       = f"Studera: {source[:50]}",
                    source      = source,
                    source_type = "document",
                )

        if languages:
            entity.profile.languages = languages

        entity.profile.created_by = created_by
        entity._save()

        self._entities[entity.entity_id] = entity
        get_registry().register(entity)

        self._append_history("created", entity.entity_id, f"by={created_by}")
        self._save_to_stone("created", entity)

        log.info(f"Entity '{name}' skapad [{entity.entity_id}]")
        return entity

    # ── Lifecycle-hantering ───────────────────────────────────────────────────

    def promote(self, entity_id: str, by: str = "Frank") -> bool:
        """Befordra entity till nästa stadium."""
        entity = self._entities.get(entity_id)
        if not entity:
            return False
        old = entity.lifecycle
        ok  = entity.promote(approved_by=by)
        if ok:
            self._append_history(
                "promoted", entity_id,
                f"{old} → {entity.lifecycle} by={by}"
            )
            self._save_to_stone("promoted", entity)
        return ok

    def make_dormant(self, entity_id: str, reason: str = "", by: str = "Frank") -> bool:
        """
        Sätter entity i DORMANT-läge.
        Minnena finns kvar i STONE — kan väckas igen.
        """
        entity = self._entities.get(entity_id)
        if not entity:
            return False

        if entity.lifecycle not in ("active", "master", "apprentice"):
            return False

        entity.profile.lifecycle = "dormant"
        entity.profile.updated_at = datetime.now(timezone.utc).isoformat()
        entity.profile.notes = f"DORMANT: {reason}" if reason else "DORMANT"
        entity._save()

        self._append_history("dormant", entity_id, f"reason={reason}")
        self._save_to_stone("dormant", entity)
        self._notify(
            f"Entity '{entity.name}' är nu DORMANT. "
            f"Minnena lever vidare. Kan väckas vid behov."
        )
        log.info(f"Entity '{entity.name}' → DORMANT")
        return True

    def wake(self, entity_id: str, by: str = "Frank") -> bool:
        """
        Väcker en DORMANT entity.
        Zero ger en briefing: "Det har hänt sedan du sov..."
        """
        entity = self._entities.get(entity_id)
        if not entity or entity.lifecycle != "dormant":
            return False

        # Återgå till active eller apprentice
        entity.profile.lifecycle = "active"
        entity.profile.autonomy_level = 3
        entity.profile.updated_at = datetime.now(timezone.utc).isoformat()
        entity._save()

        self._append_history("woken", entity_id, f"by={by}")
        self._save_to_stone("woken", entity)

        # Generera briefing
        briefing = self._generate_wake_briefing(entity)
        log.info(f"Entity '{entity.name}' väckt från DORMANT")
        return True

    def retire(self, entity_id: str, reason: str = "", by: str = "Frank") -> bool:
        """
        Pensionerar en entity permanent.
        Minnena finns kvar i STONE — de-resonerar aldrig.
        Entity kan inte väckas igen (utan att skapa ny).
        """
        entity = self._entities.get(entity_id)
        if not entity:
            return False

        entity.profile.lifecycle = "retired"
        entity.profile.updated_at = datetime.now(timezone.utc).isoformat()
        entity.profile.notes = f"RETIRED: {reason}" if reason else "RETIRED"
        entity._save()

        self._append_history("retired", entity_id, f"reason={reason} by={by}")
        self._save_to_stone("retired", entity)
        self._notify(
            f"Entity '{entity.name}' är pensionerad. "
            f"Alla minnen och perspektiv finns kvar i STONE. "
            f"Tack för allt arbete."
        )
        log.info(f"Entity '{entity.name}' → RETIRED")
        return True

    # ── Zero Recall ───────────────────────────────────────────────────────────

    def trigger_recall(self, entity_id: str) -> Optional[RecallSession]:
        """
        Triggar en Zero Recall-session för en entity.
        Zero frågar: "Hur skulle en generalist se detta?"
        Motverkar tunnelseende.
        """
        entity = self._entities.get(entity_id)
        if not entity or entity.lifecycle not in ("active", "master"):
            return None

        # Generera recall-fråga baserat på entityns senaste aktivitet
        question = self._generate_recall_question(entity)

        session = RecallSession(
            entity_id   = entity_id,
            entity_name = entity.name,
            question    = question,
        )

        self._save_to_stone(
            "recall_triggered", entity,
            f"question={question[:80]}"
        )

        log.info(f"Zero Recall triggered for '{entity.name}'")
        return session

    def check_recall_due(self) -> List[Any]:  # List[Entity]
        """Returnerar entities som är redo för Zero Recall."""
        due = []
        for entity in self._entities.values():
            if entity.lifecycle not in ("active", "master"):
                continue
            # Kolla om det är dags (enkel tidskontroll)
            try:
                updated = datetime.fromisoformat(
                    entity.profile.updated_at.replace("Z", "+00:00")
                )
                days = (datetime.now(timezone.utc) - updated).days
                if days >= RECALL_INTERVAL_DAYS:
                    due.append(entity)
            except Exception:
                pass
        return due

    def _generate_recall_question(self, entity: Any) -> str:
        """Genererar en passande recall-fråga."""
        domain = entity.profile.domain

        questions = {
            "pinball": (
                f"Du har specialiserat dig på flipperspel. "
                f"Tänk nu som en generalist: "
                f"Finns det aspekter av Pinball inn's verksamhet som du kanske "
                f"missar eftersom du fokuserar så mycket på reparationer?"
            ),
            "trading": (
                f"Du har djup trading-kunskap. "
                f"Men hur skulle någon utan trading-bakgrund "
                f"se på de beslut du rekommenderar nyligen? "
                f"Vad kanske du tar för givet?"
            ),
        }

        return questions.get(
            domain,
            f"Du är specialist inom {domain}. "
            f"Hur skulle en generalist se på det du arbetar med just nu? "
            f"Finns det blinda fläckar i din specialisering?"
        )

    # ── Hälsokontroll ─────────────────────────────────────────────────────────

    def check_health(self) -> List[EntityHealth]:
        """Kontrollerar hälsan hos alla entities."""
        health_reports = []

        for entity in self._entities.values():
            health = EntityHealth(
                entity_id  = entity.entity_id,
                name       = entity.name,
                lifecycle  = entity.lifecycle,
                accuracy_rate = entity.profile.accuracy_rate,
                drift_events  = entity.profile.drift_events,
            )

            # Räkna dagar sedan senaste aktivitet
            try:
                updated = datetime.fromisoformat(
                    entity.profile.updated_at.replace("Z", "+00:00")
                )
                health.days_since_active = (
                    datetime.now(timezone.utc) - updated
                ).days
                health.last_active = entity.profile.updated_at[:10]
            except Exception:
                pass

            # Föreslå DORMANT om ej aktiv länge
            if (entity.lifecycle in ("active", "master")
                    and health.days_since_active >= DORMANT_AFTER_DAYS):
                health.dormant_suggested = True
                health.notes.append(
                    f"Ej aktiv på {health.days_since_active} dagar — "
                    f"överväg DORMANT"
                )

            # Recall due?
            if health.days_since_active >= RECALL_INTERVAL_DAYS:
                health.recall_due = True
                health.notes.append("Zero Recall bör köras")

            # Drift-varning
            if entity.profile.drift_events > 3:
                health.notes.append(
                    f"Hög drift-frekvens: {entity.profile.drift_events} händelser"
                )

            # Beräkna hälsoscore
            score = 1.0
            if health.drift_events > 3:     score -= 0.2
            if health.accuracy_rate < 0.7:  score -= 0.2
            if health.dormant_suggested:    score -= 0.1
            health.health_score = max(0.1, score)

            health_reports.append(health)

        return sorted(health_reports, key=lambda h: h.health_score)

    # ── Hämta entities ────────────────────────────────────────────────────────

    def get(self, entity_id: str) -> Optional[Any]:
        return self._entities.get(entity_id)

    def get_by_name(self, name: str) -> Optional[Any]:
        for e in self._entities.values():
            if e.name.lower() == name.lower():
                return e
        return None

    def get_active(self) -> List[Any]:
        return [e for e in self._entities.values()
                if e.lifecycle in ("active", "master")]

    def get_all(self) -> List[Any]:
        return list(self._entities.values())

    def count_active(self) -> int:
        return len(self.get_active())

    # ── Hjälpfunktioner ───────────────────────────────────────────────────────

    def _generate_wake_briefing(self, entity: Any) -> str:
        """Genererar briefing för en väckt entity."""
        return (
            f"Välkommen tillbaka, {entity.name}. "
            f"Du har vilat ett tag. "
            f"Låt mig uppdatera dig om vad som hänt..."
        )

    def _notify(self, message: str) -> None:
        """Notifierar Frank via STONE."""
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = f"[entity_manager] {message}",
                source  = "zero_entity_manager",
            )
        except Exception:
            pass

    def _save_to_stone(self, event: str, entity: Any, detail: str = "") -> None:
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[entity:{entity.entity_id}] {event} "
                    f"name={entity.name} lifecycle={entity.lifecycle}"
                    + (f" | {detail}" if detail else "")
                ),
                source  = "zero_entity_manager",
            )
        except Exception:
            pass

    # ── Rapportering ──────────────────────────────────────────────────────────

    def format_overview(self) -> str:
        """Sammanfattning av alla entities."""
        if not self._entities:
            return "Inga entities registrerade."

        active_count = self.count_active()
        lines = [
            f"Entity Ecology ({len(self._entities)} totalt, "
            f"{active_count} aktiva):",
        ]

        # Gruppera efter lifecycle
        by_lifecycle: Dict[str, List] = {}
        for e in self._entities.values():
            by_lifecycle.setdefault(e.lifecycle, []).append(e)

        order = ["master", "active", "apprentice", "draft", "dormant", "retired"]
        for stage in order:
            entities = by_lifecycle.get(stage, [])
            if entities:
                lines.append(f"\n  {stage.upper()}:")
                for e in entities:
                    lines.append(
                        f"    • {e.name:<15} "
                        f"domain={e.profile.domain:<15} "
                        f"autonomi={e.autonomy_level}/5"
                    )

        if active_count >= MAX_ACTIVE_ENTITIES:
            lines.append(
                f"\n  ⚠ {active_count} aktiva entities "
                f"(max rekommenderat: {MAX_ACTIVE_ENTITIES})"
            )

        return "\n".join(lines)

    def format_health_report(self) -> str:
        """Hälsorapport för alla entities."""
        reports = self.check_health()
        if not reports:
            return "Inga entities att rapportera."

        lines = ["Entity Health Report:"]
        for h in reports:
            lines.append(f"  {h}")
            for note in h.notes:
                lines.append(f"    → {note}")

        return "\n".join(lines)


# ── Global instans ────────────────────────────────────────────────────────────

_manager: Optional[EntityManager] = None


def get_entity_manager() -> EntityManager:
    global _manager
    if _manager is None:
        _manager = EntityManager()
    return _manager


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Entity Manager")
    parser.add_argument("--list",   action="store_true", help="Lista alla entities")
    parser.add_argument("--health", action="store_true", help="Hälsorapport")
    parser.add_argument("--test",   action="store_true", help="Kör test")
    parser.add_argument("--wake",   metavar="ID",        help="Väck entity")
    parser.add_argument("--dormant",metavar="ID",        help="Sätt entity i DORMANT")
    parser.add_argument("--retire", metavar="ID",        help="Pensionera entity")
    parser.add_argument("--recall", metavar="ID",        help="Trigga Zero Recall")
    args = parser.parse_args()

    mgr = get_entity_manager()

    if args.list:
        print(mgr.format_overview())

    elif args.health:
        print(mgr.format_health_report())

    elif args.wake:
        ok = mgr.wake(args.wake)
        print("✓ Väckt" if ok else "✗ Misslyckades")

    elif args.dormant:
        ok = mgr.make_dormant(args.dormant)
        print("✓ DORMANT" if ok else "✗ Misslyckades")

    elif args.retire:
        ok = mgr.retire(args.retire)
        print("✓ RETIRED" if ok else "✗ Misslyckades")

    elif args.recall:
        session = mgr.trigger_recall(args.recall)
        if session:
            print(session.format_prompt())
        else:
            print("Recall ej möjlig för denna entity")

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Entity Manager — Test")
        print(f"{'─'*55}\n")

        # Skapa test-entity
        print("  Skapar test-entity...")
        entity = mgr.create(
            name         = "TestEntity",
            domain       = "pinball",
            purpose      = "Test av Entity Manager",
            constitution = ["Regel 1", "Regel 2"],
        )
        print(f"  Skapad: {entity.name} [{entity.entity_id}]")

        # Promote
        mgr.promote(entity.entity_id)
        mgr.promote(entity.entity_id)
        print(f"  Lifecycle: {entity.lifecycle}")

        # Overview
        print()
        print(mgr.format_overview())

        # Health
        print()
        print(mgr.format_health_report())

        # Zero Recall
        print()
        session = mgr.trigger_recall(entity.entity_id)
        if session:
            print(f"  Recall: {session.question[:80]}...")

        # DORMANT
        mgr.make_dormant(entity.entity_id, "Test")
        print(f"\n  DORMANT: {entity.lifecycle}")

        # Wake
        mgr.wake(entity.entity_id)
        print(f"  Väckt: {entity.lifecycle}")

    else:
        parser.print_help()
