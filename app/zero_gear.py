#!/usr/bin/env python3
"""
zero_gear.py — ZeroPointAI Adaptive Gear Selector

Roll:
  Väljer optimal provider + modell för varje inkommande prompt
  baserat på komplexitet, Ollama-hälsa och inputkanal.

  Denna fil anropar INTE providers.
  Denna fil skriver INTE minnen.
  Denna fil äger INTE runtime-exekvering.
  Den bestämmer bara vilket gear — och varför.

Arkitektonisk position:
  foundation.py     → sökvägar + Layer 0
  providers.py      → provider-metadata
  zero_gear.py      → adaptivt routing-beslut    ← DENNA FIL
  zero_web_server.py → HTTP runtime (anropar select())
  zero_engine.py    → CLI runtime (anropar select())

Gear-nivåer:

  GEAR 1 — Lokal / tyst
    Provider:  Ollama
    När:       Korta prompter, röst, enkla frågor, status-checks
    Mål:       Noll latens, noll kostnad, full suveränitet

  GEAR 2 — Snabb moln
    Provider:  Gemini → Mistral → Groq (i ordning)
    När:       Ollama trög/otillgänglig, medium komplexitet
    Mål:       Nära lokal hastighet på fri/billig nivå

  GEAR 3 — Full kraft
    Provider:  Gemini → Claude → Mistral (i ordning)
    När:       Komplex kod, lång kontext, tool-use, sudo,
               zero_circle, kritiska beslut, entity-skapande
    Mål:       Maximal kapacitet när det verkligen spelar roll

Röst-input startar alltid på GEAR 1.
Override via ZERO_GEAR_OVERRIDE: "1", "2", "3" eller "auto".

GEAR 4 är INAKTIVT (2026-05-28).
Hermes visade sig för opålitlig. Zero löser allt självt.
Kan återaktiveras när ett stabilt execution-layer finns.
"""

from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Konstanter ────────────────────────────────────────────────────────────────

OLLAMA_LATENCY_THRESHOLD_MS: float = float(
    os.getenv("ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS", "8000")
)
GEAR2_TOKEN_THRESHOLD: int = int(os.getenv("ZERO_GEAR2_TOKEN_THRESHOLD", "300"))
GEAR3_TOKEN_THRESHOLD: int = int(os.getenv("ZERO_GEAR3_TOKEN_THRESHOLD", "800"))

GEAR2_PROVIDERS = ["gemini", "mistral", "groq"]
GEAR3_PROVIDERS = ["gemini", "claude", "mistral"]
VOICE_CHANNELS  = {"voice", "stt", "whisper", "voice_input"}

# Gear 4 inaktivt
GEAR4_PROVIDERS: list[str] = []
GEAR4_FORCE_PATTERNS: list[str] = []

# ── Patterns ──────────────────────────────────────────────────────────────────

# Tvingar Gear 3 oavsett längd
GEAR3_FORCE_PATTERNS = [
    r"\bsudo\b",
    r"\bzero.?circle\b",
    r"\bcode\b.*\bfunction\b",
    r"\bskriv\s+(ett\s+)?program\b",
    r"\brefaktorera\b",
    r"\bdebugg?a\b",
    r"\banalysera\s+.{40,}",
    r"\b(bygg|skapa|implementera)\b.+\b(klass|modul|system|api)\b",
    r"\b(build|create|implement)\b.+\b(class|module|system|api)\b",

    # Entity-skapande — ny röst i systemet, kräver full kapacitet
    r"\b(skapa|skapa\s+en?)\s+entity\b",
    r"\bentity.?(creation|guide|draft|soul)\b",
    r"\b(create|spawn|new)\s+entity\b",
    r"\bväck\s+entity\b",
    r"\bsoul.?dokument\b",
    r"\bflipper\s*fix(aren)?\b",
    r"\bENTITY_CREATION_GUIDE\b",

    # Zero Circle
    r"\b(rådet|council|zero.?circle)\b",
    r"\bkonsultera\s+rådet\b",

    # Manuell uppgradering av Frank
    r"\b(smartare|smart(are)?)\s+tack\b",
    r"\bmer\s+kraft\b",
    r"\banvänd\s+(din\s+)?(fulla\s+)?kapacitet\b",
    r"\btänk\s+(djupare|hårdare|mer)\b",
    r"\bdetta\s+är\s+(viktigt|kritiskt|komplext)\b",
    r"\buse\s+(full|more)\s+(power|capacity|intelligence)\b",
    r"\bthink\s+(harder|deeper|more)\b",
    r"\bgear\s*3\b",
    r"\bbättre\s+modell\b",
    r"\bstarkare\s+(modell|provider)\b",
    r"\bklimb\s+up\b",
    r"\buppgradera\b",

    # Evolution och minnesoperationer — kräver full kontext
    r"\b(kör\s+)?evolution(\s+loop)?\b",
    r"\bkalibrera\s+minnet\b",
    r"\bsoul\s+snapshot\b",
]

