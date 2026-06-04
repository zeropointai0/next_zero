"""
zero_perspective.py — ZeroPointAI Perspective Layer

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Samlar perspektiv med kontext och säkerhet — aldrig "sanningar"
ZERO_DEPENDS:   foundation.py, drm_memory.py
ZERO_USED_BY:   zero_gear4.py, zero_identity_anchor.py

Filosofi:
    Zero äger inga sanningar.
    Zero samlar perspektiv.

    "17 källor har perspektivet att Q23 är trasig."
    "4 källor har ett annat perspektiv."
    "Frank observerade att Q23 fungerar — detta perspektiv
     är närmast verkligheten och väger tyngst."

    Alla perspektiv är giltiga från sin synvinkel.
    Frank bestämmer vad som är tillräckligt trovärdigt för att agera på.

    Tre principer:
    1. Direktobservation > Internet (Evidence > Theory)
    2. Nyare perspektiv > Äldre (Confidence decay)
    3. Frank > Allt annat (Reality Check)

    confidence_decay:
        effective_confidence = base_confidence * freshness_factor
        Sanning har en halveringstid. Perspektiv förfaller.

    reality_check:
        Om Frank observerar något direkt → override all andra perspektiv
        Frank's observation confidence = 1.0, decays very slowly
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
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

# Halveringstid för olika perspektiv-typer (dagar)
DECAY_HALFLIFE: Dict[str, float] = {
    "frank_observation":  365.0,  # Franks direktobservation — långsam decay
    "manual":             730.0,  # Officiell manual — mycket långsam
    "forum_consensus":     90.0,  # Forum-konsensus — medel
    "forum_single":        30.0,  # Enstaka forum-post — snabb
    "web_search":          14.0,  # Webbsökning — snabb
    "zero_inference":      60.0,  # Zeros egna slutledning — medel
    "unknown":             30.0,  # Okänd källa — snabb decay
}

# Källkvalitet-scores (0.0-1.0)
SOURCE_QUALITY: Dict[str, float] = {
    "frank_observation":  1.00,
    "manual":             0.95,
    "forum_consensus":    0.75,
    "forum_single":       0.50,
    "web_search":         0.60,
    "zero_inference":     0.70,
    "unknown":            0.40,
}

# Minimum confidence för att ett perspektiv ska visas
MIN_CONFIDENCE_THRESHOLD = 0.15


# ── Perspective datastruktur ──────────────────────────────────────────────────

@dataclass
class Perspective:
    """
    Ett perspektiv på ett ämne.
    Inte en sanning — ett perspektiv med kontext och säkerhet.
    """
    perspective_id:    str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    entity_id:         str = "zero"
    domain:            str = ""           # t.ex. "firepower", "general"
    subject:           str = ""           # vad perspektivet handlar om
    claim:             str = ""           # själva påståendet
    source_type:       str = "unknown"    # se DECAY_HALFLIFE
    source_detail:     str = ""           # specifik källbeskrivning
    base_confidence:   float = 0.5        # initial säkerhet
    evidence_count:    int = 1            # antal stödjande källor
    contradictions:    int = 0            # antal motstridiga perspektiv
    source_quality:    float = 0.5        # källans kvalitet
    frank_verified:    bool = False       # Frank har bekräftat
    frank_observation: bool = False       # Frank har observerat direkt
    created_at:        str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_updated_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_verified_at:  Optional[str] = None
    verification_horizon_days: float = 90.0  # hur länge perspektivet är relevant

    def effective_confidence(self) -> float:
        """
        Beräknar effektiv säkerhet med decay.
        effective_confidence = base_confidence * freshness_factor
        """
        if self.frank_observation:
            # Franks direktobservation decayar mycket långsamt
            halflife = DECAY_HALFLIFE["frank_observation"]
        else:
            halflife = DECAY_HALFLIFE.get(self.source_type, 30.0)

        # Beräkna ålder
        try:
            created = datetime.fromisoformat(
                self.last_updated_at.replace("Z", "+00:00")
            )
            age_days = (datetime.now(timezone.utc) - created).days
        except Exception:
            age_days = 0

        # Exponentiell decay: f = 0.5^(age/halflife)
        freshness = 0.5 ** (age_days / halflife) if halflife > 0 else 1.0

        # Justera för motstridigheter
        contradiction_penalty = min(0.3, self.contradictions * 0.05)

        raw = self.base_confidence * freshness * (1.0 - contradiction_penalty)
        return max(0.0, min(1.0, raw))

    def is_stale(self) -> bool:
        """Är perspektivet för gammalt för att vara relevant?"""
        return self.effective_confidence() < MIN_CONFIDENCE_THRESHOLD

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["effective_confidence"] = self.effective_confidence()
        d["is_stale"] = self.is_stale()
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Perspective":
        # Ta bort beräknade fält
        d = {k: v for k, v in d.items()
             if k not in ("effective_confidence", "is_stale")}
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})

    def __str__(self) -> str:
        conf = self.effective_confidence()
        stale = " [STALE]" if self.is_stale() else ""
        frank = " [FRANK✓]" if self.frank_observation else ""
        return (
            f"[{conf:.0%}]{frank}{stale} {self.claim[:60]} "
            f"({self.source_type}, {self.evidence_count} källor, "
            f"{self.contradictions} motstridiga)"
        )


# ── Perspective Manager ───────────────────────────────────────────────────────

class PerspectiveManager:
    """
    Hanterar perspektiv för en entity.
    Sparar i STONE + lokal JSON som fallback.
    """

    def __init__(self, entity_id: str = "zero"):
        self.entity_id   = entity_id
        self._store_file = (
            ZERO_ROOT / "data" / "perspectives" / f"{entity_id}_perspectives.json"
        )
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        self._perspectives: Dict[str, Perspective] = {}
        self._load()

    # ── Persistens ────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            data = {pid: p.to_dict() for pid, p in self._perspectives.items()}
            tmp  = self._store_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._store_file)
        except Exception as e:
            log.warning(f"perspective save: {e}")

    def _load(self) -> None:
        if not self._store_file.exists():
            return
        try:
            data = json.loads(self._store_file.read_text(encoding="utf-8"))
            self._perspectives = {
                pid: Perspective.from_dict(p) for pid, p in data.items()
            }
            log.debug(f"Loaded {len(self._perspectives)} perspectives for {self.entity_id}")
        except Exception as e:
            log.warning(f"perspective load: {e}")

    def _save_to_stone(self, p: Perspective) -> None:
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[perspective] domain={p.domain} "
                    f"subject={p.subject[:50]} "
                    f"confidence={p.effective_confidence():.2f} "
                    f"claim={p.claim[:100]}"
                ),
                source  = f"zero_perspective:{self.entity_id}",
            )
        except Exception:
            pass

    # ── Lägg till / uppdatera perspektiv ─────────────────────────────────────

    def add(
        self,
        domain:      str,
        subject:     str,
        claim:       str,
        source_type: str = "unknown",
        source_detail: str = "",
        confidence:  float = 0.5,
        frank_observation: bool = False,
    ) -> Perspective:
        """
        Lägger till ett nytt perspektiv eller uppdaterar ett befintligt.

        Om ett liknande perspektiv redan finns:
        - Om det stödjer → ökar evidence_count och confidence
        - Om det motsäger → ökar contradictions, justerar confidence

        Frank's direktobservation → override med confidence 1.0
        """
        # Hitta liknande perspektiv
        similar = self._find_similar(domain, subject, claim)

        if frank_observation:
            # Franks direktobservation — override allt
            if similar:
                # Uppdatera befintligt
                similar.base_confidence    = 1.0
                similar.frank_observation  = True
                similar.frank_verified     = True
                similar.source_type        = "frank_observation"
                similar.source_detail      = source_detail or "Frank observerade direkt"
                similar.evidence_count    += 1
                similar.last_updated_at    = datetime.now(timezone.utc).isoformat()
                similar.last_verified_at   = datetime.now(timezone.utc).isoformat()
                self._save()
                log.info(f"Frank observation updated: {similar}")
                return similar
            else:
                p = Perspective(
                    entity_id         = self.entity_id,
                    domain            = domain,
                    subject           = subject,
                    claim             = claim,
                    source_type       = "frank_observation",
                    source_detail     = source_detail or "Frank observerade direkt",
                    base_confidence   = 1.0,
                    source_quality    = 1.0,
                    frank_observation = True,
                    frank_verified    = True,
                    verification_horizon_days = 365.0,
                )
                self._perspectives[p.perspective_id] = p
                self._save()
                self._save_to_stone(p)
                log.info(f"Frank observation added: {p}")
                return p

        # Normalt perspektiv
        sq = SOURCE_QUALITY.get(source_type, 0.4)

        if similar:
            # Kontrollera om det stödjer eller motsäger
            supports = self._claims_agree(similar.claim, claim)
            if supports:
                # Stödjer — öka säkerhet
                similar.evidence_count += 1
                similar.base_confidence = min(
                    1.0,
                    similar.base_confidence + confidence * 0.1 * sq
                )
                similar.source_quality = (
                    similar.source_quality + sq
                ) / 2
                similar.last_updated_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return similar
            else:
                # Motsäger — öka contradictions
                similar.contradictions += 1
                similar.base_confidence = max(
                    0.1,
                    similar.base_confidence - 0.05
                )
                similar.last_updated_at = datetime.now(timezone.utc).isoformat()
                self._save()
                # Skapa också motstridigt perspektiv
                p = Perspective(
                    entity_id      = self.entity_id,
                    domain         = domain,
                    subject        = subject,
                    claim          = claim,
                    source_type    = source_type,
                    source_detail  = source_detail,
                    base_confidence = confidence * sq,
                    source_quality  = sq,
                    contradictions  = 1,
                )
                self._perspectives[p.perspective_id] = p
                self._save()
                return p

        # Nytt perspektiv
        p = Perspective(
            entity_id      = self.entity_id,
            domain         = domain,
            subject        = subject,
            claim          = claim,
            source_type    = source_type,
            source_detail  = source_detail,
            base_confidence = confidence * sq,
            source_quality  = sq,
        )
        self._perspectives[p.perspective_id] = p
        self._save()
        self._save_to_stone(p)
        log.info(f"Perspective added: {p}")
        return p

    def frank_observes(
        self,
        domain:  str,
        subject: str,
        claim:   str,
        detail:  str = "",
    ) -> Perspective:
        """
        Frank har observerat något direkt.
        Detta är det tyngst vägande perspektivet — override all teori.
        """
        log.info(f"Frank observation: {subject} → {claim[:60]}")
        return self.add(
            domain             = domain,
            subject            = subject,
            claim              = claim,
            source_type        = "frank_observation",
            source_detail      = detail,
            confidence         = 1.0,
            frank_observation  = True,
        )

    def frank_verifies(self, perspective_id: str) -> bool:
        """Frank bekräftar ett perspektiv utan att ange ny observation."""
        p = self._perspectives.get(perspective_id)
        if not p:
            return False
        p.frank_verified    = True
        p.base_confidence   = min(1.0, p.base_confidence + 0.2)
        p.last_verified_at  = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    # ── Hämta perspektiv ──────────────────────────────────────────────────────

    def get_on_subject(
        self,
        subject:    str,
        domain:     str = "",
        min_confidence: float = 0.0,
    ) -> List[Perspective]:
        """Hämtar alla perspektiv på ett ämne, sorterade efter effective_confidence."""
        results = []
        for p in self._perspectives.values():
            if subject.lower() not in p.subject.lower():
                continue
            if domain and domain.lower() not in p.domain.lower():
                continue
            if p.effective_confidence() < min_confidence:
                continue
            results.append(p)
        return sorted(results, key=lambda p: p.effective_confidence(), reverse=True)

    def get_stale(self) -> List[Perspective]:
        """Perspektiv som har förfallit och bör uppdateras."""
        return [p for p in self._perspectives.values() if p.is_stale()]

    def get_contested(self, min_contradictions: int = 2) -> List[Perspective]:
        """Perspektiv med många motstridigheter — osäker mark."""
        return [
            p for p in self._perspectives.values()
            if p.contradictions >= min_contradictions
        ]

    def get_frank_observations(self) -> List[Perspective]:
        """Perspektiv baserade på Franks direktobservationer."""
        return [p for p in self._perspectives.values() if p.frank_observation]

    # ── Hjälpfunktioner ───────────────────────────────────────────────────────

    def _find_similar(
        self, domain: str, subject: str, claim: str
    ) -> Optional[Perspective]:
        """Hittar ett liknande befintligt perspektiv."""
        subject_lower = subject.lower()
        for p in self._perspectives.values():
            if p.domain == domain and subject_lower in p.subject.lower():
                return p
        return None

    def _claims_agree(self, claim_a: str, claim_b: str) -> bool:
        """
        Enkel check om två påståenden stödjer varandra.
        Textbaserad — kan förbättras med embeddings.
        """
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()

        # Negationsord indikerar motsättning
        neg_words = [
            "inte", "nej", "fel", "wrong", "not ", "no ", "false",
            "fungerar inte", "doesn't work", "broken"
        ]
        a_neg = any(w in a_lower for w in neg_words)
        b_neg = any(w in b_lower for w in neg_words)

        # Samma negations-status → stödjer
        return a_neg == b_neg

    # ── Rapportering ──────────────────────────────────────────────────────────

    def summarize(
        self,
        subject:        str,
        domain:         str = "",
        max_items:      int = 5,
    ) -> str:
        """
        Sammanfattar Zero's perspektiv på ett ämne.
        Presenteras med säkerhet och källkontext.
        """
        perspectives = self.get_on_subject(subject, domain)

        if not perspectives:
            return f"Inga perspektiv på '{subject}' ännu."

        lines = [f"Zero's perspektiv på '{subject}':"]

        frank_obs = [p for p in perspectives if p.frank_observation]
        if frank_obs:
            lines.append(f"\n  Frank har observerat direkt:")
            for p in frank_obs[:2]:
                lines.append(f"    → {p.claim[:80]}")
                lines.append(f"      (säkerhet: {p.effective_confidence():.0%})")

        other = [p for p in perspectives if not p.frank_observation][:max_items]
        if other:
            lines.append(f"\n  Andra perspektiv:")
            for p in other:
                stale = " [FÖRFALLET]" if p.is_stale() else ""
                lines.append(
                    f"    • {p.effective_confidence():.0%} "
                    f"{p.claim[:70]}{stale}"
                )
                if p.contradictions > 0:
                    lines.append(
                        f"      ⚠ {p.contradictions} motstridiga perspektiv"
                    )

        contested = self.get_contested()
        if contested:
            lines.append(
                f"\n  ⚠ {len(contested)} osäkra perspektiv med motstridigheter"
            )

        return "\n".join(lines)

    def format_stats(self) -> str:
        total    = len(self._perspectives)
        stale    = len(self.get_stale())
        frank    = len(self.get_frank_observations())
        contested= len(self.get_contested())
        return (
            f"Perspektiv: {total} totalt, "
            f"{frank} från Frank, "
            f"{stale} förfallna, "
            f"{contested} osäkra"
        )


# ── Global instans ────────────────────────────────────────────────────────────

_managers: Dict[str, PerspectiveManager] = {}


def get_perspective_manager(entity_id: str = "zero") -> PerspectiveManager:
    if entity_id not in _managers:
        _managers[entity_id] = PerspectiveManager(entity_id)
    return _managers[entity_id]


# ── Publikt API ───────────────────────────────────────────────────────────────

def add_perspective(
    domain:      str,
    subject:     str,
    claim:       str,
    source_type: str   = "unknown",
    confidence:  float = 0.5,
    entity_id:   str   = "zero",
    **kwargs,
) -> Perspective:
    return get_perspective_manager(entity_id).add(
        domain=domain, subject=subject, claim=claim,
        source_type=source_type, confidence=confidence, **kwargs
    )


def frank_observes(
    domain:    str,
    subject:   str,
    claim:     str,
    detail:    str = "",
    entity_id: str = "zero",
) -> Perspective:
    """Frank har observerat något direkt — väger tyngst."""
    return get_perspective_manager(entity_id).frank_observes(
        domain=domain, subject=subject, claim=claim, detail=detail
    )


def summarize_perspectives(
    subject:   str,
    domain:    str = "",
    entity_id: str = "zero",
) -> str:
    return get_perspective_manager(entity_id).summarize(subject, domain)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Perspective Layer")
    parser.add_argument("--test",    action="store_true")
    parser.add_argument("--summary", metavar="SUBJECT")
    parser.add_argument("--entity",  default="zero")
    args = parser.parse_args()

    if args.summary:
        print(summarize_perspectives(args.summary, entity_id=args.entity))

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Perspective Layer — Test")
        print(f"{'─'*55}\n")

        mgr = get_perspective_manager("test_entity")

        # Lägg till forum-perspektiv
        print("  Lägger till forum-perspektiv...")
        for i in range(5):
            mgr.add(
                domain      = "pinball",
                subject     = "Firepower vänster flipper",
                claim       = "Solenoidspolen Q23 är ofta trasig",
                source_type = "forum_single",
                confidence  = 0.6,
            )

        # Lägg till motstridigt perspektiv
        mgr.add(
            domain      = "pinball",
            subject     = "Firepower vänster flipper",
            claim       = "Kontakten är trasig, inte spolen",
            source_type = "forum_single",
            confidence  = 0.5,
        )

        # Frank observerar direkt
        print("  Frank observerar direkt...")
        mgr.frank_observes(
            domain   = "pinball",
            subject  = "Firepower vänster flipper",
            claim    = "Q23-spolen mäter rätt resistans, kontakten är oxiderad",
            detail   = "Mätt med multimeter 2026-06-04",
        )

        # Visa sammanfattning
        print()
        print(mgr.summarize("Firepower vänster flipper"))
        print()
        print(f"  {mgr.format_stats()}")

        # Testa decay
        print(f"\n  Confidence decay test:")
        p = Perspective(
            claim          = "Test-perspektiv",
            source_type    = "forum_single",
            base_confidence = 0.8,
        )
        print(f"    Dag 0:   {p.effective_confidence():.2%}")
        p.last_updated_at = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat()
        print(f"    Dag 30:  {p.effective_confidence():.2%}")
        p.last_updated_at = (
            datetime.now(timezone.utc) - timedelta(days=90)
        ).isoformat()
        print(f"    Dag 90:  {p.effective_confidence():.2%} "
              f"{'[STALE]' if p.is_stale() else ''}")

    else:
        parser.print_help()
