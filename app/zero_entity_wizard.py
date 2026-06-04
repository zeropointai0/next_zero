"""
zero_entity_wizard.py — ZeroPointAI Specialization Wizard

ZERO_MODULE:    autonomy
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Specialization Wizard — väljer bästa lösning, designar entities med Frank
ZERO_DEPENDS:   foundation.py, zero_entity.py, zero_gear4.py
ZERO_USED_BY:   zero_gear4.py, router.py

Filosofi:
    En Entity är ett åtagande.
    Det är nästan som att skaffa barn.

    En Entity skapas INTE för:
        → Engångsuppgifter
        → Saker Zero kan lösa direkt
        → Saker en funktion kan hantera
        → Impuls

    En Entity skapas NÄR:
        → Domänen är återkommande och viktig
        → Specialisering ger tydligt mervärde över tid
        → Frank är villig att investera i utbildningen
        → Uppdraget är långsiktigt

    Wizarden är en riktig konversation — inte ett formulär.
    Zero ställer frågor, lyssnar, utmanar, sammanfattar.
    Till sist: "Är du redo att ta det här ansvaret?"

    Före wizarden:
        Zero utvärderar alltid om problemet kan lösas direkt:
        → Kan jag skriva en funktion för detta?
        → Kan jag söka och svara direkt?
        → Är detta verkligen återkommande?
        Om nej → lös direkt, ingen Entity behövs.
"""

from __future__ import annotations

import json
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

# ── Wizard-state ──────────────────────────────────────────────────────────────

@dataclass
class WizardSession:
    """Pågående wizard-session med Frank."""
    session_id:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    phase:        str = "evaluate"   # evaluate/brainstorm/design/review/confirm
    answers:      Dict[str, Any] = field(default_factory=dict)
    entity_draft: Dict[str, Any] = field(default_factory=dict)
    started_at:   str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed:    bool = False
    cancelled:    bool = False


# ── Wizard-frågor ─────────────────────────────────────────────────────────────