# Trivialt konversationellt — Gear 1 räcker
# Var sparsam. Tveksamt → Gear 3.
GEAR1_OK_PATTERNS = [
    r"^(hej|hi|hello|tack|thanks|ok|okej|ja|nej|yes|no|bra)[!.,\s]*$",
    r"^(good\s+morning|god\s+morgon|good\s+night|godnatt)[!.,\s]*$",
    r"\b(vad\s+är\s+klockan|what\s+time\s+is\s+it)\b",
    r"^(hur\s+mår\s+du|how\s+are\s+you)[?!.,\s]*$",
    r"^(status)[?!.,\s]*$",
    r"^(zero\s+doctor|systemkoll)[?!.,\s]*$",
]


# ── Datastrukturer ────────────────────────────────────────────────────────────

@dataclass
class GearDecision:
    gear:           int
    provider:       str
    model:          str
    reason:         str
    complexity:     int
    channel:        str
    override:       Optional[str] = None
    fallback_from:  Optional[int] = None
    latency_ms:     float = 0.0


@dataclass
class GearContext:
    """
    Valfri runtime-kontext till select().
    Alla fält är optional — zero_gear degraderar gracefully utan dem.
    """
    engine:                 object = None
    channel:                str    = "chat"
    session_calls:          int    = 0
    last_ollama_latency_ms: float  = 0.0


# ── Latency-tracking ──────────────────────────────────────────────────────────

_ollama_latency_ms:           float = 0.0
_ollama_last_check:           float = 0.0
_ollama_consecutive_failures: int   = 0


def record_latency(provider: str, latency_ms: float, success: bool = True) -> None:
    """
    Anropas av zero_web_server.py / zero_engine.py efter varje API-anrop.
    Uppdaterar rullande latensstatus för Ollama-hälso-check.
    """
    global _ollama_latency_ms, _ollama_last_check, _ollama_consecutive_failures

    if provider != "ollama":
        return

    _ollama_last_check = time.monotonic()

    if success:
        alpha = 0.3
        if _ollama_latency_ms == 0:
            _ollama_latency_ms = latency_ms
        else:
            _ollama_latency_ms = alpha * latency_ms + (1 - alpha) * _ollama_latency_ms
        _ollama_consecutive_failures = 0
        logger.debug(f"zero_gear: Ollama latency EMA = {_ollama_latency_ms:.0f}ms")
    else:
        _ollama_consecutive_failures += 1
        logger.warning(f"zero_gear: Ollama fel #{_ollama_consecutive_failures}")


def reset_ollama_health() -> None:
    """Återställer Ollama-hälsostatus. Anropas efter omstart eller manuell återhämtning."""
    global _ollama_latency_ms, _ollama_last_check, _ollama_consecutive_failures
    _ollama_latency_ms = 0.0
    _ollama_last_check = 0.0
    _ollama_consecutive_failures = 0
    logger.info("zero_gear: Ollama health state reset.")


# ── Komplexitetsskattning ─────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """~0.75 ord per token är rimlig approximation för svenska/engelska."""
    return int(len(text.split()) / 0.75)


