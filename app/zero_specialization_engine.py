"""
zero_specialization_engine.py — ZeroPointAI Specialization Engine

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Väljer bästa lösningsväg — DIRECT/FUNCTION/TASK/ENTITY
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_entity.py
ZERO_USED_BY:   zero_gear4.py

Filosofi:
    Specialization Engine svarar på en fråga:
    "Vad är den bästa långsiktiga lösningen?"

    Inte: "Hur löser jag detta just nu?"
    Utan: "Hur bör detta lösas — nu och i framtiden?"

    Fyra möjliga svar:

    DIRECT   → Zero löser direkt, ingen overhead
               "Visa GPU-temp" → kör nvidia-smi, svara

    FUNCTION → Zero skriver en funktion/script
               "Konvertera valuta" → skriv convert_currency()

    TASK     → Gear 4 kör ett strukturerat uppdrag
               "Analysera Firepower-felet" → task med steg

    ENTITY   → En specialist bör skapas
               "Håll koll på alla maskiner" → föreslå Entity

    Zero tänker högt om valet och förklarar varför.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
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

# ── Lösningsvägar ─────────────────────────────────────────────────────────────

PATHS = ("DIRECT", "FUNCTION", "TASK", "ENTITY")

PATH_DESCRIPTIONS = {
    "DIRECT":   "Löser direkt — snabbt, engång, ingen overhead",
    "FUNCTION": "Skriver en funktion — återanvändbar, teknisk lösning",
    "TASK":     "Kör ett strukturerat Gear 4-uppdrag — flera steg, research",
    "ENTITY":   "Skapar en specialist — långsiktig investering, lärande över tid",
}


# ── Recommendation ────────────────────────────────────────────────────────────

@dataclass
class SpecializationRecommendation:
    """Resultatet från specialization engine."""
    path:           str = "DIRECT"
    confidence:     float = 0.8
    reasons:        List[str] = field(default_factory=list)
    alternatives:   List[str] = field(default_factory=list)
    entity_domain:  str = ""
    entity_purpose: str = ""
    thinking:       str = ""
    recommended_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def format_thinking(self) -> str:
        """Zero tänker högt om sitt val."""
        lines = [
            f"**Rekommendation: {self.path}**",
            f"_{PATH_DESCRIPTIONS.get(self.path, '')}_",
            f"\n**Anledningar:**",
        ]
        for r in self.reasons:
            lines.append(f"  • {r}")

        if self.alternatives:
            lines.append(f"\n**Övervägde även:**")
            for a in self.alternatives:
                lines.append(f"  • {a}")

        if self.path == "ENTITY" and self.entity_domain:
            lines.append(
                f"\n**Entity-förslag:** Specialist inom '{self.entity_domain}'"
            )
            if self.entity_purpose:
                lines.append(f"**Syfte:** {self.entity_purpose}")
            lines.append(
                f"\nConfidence: {self.confidence:.0%} — "
                f"Vill du att vi brainstormar om detta?"
            )

        return "\n".join(lines)


# ── Specialization Engine ─────────────────────────────────────────────────────

class SpecializationEngine:
    """
    Utvärderar en GoalDecomposition och väljer lösningsväg.
    """

    def evaluate(
        self,
        decomposition: Any,   # GoalDecomposition
        entity_id: str = "zero",
    ) -> SpecializationRecommendation:
        """
        Väljer bästa lösningsväg baserat på decomposition.

        Logik:
            DIRECT   → simple, direkt, ingen recurring-signal
            FUNCTION → teknisk, återanvändbar, men inte recurring domän
            TASK     → moderate/complex, research, men inte recurring
            ENTITY   → recurring + learning + domän + long-term value
        """
        rec = SpecializationRecommendation()

        # Poängsystem
        scores = {path: 0.0 for path in PATHS}

        # ── DIRECT-signaler ───────────────────────────────────────────────────
        if decomposition.direct_solve_signals:
            scores["DIRECT"] += 3.0
            rec.reasons.append("Direktsvar räcker")

        if decomposition.complexity == "simple":
            scores["DIRECT"] += 2.0

        if not decomposition.is_recurring and not decomposition.requires_learning:
            scores["DIRECT"] += 1.0

        if decomposition.estimated_steps <= 1:
            scores["DIRECT"] += 1.0

        # ── FUNCTION-signaler ─────────────────────────────────────────────────
        if decomposition.domain in ("programming", "system"):
            scores["FUNCTION"] += 4.0
            rec.reasons.append("Teknisk uppgift — funktion är bäst")

        if decomposition.complexity == "simple" and not decomposition.direct_solve_signals:
            scores["FUNCTION"] += 1.5

        # ── TASK-signaler ─────────────────────────────────────────────────────
        if decomposition.requires_research:
            scores["TASK"] += 4.0
            rec.reasons.append("Kräver research och flera steg")

        if decomposition.domain == "pinball" and not decomposition.is_recurring:
            scores["TASK"] += 2.0

        if decomposition.complexity in ("moderate", "complex"):
            scores["TASK"] += 2.0

        if decomposition.estimated_steps >= 3:
            scores["TASK"] += 1.0

        if decomposition.missing_context:
            scores["TASK"] += 1.0

        # ── ENTITY-signaler ───────────────────────────────────────────────────
        entity_score = 0.0

        if decomposition.is_recurring:
            entity_score += 3.0
            rec.reasons.append("Återkommande behov")

        if decomposition.requires_learning:
            entity_score += 4.0
            rec.reasons.append("Kräver lärande och erfarenhet över tid")

        if decomposition.is_recurring and decomposition.requires_learning:
            entity_score += 3.0  # Bonus för kombination

        if decomposition.complexity == "complex":
            entity_score += 1.5

        if decomposition.domain not in ("general",):
            entity_score += 1.0
            rec.reasons.append(f"Tydlig domän: {decomposition.domain}")

        # Kolla om entity redan finns för denna domän
        existing = self._check_existing_entity(decomposition.domain, entity_id)
        if existing:
            entity_score -= 2.0  # Minska om entity redan finns
            rec.alternatives.append(
                f"Entity '{existing}' finns redan för {decomposition.domain}"
            )

        scores["ENTITY"] = entity_score

        # ── Välj väg ──────────────────────────────────────────────────────────
        chosen = max(scores, key=scores.get)
        rec.path       = chosen
        rec.confidence = min(0.95, scores[chosen] / (sum(scores.values()) or 1) * 2)

        # Alternativ
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        for path, score in sorted_scores[1:3]:
            if score > 0:
                rec.alternatives.append(
                    f"{path} ({score:.1f}p): {PATH_DESCRIPTIONS[path]}"
                )

        # Entity-specifik info
        if chosen == "ENTITY":
            rec.entity_domain  = decomposition.domain
            rec.entity_purpose = self._infer_entity_purpose(decomposition)
            if not rec.reasons:
                rec.reasons.append("Problemet motiverar en långsiktig specialist")

        # Confidence-justering
        if rec.confidence < 0.5:
            rec.confidence = 0.5
            rec.alternatives.append("Låg säkerhet — fråga Frank för klarhet")

        rec.thinking = rec.format_thinking()
        log.info(
            f"Specialization: {chosen} "
            f"(confidence={rec.confidence:.0%}) "
            f"for '{decomposition.raw_goal[:40]}'"
        )

        return rec

    def _check_existing_entity(self, domain: str, entity_id: str) -> Optional[str]:
        """Kollar om en entity för denna domän redan finns."""
        try:
            from app.zero_entity import get_registry
            registry = get_registry()
            for entity in registry.get_all():
                if domain.lower() in entity.profile.domain.lower():
                    return entity.name
        except Exception:
            pass
        return None

    def _infer_entity_purpose(self, decomposition: Any) -> str:
        """Härleder syftet med en potentiell entity."""
        domain = decomposition.domain
        intent = decomposition.intent

        domain_purposes = {
            "pinball":     "Expert på flipperspelsreparationer och underhåll",
            "trading":     "Specialist på marknadsanalys och trading-strategier",
            "programming": "Kodningsassistent med djup systemkännedom",
            "social_media": "Social media-strateg för Pinball inn",
        }

        if domain in domain_purposes:
            return domain_purposes[domain]

        return f"Specialist inom {domain}: {intent}"


# ── Kombinerad analys ─────────────────────────────────────────────────────────

def analyze_and_recommend(
    goal:      str,
    context:   Optional[str] = None,
    entity_id: str = "zero",
) -> tuple[Any, SpecializationRecommendation]:
    """
    Kombinerad funktion: decompose + evaluate.
    Returnerar (decomposition, recommendation).
    Används av Gear 4.
    """
    try:
        from app.zero_decomposer import decompose
    except ImportError:
        from zero_decomposer import decompose

    engine = SpecializationEngine()
    decomp = decompose(goal, context, entity_id)
    rec    = engine.evaluate(decomp, entity_id)
    return decomp, rec


# ── Global instans ────────────────────────────────────────────────────────────

_engine = SpecializationEngine()


def evaluate(decomposition: Any, entity_id: str = "zero") -> SpecializationRecommendation:
    return _engine.evaluate(decomposition, entity_id)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Specialization Engine")
    parser.add_argument("goal", nargs="?", help="Mål att analysera")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.goal:
        decomp, rec = analyze_and_recommend(args.goal)
        print(decomp.format_thinking())
        print()
        print(rec.format_thinking())

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Specialization Engine — Test")
        print(f"{'─'*55}\n")

        test_cases = [
            ("Visa GPU-temperaturen",
             "DIRECT"),
            ("Skriv ett script som konverterar bilder till webp",
             "FUNCTION"),
            ("Analysera varför Firepower-flipprets solenoid inte svarar",
             "TASK"),
            ("Håll koll på alla 80 flipperspel och skicka daglig rapport, lär dig maskinska fel",
             "ENTITY"),
        ]

        try:
            from zero_decomposer import decompose
        except ImportError:
            from app.zero_decomposer import decompose

        engine = SpecializationEngine()
        all_ok = True

        for goal, expected in test_cases:
            decomp = decompose(goal)
            rec    = engine.evaluate(decomp)
            ok     = rec.path == expected
            if not ok:
                all_ok = False
            status = "✓" if ok else "⚠"
            print(f"  {status} [{rec.path:<9}] {goal[:55]}")
            print(f"    confidence={rec.confidence:.0%} "
                  f"(förväntat: {expected})")
            if rec.reasons:
                print(f"    skäl: {rec.reasons[0]}")
            print()

        print(f"  {'Alla tester OK ✓' if all_ok else 'Notera: pattern-baserad analys, förbättras med LLM'}")

    else:
        parser.print_help()