WIZARD_PHASES = {

    "evaluate": {
        "title": "Behövs verkligen en Entity?",
        "intro": (
            "Innan vi går vidare vill jag förstå problemet ordentligt. "
            "En Entity är ett stort åtagande — nästan som att skaffa barn. "
            "Låt mig först se om vi kan lösa detta enklare."
        ),
        "questions": [
            {
                "key":      "problem",
                "question": "Berätta om problemet eller behovet du vill lösa. Vad händer just nu som inte fungerar, eller vad saknas?",
                "why":      "Förstå roten",
            },
            {
                "key":      "frequency",
                "question": "Hur ofta uppstår detta behov? Är det något som händer varje dag, varje vecka, eller mer sällan?",
                "why":      "Avgöra om Entity är motiverad",
            },
            {
                "key":      "tried",
                "question": "Har du försökt lösa det på annat sätt? Vad hände?",
                "why":      "Förstå varför enklare lösningar inte räcker",
            },
        ],
    },

    "decompose": {
        "title": "Jag tänker högt — vilken lösning passar bäst?",
        "intro": (
            "Innan vi bestämmer oss för en Entity vill jag tänka högt. "
            "Det finns ofta enklare lösningar."
        ),
    },

    "brainstorm": {
        "title": "Brainstorming — vad skulle denna Entity vara?",
        "intro": (
            "Bra. Det verkar som ett genuint återkommande behov. "
            "Nu vill jag brainstorma med dig. "
            "Det finns inga fel svar här — vi utforskar."
        ),
        "questions": [
            {
                "key":      "domain",
                "question": "Vilket område eller domän skulle denna Entity specialisera sig inom? Beskriv det så brett eller smalt du vill.",
                "why":      "Definiera fokus",
            },
            {
                "key":      "dream",
                "question": "Om denna Entity fungerade perfekt om 2 år — vad skulle den kunna göra som du inte kan idag?",
                "why":      "Förstå ambitionen",
            },
            {
                "key":      "personality",
                "question": "Hur vill du att den ska kommunicera och bete sig? Formell? Direkt? Frågvis? Kreativ?",
                "why":      "Forma identiteten",
            },
            {
                "key":      "languages",
                "question": "Vilka språk behöver den kunna? Svenska, engelska, eller andra?",
                "why":      "Kommunikationsförmåga",
            },
        ],
    },

    "design": {
        "title": "Design — vi konkretiserar",
        "intro": (
            "Nu bygger vi något konkret. "
            "Svara så detaljerat du vill — eller kortfattat om du är osäker. "
            "Vi kan alltid justera senare."
        ),
        "questions": [
            {
                "key":      "name_ideas",
                "question": (
                    "Har du namnidéer? "
                    "Ett bra entity-namn är kort, personligt och lätt att minnas. "
                    "Det behöver inte vara ett människonamn men kan vara det. "
                    "Ge gärna flera alternativ."
                ),
                "why":      "Identitet börjar med ett namn",
            },
            {
                "key":      "sources",
                "question": (
                    "Vilka kunskapskällor ska Entity:n lära sig från? "
                    "Tänk: böcker, manualer, forum, dokument, webbplatser, YouTube-kanaler, "
                    "din egen erfarenhet. Räkna upp allt du kan komma på."
                ),
                "why":      "Studieplan",
            },
            {
                "key":      "mentors",
                "question": (
                    "Ska Zero agera mentor? "
                    "Finns det områden där Zero redan har hög kunskap och kan hjälpa Entity:n lära sig snabbare?"
                ),
                "why":      "Mentorskap accelererar lärandet",
            },
            {
                "key":      "tools",
                "question": (
                    "Vilka verktyg ska Entity:n ha tillgång till? "
                    "Tänk: webssökning, mailhantering, filläsning, externa API:er, "
                    "forum-kommunikation, kamera/bilder."
                ),
                "why":      "Definiera handlingsutrymme",
            },
            {
                "key":      "boundaries",
                "question": (
                    "Finns det saker Entity:n ALDRIG ska göra? "
                    "Vad vill du att den alltid ska fråga om först? "
                    "Vilka beslut ska alltid gå via dig?"
                ),
                "why":      "Constitution och begränsningar",
            },
            {
                "key":      "lifespan",
                "question": (
                    "Hur länge tror du att du behöver den här Entity:n? "
                    "Är det ett tidsbegränsat projekt eller ett permanent behov? "
                    "Vad händer om behovet försvinner?"
                ),
                "why":      "Planera lifecycle inklusive DORMANT/RETIRED",
            },
            {
                "key":      "success",
                "question": (
                    "Hur vet du att Entity:n fungerar bra? "
                    "Vad är ett konkret tecken på framgång efter 1 månad? "
                    "Efter 6 månader?"
                ),
                "why":      "Mätbara mål",
            },
            {
                "key":      "future_advantage",
                "question": (
                    "Vad ska den här Entity:n bli BÄTTRE på än Zero om 2 år?\n\n"
                    "Zero kan redan det mesta. En Entity är bara motiverad om den "
                    "med tid och erfarenhet kan bli genuint överlägsen Zero som generalist "
                    "inom sitt område.\n\n"
                    "Vad är det specifika fördelen med specialisering här?"
                ),
                "why":      "Future Advantage — kärnan i varför Entity motiveras",
            },
            {
                "key":      "special",
                "question": (
                    "Är det något speciellt med den här Entity:n som vi inte pratat om? "
                    "Unika egenskaper, speciell historia, specifika relationer?"
                ),
                "why":      "Fånga det som inte passar i standardfrågorna",
            },
        ],
    },

    "review": {
        "title": "Granskning — stämmer detta?",
        "intro": (
            "Låt mig sammanfatta vad vi kommit fram till. "
            "Läs igenom noga. Är detta rätt? "
            "Nu är det enkelt att ändra — senare är det svårare."
        ),
    },

    "confirm": {
        "title": "Sista steget — är du redo?",
        "intro": (
            "En Entity är ett åtagande. Jag vill att du förstår vad du tackar ja till."
        ),
        "questions": [
            {
                "key":      "commitment",
                "question": (
                    "Den här Entity:n kommer behöva tid för att lära sig. "
                    "Den kommer göra misstag i början. "
                    "Den kommer fråga dig om saker som kan kännas uppenbara. "
                    "Den behöver feedback för att bli bättre.\n\n"
                    "Är du villig att investera den tid som krävs för att utbilda den?"
                ),
                "why":      "Bekräfta åtagandet",
            },
            {
                "key":      "final_name",
                "question": "Vilket namn väljer du? (Baserat på dina förslag ovan)",
                "why":      "Slutligt namn",
            },
        ],
    },
}


# ── Wizard Engine ─────────────────────────────────────────────────────────────