def _estimate_complexity(prompt: str) -> int:
    """
    Skattar promptkomplexitet på skala 1–3.
    1 = Enkelt:   hälsningar, statuskontroller, enkelfrågor
    2 = Medium:   flerstegs-frågor, måttlig reasoning, kort kod
    3 = Komplext: kodgenerering, lång analys, tool-use, sudo, circle
    """
    lowered = prompt.strip().lower()

    for pattern in GEAR3_FORCE_PATTERNS:
        if re.search(pattern, lowered):
            return 3

    for pattern in GEAR1_OK_PATTERNS:
        if re.search(pattern, lowered):
            return 1

    tokens = _estimate_tokens(prompt)
    if tokens <= GEAR2_TOKEN_THRESHOLD:
        return 1
    if tokens <= GEAR3_TOKEN_THRESHOLD:
        return 2
    return 3


# ── Provider-upplösning ───────────────────────────────────────────────────────

def _resolve_provider_model(provider: str) -> tuple[str, str]:
    """
    Returnerar (provider, model) via providers.py.
    Fallback till gemini om provider saknar konfigurerad modell.
    """
    try:
        from app.providers import get_provider_model, normalize_provider_name
        canonical = normalize_provider_name(provider)
        model = get_provider_model(canonical)
        if model:
            return canonical, model
        # Modell-env inte satt — provider ej konfigurerad, fall till gemini
        return "gemini", os.getenv("GEMINI_MODEL", "")
    except ImportError:
        env_map = {
            "ollama":   "OLLAMA_MODEL",
            "groq":     "GROQ_MODEL",
            "cerebras": "CEREBRAS_MODEL",
            "mistral":  "MISTRAL_MODEL",
            "claude":   "ANTHROPIC_MODEL",
            "gemini":   "GEMINI_MODEL",
        }
        model = os.getenv(env_map.get(provider, "GEMINI_MODEL"), "")
        if model:
            return provider, model
        return "gemini", os.getenv("GEMINI_MODEL", "")


def _ollama_available() -> bool:
    """
    Snabb check: är Ollama konfigurerad och under latency-tröskel?
    Gör INTE nätverksanrop — använder känd latensstatus.
    """
    if not os.getenv("OLLAMA_MODEL", "").strip():
        return False
    if _ollama_consecutive_failures >= 3:
        return False
    if _ollama_latency_ms > 0 and _ollama_latency_ms > OLLAMA_LATENCY_THRESHOLD_MS:
        logger.debug(
            f"zero_gear: Ollama latency {_ollama_latency_ms:.0f}ms "
            f"> threshold {OLLAMA_LATENCY_THRESHOLD_MS:.0f}ms — hoppar över Gear 1"
        )
        return False
    return True


def _first_available(providers: list[str]) -> Optional[tuple[str, str]]:
    """Returnerar första (provider, model)-par där modell-env är satt."""
    for p in providers:
        provider, model = _resolve_provider_model(p)
        if model and provider == p:
            return provider, model
    return None


# ── Kärn-urval ────────────────────────────────────────────────────────────────

