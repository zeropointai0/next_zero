"""
zero_decomposer.py — ZeroPointAI Goal Decomposer

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Analyserar mål, bryter ner problem, identifierar vad som saknas
ZERO_DEPENDS:   foundation.py, drm_memory.py, zero_perspective.py
ZERO_USED_BY:   zero_gear4.py, zero_specialization_engine.py

Filosofi:
    Innan Zero agerar måste Zero förstå.
    Decomposer ställer tre frågor:

        Vad är problemet egentligen?
        Vad vet vi redan?
        Vad saknas?

    Sedan bryter den ner målet i hanterbara delar
    och ger zero_specialization_engine.py rätt underlag
    för att välja bästa lösningsväg.

    Zero tänker högt:
        "Jag ser tre aspekter av det här problemet..."
        "Vi har redan kunskap om X men saknar Y..."
        "Det här verkar vara ett engångsbehov / återkommande..."
"""

from __future__ import annotations

import logging
import os
import re
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

# ── Decomposition result ──────────────────────────────────────────────────────

@dataclass
class GoalDecomposition:
    """
    Resultatet av en mål-analys.
    Används av zero_specialization_engine för att välja väg.
    """
    # Originalmål
    raw_goal:           str = ""

    # Vad är problemet egentligen?
    core_problem:       str = ""
    intent:             str = ""     # vad Frank egentligen vill uppnå
    success_criteria:   List[str] = field(default_factory=list)

    # Komplexitet
    complexity:         str = "simple"   # simple/moderate/complex
    is_recurring:       bool = False
    estimated_steps:    int = 1
    requires_research:  bool = False
    requires_learning:  bool = False
    requires_memory:    bool = False

    # Domän
    domain:             str = ""
    sub_domains:        List[str] = field(default_factory=list)
    related_entities:   List[str] = field(default_factory=list)

    # Vad vi vet / saknar
    known_context:      List[str] = field(default_factory=list)
    missing_context:    List[str] = field(default_factory=list)
    questions_for_frank: List[str] = field(default_factory=list)

    # Delmål
    sub_goals:          List[str] = field(default_factory=list)

    # Signaler för specialization engine
    specialization_signals: List[str] = field(default_factory=list)
    direct_solve_signals:   List[str] = field(default_factory=list)

    # Meta
    analyzed_at:        str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence:         float = 0.8

    def is_simple(self) -> bool:
        return (
            self.complexity == "simple"
            and not self.is_recurring
            and not self.requires_learning
            and self.estimated_steps <= 3
        )

    def needs_clarification(self) -> bool:
        return len(self.questions_for_frank) > 0 and self.confidence < 0.6

    def format_thinking(self) -> str:
        """
        Zero tänker högt — visas i chatten innan action.
        """
        lines = [f"Låt mig tänka igenom '{self.raw_goal[:60]}'...\n"]

        if self.core_problem:
            lines.append(f"**Kärnan:** {self.core_problem}")

        if self.intent:
            lines.append(f"**Egentliga målet:** {self.intent}")

        if self.known_context:
            lines.append(f"\n**Vad jag redan vet:**")
            for k in self.known_context[:3]:
                lines.append(f"  • {k}")

        if self.missing_context:
            lines.append(f"\n**Vad som saknas:**")
            for m in self.missing_context[:3]:
                lines.append(f"  • {m}")

        if self.sub_goals:
            lines.append(f"\n**Delmål:**")
            for i, sg in enumerate(self.sub_goals[:4], 1):
                lines.append(f"  {i}. {sg}")

        complexity_emoji = {"simple": "🟢", "moderate": "🟡", "complex": "🔴"}.get(
            self.complexity, "⚪"
        )
        lines.append(
            f"\n{complexity_emoji} Komplexitet: {self.complexity} | "
            f"Återkommande: {'Ja' if self.is_recurring else 'Nej'} | "
            f"Steg: ~{self.estimated_steps}"
        )

        return "\n".join(lines)


# ── Pattern-detektering ───────────────────────────────────────────────────────