class EntityCreationWizard:
    """
    Interaktiv wizard för att designa entities med Frank.

    Används av Zero i konversation — inte som ett standalone CLI.
    Zero kör wizarden steg för steg i chatten.
    """

    def __init__(self):
        self._session: Optional[WizardSession] = None

    @property
    def is_active(self) -> bool:
        return (
            self._session is not None
            and not self._session.completed
            and not self._session.cancelled
        )

    @property
    def current_phase(self) -> Optional[str]:
        if self._session:
            return self._session.phase
        return None

    # ── Starta / avbryta ──────────────────────────────────────────────────────

    def start(self, trigger: str = "") -> str:
        """
        Startar wizard-sessionen.
        Returnerar första meddelandet från Zero till Frank.
        """
        self._session = WizardSession()
        log.info("Entity Creation Wizard started")

        return (
            "Jag hör att du funderar på att skapa en ny Entity. "
            "Det är ett stort beslut — som att ta in en lärling. 😄\n\n"
            "Men innan vi börjar designa vill jag vara ärlig: "
            "**kanske behövs ingen Entity alls.** "
            "Många problem kan jag lösa direkt, utan att skapa något nytt.\n\n"
            "Låt mig ställa några frågor för att förstå vad du egentligen behöver.\n\n"
            f"**{WIZARD_PHASES['evaluate']['questions'][0]['question']}**"
        )

    def cancel(self) -> str:
        if self._session:
            self._session.cancelled = True
        return "Wizard avbruten. Inget skapades. Du kan starta igen när du vill."

    # ── Utvärdera om Entity behövs ────────────────────────────────────────────

    def evaluate_need(self, answers: Dict[str, str]) -> tuple[bool, str]:
        """
        Zero utvärderar om en Entity faktiskt behövs.
        Returnerar (needs_entity: bool, response: str)
        """
        problem   = answers.get("problem", "").lower()
        frequency = answers.get("frequency", "").lower()

        # Signaler på att Entity INTE behövs
        one_time_signals = [
            "en gång", "just nu", "tillfälligt", "den här gången",
            "once", "one time", "just this"
        ]
        if any(s in frequency for s in one_time_signals):
            return False, (
                "Det verkar som ett engångsbehov. "
                "Jag kan lösa det direkt utan att skapa en Entity. "
                "Vad vill du att jag gör?"
            )

        # Signaler på att en funktion räcker
        simple_signals = [
            "hämta", "räkna", "konvertera", "formatera", "sammanfatta",
            "fetch", "calculate", "convert", "format", "summarize"
        ]
        if any(s in problem for s in simple_signals):
            return False, (
                "Det här låter som något jag kan lösa med en enkel funktion. "
                "Vill du att jag skriver den nu, "
                "eller tror du att behovet är mer komplext än så?"
            )

        return True, ""

    # ── Processar svar ────────────────────────────────────────────────────────

    def process_answer(self, answer: str) -> str:
        """
        Frank svarar — Zero processar och ger nästa fråga.
        Returnerar Zeros nästa meddelande.
        """
        if not self._session:
            return "Ingen aktiv wizard-session. Skriv 'skapa entity' för att starta."

        phase     = self._session.phase
        phase_cfg = WIZARD_PHASES.get(phase, {})
        questions = phase_cfg.get("questions", [])

        # Hitta vilken fråga vi är på
        answered = len(self._session.answers)
        phase_questions_answered = sum(
            1 for q in questions
            if q["key"] in self._session.answers
        )

        # Spara svaret
        if questions and phase_questions_answered < len(questions):
            current_q = questions[phase_questions_answered]
            self._session.answers[current_q["key"]] = answer

            # Specialhantering för evaluate-fasen
            if phase == "evaluate" and current_q["key"] == "frequency":
                needs, response = self.evaluate_need(self._session.answers)
                if not needs:
                    self._session.cancelled = True
                    return response

            phase_questions_answered += 1

        # Är fasen klar?
        if phase_questions_answered >= len(questions):
            return self._advance_phase()

        # Nästa fråga i samma fas
        next_q = questions[phase_questions_answered]
        return self._format_question(next_q["question"], phase_questions_answered + 1, len(questions))

    def _advance_phase(self) -> str:
        """Går till nästa fas."""
        phases = list(WIZARD_PHASES.keys())
        current_idx = phases.index(self._session.phase)

        if current_idx >= len(phases) - 1:
            # Sista fasen klar
            return self._finalize()

        next_phase = phases[current_idx + 1]
        self._session.phase = next_phase
        phase_cfg = WIZARD_PHASES[next_phase]

        if next_phase == "decompose":
            return self._generate_decompose()

        if next_phase == "review":
            return self._generate_review()

        intro     = phase_cfg.get("intro", "")
        questions = phase_cfg.get("questions", [])
        first_q   = questions[0] if questions else None

        response = f"**{phase_cfg['title']}**\n\n{intro}"
        if first_q:
            response += f"\n\n**{first_q['question']}**"
        return response

    def _format_question(self, question: str, current: int, total: int) -> str:
        return f"**Fråga {current}/{total}:** {question}"

    def _generate_decompose(self) -> str:
        """Zero tänker högt om lösningsalternativ."""
        problem   = self._session.answers.get("problem", "")
        frequency = self._session.answers.get("frequency", "")

        return (
            f"**Låt mig tänka högt.**\n\n"
            f"Jag ser tre möjliga lösningar för '{problem[:60]}':\n\n"
            f"**1. Direkt lösning** — Jag löser det nu, engång\n"
            f"   _Bra om: engångsbehov, enkelt, snabbt_\n\n"
            f"**2. Gear 4-uppdrag** — Strukturerat arbete med flera steg\n"
            f"   _Bra om: research behövs, komplext men inte återkommande_\n\n"
            f"**3. Entity (specialist)** — Långsiktig investering\n"
            f"   _Bra om: återkommande, lärande ger värde, domänen är stor_\n\n"
            f"Baserat på att du sa '{frequency[:40]}' lutar jag åt **Entity**. "
            f"Men det är du som bestämmer.\n\n"
            f"Vill du fortsätta med Entity-designen?"
        )

    def _generate_review(self) -> str:
        """Genererar sammanfattning för Franks granskning."""
        a = self._session.answers

        # Bygg entity-draft
        name       = a.get("final_name") or a.get("name_ideas", "").split("\n")[0].strip() or "Namnlös"
        domain     = a.get("domain", "Okänt område")
        dream      = a.get("dream", "")
        personality = a.get("personality", "")
        sources    = a.get("sources", "")
        tools      = a.get("tools", "")
        boundaries = a.get("boundaries", "")
        lifespan   = a.get("lifespan", "")
        success    = a.get("success", "")
        languages  = a.get("languages", "svenska, engelska")
        special    = a.get("special", "")

        self._session.entity_draft = {
            "name":       name,
            "domain":     domain,
            "purpose":    dream,
            "languages":  languages,
            "tools":      tools,
            "boundaries": boundaries,
            "lifespan":   lifespan,
            "sources":    sources,
        }

        review = f"""**{WIZARD_PHASES['review']['title']}**

{WIZARD_PHASES['review']['intro']}

---

**Namn:** {name}
**Domän:** {domain}
**Syfte:** {dream}
**Kommunikationsstil:** {personality}
**Språk:** {languages}

**Kunskapskällor:**
{sources}

**Verktyg:**
{tools}

**Begränsningar (Constitution):**
{boundaries}

**Förväntad livslängd:**
{lifespan}

**Framgångsmått:**
{success}
"""
        if special:
            review += f"\n**Övrigt:**\n{special}\n"

        review += """
---

Stämmer detta? Skriv:
- **"ja"** — för att fortsätta
- **"ändra [vad]"** — för att korrigera något
- **"avbryt"** — för att börja om
"""
        return review

    def _finalize(self) -> str:
        """Skapar Entity:n och avslutar wizarden."""
        self._session.completed = True
        a     = self._session.answers
        draft = self._session.entity_draft

        name = a.get("final_name") or draft.get("name", "Namnlös")

        # Bygg constitution från boundaries
        boundaries = a.get("boundaries", "")
        rules = []
        if boundaries:
            for line in boundaries.split("\n"):
                line = line.strip().lstrip("-•*").strip()
                if line:
                    rules.append(line)

        # Bygg studieplan
        sources_text = a.get("sources", "")
        study_sources = []
        for line in sources_text.split("\n"):
            line = line.strip().lstrip("-•*").strip()
            if line:
                study_sources.append(line)

        # Spara wizard-output
        output_file = ZERO_ROOT / "data" / "entities" / f"wizard_{self._session.session_id}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps({
                "session_id":    self._session.session_id,
                "completed_at":  datetime.now(timezone.utc).isoformat(),
                "entity_name":   name,
                "domain":        draft.get("domain", ""),
                "purpose":       draft.get("purpose", ""),
                "constitution":  rules,
                "study_sources": study_sources,
                "all_answers":   self._session.answers,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Logga till STONE
        try:
            from app.drm_memory import save_memory
            save_memory(
                role    = "system",
                content = (
                    f"[entity_wizard_complete] name={name} "
                    f"domain={draft.get('domain', '')} "
                    f"rules={len(rules)} sources={len(study_sources)}"
                ),
                source  = "zero_entity_wizard",
            )
        except Exception:
            pass

        return f"""**{name} är redo att födas.** 🌱

Wizard-sessionen är sparad. Nu skapar jag Entity:n i **DRAFT**-stadium.

**Nästa steg:**
1. Jag skapar {name} med din constitution och studieplan
2. Du och jag går igenom studiesplanen tillsammans
3. {name} börjar som **APPRENTICE** — lär sig, frågar, föreslår
4. Efter visat förtroende — **ACTIVE**
5. Efter lång erfarenhet — **MASTER**

**Kom ihåg:**
{name} kommer fråga mycket i början. Det är inte ett misslyckande — det är lärandet.
Ge henne tid. Hon förtjänar det.

Ska jag skapa {name} nu?"""


