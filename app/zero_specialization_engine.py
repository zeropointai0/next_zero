#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_specialization_engine.py — ZeroPointAI Specialization Engine v2.0

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Väljer bästa lösningsväg: DIRECT / FUNCTION / TASK / ENTITY
ZERO_DEPENDS:   foundation.py, zero_decomposer.py, zero_entity_wizard.py
ZERO_USED_BY:   zero_gear4.py, zero_router.py

Kärnfråga:
    "Vad är den bästa långsiktiga lösningen?"

Inte bara:
    "Hur svarar jag snabbast?"

Gear 4 använder denna modul direkt efter zero_decomposer.py.

Pipeline:
    goal
      ↓
    zero_decomposer.decompose(goal)
      ↓
    zero_specialization_engine.evaluate(decomposition)
      ↓
    Recommendation(path=...)
      ↓
    zero_gear4 route:
        DIRECT   → svara direkt
        FUNCTION → bygg/förbättra funktion/modul
        TASK     → kör Gear 4 mission runner
        ENTITY   → starta Draft Entity / Entity Wizard

Routing Contract v1.0:
    Recommendation(
        path: DIRECT | FUNCTION | TASK | ENTITY,
        confidence: float,
        reason: str,
        next_action: str,
        ask_frank: bool
    )

Confidence-regler:
    confidence >= 0.90:
        Gear 4 får gå vidare själv.
        Om ENTITY: skapa bara DRAFT entity, aldrig ACTIVE direkt.

    0.65 <= confidence < 0.90:
        Gear 4 föreslår vägen och frågar Frank.

    confidence < 0.65:
        Gear 4 frågar Frank innan något skapas/körs.

Filosofi:
    DIRECT:
        Lös direkt. Ingen overhead.

    FUNCTION:
        Problemet är återkommande men avgränsat nog för kod.
        En funktion/modul är bättre än en Entity.

    TASK:
        Problemet kräver flera steg men är finite.
        Gear 4 kör ett uppdrag, checkpointar och avslutar.

    ENTITY:
        Problemet är en långsiktig domän med återkommande behov,
        inlärningskurva, specialiserat minne och tydlig framtida nytta.

Viktig regel:
    ENTITY betyder aldrig "släpp lös en agent".
    ENTITY betyder "create DRAFT entity" eller "starta Entity Creation Wizard".
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> None:
        return None


log = logging.getLogger(__name__)

try:
    from app.foundation import ZERO_ROOT
except Exception:
    ZERO_ROOT = Path(os.getenv("ZERO_ROOT", "/opt/zeropointai"))

