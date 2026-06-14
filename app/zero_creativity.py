"""
zero_creativity.py — ZeroPointAI Provider Router (Steg 1: manuellt val + kostnad)

ZERO_MODULE:    core
ZERO_LAYER:     2
ZERO_ESSENTIAL: true
ZERO_ROLE:      Manuellt provider-val + kostnad per svar. Steg 1 mot att
                ersätta zero_gear.py. Senare steg: nivåer, syntes, autonomi.
ZERO_DEPENDS:   providers.py, zero_engine.py (PROVIDER_CALLERS, calc_cost_sek)
ZERO_USED_BY:   zero_engine.py

Steg 1 — medvetet minimal:
  - Tar EN manuellt vald provider och kör EN gång.
  - Återanvänder zero_engine.PROVIDER_CALLERS och calc_cost_sek via injektion
    (inga importer tillbaka mot zero_engine → ingen cirkulär import).
  - Returnerar svar + kostnad + token för realtidsvisning.
  - Skriver INTE till STONE. Ingen nivå-logik. Ingen syntes. Ingen circle.
  - Ingen substräng-baserad eskalering. Teknisk failure → fallback. Innehåll
    är Franks omdöme, inte modulens.

Se docs/mafp/zero_creativity_STEG1_MAFP.md för avgränsningen mot v0.7.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger(__name__)

# providers.py är ren metadata och säker att importera direkt.
try:
    from app.providers import normalize_provider_name, get_provider_model
except ImportError:  # pragma: no cover - tillåt fristående testning
    def normalize_provider_name(name):  # type: ignore
        return (name or "gemini").strip().lower()

    def get_provider_model(name):  # type: ignore
        return ""


# ── Resultatobjekt ────────────────────────────────────────────────────────────

@dataclass
class CreativityResult:
    response:  str
    provider:  str
    model:     str
    in_tok:    int
    out_tok:   int
    cost_sek:  float
    latency:   float
    thinking:  list = field(default_factory=list)
    fell_back: bool = False


# ── Huvud-API ─────────────────────────────────────────────────────────────────

def run_single(
    prompt: str,
    provider: str,
    messages: list,
    system: str,
    callers: dict,
    cost_fn: Callable[[str, int, int], float],
    engine=None,
    fallback_order: Optional[list] = None,
) -> CreativityResult:
    """
    Kör ETT provider-anrop med manuellt vald provider.

    prompt          – Franks fråga (sparas/loggas inte här; zero_engine äger minne)
    provider        – Franks knapp-val. Normaliseras internt.
    messages/system – byggda av zero_engine FÖRE detta anrop. Modulen bygger
                      aldrig egen kontext.
    callers         – zero_engine.PROVIDER_CALLERS (injiceras för att undvika
                      cirkulär import).
    cost_fn         – zero_engine.calc_cost_sek (injiceras av samma skäl).
    engine          – vidarebefordras till Claude-callern (tool-loop).
    fallback_order  – providers att prova om vald provider kastar exception.

    Returnerar CreativityResult. Höjer RuntimeError om ALLA providers failar.
    """
    chosen = normalize_provider_name(provider)

    # Bygg anropsordning: vald provider först, sedan fallback utan dubbletter.
    order = [chosen]
    for p in (fallback_order or []):
        pn = normalize_provider_name(p)
        if pn not in order:
            order.append(pn)

    last_error: Optional[Exception] = None

    for pname in order:
        caller = callers.get(pname)
        if not caller:
            log.debug("creativity: ingen caller för '%s' — hoppar", pname)
            continue

        try:
            t0 = time.time()
            # Claude-callern tar engine= för sin tool-loop; övriga gör inte det.
            if pname == "claude":
                result = caller(messages, system, engine=engine)
            else:
                result = caller(messages, system)
            latency = round(time.time() - t0, 2)

            # Alla _call_* returnerar (response, in_tok, out_tok, thinking).
            response, in_tok, out_tok, thinking = result

            cost = cost_fn(pname, in_tok, out_tok)
            model = get_provider_model(pname)

            if pname != chosen:
                log.info("creativity: '%s' valdes men föll tillbaka till '%s'",
                         chosen, pname)

            return CreativityResult(
                response=response,
                provider=pname,
                model=model,
                in_tok=in_tok,
                out_tok=out_tok,
                cost_sek=cost,
                latency=latency,
                thinking=thinking or [],
                fell_back=(pname != chosen),
            )

        except Exception as e:  # noqa: BLE001 - en provider får inte stoppa resten
            last_error = e
            log.warning("creativity: provider '%s' failade: %s", pname, e)
            continue

    raise RuntimeError(
        f"creativity: alla providers failade (vald: {chosen}). Sista fel: {last_error}"
    )


# ── Hjälp för UI: vilka providers kan visas som knappar ───────────────────────

def selectable_providers() -> list[dict]:
    """
    Returnerar providers som har en konfigurerad modell (alltså är användbara
    som knappar i UI). Lokala providers markeras men exkluderas inte.

    Returnerar lista av {canonical, display, model, is_local}.
    Importeras lazy för att hålla modulen lätt att testa fristående.
    """
    try:
        from app.providers import PROVIDER_SPECS, provider_is_local, get_provider_display_name
    except ImportError:
        return []

    out: list[dict] = []
    for canonical in PROVIDER_SPECS:
        model = get_provider_model(canonical)
        if not model:
            continue  # ingen modell konfigurerad → inte en användbar knapp
        out.append({
            "canonical":  canonical,
            "display":    get_provider_display_name(canonical),
            "model":      model,
            "is_local":   provider_is_local(canonical),
        })
    return out
