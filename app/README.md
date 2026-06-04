# ZeroPointAI — app/
*Senast uppdaterad: Juni 2026 — v1.3, Zero v2 live*

Alla `.py`-filer har en header längst upp som berättar vad filen är:

```python
ZERO_MODULE:    core
ZERO_LAYER:     1
ZERO_ESSENTIAL: true
ZERO_ROLE:      Vad filen gör — en rad
ZERO_DEPENDS:   Vad den behöver
ZERO_USED_BY:   Vem som anropar den
```

---

## Lager 1 — Kärnan (systemet lever)

| Fil | Vad den gör |
|-----|-------------|
| `foundation.py` | Sökvägar + Layer 0. Enda sanningskällan. Importerar inget. |
| `drm_memory.py` | STONE-databasen. 7-lager DRM. Wave-propagation retrieval. |
| `memory_resonance.py` | Koherensberäkning per minne. Kalibreras nattligen eller on-demand. |
| `providers.py` | Provider-metadata (Claude, Gemini, Ollama etc.). Anropar inget. |
| `router.py` | Intent-detection. Naturligt språk → systemkommandon. |
| `zero_gear.py` | Gear-selektion. Väljer provider och kapacitetsnivå per prompt. |
| `zero_engine.py` | Konversationsmotor. Provider-anrop, system-prompt, minne. |
| `zero_web_server.py` | HTTP-server. Bara HTTP — ingen AI-logik. Port 8080. |
| `zero_boot.py` | Boot-sekvens. Identitetskärna + semantisk hälsokoll vid uppstart. |
| `self_reflection.py` | Post-konversation lärande. Körs var 5:e meddelande. |
| `zero_ascension.py` | Celldelning och återfödelse. Skapar och hanterar generationer. |
| `zero_memory_guard.py` | Minnesskydd — rate limiting, read-only guard, session budgets. |
| `zero_memory_search.py` | Sökverktyg — söker i STONE via naturligt språk och embeddings. |
| `zero_self_knowledge.py` | Levande självkännedom — modulkarta, STONE-inspektion, provider-status. |
| `zero_ascension_setup.py` | Interaktiv setup-wizard för nya generationer. |

---

## Lager 2 — Hälsa (systemet mår bra)

| Fil | Vad den gör |
|-----|-------------|
| `zero_doctor.py` | Diagnostik — AST-analys, systemcheck, fullständig rapport. |
| `zero_monitor.py` | Hårdvara — GPU, CPU, RAM, temperaturer, disk. |
| `zero_map.py` | Systemkarta — alla moduler, relationer, lager. |

---

## Lager 3 — Autonomi (systemet agerar självt)

| Fil | Vad den gör |
|-----|-------------|
| `zero_gear4.py` | Autonom exekveringsloop. Zero planerar och kör uppgifter. |
| `zero_sudo.py` | Tidsbegränsad admin-behörighet med loggning. |
| `zero_night.py` | Nattlig evolution, självförbättring, NIGHTLY_TASKS. |
| `zero_inventor.py` | Uppfinner verktyg som saknas. |

---

## Lager 4 — Integration (systemet kommunicerar)

| Fil | Vad den gör |
|-----|-------------|
| `zero_telegram.py` | Telegram-bot. Röst, notifikationer, fjärrstyrning. |
| `zero_mail_watcher.py` | Mail-bevakning. Notifierar via Telegram. |
| `pinball_social_entity.py` | Social media-direktör för Pinball inn. |

---

## Övriga moduler

Allt annat i `app/` är specialmoduler som Zero använder vid behov.
Zero känner igen dem via `zero_map.py` och `ZERO_MODULE`-headern.

---

## Layer 0

Layer 0 ligger **inte** i `app/` — den tillhör ingen version av Zero.

```
/opt/zeropointai/docs/layer0/
  00_REALITY.md    ← De fem lagarna
  02_MIRROR.md     ← Spegeln reflekterar. Spegeln väljer inte.
  COMPASS.md       ← DETECT → EXPRESS → ALLOW → MAINTAIN → CALIBRATE
```

Frank redigerar Layer 0. Zero läser den. Zero äger den aldrig.

---

*"Everything changes except the first 4 Laws." — LAW 5*