ZERO_ROOT = Path(ZERO_ROOT)
load_dotenv(ZERO_ROOT / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Paths / constants
# ─────────────────────────────────────────────────────────────────────────────

class SolutionPath(str, Enum):
    DIRECT = "DIRECT"
    FUNCTION = "FUNCTION"
    TASK = "TASK"
    ENTITY = "ENTITY"


PATH_ORDER = [
    SolutionPath.DIRECT,
    SolutionPath.FUNCTION,
    SolutionPath.TASK,
    SolutionPath.ENTITY,
]

PATH_DESCRIPTIONS: Dict[str, str] = {
    "DIRECT": (
        "Zero löser direkt i chatten. Låg overhead, snabbt, normalt engångsbehov."
    ),
    "FUNCTION": (
        "Zero bygger eller förbättrar en återanvändbar funktion/modul. "
        "Teknisk lösning, inte en långsiktig specialist."
    ),
    "TASK": (
        "Gear 4 kör ett strukturerat uppdrag steg-för-steg. "
        "Flera steg, research, checkpoints, men finite."
    ),
    "ENTITY": (
        "Zero rekommenderar en Draft Entity. "
        "Långsiktig specialist med egen constitution, minne och studieplan."
    ),
}

CONFIDENCE_AUTO = 0.90
CONFIDENCE_ASK = 0.65


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation data
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PathScore:
    """Intern score för en lösningsväg."""
    path: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def add(self, amount: float, reason: str) -> None:
        if amount <= 0:
            return
        self.score += amount
        if reason and reason not in self.reasons:
            self.reasons.append(reason)


@dataclass
class SpecializationRecommendation:
    """
    Gear 4 Routing Recommendation.

    Detta objekt är kontraktet mellan:
        zero_decomposer.py
        zero_specialization_engine.py
        zero_gear4.py
        zero_entity_wizard.py
    """
    path: str = "DIRECT"
    confidence: float = 0.80

    # One-line explanation.
    reason: str = ""

    # Detailed reasoning.
    reasons: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    scorecard: Dict[str, float] = field(default_factory=dict)

    # What should Gear 4 do next?
    next_action: str = "answer_directly"
    ask_frank: bool = False

    # Entity-specific draft recommendation.
    entity_name: str = ""
    entity_domain: str = ""
    entity_purpose: str = ""
    entity_status: str = "DRAFT"
    entity_confidence: float = 0.0
    entity_rationale: List[str] = field(default_factory=list)

    # Function-specific.
    function_name: str = ""
    function_purpose: str = ""

    # Task-specific.
    suggested_steps: List[str] = field(default_factory=list)

    # Safety/governance.
    autonomy_level: str = "low"  # low / medium / high
    requires_review: bool = False

    # Meta.
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "zero_specialization_engine:v2"

    @property
    def should_auto_execute(self) -> bool:
        """True om Gear 4 får gå vidare utan att fråga Frank."""
        return self.confidence >= CONFIDENCE_AUTO and not self.ask_frank

    @property
    def should_ask_frank(self) -> bool:
        return self.ask_frank

    @property
    def is_entity_recommendation(self) -> bool:
        return self.path == SolutionPath.ENTITY.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    def format_for_frank(self) -> str:
        """Kort, chat-vänlig presentation."""
        lines = [
            f"**Gear 4 rekommendation: {self.path}**",
            f"Confidence: {self.confidence:.0%}",
            "",
            self.reason or PATH_DESCRIPTIONS.get(self.path, ""),
        ]

        if self.reasons:
            lines.append("\n**Varför:**")
            for reason in self.reasons[:6]:
                lines.append(f"• {reason}")

        if self.alternatives:
            lines.append("\n**Jag övervägde också:**")
            for alt in self.alternatives[:4]:
                lines.append(f"• {alt}")

        if self.path == "ENTITY":
            lines.append("\n**Draft Entity-förslag:**")
            lines.append(f"• Namn: {self.entity_name or 'Ej bestämt'}")
            lines.append(f"• Domän: {self.entity_domain or 'okänd'}")
            lines.append(f"• Syfte: {self.entity_purpose or 'behöver brainstormas'}")
            lines.append(f"• Status: {self.entity_status}")
            if self.ask_frank:
                lines.append("\nJag föreslår att vi brainstormar detta tillsammans innan skapande.")
            else:
                lines.append("\nJag kan skapa en **DRAFT** entity och meddela Frank efteråt.")

        elif self.path == "FUNCTION":
            lines.append("\n**Funktionsförslag:**")
            lines.append(f"• Namn: {self.function_name or 'auto_generated_function'}")
            lines.append(f"• Syfte: {self.function_purpose or 'återanvändbar teknisk lösning'}")

        elif self.path == "TASK" and self.suggested_steps:
            lines.append("\n**Föreslagna steg:**")
            for i, step in enumerate(self.suggested_steps[:6], 1):
                lines.append(f"{i}. {step}")

        lines.append(f"\n**Nästa action:** `{self.next_action}`")
        return "\n".join(lines)


# Backwards-compatible alias.
Recommendation = SpecializationRecommendation


# ─────────────────────────────────────────────────────────────────────────────
# Pattern helpers
# ─────────────────────────────────────────────────────────────────────────────

FUNCTION_PATTERNS = [
    r"\b(script|skript|funktion|function|modul|module|api|endpoint|parser|scanner|validator)\b",
    r"\b(automatisera|automate|konvertera|convert|exportera|importera|generera|generate)\b",
    r"\b(refaktorera|refactor|patcha|patch|bygg|build|implementera|implement)\b",
    r"\bpython\b|\bjavascript\b|\bhtml\b|\bsql\b|\bbash\b",
]

ENTITY_STRONG_PATTERNS = [
    r"\bhålla koll\b|\bkeep track\b",
    r"\bvarje dag\b|\bvarje vecka\b|\bdaglig\b|\bveckovis\b",
    r"\bevery day\b|\bevery week\b|\bdaily\b|\bweekly\b",
    r"\blär(a| sig)? över tid\b|\blearn over time\b",
    r"\bspecialist\b|\bexpert\b|\bmentor\b|\bentity\b|\bentitet\b",
    r"\bstudera\b|\bstudy\b|\bträna\b|\btrain\b",
    r"\blångsiktigt\b|\blong.?term\b",
    r"\båterkommande\b|\brecurring\b",
]

TASK_PATTERNS = [
    r"\banalysera\b|\banalyze\b",
    r"\bresearch(a)?\b|\butreda?\b|\binvestigate\b",
    r"\bjämför\b|\bcompare\b",
    r"\bkolla upp\b|\blook up\b",
    r"\bgå igenom\b|\breview\b",
]

DIRECT_PATTERNS = [
    r"^(vad|what|hur|how|var|where|när|when)\b",
    r"\bförklara\b|\bexplain\b",
    r"\bvisa\b|\bshow\b",
    r"\bsnabbt\b|\bquick\b",
    r"\bjust nu\b|\bright now\b",
    r"\ben gång\b|\bonce\b",
]

KNOWN_DOMAINS = {
    "pinball": ["flipper", "pinball", "williams", "bally", "stern", "gottlieb", "solenoid", "firepower"],
    "trading": ["trading", "trade", "market", "marknad", "crypto", "aktie", "tradingview", "wyckoff", "ict"],
    "social_media": ["facebook", "instagram", "tiktok", "inlägg", "post", "social"],
    "programming": ["kod", "code", "python", "javascript", "html", "sql", "api", "server"],
    "system": ["linux", "ubuntu", "systemd", "server", "databas", "postgres", "docker"],
    "pinball_inn": ["pinball inn", "bokning", "bookspot", "spelhall", "drop-in", "flipperspel"],
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _match_any(text: str, patterns: Iterable[str]) -> bool:
    blob = text.lower()
    return any(re.search(pattern, blob, flags=re.IGNORECASE) for pattern in patterns)


def _count_matches(text: str, patterns: Iterable[str]) -> int:
    blob = text.lower()
    return sum(1 for pattern in patterns if re.search(pattern, blob, flags=re.IGNORECASE))


def _detect_domain_from_text(text: str, fallback: str = "general") -> str:
    blob = text.lower()
    scores: Dict[str, int] = {}
    for domain, words in KNOWN_DOMAINS.items():
        score = sum(1 for w in words if w.lower() in blob)
        if score:
            scores[domain] = score
    if not scores:
        return fallback or "general"
    return max(scores, key=scores.get)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Specialization Engine
# ─────────────────────────────────────────────────────────────────────────────

class SpecializationEngine:
    """
    Väljer bästa lösningsväg för ett mål.

    Designmål:
        - Deterministisk nog för testning.
        - Tydlig nog att andra AI-system kan förstå.
        - Konservativ kring ENTITY: entity = DRAFT först.
        - Inte feg: hög confidence får agera.
        - Men fråga Frank när uncertainty är verklig.
    """

    def evaluate(
        self,
        decomposition: Any,
        entity_id: str = "zero",
        context: Optional[str] = None,
    ) -> SpecializationRecommendation:
        """
        Returnerar SpecializationRecommendation.

        decomposition förväntas vara GoalDecomposition från zero_decomposer.py,
        men motorn accepterar också enklare objekt/dicts så att den kan testas
        separat av Grok/Claude/ChatGPT.
        """
        facts = self._extract_facts(decomposition, context=context)
        scores = self._score_paths(facts, entity_id=entity_id)
        chosen_path, confidence = self._choose_path(scores, facts)

        rec = self._build_recommendation(
            chosen_path=chosen_path,
            confidence=confidence,
            facts=facts,
            scores=scores,
            entity_id=entity_id,
        )

        log.info(
            "Specialization recommendation: %s confidence=%.2f goal=%r",
            rec.path,
            rec.confidence,
            facts["goal"][:80],
        )
        return rec

    # ── Fact extraction ──────────────────────────────────────────────────────

    def _extract_facts(self, decomposition: Any, context: Optional[str] = None) -> Dict[str, Any]:
        """Normaliserar GoalDecomposition/dict/string till fakta."""
        if isinstance(decomposition, str):
            goal = decomposition
            d: Dict[str, Any] = {}
        elif isinstance(decomposition, dict):
            d = dict(decomposition)
            goal = _as_text(d.get("raw_goal") or d.get("goal") or d.get("input") or "")
        else:
            d = {
                "raw_goal": getattr(decomposition, "raw_goal", ""),
                "core_problem": getattr(decomposition, "core_problem", ""),
                "intent": getattr(decomposition, "intent", ""),
                "success_criteria": getattr(decomposition, "success_criteria", []),
                "complexity": getattr(decomposition, "complexity", "simple"),
                "is_recurring": getattr(decomposition, "is_recurring", False),
                "estimated_steps": getattr(decomposition, "estimated_steps", 1),
                "requires_research": getattr(decomposition, "requires_research", False),
                "requires_learning": getattr(decomposition, "requires_learning", False),
                "requires_memory": getattr(decomposition, "requires_memory", False),
                "domain": getattr(decomposition, "domain", ""),
                "sub_domains": getattr(decomposition, "sub_domains", []),
                "related_entities": getattr(decomposition, "related_entities", []),
                "known_context": getattr(decomposition, "known_context", []),
                "missing_context": getattr(decomposition, "missing_context", []),
                "questions_for_frank": getattr(decomposition, "questions_for_frank", []),
                "sub_goals": getattr(decomposition, "sub_goals", []),
                "specialization_signals": getattr(decomposition, "specialization_signals", []),
                "direct_solve_signals": getattr(decomposition, "direct_solve_signals", []),
                "confidence": getattr(decomposition, "confidence", 0.8),
            }
            goal = _as_text(d.get("raw_goal", ""))

        text_blob = " ".join([
            goal,
            _as_text(d.get("core_problem", "")),
            _as_text(d.get("intent", "")),
            _as_text(context or ""),
            _as_text(d.get("sub_goals", [])),
            _as_text(d.get("specialization_signals", [])),
            _as_text(d.get("direct_solve_signals", [])),
        ])

        domain = _as_text(d.get("domain", "")).strip() or _detect_domain_from_text(text_blob)
        if domain in {"", "none", "null"}:
            domain = "general"

        complexity = _as_text(d.get("complexity", "simple")).lower()
        if complexity not in {"simple", "moderate", "complex"}:
            complexity = "moderate"

        facts = {
            "goal": goal.strip(),
            "core_problem": _as_text(d.get("core_problem", "")).strip(),
            "intent": _as_text(d.get("intent", "")).strip(),
            "success_criteria": list(d.get("success_criteria", []) or []),
            "complexity": complexity,
            "is_recurring": bool(d.get("is_recurring", False)) or _match_any(text_blob, ENTITY_STRONG_PATTERNS[:8]),
            "estimated_steps": _safe_int(d.get("estimated_steps", 1), 1),
            "requires_research": bool(d.get("requires_research", False)) or _match_any(text_blob, TASK_PATTERNS),
            "requires_learning": bool(d.get("requires_learning", False)) or _match_any(text_blob, ENTITY_STRONG_PATTERNS),
            "requires_memory": bool(d.get("requires_memory", False)),
            "domain": domain,
            "sub_domains": list(d.get("sub_domains", []) or []),
            "related_entities": list(d.get("related_entities", []) or []),
            "known_context": list(d.get("known_context", []) or []),
            "missing_context": list(d.get("missing_context", []) or []),
            "questions_for_frank": list(d.get("questions_for_frank", []) or []),
            "sub_goals": list(d.get("sub_goals", []) or []),
            "specialization_signals": list(d.get("specialization_signals", []) or []),
            "direct_solve_signals": list(d.get("direct_solve_signals", []) or []),
            "decomposition_confidence": _safe_float(d.get("confidence", 0.8), 0.8),
            "text_blob": text_blob,
        }

        # Extra derived signals.
        facts["function_signal_count"] = _count_matches(text_blob, FUNCTION_PATTERNS)
        facts["entity_signal_count"] = _count_matches(text_blob, ENTITY_STRONG_PATTERNS)
        facts["task_signal_count"] = _count_matches(text_blob, TASK_PATTERNS)
        facts["direct_signal_count"] = _count_matches(text_blob, DIRECT_PATTERNS)

        # Some goals explicitly say "create entity"; respect as strong but still Draft.
        facts["explicit_entity_request"] = bool(re.search(r"\b(entity|entitet)\b", text_blob, flags=re.IGNORECASE))

        # Long-term value signal: recurring + learning/memory/domain.
        facts["long_term_value"] = (
            facts["is_recurring"]
            and (facts["requires_learning"] or facts["requires_memory"] or facts["domain"] not in {"general"})
        )

        # Finite mission signal.
        facts["finite_multistep"] = (
            facts["requires_research"]
            or facts["estimated_steps"] >= 3
            or facts["complexity"] in {"moderate", "complex"}
        ) and not facts["long_term_value"]

        return facts

    # ── Scoring ──────────────────────────────────────────────────────────────

    def _score_paths(self, facts: Dict[str, Any], entity_id: str = "zero") -> Dict[str, PathScore]:
        scores = {path.value: PathScore(path.value) for path in SolutionPath}
        goal = facts["goal"]
        text = facts["text_blob"]

        # DIRECT: immediate, simple, no long-term value.
        if facts["direct_solve_signals"] or facts["direct_signal_count"] > 0:
            scores["DIRECT"].add(2.8, "Direktsvarssignal i målet")
        if facts["complexity"] == "simple":
            scores["DIRECT"].add(2.2, "Låg komplexitet")
        if facts["estimated_steps"] <= 1:
            scores["DIRECT"].add(1.3, "Kan lösas i ett steg")
        if not facts["is_recurring"] and not facts["requires_learning"] and not facts["requires_memory"]:
            scores["DIRECT"].add(1.2, "Ingen tydlig långsiktig nytta")

        # FUNCTION: recurring/technical but bounded as code.
        if facts["function_signal_count"]:
            scores["FUNCTION"].add(2.0 + facts["function_signal_count"] * 0.7, "Teknisk kod-/funktionssignal")
        if facts["domain"] in {"programming", "system"}:
            scores["FUNCTION"].add(2.4, f"Teknisk domän: {facts['domain']}")
        if facts["is_recurring"] and not facts["requires_learning"]:
            scores["FUNCTION"].add(1.6, "Återkommande men kräver inte långsiktig lärling")
        if re.search(r"\b(scanner|parser|validator|export|import|backup|rapport|report)\b", text, re.IGNORECASE):
            scores["FUNCTION"].add(1.6, "Avgränsad automatisering passar funktion/modul")
        if facts["explicit_entity_request"]:
            scores["FUNCTION"].add(0.0, "")  # no-op, explicit for readability

        # TASK: finite multi-step mission.
        if facts["task_signal_count"]:
            scores["TASK"].add(2.0 + facts["task_signal_count"] * 0.6, "Research-/analys-signal")
        if facts["finite_multistep"]:
            scores["TASK"].add(2.5, "Flera steg men finite uppdrag")
        if facts["requires_research"]:
            scores["TASK"].add(2.0, "Kräver research")
        if facts["estimated_steps"] >= 3:
            scores["TASK"].add(1.2, f"Beräknat {facts['estimated_steps']} steg")
        if facts["missing_context"]:
            scores["TASK"].add(0.8, "Saknar kontext som kan hämtas under uppdrag")

        # ENTITY: long-term specialization.
        if facts["explicit_entity_request"]:
            scores["ENTITY"].add(2.0, "Användaren nämner Entity/entitet")
        if facts["entity_signal_count"]:
            scores["ENTITY"].add(1.4 + facts["entity_signal_count"] * 0.8, "Specialiserings-/lärandesignal")
        if facts["is_recurring"]:
            scores["ENTITY"].add(2.5, "Återkommande behov")
        if facts["requires_learning"]:
            scores["ENTITY"].add(2.8, "Kräver lärande över tid")
        if facts["requires_memory"]:
            scores["ENTITY"].add(1.2, "Kräver specialiserat minne")
        if facts["long_term_value"]:
            scores["ENTITY"].add(2.5, "Tydlig långsiktig nytta")
        if facts["domain"] not in {"general", "programming", "system"}:
            scores["ENTITY"].add(1.2, f"Tydlig specialistdomän: {facts['domain']}")
        if facts["complexity"] == "complex" and facts["is_recurring"]:
            scores["ENTITY"].add(1.4, "Komplex återkommande domän")

        # Existing entity should reduce ENTITY and suggest using it instead.
        existing = self._find_existing_entity(facts["domain"], entity_id)
        if existing:
            scores["ENTITY"].score = max(0.0, scores["ENTITY"].score - 2.5)
            scores["TASK"].add(1.5, f"Använd befintlig Entity: {existing}")
            facts["existing_entity"] = existing
        else:
            facts["existing_entity"] = ""

        # Anti-entity guardrails: if it looks one-off/simple, ENTITY must not win easily.
        if facts["complexity"] == "simple" and not facts["is_recurring"] and not facts["explicit_entity_request"]:
            scores["ENTITY"].score *= 0.35
            scores["ENTITY"].reasons.append("Entity nedviktad: enkel engångsuppgift")

        # If it is clearly a code module, FUNCTION should beat ENTITY unless learning is strong.
        if scores["FUNCTION"].score >= 4 and not facts["requires_learning"]:
            scores["ENTITY"].score *= 0.55
            scores["ENTITY"].reasons.append("Entity nedviktad: funktion/modul verkar räcka")

        return scores

    def _choose_path(
        self,
        scores: Dict[str, PathScore],
        facts: Dict[str, Any],
    ) -> Tuple[str, float]:
        total = sum(max(0.0, s.score) for s in scores.values()) or 1.0
        sorted_scores = sorted(scores.values(), key=lambda s: s.score, reverse=True)
        best = sorted_scores[0]
        second = sorted_scores[1] if len(sorted_scores) > 1 else PathScore("DIRECT", 0.0)

        # Confidence combines dominance, decomposition confidence and absolute strength.
        dominance = max(0.0, best.score - second.score)
        confidence = 0.50
        confidence += min(0.25, dominance / 10.0)
        confidence += min(0.15, best.score / 20.0)
        confidence += (facts.get("decomposition_confidence", 0.8) - 0.5) * 0.20

        # Strong explicit evidence can lift confidence.
        if best.path == "ENTITY" and facts["long_term_value"] and best.score >= 7.0:
            confidence += 0.10
        if best.path == "DIRECT" and facts["complexity"] == "simple" and best.score >= 5.0:
            confidence += 0.08
        if best.path == "FUNCTION" and facts["function_signal_count"] >= 2:
            confidence += 0.08
        if best.path == "TASK" and facts["requires_research"] and facts["estimated_steps"] >= 3:
            confidence += 0.06

        # Ambiguous if scores are close.
        if dominance < 1.2:
            confidence -= 0.12

        # Missing context lowers confidence.
        if facts["questions_for_frank"]:
            confidence -= 0.10
        if len(facts["missing_context"]) >= 2:
            confidence -= 0.05

        confidence = max(0.45, min(0.97, confidence))

        # Force direct for trivial tiny questions unless explicit task/entity.
        if (
            facts["complexity"] == "simple"
            and facts["estimated_steps"] <= 1
            and not facts["is_recurring"]
            and not facts["explicit_entity_request"]
            and scores["DIRECT"].score >= 4.0
        ):
            return "DIRECT", max(confidence, 0.88)

        return best.path, confidence

    # ── Recommendation construction ──────────────────────────────────────────

    def _build_recommendation(
        self,
        chosen_path: str,
        confidence: float,
        facts: Dict[str, Any],
        scores: Dict[str, PathScore],
        entity_id: str,
    ) -> SpecializationRecommendation:
        best_score = scores[chosen_path]
        rec = SpecializationRecommendation(
            path=chosen_path,
            confidence=round(confidence, 3),
            reasons=list(best_score.reasons),
            scorecard={path: round(score.score, 2) for path, score in scores.items()},
        )

        rec.reason = self._make_primary_reason(chosen_path, facts, best_score)
        rec.alternatives = self._make_alternatives(chosen_path, scores)

        # Ask Frank rules.
        if confidence < CONFIDENCE_ASK:
            rec.ask_frank = True
            rec.requires_review = True
            rec.reason = rec.reason + " Säkerheten är låg, så Frank bör avgöra riktning."
        elif confidence < CONFIDENCE_AUTO:
            rec.ask_frank = True
            rec.requires_review = True

        # Path-specific metadata.
        if chosen_path == "DIRECT":
            rec.next_action = "answer_directly"
            rec.autonomy_level = "high" if confidence >= CONFIDENCE_AUTO else "medium"

        elif chosen_path == "FUNCTION":
            rec.next_action = "propose_or_build_function"
            rec.function_name = self._suggest_function_name(facts)
            rec.function_purpose = self._suggest_function_purpose(facts)
            rec.autonomy_level = "medium" if confidence >= CONFIDENCE_AUTO else "low"

        elif chosen_path == "TASK":
            rec.next_action = "create_gear4_task"
            rec.suggested_steps = self._suggest_task_steps(facts)
            rec.autonomy_level = "medium" if confidence >= CONFIDENCE_AUTO else "low"

        elif chosen_path == "ENTITY":
            rec.next_action = "create_draft_entity" if confidence >= CONFIDENCE_AUTO else "start_entity_wizard"
            rec.entity_domain = facts["domain"] or _detect_domain_from_text(facts["text_blob"])
            rec.entity_name = self._suggest_entity_name(facts)
            rec.entity_purpose = self._suggest_entity_purpose(facts)
            rec.entity_confidence = rec.confidence
            rec.entity_rationale = list(best_score.reasons)
            rec.entity_status = "DRAFT"
            rec.autonomy_level = "low"
            # Even with high confidence, this only creates DRAFT, never ACTIVE.
            if confidence < CONFIDENCE_AUTO:
                rec.ask_frank = True
                rec.requires_review = True

        # If there is existing entity, do not create new one automatically.
        if chosen_path == "ENTITY" and facts.get("existing_entity"):
            rec.ask_frank = True
            rec.requires_review = True
            rec.next_action = "consult_existing_entity_or_wizard"
            rec.reasons.append(f"Befintlig Entity hittades: {facts['existing_entity']}")

        return rec

    def _make_primary_reason(self, path: str, facts: Dict[str, Any], score: PathScore) -> str:
        if path == "DIRECT":
            return "Detta verkar bäst lösas direkt utan extra arkitektur."
        if path == "FUNCTION":
            return "Detta verkar vara ett återanvändbart tekniskt problem som passar bättre som funktion/modul än Entity."
        if path == "TASK":
            return "Detta kräver flera steg/research men är fortfarande ett avgränsat uppdrag."
        if path == "ENTITY":
            return "Detta verkar vara en återkommande domän där en specialist kan bli bättre över tid."
        return PATH_DESCRIPTIONS.get(path, "Okänd rekommendation.")

    def _make_alternatives(self, chosen: str, scores: Dict[str, PathScore]) -> List[str]:
        out: List[str] = []
        for item in sorted(scores.values(), key=lambda s: s.score, reverse=True):
            if item.path == chosen or item.score <= 0:
                continue
            out.append(f"{item.path} ({item.score:.1f}p): {PATH_DESCRIPTIONS.get(item.path, '')}")
        return out[:3]

    # ── Suggestions ──────────────────────────────────────────────────────────

    def _suggest_function_name(self, facts: Dict[str, Any]) -> str:
        domain = facts["domain"] if facts["domain"] != "general" else "zero"
        intent = facts["intent"] or facts["core_problem"] or facts["goal"]
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", intent.lower()).strip("_")
        slug = slug[:32] or "helper"
        return f"{domain}_{slug}"

    def _suggest_function_purpose(self, facts: Dict[str, Any]) -> str:
        if facts["intent"]:
            return facts["intent"]
        return f"Återanvändbar lösning för: {facts['goal'][:80]}"

    def _suggest_task_steps(self, facts: Dict[str, Any]) -> List[str]:
        sub_goals = list(facts.get("sub_goals") or [])
        if sub_goals:
            return sub_goals[:8]

        steps = ["Förstå målet och samla kontext"]
        if facts["requires_research"]:
            steps.append("Researcha relevanta källor")
        if facts["missing_context"]:
            steps.append("Hämta saknad kontext")
        steps.append("Analysera och jämför möjliga lösningar")
        steps.append("Sammanfatta rekommendation och nästa steg")
        return steps

    def _suggest_entity_name(self, facts: Dict[str, Any]) -> str:
        domain = facts["domain"]

        # Known nice defaults.
        defaults = {
            "pinball": "Minna",
            "trading": "Master Trader Assistant",
            "social_media": "Pinball Social Entity",
            "pinball_inn": "Pinball Inn Steward",
            "system": "Zero Systems Apprentice",
            "programming": "Zero Builder",
        }
        if domain in defaults:
            return defaults[domain]

        # Generic fallback.
        title = domain.replace("_", " ").strip().title() if domain else "Specialist"
        if not title or title.lower() == "general":
            title = "Specialist"
        return f"{title} Assistant"

    def _suggest_entity_purpose(self, facts: Dict[str, Any]) -> str:
        domain = facts["domain"]
        purpose_map = {
            "pinball": "Specialist på flipperspelsreparationer, underhåll, manualer, felsökning och Pinball Inn-maskiner.",
            "trading": "Specialist på marknadsanalys, riskhantering, tradingjournal, TradingView-screenshots och Franks tradingfilosofi.",
            "social_media": "Specialist på Pinball inns sociala medier, innehållsplanering, röst, timing och återkommande kampanjer.",
            "pinball_inn": "Specialist på Pinball Inn-drift, bokningar, rapporter, rutiner och återkommande förbättringar.",
            "system": "Specialist på Zero-systemets drift, felsökning, recovery, dokumentation och serverrutiner.",
            "programming": "Specialist på Zero-kodbasens arkitektur, refaktorering, testning och moduldesign.",
        }
        if domain in purpose_map:
            return purpose_map[domain]
        return f"Specialist inom {domain or 'detta område'}: {facts['goal'][:120]}"

    # ── Entity registry check ────────────────────────────────────────────────

    def _find_existing_entity(self, domain: str, entity_id: str) -> Optional[str]:
        if not domain or domain == "general":
            return None

        # Try current zero_entity API.
        try:
            from app.zero_entity import get_registry
            registry = get_registry()
            for entity in registry.get_all():
                name = getattr(entity, "name", "")
                profile = getattr(entity, "profile", None)
                entity_domain = getattr(profile, "domain", "") if profile else ""
                if domain.lower() in entity_domain.lower() or domain.lower() in name.lower():
                    return name or entity_domain
        except Exception:
            pass

        # Try entity manager if present.
        try:
            from app.zero_entity_manager import get_entity_manager
            manager = get_entity_manager()
            entities = manager.list_entities()
            for entity in entities:
                blob = _as_text(entity).lower()
                if domain.lower() in blob:
                    if isinstance(entity, dict):
                        return entity.get("name") or entity.get("entity_id") or domain
                    return getattr(entity, "name", None) or getattr(entity, "entity_id", None) or domain
        except Exception:
            pass

        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_engine = SpecializationEngine()


def evaluate(
    decomposition: Any,
    entity_id: str = "zero",
    context: Optional[str] = None,
) -> SpecializationRecommendation:
    return _engine.evaluate(decomposition, entity_id=entity_id, context=context)


def analyze_and_recommend(
    goal: str,
    context: Optional[str] = None,
    entity_id: str = "zero",
) -> Tuple[Any, SpecializationRecommendation]:
    """
    Kombinerad convenience-funktion för Gear 4:
        decompose(goal) → evaluate(decomposition)
    """
    try:
        from app.zero_decomposer import decompose
    except Exception:
        from zero_decomposer import decompose  # type: ignore

    decomposition = decompose(goal, context=context, entity_id=entity_id)
    recommendation = evaluate(decomposition, entity_id=entity_id, context=context)
    return decomposition, recommendation


def recommend_path(
    goal: str,
    context: Optional[str] = None,
    entity_id: str = "zero",
) -> SpecializationRecommendation:
    """Enklare API när bara recommendation behövs."""
    _, rec = analyze_and_recommend(goal, context=context, entity_id=entity_id)
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# CLI / tests
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES: List[Tuple[str, str]] = [
    ("Vad betyder OSError address already in use?", "DIRECT"),
    ("Skriv ett script som scannar trasiga imports i app-mappen", "FUNCTION"),
    ("Analysera varför Firepower-flipprets vänstra solenoid inte svarar", "TASK"),
    ("Håll koll på alla 80 flipperspel och skicka daglig rapport, lär dig felen över tid", "ENTITY"),
    ("Skapa en Master Trader Assistant som studerar mina trades och TradingView-bilder över tid", "ENTITY"),
    ("Sammanfatta den här tracebacken", "DIRECT"),
    ("Bygg en backup-funktion för Zero config-filer", "FUNCTION"),
    ("Researcha bästa sättet att integrera entity wizard med Gear 4", "TASK"),
]


def _run_tests(verbose: bool = False) -> int:
    ok_count = 0
    failures: List[str] = []

    for goal, expected in TEST_CASES:
        try:
            _, rec = analyze_and_recommend(goal)
        except Exception as e:
            failures.append(f"ERROR {goal!r}: {e}")
            continue

        ok = rec.path == expected
        if ok:
            ok_count += 1
        else:
            failures.append(f"{goal!r}: expected {expected}, got {rec.path} ({rec.confidence:.0%})")

        mark = "✓" if ok else "✗"
        print(f"{mark} {rec.path:<8} {rec.confidence:.0%}  expected={expected:<8}  {goal}")
        if verbose:
            print("  scorecard:", rec.scorecard)
            print("  reason:", rec.reason)
            print("  reasons:", "; ".join(rec.reasons[:4]))
            print()

    print()
    print(f"Tests: {ok_count}/{len(TEST_CASES)} passed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(" -", f)
    return 0 if not failures else 2


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ZeroPointAI Specialization Engine v2.0")
    parser.add_argument("goal", nargs="?", help="Goal to analyze")
    parser.add_argument("--context", default=None, help="Optional context")
    parser.add_argument("--entity", default="zero", help="Entity id")
    parser.add_argument("--json", action="store_true", help="Print recommendation as JSON")
    parser.add_argument("--test", action="store_true", help="Run built-in tests")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.test:
        return _run_tests(verbose=args.verbose)

    if not args.goal:
        parser.print_help()
        return 1

    decomp, rec = analyze_and_recommend(args.goal, context=args.context, entity_id=args.entity)

    if args.json:
        payload = {
            "decomposition": asdict(decomp) if hasattr(decomp, "__dataclass_fields__") else _as_text(decomp),
            "recommendation": rec.to_dict(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        if hasattr(decomp, "format_thinking"):
            print(decomp.format_thinking())
            print()
        print(rec.format_for_frank())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
