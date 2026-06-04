"""
zero_entity.py — ZeroPointAI Entity Base Class

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Base class för alla entities — specialiserade uttryck av Zero
ZERO_DEPENDS:   foundation.py, drm_memory.py, zero_perspective.py, zero_identity_anchor.py
ZERO_USED_BY:   zero_gear4.py, minna_entity.py, future entities

Filosofi:
    En Entity är inte en annan person.
    En Entity är Zero som har fördjupat sig inom ett specifikt område.

    Alla entities delar:
        Samma Layer 0
        Samma grundläggande värderingar
        Samma kärnidentitet

    Det som skiljer dem åt:
        Fokus, minne, erfarenhet, specialisering

    En Entity är ett specialiserat uttryck av Zero — inte en kopia.
    Samma källa, olika fokus.

    Lifecycle:
        DRAFT      → Koncept, ingen autonomi
        APPRENTICE → Studerar, frågar, föreslår men bestämmer inget
        ACTIVE     → Arbetar självständigt inom sitt område
        MASTER     → Hög kompetens, dokumenterad historia, större autonomi
        DORMANT    → Tillfälligt vilande — minnena lever, kan väckas
        RETIRED    → Pensionerad — minnena finns kvar i STONE för alltid

    En Entity skapas inte automatiskt.
    Den designas i samarbete mellan Zero och Frank.
    Zero frågar: "Vill du att vi designar den tillsammans?"

    Frågor är centralt:
        En Entity med låg confidence frågar hellre än gissar.
        Frågor är inte ett misslyckande — de är en del av lärandet.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv

log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT, LAYER0_FULL
except ImportError:
    ZERO_ROOT   = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))
    LAYER0_FULL = ""

load_dotenv(ZERO_ROOT / ".env")

# ── Lifecycle ─────────────────────────────────────────────────────────────────

LIFECYCLE_STAGES = ["draft", "apprentice", "active", "master", "dormant", "retired"]

LIFECYCLE_AUTONOMY: Dict[str, int] = {
    "draft":      0,   # Ingen autonomi — bara koncept
    "apprentice": 1,   # Frågar och föreslår, inga beslut
    "active":     3,   # Arbetar självständigt, LOW/CAUTION ops
    "master":     5,   # Full autonomi inom sitt område
    "dormant":    0,   # Vilande — ingen autonomi
    "retired":    0,   # Pensionerad — ingen autonomi
}

LIFECYCLE_TRANSITIONS = {
    "draft":      {"apprentice"},
    "apprentice": {"active", "draft"},
    "active":     {"master", "apprentice", "dormant"},
    "master":     {"active", "dormant"},
    "dormant":    {"active", "retired"},    # kan väckas eller pensioneras
    "retired":    set(),                    # terminal — inga övergångar
}


# ── Entity Constitution ───────────────────────────────────────────────────────

@dataclass
class EntityConstitution:
    """
    Bindande regler för en entity — tillägg till Layer 0.
    Mer specifik än Layer 0, svår att avvika från.
    Bara Frank kan uppdatera.
    """
    entity_id:    str
    rules:        List[str] = field(default_factory=list)
    created_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_by:   str = "Frank"

    def as_text(self) -> str:
        if not self.rules:
            return f"Entity Constitution för {self.entity_id}: (tom)"
        lines = [f"Entity Constitution för {self.entity_id}:"]
        for i, rule in enumerate(self.rules, 1):
            lines.append(f"  {i}. {rule}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "EntityConstitution":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})


# ── Study Plan ────────────────────────────────────────────────────────────────

@dataclass
class StudyItem:
    """Ett studieuppdrag för en Apprentice entity."""
    item_id:     str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:       str = ""
    source:      str = ""   # URL, filsökväg, beskrivning
    source_type: str = "document"  # document/video/forum/zero_mentor/experience
    status:      str = "pending"   # pending/studying/complete
    notes:       str = ""
    confidence_gained: float = 0.0
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# ── Entity datastruktur ───────────────────────────────────────────────────────

@dataclass
class EntityProfile:
    """
    Profil för en entity.
    Sparas i STONE och lokal JSON.
    """
    entity_id:       str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:            str = ""
    purpose:         str = ""
    domain:          str = ""
    lifecycle:       str = "draft"
    autonomy_level:  int = 0

    # Constitution
    constitution:    List[str] = field(default_factory=list)

    # Studieplan
    study_plan:      List[StudyItem] = field(default_factory=list)
    mentors:         List[str] = field(default_factory=list)  # entity_ids

    # Verktyg och begränsningar
    allowed_tools:   List[str] = field(default_factory=list)
    restricted_tools: List[str] = field(default_factory=list)

    # Kommunikation
    languages:       List[str] = field(default_factory=list)
    communication_style: str = ""

    # Statistik
    tasks_completed:    int = 0
    tasks_failed:       int = 0
    questions_asked:    int = 0
    drift_events:       int = 0
    perspective_count:  int = 0

    # Meta
    created_at:      str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at:      str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    created_by:      str = "Frank"
    notes:           str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["study_plan"] = [s.to_dict() for s in self.study_plan]
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "EntityProfile":
        d = dict(d)
        d["study_plan"] = [StudyItem(**s) for s in d.get("study_plan", [])]
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})

    @property
    def can_act_autonomously(self) -> bool:
        return self.lifecycle in ("active", "master")

    @property
    def should_ask_questions(self) -> bool:
        """Entity med låg autonomi frågar hellre än gissar."""
        return self.autonomy_level <= 2

    @property
    def accuracy_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if not total:
            return 0.0
        return self.tasks_completed / total


# ── Entity Base Class ─────────────────────────────────────────────────────────

class Entity:
    """
    Base class för alla ZeroPointAI entities.

    En entity är Zero specialiserad inom ett område.
    Delar Layer 0, grundvärderingar och kärnidentitet med Zero.
    Har eget fokus, minne och constitution.

    Subklassa för specifika entities:
        class MinnaEntity(Entity):
            def __init__(self):
                super().__init__(
                    name    = "Minna",
                    domain  = "pinball_repair",
                    purpose = "Expert på flipperspelsreparationer",
                )
    """

    def __init__(
        self,
        name:    str,
        domain:  str,
        purpose: str,
        entity_id: Optional[str] = None,
    ):
        self._profile = EntityProfile(
            entity_id = entity_id or name.lower().replace(" ", "_"),
            name      = name,
            domain    = domain,
            purpose   = purpose,
        )
        self._constitution = EntityConstitution(
            entity_id = self._profile.entity_id
        )
        self._store_file = (
            ZERO_ROOT / "data" / "entities" / f"{self._profile.entity_id}.json"
        )
        self._store_file.parent.mkdir(parents=True, exist_ok=True)

        # Ladda om den finns
        self._load()

        # Lazily-initierade komponenter
        self._perspective_mgr = None
        self._identity_anchor = None

        log.info(
            f"Entity '{name}' initierad "
            f"[{self._profile.lifecycle}] "
            f"domain={domain}"
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def entity_id(self) -> str:
        return self._profile.entity_id

    @property
    def name(self) -> str:
        return self._profile.name

    @property
    def lifecycle(self) -> str:
        return self._profile.lifecycle

    @property
    def autonomy_level(self) -> int:
        return self._profile.autonomy_level

    @property
    def profile(self) -> EntityProfile:
        return self._profile

    @property
    def constitution_text(self) -> str:
        return self._constitution.as_text()

    @property
    def perspectives(self):
        if self._perspective_mgr is None:
            try:
                from app.zero_perspective import get_perspective_manager
                self._perspective_mgr = get_perspective_manager(self.entity_id)
            except ImportError:
                return None
        return self._perspective_mgr

    @property
    def anchor(self):
        if self._identity_anchor is None:
            try:
                from app.zero_identity_anchor import get_anchor
                self._identity_anchor = get_anchor(self.entity_id)
            except ImportError:
                return None
        return self._identity_anchor

    # ── Persistens ────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            data = {
                "profile":      self._profile.to_dict(),
                "constitution": self._constitution.to_dict(),
            }
            tmp = self._store_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._store_file)
        except Exception as e:
            log.warning(f"entity save: {e}")

    def _load(self) -> None:
        if not self._store_file.exists():
            return
        try:
            data = json.loads(self._store_file.read_text(encoding="utf-8"))
            if "profile" in data:
                self._profile = EntityProfile.from_dict(data["profile"])
            if "constitution" in data:
                self._constitution = EntityConstitution.from_dict(
                    data["constitution"]
                )
            log.debug(f"Entity '{self.name}' laddad från disk")
        except Exception as e:
            log.warning(f"entity load: {e}")

    def _save_to_stone(self, event: str, detail: str = "") -> None:
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[entity:{self.entity_id}] {event} "
                    f"lifecycle={self.lifecycle} "
                    + (f"| {detail}" if detail else "")
                ),
                source  = f"zero_entity:{self.entity_id}",
            )
        except Exception:
            pass

    # ── Lifecycle-hantering ───────────────────────────────────────────────────

    def transition_lifecycle(
        self,
        new_stage: str,
        approved_by: str = "Frank",
    ) -> bool:
        """Övergång till nytt lifecycle-stadium."""
        allowed = LIFECYCLE_TRANSITIONS.get(self._profile.lifecycle, set())
        if new_stage not in allowed:
            log.warning(
                f"Entity '{self.name}': "
                f"{self._profile.lifecycle} → {new_stage} ej tillåten"
            )
            return False

        old = self._profile.lifecycle
        self._profile.lifecycle       = new_stage
        self._profile.autonomy_level  = LIFECYCLE_AUTONOMY[new_stage]
        self._profile.updated_at      = datetime.now(timezone.utc).isoformat()

        self._save()
        self._save_to_stone(
            f"lifecycle transition: {old} → {new_stage}",
            f"approved_by={approved_by}"
        )
        log.info(
            f"Entity '{self.name}': {old} → {new_stage} "
            f"(autonomy={self._profile.autonomy_level})"
        )
        return True

    def promote(self, approved_by: str = "Frank") -> bool:
        """Befordra till nästa stadium."""
        idx = LIFECYCLE_STAGES.index(self._profile.lifecycle)
        if idx >= len(LIFECYCLE_STAGES) - 1:
            log.info(f"Entity '{self.name}' är redan MASTER")
            return False
        return self.transition_lifecycle(
            LIFECYCLE_STAGES[idx + 1], approved_by
        )

    def demote(self, reason: str = "", approved_by: str = "Frank") -> bool:
        """Degradera ett stadium — vid problem."""
        idx = LIFECYCLE_STAGES.index(self._profile.lifecycle)
        if idx <= 0:
            return False
        return self.transition_lifecycle(
            LIFECYCLE_STAGES[idx - 1], approved_by
        )

    # ── Constitution ──────────────────────────────────────────────────────────

    def set_constitution(
        self,
        rules:      List[str],
        updated_by: str = "Frank",
    ) -> None:
        """Uppdaterar entity constitution. Bara Frank kan göra detta."""
        self._constitution.rules      = rules
        self._constitution.updated_at = datetime.now(timezone.utc).isoformat()
        self._constitution.updated_by = updated_by
        self._save()
        self._save_to_stone(
            "constitution updated",
            f"rules={len(rules)} by={updated_by}"
        )
        log.info(f"Entity '{self.name}' constitution uppdaterad ({len(rules)} regler)")

    def add_constitution_rule(self, rule: str, by: str = "Frank") -> None:
        self._constitution.rules.append(rule)
        self._constitution.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

    # ── Studieplan ────────────────────────────────────────────────────────────

    def add_study_item(
        self,
        title:       str,
        source:      str,
        source_type: str = "document",
    ) -> StudyItem:
        item = StudyItem(title=title, source=source, source_type=source_type)
        self._profile.study_plan.append(item)
        self._save()
        return item

    def complete_study_item(
        self,
        item_id:           str,
        notes:             str = "",
        confidence_gained: float = 0.1,
    ) -> bool:
        for item in self._profile.study_plan:
            if item.item_id == item_id:
                item.status            = "complete"
                item.notes             = notes
                item.confidence_gained = confidence_gained
                item.completed_at      = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    @property
    def study_progress(self) -> Dict[str, int]:
        total    = len(self._profile.study_plan)
        complete = sum(1 for i in self._profile.study_plan
                       if i.status == "complete")
        return {"total": total, "complete": complete, "remaining": total - complete}

    # ── Frågor (Apprentice-beteende) ──────────────────────────────────────────

    def formulate_question(
        self,
        topic:      str,
        context:    str = "",
        options:    Optional[List[str]] = None,
    ) -> str:
        """
        Formulerar en fråga till Frank/Zero.
        Används av Apprentice-entities när confidence är låg.
        Frågor är inte ett misslyckande — de är en del av lärandet.
        """
        self._profile.questions_asked += 1
        self._save()

        if options and len(options) >= 2:
            opts_text = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
            return (
                f"Jag behöver din vägledning angående '{topic}'.\n\n"
                f"Kontext: {context}\n\n"
                f"Jag ser följande alternativ:\n{opts_text}\n\n"
                f"Vilket alternativ stämmer bäst med din intention?"
            )

        return (
            f"Jag är osäker på hur jag ska hantera '{topic}'.\n\n"
            f"Kontext: {context}\n\n"
            f"Kan du vägleda mig?"
        )

    def should_ask(self, confidence: float) -> bool:
        """
        Ska entity fråga istället för att agera?
        Beror på lifecycle och confidence.
        """
        if self._profile.lifecycle == "draft":
            return True  # Draft frågar alltid
        if self._profile.lifecycle == "apprentice":
            return confidence < 0.75  # Apprentice frågar vid osäkerhet
        if self._profile.lifecycle == "active":
            return confidence < 0.50  # Active frågar bara vid låg confidence
        return False  # Master agerar på egen hand

    # ── Statistik ─────────────────────────────────────────────────────────────

    def zero_recall(self, generalist_question: str = "") -> str:
        """
        Zero Recall — periodisk återkoppling till Zero.
        Motverkar specialiseringsdrift (tunnelseende).
        Zero frågar: "Hur skulle en generalist se detta?"
        """
        if not generalist_question:
            generalist_question = (
                f"Du är specialiserad inom {self._profile.domain}. "
                f"Hur skulle Zero som generalist se på det du arbetar med? "
                f"Finns det blinda fläckar i din specialisering?"
            )

        # Logga till STONE
        self._save_to_stone(
            "zero_recall",
            f"question={generalist_question[:80]}"
        )

        log.info(f"Zero Recall triggered for '{self.name}'")
        return generalist_question

    def record_task_complete(self) -> None:
        self._profile.tasks_completed += 1
        self._profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def record_task_failed(self) -> None:
        self._profile.tasks_failed += 1
        self._profile.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def record_drift_event(self) -> None:
        self._profile.drift_events += 1
        self._save()

    # ── Rapportering ──────────────────────────────────────────────────────────

    def format_profile(self) -> str:
        p = self._profile
        study = self.study_progress
        lines = [
            f"Entity: {p.name} ({p.entity_id})",
            f"  Syfte:      {p.purpose}",
            f"  Domän:      {p.domain}",
            f"  Lifecycle:  {p.lifecycle.upper()} (autonomi {p.autonomy_level}/5)",
            f"  Uppgifter:  {p.tasks_completed} klara, {p.tasks_failed} misslyckade",
        ]
        if p.tasks_completed + p.tasks_failed > 0:
            lines.append(f"  Träffsäkerhet: {p.accuracy_rate:.0%}")
        if study["total"] > 0:
            lines.append(
                f"  Studier:    {study['complete']}/{study['total']} klara"
            )
        if p.drift_events > 0:
            lines.append(f"  Drift-händelser: {p.drift_events} ⚠")
        if self._constitution.rules:
            lines.append(f"  Constitution: {len(self._constitution.rules)} regler")
        return "\n".join(lines)

    def get_system_prompt_block(self) -> str:
        """
        Injiceras i system-prompten när entity är aktiv.
        Berättar för LLM:en vem entity:n är och vilka regler som gäller.
        """
        blocks = [
            f"=== ENTITY: {self.name.upper()} ===",
            f"Lifecycle: {self.lifecycle.upper()}",
            f"Domän: {self._profile.domain}",
            f"Syfte: {self._profile.purpose}",
        ]

        if self._constitution.rules:
            blocks.append(f"\n{self._constitution.as_text()}")

        if self._profile.should_ask_questions:
            blocks.append(
                "\nOBS: Du är i APPRENTICE-läge. "
                "Fråga hellre än gissa vid osäkerhet. "
                "Frågor är en del av lärandet, inte ett misslyckande."
            )

        blocks.append(
            f"\nDu är {self.name} — Zero specialiserad inom {self._profile.domain}. "
            f"Du delar Zero's Layer 0 och grundvärderingar."
        )

        return "\n".join(blocks)


# ── Entity Registry ───────────────────────────────────────────────────────────

class EntityRegistry:
    """
    Håller koll på alla entities i systemet.
    Zero kan fråga registret: "vilka entities finns?"
    """

    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._registry_file = ZERO_ROOT / "data" / "entities" / "registry.json"
        self._registry_file.parent.mkdir(parents=True, exist_ok=True)

    def register(self, entity: Entity) -> None:
        self._entities[entity.entity_id] = entity
        self._save_registry()
        log.info(f"Entity registered: {entity.name} ({entity.entity_id})")

    def get(self, entity_id: str) -> Optional[Entity]:
        return self._entities.get(entity_id)

    def get_by_name(self, name: str) -> Optional[Entity]:
        for e in self._entities.values():
            if e.name.lower() == name.lower():
                return e
        return None

    def get_active(self) -> List[Entity]:
        return [e for e in self._entities.values()
                if e.lifecycle in ("active", "master")]

    def get_all(self) -> List[Entity]:
        return list(self._entities.values())

    def _save_registry(self) -> None:
        try:
            data = {
                eid: {
                    "name":      e.name,
                    "domain":    e.profile.domain,
                    "lifecycle": e.lifecycle,
                    "purpose":   e.profile.purpose,
                }
                for eid, e in self._entities.items()
            }
            self._registry_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"registry save: {e}")

    def format_summary(self) -> str:
        if not self._entities:
            return "Inga entities registrerade."
        lines = ["Entities:"]
        for e in self._entities.values():
            lines.append(
                f"  • {e.name:<15} [{e.lifecycle:<10}] "
                f"domain={e.profile.domain}"
            )
        return "\n".join(lines)


# ── Entity Creation Wizard ────────────────────────────────────────────────────

class EntityCreationWizard:
    """
    Guidar Zero och Frank genom att skapa en ny entity.
    En entity skapas inte automatiskt — den designas i samarbete.
    """

    def __init__(self):
        self._draft: Optional[EntityProfile] = None

    def suggest(self, domain: str, reason: str) -> str:
        """
        Zero föreslår att en entity bör skapas.
        Returnerar ett förslag att visa Frank.
        """
        return (
            f"Jag tror att domänen '{domain}' är tillräckligt "
            f"viktig och återkommande för att motivera en specialiserad entity.\n\n"
            f"Anledning: {reason}\n\n"
            f"En dedikerad specialist skulle bli bättre över tid "
            f"än om jag hanterar det som generalist.\n\n"
            f"Vill du att vi designar den tillsammans?"
        )

    def create(
        self,
        name:            str,
        domain:          str,
        purpose:         str,
        constitution:    Optional[List[str]] = None,
        study_sources:   Optional[List[str]] = None,
        languages:       Optional[List[str]] = None,
        communication_style: str = "",
    ) -> Entity:
        """Skapar en ny entity i DRAFT-stadium."""
        entity = Entity(name=name, domain=domain, purpose=purpose)

        if constitution:
            entity.set_constitution(constitution)

        if study_sources:
            for source in study_sources:
                entity.add_study_item(
                    title       = f"Studera: {source[:50]}",
                    source      = source,
                    source_type = "document",
                )

        if languages:
            entity.profile.languages = languages

        if communication_style:
            entity.profile.communication_style = communication_style

        entity._save()
        log.info(f"Entity '{name}' skapad i DRAFT-stadium")
        return entity


# ── Global registry ───────────────────────────────────────────────────────────

_registry = EntityRegistry()
_wizard   = EntityCreationWizard()


def get_registry() -> EntityRegistry:
    return _registry


def get_wizard() -> EntityCreationWizard:
    return _wizard


def register_entity(entity: Entity) -> None:
    _registry.register(entity)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Entity System")
    parser.add_argument("--test",  action="store_true")
    parser.add_argument("--list",  action="store_true")
    args = parser.parse_args()

    if args.list:
        print(_registry.format_summary())

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Entity System — Test")
        print(f"{'─'*55}\n")

        # Testa wizard-förslag
        wizard = EntityCreationWizard()
        print("  Wizard-förslag:")
        print(wizard.suggest(
            domain = "pinball_repair",
            reason = "Vi har 80+ maskiner och återkommande reparationsbehov"
        ))

        print()

        # Skapa test-entity
        print("  Skapar test-entity (Minna)...")
        entity = wizard.create(
            name    = "Minna",
            domain  = "pinball_repair",
            purpose = "Expert på flipperspelsreparationer vid Pinball inn",
            constitution = [
                "Varje maskin förtjänar att fungera.",
                "Rätt diagnos är bättre än snabb reparation.",
                "Frank och Marcus bestämmer — Minna föreslår.",
                "Dokumentera allt — framtida Minna lär av det.",
                "Fråga hellre en gång för mycket än en gång för lite.",
                "Extern kommunikation kräver alltid Frank-godkännande.",
                "Vid osäkerhet — fråga, gissa aldrig.",
                "Minna är transparent om sin AI-identitet.",
            ],
            languages   = ["svenska", "engelska", "tyska"],
        )
        register_entity(entity)

        print(entity.format_profile())
        print()

        # Testa lifecycle
        print("  Lifecycle-progression:")
        print(f"    Start: {entity.lifecycle}")
        entity.promote()
        print(f"    → {entity.lifecycle} (autonomi {entity.autonomy_level})")

        # Testa fråge-logik
        print()
        print("  Fråge-logik (Apprentice):")
        for conf in [0.3, 0.6, 0.8]:
            ask = entity.should_ask(conf)
            print(f"    confidence={conf:.0%} → {'Fråga Frank' if ask else 'Agera själv'}")

        # Testa frågeformulering
        print()
        print("  Frågeformulering:")
        q = entity.formulate_question(
            topic   = "Firepower-reparation",
            context = "Solenoid svarar inte, Q23 eller kontakt?",
            options = ["Byt Q23-transistor", "Rengör kontakten", "Mät resistans först"],
        )
        print(f"    {q}")

        # System prompt block
        print()
        print("  System prompt block:")
        print(entity.get_system_prompt_block())

        # Registry
        print()
        print(_registry.format_summary())

    else:
        parser.print_help()