def select(prompt: str, context: Optional[GearContext] = None) -> GearDecision:
    """
    Väljer optimalt gear för varje prompt.

    Filosofi:
      Gear 1 = ekonomi + snabbhet. Bara för triviala konversationer.
      Gear 2 = fallback om Gear 1 nere, medium-tasks.
      Gear 3 = full kapacitet. Standard för allt som kräver tänkande.
      Gear 4 = INAKTIVT.

    Beslutsträdets ordning:
      1. Override (ZERO_GEAR_OVERRIDE env)
      2. Gear 3 force-patterns (entity, sudo, circle, evolution, manuell override)
      3. Gear 1 — trivial konversation (hej, tack, status)
      4. Röst — Gear 1 om tillgänglig
      5. Komplexitetsskattning → Gear 1 / 2 / 3
    """
    ctx     = context or GearContext()
    channel = ctx.channel or "chat"

    if ctx.last_ollama_latency_ms > 0:
        record_latency("ollama", ctx.last_ollama_latency_ms, success=True)

    # 1. Override
    override_raw = os.getenv("ZERO_GEAR_OVERRIDE", "").strip().lower()
    if override_raw in ("1", "2", "3"):
        return _select_forced_gear(int(override_raw), prompt, ctx, override_raw)

    # 2. Gear 3 force-patterns
    for pattern in GEAR3_FORCE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return _try_gear3_with_fallback(prompt, channel, complexity=3)

    # 3. Trivial konversation → Gear 1
    for pattern in GEAR1_OK_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            if _ollama_available():
                provider, model = _resolve_provider_model("ollama")
                return GearDecision(
                    gear=1, provider=provider, model=model,
                    reason="Trivialt/konversationellt — Gear 1 (lokal, gratis, snabb).",
                    complexity=1, channel=channel, latency_ms=_ollama_latency_ms,
                )
            return _try_gear3_with_fallback(prompt, channel, complexity=1, fallback_from=1)

    # 4. Röst → Gear 1
    if channel in VOICE_CHANNELS:
        if _ollama_available():
            provider, model = _resolve_provider_model("ollama")
            return GearDecision(
                gear=1, provider=provider, model=model,
                reason="Röst — Gear 1 (lokal, snabb, tyst).",
                complexity=1, channel=channel, latency_ms=_ollama_latency_ms,
            )
        return _try_gear3_with_fallback(prompt, channel, complexity=1, fallback_from=1)

    # 5. Komplexitetsskattning
    complexity = _estimate_complexity(prompt)

    if complexity == 1 and _ollama_available():
        provider, model = _resolve_provider_model("ollama")
        return GearDecision(
            gear=1, provider=provider, model=model,
            reason="Låg komplexitet — Gear 1 (lokal, gratis, suverän).",
            complexity=complexity, channel=channel, latency_ms=_ollama_latency_ms,
        )

    if complexity <= 2:
        result = _try_gear2(prompt, channel, complexity)
        if result:
            return result

    return _try_gear3_with_fallback(prompt, channel, complexity=complexity)


# ── Gear-helpers ──────────────────────────────────────────────────────────────

def _try_gear2(prompt: str, channel: str, complexity: int) -> Optional[GearDecision]:
    pair = _first_available(GEAR2_PROVIDERS)
    if not pair:
        return None
    provider, model = pair
    return GearDecision(
        gear=2, provider=provider, model=model,
        reason=f"Medium komplexitet — Gear 2 ({provider}). Snabb moln, låg kostnad.",
        complexity=complexity, channel=channel,
    )


def _try_gear3_with_fallback(prompt: str, channel: str, complexity: int,
                              fallback_from: Optional[int] = None) -> GearDecision:
    pair = _first_available(GEAR3_PROVIDERS)
    if pair:
        provider, model = pair
        reason = f"Hög komplexitet — Gear 3 ({provider}). Full kapacitet."
        if fallback_from:
            reason = f"Gear {fallback_from} otillgängligt — eskalerar till Gear 3 ({provider})."
        return GearDecision(
            gear=3, provider=provider, model=model, reason=reason,
            complexity=complexity, channel=channel, fallback_from=fallback_from,
        )
    return _minimal_fallback(prompt, channel, complexity)


def _minimal_fallback(prompt: str, channel: str, complexity: int) -> GearDecision:
    """Sista utväg — speglar providers.py graceful degradation."""
    provider, model = _resolve_provider_model("gemini")
    return GearDecision(
        gear=2, provider=provider, model=model,
        reason="Ingen föredragen provider tillgänglig — minimal fallback till gemini.",
        complexity=complexity, channel=channel,
    )