# ── Snabb Entity-check (Gear 4 använder detta) ────────────────────────────────

def should_create_entity(
    problem:    str,
    frequency:  str,
    domain:     str,
) -> tuple[bool, str]:
    """
    Gear 4 använder detta för att avgöra om ett problem kräver Entity.
    Returnerar (create_entity: bool, reason: str)
    """
    problem_lower   = problem.lower()
    frequency_lower = frequency.lower()

    # Signaler på att Entity behövs
    entity_signals = [
        "varje dag",     "every day",
        "varje vecka",   "every week",
        "återkommande",  "recurring",
        "långsiktigt",   "long-term",
        "specialiserad", "specialized",
        "expert",        "expertise",
        "lär sig",       "learn over time",
        "bygga upp",     "build up",
    ]

    # Signaler på att direkt lösning räcker
    direct_signals = [
        "en gång",    "once",
        "just nu",    "right now",
        "snabbt",     "quickly",
        "enkelt",     "simple",
        "ett skript", "a script",
        "en funktion", "a function",
    ]

    if any(s in frequency_lower for s in direct_signals):
        return False, "Engångsbehov — lös direkt"

    if any(s in problem_lower for s in direct_signals):
        return False, "Enkel uppgift — lös direkt"

    if any(s in frequency_lower + problem_lower for s in entity_signals):
        return True, f"Återkommande domänbehov: {domain}"

    return False, "Oklart behov — fråga Frank"


