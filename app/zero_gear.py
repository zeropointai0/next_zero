#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zero_gear.py — ZeroPointAI Adaptive Gear Selector v1.0

Role:
  Selects the optimal provider + model for each incoming request
  based on complexity, Ollama health, and input channel.

  This module does NOT call providers.
  This module does NOT write memory.
  This module does NOT own runtime execution.
  This module only decides which gear to use — and why.

Architectural position:

  foundation.py           → canonical truth
  providers.py            → provider metadata
  zero_gear.py            → adaptive routing decision  ← THIS FILE
  zero_web_server.py      → HTTP runtime (calls select())
  zero_engine.py          → CLI runtime (calls select())

Gear levels:

  GEAR 1 — Local / silent
    Provider:  Ollama
    Use when:  Short prompts, voice input, simple questions,
               memory ops, reflection, status checks.
    Goal:      Zero latency, zero cost, full sovereignty.

  GEAR 2 — Fast cloud
    Provider:  Groq → Cerebras → Mistral (in order)
    Use when:  Ollama is slow/unavailable, medium complexity,
               reasoning tasks that need more than local can give.
    Goal:      Near-local speed at free/cheap tier.

  GEAR 3 — Full power
    Provider:  Claude → Gemini → Mistral (in order)
    Use when:  Complex code, long context, tool-use, sudo requests,
               zero_circle, critical decisions.
    Goal:      Maximum capability when it actually matters.

