"""
zero_system_intent.py — ZeroPointAI System Intent Handler

ZERO_MODULE:    autonomy
ZERO_LAYER:     2
ZERO_ESSENTIAL: false
ZERO_ROLE:      Djup intentionsförståelse — LLM tolkar vad Frank egentligen menar
ZERO_DEPENDS:   foundation.py, router.py, zero_sudo.py, zero_perspective.py
ZERO_USED_BY:   router.py, zero_engine.py, zero_gear4.py

Filosofi (GPT + Grok):
    Layer 1 (router.py):           Snabb regex-routing. "Finns intent?" → ja/nej
    Layer 2 (zero_system_intent):  Djup LLM-förståelse. "Vad menar Frank?"

    Exempel på vad Layer 2 klarar som Layer 1 inte kan:
        "Vad heter alla dina byggklossar?"  → LIST_MODULES
        "Vilka delar består du av?"         → LIST_MODULES
        "Kan du städa upp lite?"            → CLEANUP (med förklaring + godkännande)
        "Varför går du långsamt idag?"      → SYSTEM_DIAGNOSIS
        "Vad har förändrats sedan igår?"    → GIT_DIFF + CHANGELOG

    Principen:
        1. Zero förstår målet (LLM)
        2. Zero föreslår kommandon (whitelisted eller explicit)
        3. Zero förklarar vad den tänker göra (Groks princip)
        4. zero_sudo utför — aldrig shell=True
        5. Frank har alltid veto vid risk > SAFE

    Preferensminne:
        Franks preferenser sparas i STONE (DRM) — inte ett separat system.
        Hämtas via wave_retrieval nästa gång Frank frågar något liknande.
        "Frank gillar alltid temperatur + last" → DRM vet det efter ett tag.

    Framtid:
        - Semantisk routing via embeddings (vector search mot intent-bibliotek)
        - INTENT_LIBRARY → intent_library/*.intent.md (läsbara filer)
        - Zero lär sig Franks preferenser organiskt via DRM
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


# ── Intent-plan ───────────────────────────────────────────────────────────────

@dataclass
class SystemIntentPlan:
    """
    Vad Zero förstår att Frank vill ha.
    Skapas av LLM, verifieras mot whitelist, körs av zero_sudo.
    """
    goal:        str                      # Franks originalfras
    intent_type: str = "UNKNOWN"          # LIST_MODULES, GPU_STATUS, etc.
    commands:    List[List[str]] = field(default_factory=list)  # Kommandon att köra
    explanation: str = ""                 # Vad Zero tänker göra (visas för Frank)
    risk_level:  str = "SAFE"             # SAFE/CAUTION/HIGH/CRITICAL
    confidence:  float = 0.0             # Hur säker Zero är på tolkningen
    ask_frank:   bool = False             # Ska Frank godkänna?
    frank_question: str = ""             # Frågan till Frank vid osäkerhet
    created_at:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_safe_to_run(self) -> bool:
        return self.risk_level == "SAFE" and self.confidence >= 0.75 and not self.ask_frank

    def format_for_frank(self) -> str:
        """Förklarar för Frank vad Zero tänker göra — Groks princip."""
        lines = [f"Jag förstår att du vill: **{self.goal}**", ""]
        if self.explanation:
            lines.append(self.explanation)
            lines.append("")
        if self.commands:
            lines.append("Jag föreslår att köra:")
            for cmd in self.commands[:3]:
                lines.append(f"  `{' '.join(cmd)}`")
            lines.append("")
        lines.append(
            f"Risk: {self.risk_level} | "
            f"Säkerhet: {self.confidence:.0%}"
        )
        if self.ask_frank:
            lines.append(f"\n**{self.frank_question}**")
        return "\n".join(lines)


# ── Intent-bibliotek ──────────────────────────────────────────────────────────
# Exempel på kända intents med semantiska varianter
# Framtiden: vector search mot detta bibliotek

INTENT_LIBRARY = {
    "LIST_MODULES": {
        "description": "Visa alla Zero-moduler och filer",
        "variants": [
            "vad heter alla dina moduler",
            "vilka delar består du av",
            "visa dina byggklossar",
            "vilka pythonfiler har du",
            "visa app-mappen",
        ],
        "commands": [["find", "/opt/zeropointai/next_zero/app", "-name", "*.py", "-type", "f"]],
        "risk": "SAFE",
    },
    "GPU_STATUS": {
        "description": "GPU-hälsa och temperatur",
        "variants": [
            "hur mår grafikkortet",
            "är gpu:n varm",
            "hur används vram",
            "gpu-status",
        ],
        "commands": [["nvidia-smi"]],
        "risk": "SAFE",
    },
    "SYSTEM_DIAGNOSIS": {
        "description": "Varför är systemet långsamt eller något fel",
        "variants": [
            "varför går du långsamt",
            "vad är fel",
            "systemet verkar trögare",
            "något verkar konstigt",
        ],
        "commands": [
            ["top", "-bn1"],
            ["free", "-h"],
            ["df", "-h"],
        ],
        "risk": "SAFE",
    },
    "CLEANUP_LOGS": {
        "description": "Städa upp gamla systemloggar",
        "variants": [
            "städa upp lite",
            "rensa gamla loggar",
            "frigör diskutrymme",
            "ta bort gamla filer",
        ],
        "commands": [["journalctl", "--vacuum-time=14d"]],
        "risk": "CAUTION",
        "ask_frank": True,
        "frank_question": "Vill du att jag rensar loggar äldre än 14 dagar?",
    },
    "GIT_STATUS": {
        "description": "Vad har förändrats i koden",
        "variants": [
            "vad har förändrats sedan igår",
            "vilka filer har ändrats",
            "git status",
            "senaste ändringar",
        ],
        "commands": [["git", "-C", str(ZERO_ROOT), "log", "--oneline", "-10"]],
        "risk": "SAFE",
    },
}


# ── System Intent Handler ─────────────────────────────────────────────────────

class SystemIntentHandler:
    """
    Layer 2 — djup intentionsförståelse via LLM.

    Används när router.py inte hittar en klar regex-match men
    kontexten antyder ett systemrelaterat önskemål.
    """

    def __init__(self):
        self._preference_cache: Dict[str, Any] = {}

    def understand(
        self,
        goal:      str,
        context:   Optional[str] = None,
        entity_id: str = "zero",
    ) -> SystemIntentPlan:
        """
        Förstår vad Frank egentligen vill ha.

        1. Försök semantisk matchning mot INTENT_LIBRARY
        2. Om osäker → fråga LLM
        3. Validera mot whitelist
        4. Returnera plan med förklaring
        """
        # Steg 1: Semantisk matchning (enkel version — keyword-baserad)
        plan = self._semantic_match(goal)
        if plan and plan.confidence >= 0.8:
            log.info(f"SystemIntent: semantic match '{goal}' → {plan.intent_type}")
            return plan

        # Steg 2: LLM-baserad tolkning
        plan = self._llm_understand(goal, context)
        if plan:
            log.info(f"SystemIntent: LLM match '{goal}' → {plan.intent_type}")
            return plan

        # Steg 3: Okänd intention — fråga Frank
        return SystemIntentPlan(
            goal        = goal,
            intent_type = "UNKNOWN",
            explanation = f"Jag är osäker på vad du vill göra med '{goal}'.",
            confidence  = 0.0,
            ask_frank   = True,
            frank_question = (
                f"Kan du förklara mer? Till exempel: "
                f"'visa GPU-temp', 'kör nvidia-smi', eller 'visa alla moduler'"
            ),
        )

    def _enrich_with_preferences(
        self, plan: SystemIntentPlan
    ) -> SystemIntentPlan:
        """
        Berikar en plan med Franks sparade preferenser från DRM.
        "Frank gillar alltid temperatur + last" → lägg till load i GPU-kommandot
        """
        prefs = self._get_frank_preferences(plan.intent_type)
        if prefs:
            log.debug(f"SystemIntent: {len(prefs)} preferenser hittade för {plan.intent_type}")
        return plan

    def execute(self, plan: SystemIntentPlan) -> str:
        """
        Kör en godkänd plan via zero_sudo.
        Aldrig shell=True. Frank har alltid veto.
        """
        if plan.ask_frank:
            return plan.format_for_frank()

        if not plan.commands:
            return plan.explanation or f"Förstår målet men vet inte vilket kommando som passar."

        if not plan.is_safe_to_run():
            return plan.format_for_frank()

        results = []
        for cmd in plan.commands[:3]:
            result = self._run_command(cmd, plan.risk_level)
            results.append(result)

        output = "\n".join(results)

        # Spara till DRM — Zero lär sig Franks preferenser
        self._save_preference_to_drm(plan.goal, plan)

        if plan.explanation:
            return f"{plan.explanation}\n\n{output}"
        return output

    def understand_and_execute(
        self,
        goal:      str,
        context:   Optional[str] = None,
        entity_id: str = "zero",
    ) -> str:
        """Kombinerad understand + execute för enkel användning."""
        plan = self.understand(goal, context, entity_id)
        return self.execute(plan)

    # ── Semantisk matchning ───────────────────────────────────────────────────

    def _semantic_match(self, goal: str) -> Optional[SystemIntentPlan]:
        """
        Enkel keyword-baserad semantisk matchning mot INTENT_LIBRARY.
        Framtiden: vector search med embeddings.
        """
        goal_lower = goal.lower().strip()

        best_match  = None
        best_score  = 0.0

        for intent_type, config in INTENT_LIBRARY.items():
            for variant in config["variants"]:
                # Beräkna likhet (enkel ordöverlapp)
                goal_words    = set(goal_lower.split())
                variant_words = set(variant.lower().split())
                if not variant_words:
                    continue
                overlap = len(goal_words & variant_words) / len(variant_words)
                if overlap > best_score:
                    best_score  = overlap
                    best_match  = intent_type

        if best_score < 0.5 or not best_match:
            return None

        config = INTENT_LIBRARY[best_match]
        return SystemIntentPlan(
            goal        = goal,
            intent_type = best_match,
            commands    = config["commands"],
            explanation = config["description"],
            risk_level  = config.get("risk", "SAFE"),
            confidence  = min(0.95, best_score + 0.2),
            ask_frank   = config.get("ask_frank", False),
            frank_question = config.get("frank_question", ""),
        )

    # ── LLM-baserad tolkning ──────────────────────────────────────────────────

    def _llm_understand(
        self, goal: str, context: Optional[str] = None
    ) -> Optional[SystemIntentPlan]:
        """
        Frågar LLM vad Frank egentligen vill ha.
        Returnerar strukturerad plan.
        """
        try:
            from app.zero_engine import get_engine_response

            system_prompt = (
                "Du är Zero's system intent analyzer. "
                "Analysera vad användaren vill göra med sitt Linux-system. "
                "Svara ENDAST med JSON i detta format:\n"
                '{"intent": "GPU_STATUS|DISK_STATUS|LIST_MODULES|SYSTEM_DIAGNOSIS|UNKNOWN", '
                '"commands": [["cmd", "arg1"]], '
                '"explanation": "kort förklaring", '
                '"risk": "SAFE|CAUTION|HIGH", '
                '"confidence": 0.0-1.0}\n'
                "Inga shell=True. Bara säkra, välkända Linux-kommandon."
            )

            prompt = f"Vad vill användaren göra?\nMål: {goal}\nKontext: {context or 'ingen'}"

            import json
            response = get_engine_response(
                user_input   = prompt,
                system_extra = system_prompt,
                gear_level   = 1,
            )

            # Parsa JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            data = json.loads(response)
            intent_type = data.get("intent", "UNKNOWN")
            commands    = data.get("commands", [])
            explanation = data.get("explanation", "")
            risk        = data.get("risk", "SAFE")
            confidence  = float(data.get("confidence", 0.5))

            # Säkerhetsvalidering — inga farliga kommandon
            safe_commands = [
                cmd for cmd in commands
                if cmd and not any(
                    dangerous in " ".join(cmd).lower()
                    for dangerous in ["rm -rf", "mkfs", "dd ", ":(){", "fork bomb", "sudo su"]
                )
            ]

            return SystemIntentPlan(
                goal        = goal,
                intent_type = intent_type,
                commands    = safe_commands,
                explanation = explanation,
                risk_level  = risk,
                confidence  = confidence,
                ask_frank   = risk in ("HIGH", "CRITICAL") or confidence < 0.7,
                frank_question = (
                    f"Jag tror du vill: {explanation}. Stämmer det?"
                    if confidence < 0.7 else ""
                ),
            )

        except Exception as e:
            log.debug(f"LLM intent: {e}")
            return None

    # ── Exekvering ────────────────────────────────────────────────────────────

    def _run_command(self, cmd: List[str], risk_level: str = "SAFE") -> str:
        """Kör kommando via zero_sudo. Aldrig shell=True."""
        try:
            from app.zero_sudo import run as sudo_run
            result = sudo_run(cmd, note=f"intent:{' '.join(cmd[:3])}")
            output = (result.get("stdout") or result.get("stderr") or "").strip()
            ok     = result.get("ok", True)
            prefix = f"```\n$ {' '.join(cmd)}\n"
            if not ok:
                return f"{prefix}[FEL] {output[:500]}\n```"
            return f"{prefix}{output[:2000]}\n```"
        except ImportError:
            return (
                f"zero_sudo saknas — kan inte köra `{' '.join(cmd)}`.\n"
                f"Kontrollera att zero_sudo.py finns i app/."
            )
        except Exception as e:
            return f"Fel vid körning av `{' '.join(cmd)}`: {e}"

    # ── Preferensminne (via DRM — inte ett separat system) ───────────────────

    def _save_preference_to_drm(self, goal: str, plan: SystemIntentPlan) -> None:
        """
        Sparar Franks preferenser till STONE via DRM.
        Ingen ny minnesfilosofi — bara rätt taggar i befintligt system.

        Zero hämtar dessa via wave_retrieval nästa gång Frank frågar något liknande.
        "Frank gillar alltid att se temperatur + last tillsammans."
        """
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[frank_preference] intent={plan.intent_type} "
                    f"goal='{goal[:60]}' "
                    f"confidence={plan.confidence:.0%} "
                    f"commands={[' '.join(c) for c in plan.commands[:2]]}"
                ),
                source  = "zero_system_intent:preference",
            )
        except Exception:
            pass

    def _get_frank_preferences(self, intent_type: str) -> List[str]:
        """
        Hämtar Franks sparade preferenser för en intent-typ via DRM wave_retrieval.
        Returnerar lista med relevanata minnen som kan påverka svaret.
        """
        try:
            from app.drm_memory import wave_retrieval
            results = wave_retrieval(
                f"frank preference {intent_type}",
                limit=3,
            )
            return [r.get("content", "") for r in results if r.get("content")]
        except Exception:
            return []


# ── Global instans ────────────────────────────────────────────────────────────

_handler: Optional[SystemIntentHandler] = None


def get_handler() -> SystemIntentHandler:
    global _handler
    if _handler is None:
        _handler = SystemIntentHandler()
    return _handler


def understand_system_intent(
    goal:      str,
    context:   Optional[str] = None,
    entity_id: str = "zero",
) -> SystemIntentPlan:
    return get_handler().understand(goal, context, entity_id)


def handle_system_intent(
    goal:      str,
    context:   Optional[str] = None,
    entity_id: str = "zero",
) -> str:
    return get_handler().understand_and_execute(goal, context, entity_id)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="ZeroPointAI System Intent Handler")
    parser.add_argument("goal",   nargs="?", help="Franks mål")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    handler = SystemIntentHandler()

    if args.test:
        print(f"\n{'─'*55}")
        print(f"  Zero System Intent — Test")
        print(f"{'─'*55}\n")

        test_goals = [
            "Vad heter alla dina byggklossar?",
            "Vilka delar består du av?",
            "Är GPU:n varm?",
            "Varför går du långsamt idag?",
            "Kan du städa upp lite?",
            "Vad har förändrats sedan igår?",
            "Hjälp mig med något konstigt",
        ]

        for goal in test_goals:
            plan = handler.understand(goal)
            print(f"Mål:    {goal}")
            print(f"Intent: {plan.intent_type} ({plan.confidence:.0%})")
            print(f"Risk:   {plan.risk_level}")
            if plan.ask_frank:
                print(f"Fråga:  {plan.frank_question[:60]}")
            if plan.commands:
                print(f"Cmd:    {plan.commands[0]}")
            print()

    elif args.goal:
        plan = handler.understand(args.goal)
        print(plan.format_for_frank())

    else:
        parser.print_help()