# Signaler på att problemet är återkommande / kräver specialisering
RECURRING_PATTERNS = [
    r"\bhålla koll\b", r"\bskickar? (daglig|veckovis)\b",
    r"\balle? (maskiner|spel)\b",
    r"\bvarje (dag|vecka|månad|gång)\b",
    r"\bevery (day|week|month|time)\b",
    r"\bregelbundet\b", r"\bregularly\b",
    r"\bkontinuerligt\b", r"\bcontinuously\b",
    r"\bhålla koll\b", r"\bkeep track\b",
    r"\bmonitorera\b", r"\bmonitor\b",
    r"\bautomatisera\b", r"\bautomate\b",
    r"\blångsiktigt\b", r"\blong.?term\b",
    r"\bbygga upp\b", r"\bbuild up\b",
    r"\bspecialist\b", r"\bexpert\b",
]

# Signaler på att direkt lösning räcker
DIRECT_PATTERNS = [
    r"\b(visa|show|berätta|tell|förklara|explain)\b",
    r"\b(vad är|what is|hur fungerar|how does)\b",
    r"\b(räkna|calculate|konvertera|convert)\b",
    r"\b(sammanfatta|summarize|översätt|translate)\b",
    r"\b(sök|search|hitta|find)\b",
    r"\ben gång\b", r"\bonce\b",
    r"\bjust nu\b", r"\bright now\b",
    r"\bsnabbt\b", r"\bquickly\b",
]

# Signaler på att research behövs
RESEARCH_PATTERNS = [
    r"\bresearcha\b", r"\bresearch\b",
    r"\banalysera\b", r"\banalyze\b",
    r"\butred[a]?\b", r"\binvestigate\b",
    r"\bjämför\b", r"\bcompare\b",
    r"\bkolla upp\b", r"\blook up\b",
]

# Signaler på att lärande / minne behövs
LEARNING_PATTERNS = [
    r"\blär (sig|dig)\b", r"\blearn\b",
    r"\bkomma ihåg\b", r"\bremember\b",
    r"\bförbättra\b", r"\bimprove over time\b",
    r"\berfaren(het)?\b", r"\bexperience\b",
    r"\bträna\b", r"\btrain\b",
]

# Domän-detektering
DOMAIN_PATTERNS = {
    "pinball":     [r"\bflipp(er|ar)\b", r"\bpinball\b", r"\bmaskin(er)?\b", r"\breparera\b", r"\bsolenoid\b", r"\bfirepower\b"],
    "trading":     [r"\btrading\b", r"\bmarknad(er)?\b", r"\baktier?\b", r"\bcrypto\b"],
    "programming": [r"\bkod(a)?\b", r"\bprogram(mera)?\b", r"\bscript\b", r"\bpython\b"],
    "social_media":[r"\binstagram\b", r"\bfacebook\b", r"\btiktok\b", r"\binlägg\b"],
    "mail":        [r"\bmail\b", r"\bepost\b", r"\bemail\b"],
    "system":      [r"\bserver\b", r"\bservice\b", r"\bsystem(et)?\b", r"\bdatabas\b"],
}


def _match_patterns(text: str, patterns: List[str]) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


def _detect_domain(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for domain, patterns in DOMAIN_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_lower))
        if score > 0:
            scores[domain] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


# ── Decomposer ────────────────────────────────────────────────────────────────

