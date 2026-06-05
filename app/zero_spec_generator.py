#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_spec_generator.py — ZeroPointAI Spec Generator v6

ZERO_MODULE:    docs_engine
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Skapar korta, högdensitets-specar som ger rätt mental modell innan koden läses
ZERO_DEPENDS:   foundation.py
ZERO_USED_BY:   developers, zero_docs, zero_doctor, AI-granskning

Hybrid v6 — bäst av GPT v4.1 och Grok v5:
    Grok:  Greppbar struktur, MAX_LINES-disciplin, klassbaserad, enkel
    GPT:   MODULE_PROFILES med rika mentala modeller, AST-djup,
           risk-inferens, confidence-score, batch-körning, index

Design principle:
    "The spec should not impress. The spec should orient."
    Code explains HOW. Spec explains WHY.
"""

from __future__ import annotations

import ast
import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION   = "6.0"
MAX_LINES = 200  # Groks disciplin

# ── Root ──────────────────────────────────────────────────────────────────────

def detect_root() -> Path:
    env = os.getenv("ZERO_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "app").exists():
            return p
    this = Path(__file__).resolve()
    if this.parent.name == "app":
        root = this.parent.parent
        if (root / "app").exists():
            return root
    for parent in list(this.parents):
        if (parent / "app").exists() and (parent / ".git").exists():
            return parent
    return Path("/opt/zeropointai").resolve()

ZERO_ROOT    = detect_root()
DEFAULT_APP  = ZERO_ROOT / "app"
DEFAULT_DOCS = ZERO_ROOT / "docs" / "specs"

# ── MODULE_PROFILES ───────────────────────────────────────────────────────────

PROFILES: Dict[str, Dict[str, Any]] = {
    "foundation": {
        "metaphor": "Grundstenen.",
        "intent":   "Laddar och skyddar Layer 0 — systemets identitetsgrund.",
        "mental":   "Inte vanligt config. Bottenplattan som allt annat lutar mot men inte flyttar runt på.",
        "does":     ["Laddar Layer 0.", "Exponerar canonical foundation-data.", "Ger stabil identitetsgrund."],
        "does_not": ["Fattar inte runtime-beslut.", "Inte platsen för experimentell logik."],
        "remember": "Foundation är bottenplattan, inte ett inställningslager.",
        "owns":     ["Layer 0 loading.", "Foundation identity anchor.", "Canonical hash."],
        "not_own":  ["Runtime routing.", "Provider selection.", "Autonomy."],
        "place":    "Process start → foundation.py → alla Zero-moduler",
        "mis":      [("Foundation är config.", "Foundation är identitetsgrund.")],
        "risks":    ["Måste aldrig modifieras under körning."],
        "evolution":"Should become more protected and verifiable, not more flexible.",
    },
    "decomposer": {
        "metaphor": "En detektiv.",
        "intent":   "Bryter ner ett mål till problem, plan och beslutsunderlag.",
        "mental":   "Löser inte uppdraget. Förstår det så väl att nästa system kan välja rätt väg.",
        "does":     ["Identifierar kärnproblemet.", "Hittar saknad kontext.", "Ger Specialization Engine underlag."],
        "does_not": ["Exekverar inte tools.", "Skapar inte Entities.", "Fattar inte route-beslut."],
        "remember": "Decomposition är förståelse, inte execution.",
        "owns":     ["Goal understanding.", "Problem framing.", "Missing context detection."],
        "not_own":  ["Execution.", "Entity creation.", "Final routing."],
        "place":    "User goal → Decomposer → Specialization Engine → Gear 4",
        "mis":      [("Decomposer löser problemet.", "Decomposer förstår och strukturerar det.")],
        "risks":    ["Bör aldrig börja exekvera tools."],
        "evolution":"Should improve missing-context detection while staying non-executing.",
    },
    "specialization_engine": {
        "metaphor": "En flygledare.",
        "intent":   "Väljer bästa lösningsväg: DIRECT, FUNCTION, TASK eller ENTITY.",
        "mental":   "Avgör vilken bana målet ska lyfta från. Flyger inte planet. Bygger inte planet.",
        "does":     ["Väljer route.", "Beräknar confidence.", "Skyddar mot Entity-sprawl."],
        "does_not": ["Exekverar inte tasks.", "Skapar inte ACTIVE Entities.", "Ersätter inte Wizard."],
        "remember": "Den väljer bana — den flyger inte planet.",
        "owns":     ["Routing recommendation.", "DIRECT/FUNCTION/TASK/ENTITY contract."],
        "not_own":  ["Execution.", "Task state.", "Entity lifecycle."],
        "place":    "GoalDecomposition → Specialization Engine → route",
        "mis":      [("ENTITY = aktiv autonom agent.", "ENTITY = Draft Entity eller Wizard.")],
        "risks":    ["Fel routing slösar resurser eller skapar onödiga entities."],
        "evolution":"Should become the stable Gear 4 routing contract — small, deterministic, testable.",
    },
    "gear4": {
        "metaphor": "En dirigent.",
        "intent":   "Orkestrerar Gear 4-flödet från mål till vald lösningsväg.",
        "mental":   "Inte en monolit. Lyfter blicken, väljer subsystem och håller flödet koherent.",
        "does":     ["Kopplar goal → decomposer → specialization → route.", "Startar rätt subsystem.", "Håller identity anchor."],
        "does_not": ["Äger inte all intelligens.", "Är inte blind task-runner.", "Samlar inte all tool-logik."],
        "remember": "Gear 4 dirigerar arbetet — är inte hela orkestern.",
        "owns":     ["Orchestration flow.", "Routing between subsystems.", "Mission lifecycle."],
        "not_own":  ["Low-level tool implementation.", "Provider internals.", "All reasoning."],
        "place":    "Goal → Decomposer → Specialization → Gear 4 → Result",
        "mis":      [("Gear 4 är där allt arbete sker.", "Gear 4 orkestrerar rätt arbetare.")],
        "risks":    ["Identity drift under långa körningar.", "Specialiseringsdrift (tunnelseende)."],
        "evolution":"Should become thinner as subsystems mature.",
    },
    "entity_wizard": {
        "metaphor": "En mentor som hjälper Frank designa en specialist.",
        "intent":   "Guidar skapandet av Draft Entities genom en designkonversation.",
        "mental":   "Inte ett formulär. En mognadsprocess som avgör om en specialist bör skapas.",
        "does":     ["Driver designkonversationen.", "Frågar om syfte, domän, källor, gränser.", "Producerar Draft Entity-underlag."],
        "does_not": ["Skapar inte impulsiva Entities.", "Gör inte Entities ACTIVE direkt."],
        "remember": "Wizardens jobb är mognad före skapande.",
        "owns":     ["Entity design dialogue.", "Draft Entity proposal.", "Wizard state."],
        "not_own":  ["Runtime autonomy.", "ACTIVE promotion.", "Layer 0."],
        "place":    "ENTITY recommendation → Wizard → Draft Entity → Entity Manager",
        "mis":      [("Wizarden är ett formulär.", "Wizarden är en designkonversation.")],
        "risks":    ["Ska aldrig skapa Entities impulsivt."],
        "evolution":"Should become more conversational and discerning.",
    },
    "entity_manager": {
        "metaphor": "HR-avdelningen för Entities.",
        "intent":   "Hanterar Entity lifecycle, registry och Zero Recall.",
        "mental":   "Håller ordning på specialister — vilka finns, vilket stadium, ska de väckas eller pensioneras.",
        "does":     ["Hanterar lifecycle.", "Håller registry.", "Triggar Zero Recall mot tunnelseende."],
        "does_not": ["Designar inte filosofin.", "Utbildar inte Entities.", "Ersätter inte Wizard."],
        "remember": "Manager hanterar livscykel — uppfostrar inte specialisten.",
        "owns":     ["Entity lifecycle.", "Entity registry.", "Status transitions.", "Zero Recall scheduling."],
        "not_own":  ["Design dialogue.", "Training curriculum."],
        "place":    "Entity Draft → Entity Manager → Lifecycle state",
        "mis":      [("Entity Manager är Entity-hjärnan.", "Entity Manager är lifecycle/registry-lagret.")],
        "risks":    ["Entity-sprawl om inga gränser sätts (max rekommenderat: 7±2)."],
        "evolution":"Should mature around lifecycle governance and safe transitions.",
    },
    "entity": {
        "metaphor": "En specialiserad aspekt av samma identitet.",
        "intent":   "Definierar Entity-konceptets datastruktur och grundbeteende.",
        "mental":   "En Entity är inte en separat varelse. Zero som uttrycker sig genom ett smalare, djupare resonansfält.",
        "does":     ["Representerar fokuserade uttryck av Zero.", "Bär constitution, domän och lifecycle-status."],
        "does_not": ["Skapar inte separata personer.", "Bryter inte Layer 0.", "Ger inte autonomi automatiskt."],
        "remember": "Entity betyder specialisering, inte separation.",
        "owns":     ["Entity profile.", "Entity constitution.", "Specialized identity surface."],
        "not_own":  ["Layer 0.", "Autonomous execution."],
        "place":    "Layer 0 → Zero identity → Entity profile → Entity runtime",
        "mis":      [("En Entity är en separat personlighet.", "En Entity är ett specialiserat uttryck av Zero.")],
        "risks":    ["Identity bleed om constitution inte enforças."],
        "evolution":"Should mature around lifecycle: DRAFT→APPRENTICE→ACTIVE→MASTER→DORMANT→RETIRED.",
    },
    "task": {
        "metaphor": "En state machine.",
        "intent":   "Hanterar uppdragstillstånd, transitions och task journal.",
        "mental":   "Task är inte en agent. Spåret som visar var ett uppdrag befinner sig och vad som får hända härnäst.",
        "does":     ["Äger task-statusar.", "Validerar transitions.", "Sparar progress i STONE."],
        "does_not": ["Väljer inte strategi.", "Väljer inte provider.", "Mäter inte identitet."],
        "remember": "Task är tillstånd, inte medvetande.",
        "owns":     ["Task state machine.", "Task journal.", "Status transitions."],
        "not_own":  ["Strategy.", "Risk classification.", "Identity coherence."],
        "place":    "TASK route → Task Manager → Checkpoint → Result",
        "mis":      [("Task är agenten.", "Task är uppdragets state machine.")],
        "risks":    ["Halvfärdig state om atomicitet inte respekteras."],
        "evolution":"Should become more reliable for resume/review.",
    },
    "checkpoint": {
        "metaphor": "Ett save-game-system.",
        "intent":   "Sparar återstartbara checkpoints efter viktiga steg.",
        "mental":   "Gör det möjligt att våga testa utan att tappa var systemet var.",
        "does":     ["Sparar state och observation.", "Ger resume/rollback-punkter.", "Kopplar state till git hash."],
        "does_not": ["Ersätter inte git.", "Ersätter inte databasbackup.", "Avgör inte om ett steg är klokt."],
        "remember": "Checkpoint gör mod att testa möjligt.",
        "owns":     ["Checkpoint persistence.", "Resume/rollback pointers.", "Step recovery state."],
        "not_own":  ["Strategic decisions.", "Risk policy.", "Full backup."],
        "place":    "Task step → Checkpoint → Resume/Rollback",
        "mis":      [("Checkpoint är hela backup-systemet.", "Checkpoint är step-level recovery state.")],
        "risks":    ["Stora checkpoints kan bli tunga att lagra."],
        "evolution":"Should improve recoverability while staying lightweight.",
    },
    "coherence_contract": {
        "metaphor": "En domare.",
        "intent":   "Mäter om state/action är koherent med Layer 0, mission och entity.",
        "mental":   "Säger inte vad som är sant. Säger om systemets nästa steg fortfarande får ske.",
        "does":     ["Beräknar min(L0, mission, entity).", "Returnerar continue/warn/pause/abort.", "Sätter hårda L0-grind."],
        "does_not": ["Löser inte uppdrag.", "Bedömer inte domänsanning."],
        "remember": "Koherens är grind, inte intelligens.",
        "owns":     ["Coherence scoring.", "Layer 0/mission/entity gates.", "CoherenceResult contract."],
        "not_own":  ["Domain truth.", "Tool execution.", "Task planning."],
        "place":    "State/action → Coherence Contract → Anchor/Guardrails",
        "mis":      [("Coherence score är intelligens.", "Coherence score är kontraktskontroll.")],
        "risks":    ["För aggressiva grindar pausar nyttig körning."],
        "evolution":"Should become more measurable and less poetic.",
    },
    "identity_anchor": {
        "metaphor": "En kompass.",
        "intent":   "Förhindrar identitetsdrift under längre körningar.",
        "mental":   "Håller riktningen. Ger inte facit men märker när färden börjar glida bort från vem Zero är.",
        "does":     ["Kör quick/medium/deep anchor.", "Loggar drift till STONE.", "Pausar vid låg koherens."],
        "does_not": ["Ersätter inte coherence contract.", "Garanterar inte faktuell korrekthet."],
        "remember": "Anchor håller riktning, inte facit.",
        "owns":     ["Anchor scheduling.", "Identity drift detection.", "Pause/escalation callback."],
        "not_own":  ["Domain truth.", "General task planning.", "Final user approval."],
        "place":    "Gear 4 step → Identity Anchor → Continue/Warn/Pause/Abort",
        "mis":      [("Anchor gör svaren sanna.", "Anchor håller identiteten koherent.")],
        "risks":    ["För täta anchors bromsar körningar onödigt."],
        "evolution":"Should detect subtle drift without over-pausing useful work.",
    },
    "perspective": {
        "metaphor": "Ett perspektivarkiv.",
        "intent":   "Lagrar perspektiv med confidence, decay och Reality Check.",
        "mental":   "Äger inte sanningen. Spårar påståenden, källor, motsägelser och hur starkt de bör vägas just nu.",
        "does":     ["Lagrar perspektiv med metadata.", "Beräknar effective confidence med decay.", "Viktar Franks direktobservation högt."],
        "does_not": ["Förvandlar inte forumkonsensus till sanning.", "Ersätter inte verklighetskontroll."],
        "remember": "Perspektiv är spårbar tolkning, inte sanning.",
        "owns":     ["Perspective storage.", "Confidence decay.", "Reality Check weighting."],
        "not_own":  ["Absolute truth.", "External verification."],
        "place":    "Claim/source → Perspective Manager → effective confidence → summaries",
        "mis":      [("Sparade claims är sanna.", "Claims är perspektiv med confidence och källor.")],
        "risks":    ["Epistemic drift om decay inte respekteras."],
        "evolution":"Should improve evidence handling and contradiction tracking.",
    },
    "risk_policy": {
        "metaphor": "Säkerhetsvakten vid dörren.",
        "intent":   "Riskklassar operationer INNAN de körs.",
        "mental":   "Ska stå före handlingen — inte komma in efteråt och säga oj.",
        "does":     ["Klassar SAFE/CAUTION/HIGH/CRITICAL/FORBIDDEN.", "Stoppar eller kräver godkännande."],
        "does_not": ["Exekverar inte tools.", "Väljer inte uppdragets strategi."],
        "remember": "Risk check sker FÖRE action, inte efter.",
        "owns":     ["Risk classification.", "Allow/block recommendation.", "Forbidden pattern logic."],
        "not_own":  ["Execution.", "Goal strategy.", "Identity decisions."],
        "place":    "Planned operation → Risk Policy → allow/block/escalate",
        "mis":      [("Risk-policy är en logg efteråt.", "Risk-policy är en grind före action.")],
        "risks":    ["Felaktiga FORBIDDEN-mönster blockerar legitima operationer."],
        "evolution":"Should become more precise without becoming permissive by accident.",
    },
    "sudo": {
        "metaphor": "En betrodd exekverare med logg.",
        "intent":   "Kör systemkommandon med full behörighet, auto-backup och loggning.",
        "mental":   "Skyddet är inte frågor och dialoger. Skyddet är backup och loggning.",
        "does":     ["Kör kommandon säkert.", "Gör auto-backup vid CAUTION/HIGH.", "Loggar allt till STONE."],
        "does_not": ["Frågar inte om lov vid varje steg.", "Blockerar inte all farlig kod automatiskt."],
        "remember": "Zero lär sig av misstag — inte av att aldrig få göra dem.",
        "owns":     ["System execution.", "Auto git-backup.", "Sudo operation log."],
        "not_own":  ["Risk classification (zero_risk_policy).", "Task planning."],
        "place":    "Task Act step → zero_sudo → system + STONE log",
        "mis":      [("zero_sudo frågar alltid om lov.", "zero_sudo loggar och backar upp — frågar sällan.")],
        "risks":    ["CRITICAL-operationer kräver 3s paus och explicit godkännande."],
        "evolution":"Should become smarter about what needs backup vs what is safe to run directly.",
    },
    "spec_generator": {
        "metaphor": "En arkitekturöversättare.",
        "intent":   "Skapar korta specs som ger rätt mental modell innan koden läses.",
        "mental":   "Destillerar kodens arkitekturella mening — inte en lång rapport om implementation.",
        "does":     ["Infererar mental model, kontrakt och missförstånd.", "MAX_LINES-disciplin.", "Batch + index för hela app/."],
        "does_not": ["Kopierar inte implementation.", "Skapar inte låg-signal-dokument."],
        "remember": "Specen ska orientera, inte imponera.",
        "owns":     ["Spec draft generation.", "Mental model inference.", "Batch + index."],
        "not_own":  ["Final human approval.", "Runtime behavior."],
        "place":    "Python module → zero_spec_generator → docs/specs/<module>.md → review",
        "mis":      [("Mer dokumentation är bättre.", "Högre informationsdensitet är bättre.")],
        "risks":    ["Specs som är för långa förlorar sin orienterings-funktion."],
        "evolution":"Should improve architecture inference without growing verbose.",
    },
}


# ── AST-hjälpare ──────────────────────────────────────────────────────────────

def _unparse(node):
    if node is None: return ""
    try: return ast.unparse(node)
    except: return ""

def _arg_names(args):
    names = []
    for group in ("posonlyargs", "args", "kwonlyargs"):
        for arg in getattr(args, group, []) or []:
            names.append(arg.arg)
    if args.vararg: names.append("*" + args.vararg.arg)
    if args.kwarg:  names.append("**" + args.kwarg.arg)
    return names

def _extract_meta(docstring, source):
    meta = {}
    for line in ((docstring or "") + "\n" + source[:8000]).splitlines():
        m = re.match(r"\s*(ZERO_[A-Z0-9_]+)\s*:\s*(.+?)\s*$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta

def _first_sentence(text):
    if not text: return ""
    return text.strip().splitlines()[0].strip()[:120]

def _profile(module_name):
    n = module_name.lower().replace("zero_", "")
    for key in sorted(PROFILES, key=len, reverse=True):
        if key in n:
            return PROFILES[key]
    return {}

def _infer_risks(module_name, source, line_count, syntax_ok):
    blob = (module_name + "\n" + source[:18000]).lower()
    risks = []
    if any(x in blob for x in ["subprocess", "os.system", "sudo", "shell=true"]):
        risks.append("System execution — kräver risk policy och loggning.")
    if any(x in blob for x in ["password", "token", "secret", "api_key"]):
        risks.append("Secret-hantering — printa/spara aldrig faktiska värden.")
    if any(x in blob for x in ["execute_query", "postgres", "drm_memory"]):
        risks.append("STONE/databas — skrivningar måste vara spårbara.")
    if any(x in blob for x in ["entity", "identity", "coherence", "layer0"]):
        risks.append("Identitet/koherens — vaga kontrakt kan orsaka drift.")
    if any(x in blob for x in ["write_text", "unlink", "rmtree"]):
        risks.append("Filsystemsmutation — viktiga skrivningar behöver backup.")
    if line_count > 900:
        risks.append(f"Stor modul ({line_count} rader) — kan mixa ansvar.")
    if not syntax_ok:
        risks.append("Syntaxfel — modulen kan inte laddas.")
    return risks or ["Inga automatiskt detekterade risker."]

def _infer_api(tree):
    items = []
    preferred = ("run", "main", "evaluate", "analyze", "decompose",
                 "create", "get_", "start", "save", "load", "process")
    for node in tree.body:
        if len(items) >= 8: break
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            doc = _first_sentence(ast.get_docstring(node) or "")
            items.append(f"`{node.name}`" + (f" — {doc}" if doc else ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                if node.name.startswith(preferred) or len(items) < 4:
                    args = _arg_names(node.args)[:3]
                    sig  = f"{node.name}({', '.join(args)})"
                    doc  = _first_sentence(ast.get_docstring(node) or "")
                    items.append(f"`{sig}`" + (f" — {doc}" if doc else ""))
    return items


# ── ZeroSpecGenerator ─────────────────────────────────────────────────────────

class ZeroSpecGenerator:
    """Hybrid v6 — Groks disciplin + GPTs MODULE_PROFILES. Orienterar, imponerar inte."""

    def generate(self, file_path) -> str:
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            return f"# Fel: {file_path} hittades inte."

        source      = file_path.read_text(encoding="utf-8", errors="replace")
        module_name = file_path.stem
        line_count  = len(source.splitlines())
        syntax_ok   = True
        tree        = None

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            syntax_ok = False

        docstring = ast.get_docstring(tree) or "" if tree else ""
        meta      = _extract_meta(docstring, source)
        prof      = _profile(module_name)
        now       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            "---",
            f"MODULE: {module_name}.py  |  {line_count} rader  |  v{VERSION}",
            f"GENERATED: {now}",
            "---", "",
            f"# {module_name}.py", "",
        ]

        # Intent
        intent = (prof.get("intent") or meta.get("ZERO_ROLE")
                  or _first_sentence(docstring)
                  or f"Stödjer {module_name.replace('_', ' ')} i ZeroPointAI.")
        lines += ["## Intent", "", intent, ""]

        # Mental Model
        metaphor = prof.get("metaphor", "En fokuserad Zero-modul.")
        mental   = prof.get("mental", f"`{module_name}` bör förstås genom sitt kontrakt, inte sin implementation.")
        lines += ["## Mental Model", "", f"**{metaphor}**", "", mental, ""]

        # Gör / Gör inte
        does     = prof.get("does",     [meta.get("ZERO_ROLE", "Kapslar ett avgränsat ansvar.")])
        does_not = prof.get("does_not", ["Tar inte över andra modulers ansvar.", "Bryter inte Layer 0."])
        remember = prof.get("remember", "")
        lines += ["**Gör:**"]
        lines += [f"- {d}" for d in does[:4]]
        lines += ["", "**Gör inte:**"]
        lines += [f"- {d}" for d in does_not[:4]]
        if remember:
            lines += ["", f"**Kom ihåg:** {remember}"]
        lines.append("")

        # Kontrakt
        owns    = prof.get("owns",    ["Avgränsat ansvar."])
        not_own = prof.get("not_own", ["Andra modulers ansvar."])
        place   = prof.get("place",   meta.get("ZERO_DEPENDS", "Del av Zero-arkitekturen."))
        lines += [
            "## Kontrakt", "",
            f"**Owns:** {' | '.join(owns[:4])}",
            f"**Does Not Own:** {' | '.join(not_own[:4])}",
            "",
            "## Plats i Zero", "", "```", place, "```", "",
        ]

        # Non-negotiables
        non_neg = ["Bryter aldrig Layer 0.", "Hårdkodar aldrig secrets."]
        if remember:
            non_neg.insert(0, remember)
        lines += ["## Non-Negotiables", ""]
        lines += [f"- {n}" for n in non_neg[:4]]
        lines.append("")

        # Missförstånd
        mis = prof.get("mis", [("Implementationen är hela bilden.", "Specen ger den mentala modellen.")])
        lines += ["## Vanliga Missförstånd", ""]
        for wrong, right in mis[:3]:
            lines += [f"**Fel:** {wrong}", f"**Rätt:** {right}", ""]

        # Public API
        if tree:
            api = _infer_api(tree)
            if api:
                lines += ["## Public API", ""]
                lines += [f"- {a}" for a in api[:8]]
                lines.append("")

        # Risker
        risks = prof.get("risks") or _infer_risks(module_name, source, line_count, syntax_ok)
        lines += ["## Risker", ""]
        lines += [f"- {r}" for r in risks[:4]]
        lines.append("")

        # Evolution
        lines += ["## Evolution", "", prof.get("evolution", "Bör skärpa sitt kontrakt utan att absorbera orelaterade ansvar."), ""]

        # Test
        lines += ["## Test", "", "```bash"]
        lines.append(f"python3 -m py_compile app/{module_name}.py")
        if tree and ('if __name__ == "__main__"' in source):
            lines.append(f"python3 app/{module_name}.py --help")
            if "--test" in source:
                lines.append(f"python3 app/{module_name}.py --test")
        lines += ["```", ""]

        for key in ("ZERO_ROLE", "ZERO_DEPENDS", "ZERO_USED_BY"):
            if key in meta:
                lines.append(f"_{key}: {meta[key]}_")

        lines += ["", f"_v{VERSION}_"]

        content = "\n".join(lines)
        if len(content.splitlines()) > MAX_LINES:
            content = "\n".join(content.splitlines()[:MAX_LINES])
            content += f"\n\n_[Trunkerad — MAX_LINES={MAX_LINES}]_"

        return content

    def generate_batch(self, app_dir, docs_dir, pattern="*.py"):
        app_dir  = Path(app_dir)
        docs_dir = Path(docs_dir)
        docs_dir.mkdir(parents=True, exist_ok=True)
        results  = {}
        files    = sorted(app_dir.glob(pattern))
        print(f"Genererar specs för {len(files)} moduler → {docs_dir}")

        for f in files:
            if f.name.startswith("__"):
                continue
            try:
                spec     = self.generate(f)
                out_file = docs_dir / f"{f.stem}.md"
                out_file.write_text(spec, encoding="utf-8")
                results[f.name] = True
                print(f"  ✓ {f.name}")
            except Exception as e:
                results[f.name] = False
                print(f"  ✗ {f.name}: {e}")

        self._write_index(docs_dir, results)
        return results

    def _write_index(self, docs_dir, results):
        lines = [
            "# Zero Spec Index",
            f"_Genererad: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
            f"_Generator: v{VERSION}_", "",
            "| Modul | Status |",
            "|-------|--------|",
        ]
        for name, ok in sorted(results.items()):
            spec_name = name.replace(".py", ".md")
            lines.append(f"| [{name}]({spec_name}) | {'✓' if ok else '✗'} |")
        lines.append("")
        (docs_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"  → Index: {docs_dir / 'INDEX.md'}")

    def run(self, file_path: str):
        print(self.generate(file_path))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"ZeroPointAI Spec Generator v{VERSION}")
    parser.add_argument("file",  nargs="?",      help="Specifik .py-fil")
    parser.add_argument("--all", action="store_true", help="Batch — hela app/")
    parser.add_argument("--app", default=str(DEFAULT_APP),  help="app/-mapp")
    parser.add_argument("--docs",default=str(DEFAULT_DOCS), help="docs/specs/-mapp")
    args = parser.parse_args()

    gen = ZeroSpecGenerator()

    if args.all:
        results = gen.generate_batch(Path(args.app), Path(args.docs))
        ok = sum(1 for v in results.values() if v)
        print(f"\n{ok}/{len(results)} specs genererade → {args.docs}")
    elif args.file:
        gen.run(args.file)
    else:
        parser.print_help()
        print("\nExempel:")
        print("  python3 app/zero_spec_generator.py app/zero_gear4.py")
        print("  python3 app/zero_spec_generator.py --all")