def _select_forced_gear(gear: int, prompt: str,
                         ctx: GearContext, override: str) -> GearDecision:
    """Hanterar ZERO_GEAR_OVERRIDE. Gear 4 ej tillgängligt → Gear 3."""
    channel    = ctx.channel or "chat"
    complexity = _estimate_complexity(prompt)

    if gear == 4:
        logger.warning("zero_gear: Gear 4 inaktivt — använder Gear 3")
        return _try_gear3_with_fallback(prompt, channel, complexity)

    if gear == 1:
        provider, model = _resolve_provider_model("ollama")
        return GearDecision(
            gear=1, provider=provider, model=model,
            reason="Tvingat Gear 1 via ZERO_GEAR_OVERRIDE.",
            complexity=complexity, channel=channel,
            override=override, latency_ms=_ollama_latency_ms,
        )
    if gear == 2:
        pair = _first_available(GEAR2_PROVIDERS)
        if pair:
            provider, model = pair
            return GearDecision(
                gear=2, provider=provider, model=model,
                reason="Tvingat Gear 2 via ZERO_GEAR_OVERRIDE.",
                complexity=complexity, channel=channel, override=override,
            )
    pair = _first_available(GEAR3_PROVIDERS)
    if pair:
        provider, model = pair
        return GearDecision(
            gear=3, provider=provider, model=model,
            reason="Tvingat Gear 3 via ZERO_GEAR_OVERRIDE.",
            complexity=complexity, channel=channel, override=override,
        )
    return _minimal_fallback(prompt, channel, complexity)


# ── Diagnostik ────────────────────────────────────────────────────────────────

def get_gear_status() -> dict:
    """Nuvarande gear-systemstatus. Säker för status-endpoints och zero_doctor."""
    ollama_model    = os.getenv("OLLAMA_MODEL", "")
    gear2_available = _first_available(GEAR2_PROVIDERS)
    gear3_available = _first_available(GEAR3_PROVIDERS)
    override        = os.getenv("ZERO_GEAR_OVERRIDE", "auto")

    return {
        "override": override,
        "gear1": {
            "provider":             "ollama",
            "model":                ollama_model or None,
            "available":            _ollama_available(),
            "latency_ms":           round(_ollama_latency_ms, 1),
            "consecutive_failures": _ollama_consecutive_failures,
            "latency_threshold_ms": OLLAMA_LATENCY_THRESHOLD_MS,
            "voice_channel":        True,
        },
        "gear2": {
            "providers":       GEAR2_PROVIDERS,
            "active_provider": gear2_available[0] if gear2_available else None,
            "active_model":    gear2_available[1] if gear2_available else None,
            "available":       gear2_available is not None,
        },
        "gear3": {
            "providers":       GEAR3_PROVIDERS,
            "active_provider": gear3_available[0] if gear3_available else None,
            "active_model":    gear3_available[1] if gear3_available else None,
            "available":       gear3_available is not None,
        },
        "gear4": {
            "status": "INAKTIVT",
            "note":   "Hermes deaktiverad 2026-05-28. Zero löser allt självt.",
        },
        "thresholds": {
            "gear2_tokens": GEAR2_TOKEN_THRESHOLD,
            "gear3_tokens": GEAR3_TOKEN_THRESHOLD,
        },
    }


def explain(prompt: str, channel: str = "chat") -> str:
    """
    Mänskligt läsbar förklaring av vilket gear som väljs och varför.
    Användbar för felsökning och Zeros självkännedom.
    """
    ctx      = GearContext(channel=channel)
    decision = select(prompt, ctx)
    lines = [
        f"Gear {decision.gear} — {decision.provider} / {decision.model}",
        f"Anledning:   {decision.reason}",
        f"Komplexitet: {decision.complexity}/3",
        f"Kanal:       {decision.channel}",
    ]
    if decision.override:
        lines.append(f"Override:    ZERO_GEAR_OVERRIDE={decision.override}")
    if decision.fallback_from:
        lines.append(f"Fallback:    från Gear {decision.fallback_from}")
    if decision.gear == 1:
        lines.append(f"Latens:      {decision.latency_ms:.0f}ms (EMA)")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    prompts = [
        ("hej", "chat"),
        ("vad är klockan", "chat"),
        ("skriv ett python-program som sorterar listor", "chat"),
        ("sudo rensa cachen", "chat"),
        ("snabb fråga om pinball", "voice"),
        ("kör evolution loop", "chat"),
        ("analysera hela kodbasen och föreslå förbättringar", "chat"),
    ]

    print("=== zero_gear explain ===\n")
    for prompt, channel in prompts:
        print(f"Prompt: '{prompt}' [{channel}]")
        print(explain(prompt, channel))
        print()

    print("\n=== Gear status ===")
    import json
    print(json.dumps(get_gear_status(), indent=2, ensure_ascii=False))