class GoalDecomposer:
    """
    Analyserar ett mål och bryter ner det.
    Zero tänker högt om vad problemet egentligen är.
    """

    def analyze(
        self,
        goal:       str,
        context:    Optional[str] = None,
        entity_id:  str = "zero",
    ) -> GoalDecomposition:
        """
        Huvudfunktionen. Analyserar ett mål och returnerar decomposition.

        1. Detekterar mönster (recurring, direct, research, learning)
        2. Identifierar domän
        3. Bryter ner i sub-goals
        4. Hämtar relevant kontext från STONE
        5. Identifierar vad som saknas
        """
        d = GoalDecomposition(raw_goal=goal)

        goal_lower = goal.lower()

        # ── Grundläggande analys ──────────────────────────────────────────────

        d.is_recurring      = _match_patterns(goal, RECURRING_PATTERNS)
        d.requires_research = _match_patterns(goal, RESEARCH_PATTERNS)
        d.requires_learning = _match_patterns(goal, LEARNING_PATTERNS)
        d.domain            = _detect_domain(goal)

        # Recurring signaler
        if d.is_recurring:
            d.specialization_signals.append("Återkommande behov")
        if d.requires_learning:
            d.specialization_signals.append("Kräver lärande över tid")

        # Direct-signaler
        if _match_patterns(goal, DIRECT_PATTERNS) and not d.is_recurring:
            d.direct_solve_signals.append("Verkar vara ett direktsvar")

        # ── Komplexitet ───────────────────────────────────────────────────────

        complexity_score = 0
        if d.is_recurring:        complexity_score += 2
        if d.requires_research:   complexity_score += 1
        if d.requires_learning:   complexity_score += 2
        if len(goal.split()) > 20: complexity_score += 1
        if "och" in goal_lower or "and" in goal_lower: complexity_score += 1

        if complexity_score <= 1:
            d.complexity      = "simple"
            d.estimated_steps = 1
        elif complexity_score <= 3:
            d.complexity      = "moderate"
            d.estimated_steps = 3
        else:
            d.complexity      = "complex"
            d.estimated_steps = 7

        # ── Kärna och intent ──────────────────────────────────────────────────

        d.core_problem = self._extract_core(goal)
        d.intent       = self._extract_intent(goal)

        # ── Sub-goals ─────────────────────────────────────────────────────────

        d.sub_goals = self._decompose_to_subgoals(goal, d)

        # ── Kontext från STONE ────────────────────────────────────────────────

        d.known_context, d.missing_context = self._check_stone_context(
            goal, d.domain, entity_id
        )

        # ── Frågor för Frank ──────────────────────────────────────────────────

        if d.complexity == "complex" and not context:
            d.questions_for_frank = self._generate_clarifying_questions(goal, d)
            d.confidence = 0.6
        else:
            d.confidence = 0.85

        # ── Success criteria ──────────────────────────────────────────────────

        d.success_criteria = self._infer_success(goal, d)

        # ── Requires memory ───────────────────────────────────────────────────

        d.requires_memory = d.is_recurring or d.requires_learning

        log.info(
            f"Decomposed: '{goal[:40]}' → "
            f"complexity={d.complexity} "
            f"recurring={d.is_recurring} "
            f"domain={d.domain}"
        )

        return d

    def _extract_core(self, goal: str) -> str:
        """Extraherar kärnan av problemet."""
        # Rensa bort inledande fraser
        goal = re.sub(r"^(jag vill|jag behöver|kan du|please|hjälp mig)\s+", "",
                      goal.lower()).strip()
        # Kapitalisera
        return goal[:100].capitalize() if goal else goal

    def _extract_intent(self, goal: str) -> str:
        """Försöker förstå det egentliga syftet."""
        goal_lower = goal.lower()

        intent_map = [
            (r"\beffektivare\b|\bsnabbare\b",    "Effektivisera ett återkommande arbete"),
            (r"\bautomati[sz]era\b",              "Automatisera manuellt arbete"),
            (r"\bförstå\b|\blearn\b|\blär",       "Bygga kunskap och förståelse"),
            (r"\bhålla koll\b|\btrack\b",         "Skapa översikt och kontroll"),
            (r"\banalys[ae]\b|\banalyz",          "Ta informerade beslut baserat på analys"),
            (r"\bkommunicer[a]?\b|\bposta\b",     "Kommunicera mer effektivt"),
            (r"\blaga\b|\bfixa\b|\breparera\b",   "Lösa ett tekniskt problem"),
        ]

        for pattern, intent in intent_map:
            if re.search(pattern, goal_lower):
                return intent

        return "Lösa ett konkret problem"

    def _decompose_to_subgoals(
        self, goal: str, d: GoalDecomposition
    ) -> List[str]:
        """Bryter ner målet i delmål."""
        sub_goals = []

        if d.requires_research:
            sub_goals.append(f"Samla relevant information om {d.domain}")
        if d.requires_learning:
            sub_goals.append(f"Förstå grunderna i {d.domain}")
        if d.missing_context:
            sub_goals.append("Hämta saknad kontext")

        # Domänspecifika sub-goals
        if d.domain == "pinball":
            if "reparera" in goal.lower() or "fixa" in goal.lower():
                sub_goals += [
                    "Identifiera symptom",
                    "Diagnostisera möjliga orsaker",
                    "Föreslå lösning",
                ]
        elif d.domain == "trading":
            sub_goals += ["Hämta marknadsdata", "Analysera", "Sammanfatta"]

        if not sub_goals:
            sub_goals = [f"Analysera: {goal[:50]}", "Genomför", "Verifiera resultat"]

        return sub_goals[:6]

    def _check_stone_context(
        self, goal: str, domain: str, entity_id: str
    ) -> tuple[List[str], List[str]]:
        """Kollar STONE efter relevant kontext."""
        known   = []
        missing = []

        try:
            from app.drm_memory import search_memories
            results = search_memories(goal[:100], limit=3)
            if results:
                for r in results[:2]:
                    known.append(f"Minne: {r.get('content', '')[:80]}")
            else:
                missing.append(f"Ingen tidigare kunskap om '{domain}' i STONE")
        except Exception:
            missing.append("STONE ej tillgänglig")

        # Kolla perspectives
        try:
            from app.zero_perspective import get_perspective_manager
            mgr = get_perspective_manager(entity_id)
            perspectives = mgr.get_on_subject(goal[:30], domain)
            if perspectives:
                known.append(
                    f"{len(perspectives)} perspektiv på '{domain}' "
                    f"(säkerhet: {perspectives[0].effective_confidence():.0%})"
                )
            else:
                missing.append(f"Inga perspektiv på '{domain}'")
        except Exception:
            pass

        return known, missing

    def _generate_clarifying_questions(
        self, goal: str, d: GoalDecomposition
    ) -> List[str]:
        """Genererar frågor till Frank vid oklar input."""
        questions = []

        if d.complexity == "complex":
            questions.append(
                f"Är '{d.core_problem}' något som uppstår regelbundet, "
                f"eller är det ett engångsfall?"
            )
        if not d.success_criteria:
            questions.append("Hur vet du att det är löst? Vad ser framgång ut som?")
        if d.domain == "general":
            questions.append("Vilket område eller system rör detta?")

        return questions[:3]

    def _infer_success(self, goal: str, d: GoalDecomposition) -> List[str]:
        """Härleder framgångskriterier."""
        criteria = []

        if d.domain == "pinball":
            criteria.append("Maskinen fungerar korrekt")
            criteria.append("Felet är dokumenterat i STONE")
        elif d.domain == "trading":
            criteria.append("Analysen är klar och förstådd")
        elif d.domain == "social_media":
            criteria.append("Innehållet är publicerat på rätt plattform")
        else:
            criteria.append("Uppgiften är utförd och verifierad")
            criteria.append("Resultatet är sparat i STONE")

        return criteria