# ── Global wizard-instans ─────────────────────────────────────────────────────

_wizard: Optional[EntityCreationWizard] = None


def get_wizard() -> EntityCreationWizard:
    global _wizard
    if _wizard is None or not _wizard.is_active:
        _wizard = EntityCreationWizard()
    return _wizard


def start_wizard() -> str:
    global _wizard
    _wizard = EntityCreationWizard()
    return _wizard.start()


# ── CLI (för testning) ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="Entity Creation Wizard")
    parser.add_argument("--demo",  action="store_true", help="Kör demo-session")
    parser.add_argument("--check", nargs=3,
                        metavar=("PROBLEM", "FREQUENCY", "DOMAIN"),
                        help="Kontrollera om Entity behövs")
    args = parser.parse_args()

    if args.check:
        needs, reason = should_create_entity(*args.check)
        print(f"\n  Entity behövs: {'Ja' if needs else 'Nej'}")
        print(f"  Anledning: {reason}")

    elif args.demo:
        print(f"\n{'─'*55}")
        print(f"  Entity Creation Wizard — Demo")
        print(f"{'─'*55}")

        wizard = EntityCreationWizard()

        # Simulera en konversation
        demo_answers = [
            # Evaluate
            "Vi har 80+ flipperspel och behöver hjälp med reparationer. "
            "Det tar mycket tid att felsöka och vi saknar strukturerad dokumentation.",
            "Varje vecka — nästan varje dag har vi maskiner som behöver service.",
            "Jag har försökt hålla koll manuellt men det blir rörigt.",
            # Brainstorm
            "Flipperspels-reparationer, elektronik, mekanik, Williams/Bally/Stern",
            "Att kunna diagnostisera fel på 30 sekunder, veta vilka delar vi behöver, "
            "ha koll på vad som är trasigt och vad som väntar.",
            "Praktisk, direkt, ärlig. Frågar hellre en gång för mycket.",
            "Svenska, engelska, lite tyska för tyska forum",
        ]

        print()
        response = wizard.start()
        print(f"Zero: {response[:200]}...")

        for answer in demo_answers[:3]:
            print(f"\nFrank: {answer[:80]}...")
            response = wizard.process_answer(answer)
            print(f"Zero: {response[:200]}...")

        print()
        print("  [Demo avslutad — full wizard körs i Zero-chatten]")

    else:
        parser.print_help()
        print()
        print("  Exempelanvändning:")
        print('  python3 zero_entity_wizard.py --check "reparera flipper" "varje dag" "pinball"')
        print('  python3 zero_entity_wizard.py --demo')