Voice input always starts at GEAR 1.
Override via ZERO_GEAR_OVERRIDE env var: "1", "2", "3", or "auto".

ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Gear-selektion — väljer provider och kapacitetsnivå per prompt
ZERO_DEPENDS:   foundation.py, providers.py
ZERO_USED_BY:   zero_engine.py, zero_web_server.py
"""

from __future__ import annotations

import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Ollama latency threshold. If last call took longer than this, skip Gear 1.
OLLAMA_LATENCY_THRESHOLD_MS: float = float(
    os.getenv("ZERO_GEAR_OLLAMA_LATENCY_THRESHOLD_MS", "8000")
)

# Token estimate thresholds for complexity scoring
GEAR2_TOKEN_THRESHOLD: int = int(os.getenv("ZERO_GEAR2_TOKEN_THRESHOLD", "300"))
GEAR3_TOKEN_THRESHOLD: int = int(os.getenv("ZERO_GEAR3_TOKEN_THRESHOLD", "800"))

# Gear 2 provider preference order (first available wins)
GEAR2_PROVIDERS = ["gemini", "mistral", "groq"]

# Gear 3 provider preference order (first available wins)
GEAR3_PROVIDERS = ["gemini", "claude", "mistral"]

# Input channels that always start at Gear 1
VOICE_CHANNELS = {"voice", "stt", "whisper", "voice_input"}

# Patterns that force Gear 3 regardless of length
GEAR3_FORCE_PATTERNS = [
    r"\bsudo\b",
    r"\bzero.?circle\b",
    r"\bcode\b.*\bfunction\b",
    r"\bskriv\s+(ett\s+)?program\b",
    r"\brefaktorera\b",
    r"\bdebugg?a\b",
    r"\banalysera\s+.{40,}",          # long analysis requests
    r"\b(bygg|skapa|implementera)\b.+\b(klass|modul|system|api)\b",
    r"\b(build|create|implement)\b.+\b(class|module|system|api)\b",

    # Entity-skapande kräver alltid Gear 3 — aldrig Gear 1/2
    # En entity är en ny röst i systemet. Det kräver full kapacitet.
    r"\b(skapa|skapa\s+en?)\s+entity\b",
    r"\bentity.?(creation|guide|draft|soul)\b",
    r"\b(create|spawn|new)\s+entity\b",
    r"\bväck\s+entity\b",
    r"\bsoul.?dokument\b",
    r"\bflipper\s*fix(aren)?\b",
    r"\bENTITY_CREATION_GUIDE\b",

    # Zero Circle konsultation kräver Gear 3
    r"\b(rådet|council|zero.?circle)\b",
    r"\bkonsultera\s+rådet\b",

    # Systemrelaterade frågor — kräver faktisk åtkomst, inte träningsdata
    r"\b(\.env|env.fil|miljövariabel|environment variable)\b",
    r"\b(mailserver|imap|smtp|mail.*inställning)\b",
    r"\b(finns det|finns det.*\?|har du|kan du läsa|kan du kolla)\b.{0,30}\b(fil|mapp|modul|konfiguration|inställning)\b",
    r"\b(läs|visa|kolla|hämta).{0,20}\b(fil|\.env|\.py|\.json|\.yaml)\b",

    # Manuell override — Frank ber om mer kapacitet
    # Naturligt språk för att byta upp till Gear 3
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
]

# Patterns som är trivialt konversationella — Gear 1 räcker
# VIKTIGT: Var snål med dessa. Tveksamt? → Gear 3.
# Gear 1 = ekonomi och snabbhet, INTE "enkla frågor"
GEAR1_OK_PATTERNS = [
    r"^(hej|hi|hello|tack|thanks|ok|okej|ja|nej|yes|no|bra|ok)[!.,\s]*$",
    r"^(good\s+morning|god\s+morgon|good\s+night|godnatt)[!.,\s]*$",
    r"\b(vad\s+är\s+klockan|what\s+time\s+is\s+it)\b",
    r"^(hur\s+mår\s+du|how\s+are\s+you)[?!.,\s]*$",
    r"^(status)[?!.,\s]*$",
    r"^(zero\s+doctor|systemkoll)[?!.,\s]*$",
]

# Gear 4 är INAKTIVT (2026-05-28)
# Hermes visade sig vara för opålitlig för produktionsbruk.
# Zero löser alla uppgifter själv via sina egna moduler och API-endpoints.
# Gear 4 kan återaktiveras när ett stabilt execution-layer byggts internt.
GEAR4_PROVIDERS: list[str] = []
GEAR4_FORCE_PATTERNS: list[str] = []

# Rolling latency tracker for Ollama (updated externally via record_latency())
_ollama_latency_ms: float = 0.0
_ollama_last_check: float = 0.0
_ollama_consecutive_failures: int = 0

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class GearDecision:
    gear: int                          # 1, 2, or 3
    provider: str                      # canonical provider name
    model: str                         # model string from .env
    reason: str                        # human-readable explanation
    complexity: int                    # estimated complexity 1–3
    channel: str                       # input channel ("chat", "voice", etc.)
    override: Optional[str] = None     # ZERO_GEAR_OVERRIDE value if active
    fallback_from: Optional[int] = None  # if we fell back from a higher gear
    latency_ms: float = 0.0            # Ollama last known latency

@dataclass
class GearContext:
    """
    Optional runtime context passed to select().
    All fields are optional — zero_gear degrades gracefully without them.
    """
    engine: object = None              # zero engine instance (for health score)
    channel: str = "chat"              # "chat", "voice", "stt", "telegram", etc.
    session_calls: int = 0             # number of calls in this session
    last_ollama_latency_ms: float = 0.0  # injected by caller if available

# ── Complexity estimation ─────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """
    Rough token estimate without a tokenizer.
    ~0.75 words per token is a reasonable approximation for Swedish/English.
    """
    words = len(text.split())
    return int(words / 0.75)

def _estimate_complexity(prompt: str) -> int:
    """
    Estimate prompt complexity on a 1–3 scale.

    1 = Simple:  greetings, status checks, single-fact questions, voice input
    2 = Medium:  multi-step questions, moderate reasoning, short code questions
    3 = Complex: code generation, long analysis, tool-use, sudo, zero_circle

    Returns int 1, 2, or 3.
    """
    lowered = prompt.strip().lower()

    # Gear 3 override patterns — checked first
    for pattern in GEAR3_FORCE_PATTERNS:
        if re.search(pattern, lowered):
            return 3

    # Gear 1 shortcut patterns — checked before token count
    for pattern in GEAR1_OK_PATTERNS:
        if re.search(pattern, lowered):
            return 1

    # Token-based fallback
    tokens = _estimate_tokens(prompt)
    if tokens <= GEAR2_TOKEN_THRESHOLD:
        return 1
    if tokens <= GEAR3_TOKEN_THRESHOLD:
        return 2
    return 3

# ── Provider resolution ───────────────────────────────────────────────────────

def _resolve_provider_model(provider: str) -> tuple[str, str]:
    """
    Return (provider, model) using providers.py metadata.
    Falls back to mistral if provider is unavailable or model env is empty.
    """
    try:
        from app.providers import get_provider_model, normalize_provider_name
        canonical = normalize_provider_name(provider)
        model = get_provider_model(canonical)
        if model:
            return canonical, model
        # Model env not set — provider not configured
        return "mistral", os.getenv("MISTRAL_MODEL", "mistral-medium-latest")
    except ImportError:
        # providers.py not available — minimal fallback
        env_map = {
            "ollama":    "OLLAMA_MODEL",
            "groq":      "GROQ_MODEL",
            "cerebras":  "CEREBRAS_MODEL",
            "mistral":   "MISTRAL_MODEL",
            "claude":    "CLAUDE_MODEL",
            "gemini":    "GEMINI_MODEL",
        }
        env_key = env_map.get(provider, "MISTRAL_MODEL")
        model = os.getenv(env_key, "")
        if model:
            return provider, model
        return "mistral", os.getenv("MISTRAL_MODEL", "mistral-medium-latest")

def _ollama_available() -> bool:
    """
    Quick check: is Ollama configured and not over latency threshold?
    Does NOT make a network call — uses known latency state.
    """
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not model:
        return False
    if _ollama_consecutive_failures >= 3:
        return False
    if _ollama_latency_ms > 0 and _ollama_latency_ms > OLLAMA_LATENCY_THRESHOLD_MS:
        logger.debug(
            f"zero_gear: Ollama latency {_ollama_latency_ms:.0f}ms "
            f"> threshold {OLLAMA_LATENCY_THRESHOLD_MS:.0f}ms — skipping Gear 1"
        )
        return False
    return True

def _first_available(providers: list[str]) -> Optional[tuple[str, str]]:
    """
    Return the first (provider, model) pair where a model env is set.
    """
    for p in providers:
        provider, model = _resolve_provider_model(p)
        if model and provider == p:  # ensure we got what we asked for
            return provider, model
    return None

# ── Core selection logic ──────────────────────────────────────────────────────

def select(
    prompt: str,
    context: Optional[GearContext] = None,
) -> GearDecision:
    """
    Väljer optimalt gear för varje prompt.

    FILOSOFI (2026-05-28):
      Gear 1 = ekonomi + snabbhet. Bara för triviala konversationer.
      Gear 2 = fallback om Gear 3 nere.
      Gear 3 = Full kapacitet. Används när Gear 1/2 inte räcker.
      Gear 4 = INAKTIVT. Zero löser allt själv.

    Local-first: Gear 1 → Gear 2 → Gear 3 (eskalera vid behov).
    Gear 3 för komplexa uppgifter, entitets-skapande, sudo, analys.
    Det som kostar mer är dåliga svar.

    Beslutsträdets ordning:
      1. Override (ZERO_GEAR_OVERRIDE env)
      2. Gear 3 — force patterns (entity, sudo, circle, manuell override)?
      3. Gear 1 — trivialt konversationellt (hej, tack, status)?
      4. Röst — Gear 1 om tillgänglig
      5. Gear 3 — standard för allt annat
    """
    ctx = context or GearContext()

    if ctx.last_ollama_latency_ms > 0:
        record_latency("ollama", ctx.last_ollama_latency_ms, success=True)

    channel = ctx.channel or "chat"

    # === 1. OVERRIDE ===
    override_raw = os.getenv("ZERO_GEAR_OVERRIDE", "").strip().lower()
    if override_raw in ("1", "2", "3"):
        override_gear = int(override_raw)
        return _select_forced_gear(override_gear, prompt, ctx, override=override_raw)

    # === 2. GEAR 3 — force patterns ===
    for pattern in GEAR3_FORCE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return _try_gear3_with_fallback(prompt, channel, complexity=3)

    # === 3. GEAR 1 — trivialt konversationellt ===
    for pattern in GEAR1_OK_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            if _ollama_available():
                provider, model = _resolve_provider_model("ollama")
                return GearDecision(
                    gear=1,
                    provider=provider,
                    model=model,
                    reason="Trivial/konversationellt — Gear 1 (lokal, gratis, snabb).",
                    complexity=1,
                    channel=channel,
                    latency_ms=_ollama_latency_ms,
                )
            # Ollama nere — Gear 3 direkt
            return _try_gear3_with_fallback(prompt, channel, complexity=1, fallback_from=1)

    # === 4. RÖST — alltid Gear 1 om tillgänglig ===
    if channel in VOICE_CHANNELS:
        if _ollama_available():
            provider, model = _resolve_provider_model("ollama")
            return GearDecision(
                gear=1,
                provider=provider,
                model=model,
                reason="Röst — Gear 1 (lokal, snabb, tyst).",
                complexity=1,
                channel=channel,
                latency_ms=_ollama_latency_ms,
            )
        return _try_gear3_with_fallback(prompt, channel, complexity=1, fallback_from=1)

    # === 5. GEAR 3 — standard för allt annat ===
    # Local-first: försök Gear 1 för enkla frågor, Gear 2 för medium, Gear 3 bara vid behov
    complexity = _estimate_complexity(prompt)
    if complexity == 1:
        if _ollama_available():
            provider, model = _resolve_provider_model("ollama")
            return GearDecision(
                gear=1, provider=provider, model=model,
                reason="Low complexity — Gear 1 (local, free, sovereign).",
                complexity=complexity, channel=channel,
                latency_ms=_ollama_latency_ms,
            )
    if complexity <= 2:
        result = _try_gear2(prompt, channel, complexity)
        if result:
            return result
    return _try_gear3_with_fallback(prompt, channel, complexity=complexity)

def _try_gear1_with_fallback(
    prompt: str, channel: str, complexity: int
) -> GearDecision:
    if _ollama_available():
        provider, model = _resolve_provider_model("ollama")
        return GearDecision(
            gear=1,
            provider=provider,
            model=model,
            reason="Simple prompt — Gear 1 (local Ollama). Fast, free, sovereign.",
            complexity=complexity,
            channel=channel,
            latency_ms=_ollama_latency_ms,
        )

    # Ollama not available — try Gear 2
    result = _try_gear2(prompt, channel, complexity)
    if result:
        result.reason = f"Gear 1 unavailable (Ollama not configured/slow) — using Gear 2 ({result.provider})."
        result.fallback_from = 1
        return result

    # Nothing available — last resort
    return _minimal_fallback(prompt, channel, complexity)

def _try_gear2(
    prompt: str, channel: str, complexity: int
) -> Optional[GearDecision]:
    pair = _first_available(GEAR2_PROVIDERS)
    if not pair:
        return None
    provider, model = pair
    return GearDecision(
        gear=2,
        provider=provider,
        model=model,
        reason=f"Medium complexity — Gear 2 ({provider}). Fast cloud, low cost.",
        complexity=complexity,
        channel=channel,
    )

def _try_gear3_with_fallback(
    prompt: str, channel: str, complexity: int,
    fallback_from: Optional[int] = None,
) -> GearDecision:
    pair = _first_available(GEAR3_PROVIDERS)
    if pair:
        provider, model = pair
        reason = f"High complexity — Gear 3 ({provider}). Full capability."
        if fallback_from:
            reason = f"Gear {fallback_from} unavailable — escalated to Gear 3 ({provider})."
        return GearDecision(
            gear=3,
            provider=provider,
            model=model,
            reason=reason,
            complexity=complexity,
            channel=channel,
            fallback_from=fallback_from,
        )

    return _minimal_fallback(prompt, channel, complexity)

def _try_gear4(
    prompt: str, channel: str, complexity: int,
) -> Optional[GearDecision]:
    """Gear 4 är INAKTIVT. Returnerar alltid None."""
    return None

def _minimal_fallback(prompt: str, channel: str, complexity: int) -> GearDecision:
    """Last-resort fallback — mirrors providers.py graceful degradation to mistral."""
    provider, model = _resolve_provider_model("mistral")
    return GearDecision(
        gear=2,
        provider=provider,
        model=model,
        reason="No preferred provider available — minimal fallback to mistral.",
        complexity=complexity,
        channel=channel,
    )

def _select_forced_gear(
    gear: int, prompt: str, ctx: GearContext, override: str
) -> GearDecision:
    """Handle explicit ZERO_GEAR_OVERRIDE. Gear 4 ej tillgängligt."""
    channel = ctx.channel or "chat"
    complexity = _estimate_complexity(prompt)

    if gear == 4:
        # Gear 4 är inaktivt — faller till Gear 3
        logger.warning("zero_gear: Gear 4 är inaktivt — använder Gear 3")
        return _try_gear3_with_fallback(prompt, channel, complexity)

    if gear == 1:
        provider, model = _resolve_provider_model("ollama")
        return GearDecision(
            gear=1, provider=provider, model=model,
            reason="Forced Gear 1 via ZERO_GEAR_OVERRIDE.",
            complexity=complexity, channel=channel, override=override,
            latency_ms=_ollama_latency_ms,
        )
    if gear == 2:
        pair = _first_available(GEAR2_PROVIDERS)
        if pair:
            provider, model = pair
            return GearDecision(
                gear=2, provider=provider, model=model,
                reason="Forced Gear 2 via ZERO_GEAR_OVERRIDE.",
                complexity=complexity, channel=channel, override=override,
            )
    # gear == 3 or gear 2 unavailable
    pair = _first_available(GEAR3_PROVIDERS)
    if pair:
        provider, model = pair
        return GearDecision(
            gear=3, provider=provider, model=model,
            reason=f"Forced Gear 3 via ZERO_GEAR_OVERRIDE.",
            complexity=complexity, channel=channel, override=override,
        )

    return _minimal_fallback(prompt, channel, complexity)

# ── Latency tracking ──────────────────────────────────────────────────────────

# ── Response Quality Detection ───────────────────────────────────────────────

# Signaler på att Gear 1 inte klarade uppgiften
GEAR1_FAILURE_SIGNALS = [
    "kan inte scanna",
    "kan inte läsa",
    "har inte tillgång",
    "ingen direkt",
    "saknar åtkomst",
    "i cannot",
    "i don't have access",
    "unable to access",
    "cannot read",
    "don't have the ability",
    "jag kan inte",
    "det är inte möjligt för mig",
    "som ai har jag inte",
    "men jag kan inte",
    "tyvärr kan jag inte",
]

def response_needs_escalation(response: str, gear: int) -> bool:
    """
    Kollar om ett Gear 1-svar indikerar att Zero inte klarade uppgiften.
    Om ja → eskalera till Gear 3.

    "Om Zero svarar negativt på Gear 1 ska den växla upp" — Frank
    """
    if gear != 1:
        return False
    if not response:
        return False

    response_lower = response.lower()
    return any(signal in response_lower for signal in GEAR1_FAILURE_SIGNALS)


def record_latency(provider: str, latency_ms: float, success: bool = True) -> None:
    """
    Called by zero_web_server.py / zero_engine.py after each API call.
    Updates the rolling latency state used by _ollama_available().

    Usage:
        after each Ollama call:
            zero_gear.record_latency("ollama", elapsed_ms, success=True)
        on Ollama timeout/error:
            zero_gear.record_latency("ollama", 0, success=False)
    """
    global _ollama_latency_ms, _ollama_last_check, _ollama_consecutive_failures

    if provider != "ollama":
        return

    _ollama_last_check = time.monotonic()

    if success:
        # Exponential moving average — smooths out spikes
        alpha = 0.3
        if _ollama_latency_ms == 0:
            _ollama_latency_ms = latency_ms
        else:
            _ollama_latency_ms = alpha * latency_ms + (1 - alpha) * _ollama_latency_ms
        _ollama_consecutive_failures = 0
        logger.debug(f"zero_gear: Ollama latency EMA = {_ollama_latency_ms:.0f}ms")
    else:
        _ollama_consecutive_failures += 1
        logger.warning(
            f"zero_gear: Ollama failure #{_ollama_consecutive_failures}"
        )

def reset_ollama_health() -> None:
    """
    Reset Ollama health state. Call after Ollama restart or manual recovery.
    Accessible via router.py or zero_doctor.py.
    """
    global _ollama_latency_ms, _ollama_last_check, _ollama_consecutive_failures
    _ollama_latency_ms = 0.0
    _ollama_last_check = 0.0
    _ollama_consecutive_failures = 0
    logger.info("zero_gear: Ollama health state reset.")

# ── Diagnostics ───────────────────────────────────────────────────────────────

def get_gear_status() -> dict:
    """
    Return current gear system state.
    Safe for status endpoints and zero_doctor.
    """
    ollama_model = os.getenv("OLLAMA_MODEL", "")
    gear2_available = _first_available(GEAR2_PROVIDERS)
    gear3_available = _first_available(GEAR3_PROVIDERS)
    override = os.getenv("ZERO_GEAR_OVERRIDE", "auto")

    return {
        "override": override,
        "gear1": {
            "provider": "ollama",
            "model": ollama_model or None,
            "available": _ollama_available(),
            "latency_ms": round(_ollama_latency_ms, 1),
            "consecutive_failures": _ollama_consecutive_failures,
            "latency_threshold_ms": OLLAMA_LATENCY_THRESHOLD_MS,
            "voice_channel": True,
        },
        "gear2": {
            "providers": GEAR2_PROVIDERS,
            "active_provider": gear2_available[0] if gear2_available else None,
            "active_model": gear2_available[1] if gear2_available else None,
            "available": gear2_available is not None,
        },
        "gear3": {
            "providers": GEAR3_PROVIDERS,
            "active_provider": gear3_available[0] if gear3_available else None,
            "active_model": gear3_available[1] if gear3_available else None,
            "available": gear3_available is not None,
        },
        "thresholds": {
            "gear2_tokens": GEAR2_TOKEN_THRESHOLD,
            "gear3_tokens": GEAR3_TOKEN_THRESHOLD,
        },
    }

def explain(prompt: str, channel: str = "chat") -> str:
    """
    Human-readable explanation of what gear would be chosen and why.
    Useful for debugging and for Zero's self-knowledge.

    Usage from chat:
        import zero_gear
        print(zero_gear.explain("skriv ett python-program som sorterar listor"))
    """
    ctx = GearContext(channel=channel)
    decision = select(prompt, ctx)
    lines = [
        f"Gear {decision.gear} — {decision.provider} / {decision.model}",
        f"Reason:     {decision.reason}",
        f"Complexity: {decision.complexity}/3",
        f"Channel:    {decision.channel}",
    ]
    if decision.override:
        lines.append(f"Override:   ZERO_GEAR_OVERRIDE={decision.override}")
    if decision.fallback_from:
        lines.append(f"Fallback:   from Gear {decision.fallback_from}")
    if decision.gear == 1:
        lines.append(f"Latency:    {decision.latency_ms:.0f}ms (EMA)")
    return "\n".join(lines)

# ── Integration guide (not executed) ─────────────────────────────────────────
#
# In zero_web_server.py, replace direct provider selection with:
#
#   from app import zero_gear
#
#   ctx = zero_gear.GearContext(
#       channel=request.get("channel", "chat"),
#       last_ollama_latency_ms=engine.last_latency * 1000,
#   )
#   decision = zero_gear.select(user_message, ctx)
#   provider = decision.provider
#   model    = decision.model
#
#   # After the call completes:
#   elapsed_ms = (time.monotonic() - t0) * 1000
#   zero_gear.record_latency(decision.provider, elapsed_ms, success=True)
#
#   # Optionally log the decision to STONE:
#   # store_memory(f"gear:{decision.gear}:{decision.provider}", decision.reason)
#
# Voice channel example (future STT integration):
#
#   ctx = zero_gear.GearContext(channel="voice")
#   decision = zero_gear.select(transcribed_text, ctx)
#   # Always routes to Gear 1 (Ollama) unless unavailable
#
# ─────────────────────────────────────────────────────────────────────────────