# ── Global instans ────────────────────────────────────────────────────────────

_decomposer = GoalDecomposer()


def decompose(
    goal:      str,
    context:   Optional[str] = None,
    entity_id: str = "zero",
) -> GoalDecomposition:
    """Publikt API — analyserar ett mål."""
    return _decomposer.analyze(goal, context, entity_id)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI Goal Decomposer")
    parser.add_argument("goal", nargs="?", help="Mål att analysera")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.goal:
        d = decompose(args.goal)
        print(d.format_thinking())

    elif args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero Decomposer — Test")
        print(f"{'─'*55}\n")

        test_goals = [
            "Visa GPU-temperaturen",
            "Hjälp mig reparera Firepower-flippret som har trasig vänster solenoid",
            "Jag vill att du håller koll på alla flipperspel och skickar en daglig rapport",
            "Analysera trading-strategier och lär dig vad som fungerar för mig",
            "Sammanfatta senaste nyheterna",
        ]

        for goal in test_goals:
            d = decompose(goal)
            print(f"Mål: {goal[:60]}")
            print(f"  Komplexitet:  {d.complexity}")
            print(f"  Återkommande: {'Ja' if d.is_recurring else 'Nej'}")
            print(f"  Domän:        {d.domain}")
            print(f"  Direkt:       {'Ja' if d.direct_solve_signals else 'Nej'}")
            print(f"  Specialisering: {'Ja' if d.specialization_signals else 'Nej'}")
            if d.sub_goals:
                print(f"  Delmål:       {', '.join(d.sub_goals[:2])}")
            print()

    else:
        parser.print_help()
