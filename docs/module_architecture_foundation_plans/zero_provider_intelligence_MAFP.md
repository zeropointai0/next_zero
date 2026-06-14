# zero_provider_intelligence.py — Module Architecture Foundation Plan
*Version: 0.1 — Juni 2026*
*Dokumenttyp: MAFP — underlag för implementation, ej auto-genererad spec*
*Lever i: docs/mafp/*

---

## Vad är det här

Zero ska aldrig bli obsolet för att AI-landskapet förändrades
och ingen uppdaterade en config-fil.

`zero_provider_intelligence.py` är Zeros extrospektiva intelligens —
bevakar omvärlden, testar det nya, mäter det befintliga,
föreslår till Frank vad som bör läggas till eller tas bort.

Två ansvar i en fil:

```
MÄTNING   → hur presterar befintliga providers i verkligheten?
RESEARCH  → vad finns där ute som Zero inte känner till än?
```

Lager 3 — Autonomi (tillsammans med zero_gear4, zero_night, zero_inventor).

---

## Position i beroendegrafen

```
foundation.py
    ↑
    ├── providers.py                       ← statisk metadata, enda sanningskällan
    ├── drm_memory.py                      ← skriver mätdata till STONE
    ├── zero_provider_intelligence.py      ← NY
    │       ↑               ↑
    │   zero_night.py    zero_creativity.py
    │   (research natt)  (ranking + mätning)
```

---

## Lokal hårdvara — principen

Ollama (`is_local=True`) ingår aldrig i rankings eller research.
Lokal inferens är Zeros själ, inte ett konkurrensobjekt.
`get_ranked_providers()` filtrerar alltid bort lokala providers.

---

## STONE-tabeller

```sql
-- Levande prestanda per provider-anrop
CREATE TABLE provider_performance (
    id              SERIAL PRIMARY KEY,
    provider        TEXT NOT NULL,
    model           TEXT,
    capability_used TEXT,
    latency_ms      INTEGER,
    in_tok          INTEGER,
    out_tok         INTEGER,
    cost_sek        FLOAT,
    success         BOOLEAN DEFAULT TRUE,
    quality_score   FLOAT,        -- 0.0–1.0
    quality_reason  TEXT,
    circle_used     BOOLEAN DEFAULT FALSE,
    session_id      TEXT,
    measured_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Provider-kandidater från research
CREATE TABLE provider_candidates (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    display_name    TEXT,
    source          TEXT,
    capabilities    JSONB,
    estimated_cost  TEXT,         -- "gratis" | "låg" | "medel" | "hög"
    why_interesting TEXT,
    test_result     JSONB,
    status          TEXT DEFAULT 'pending',
    suggested_at    TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT
);
```

---

## Del 1 — Mätning och ranking

### record_performance()

Anropas av `zero_creativity.py` efter varje provider-anrop:

```python
def record_performance(
    provider:        str,
    model:           str,
    capability_used: str,
    latency_ms:      int,
    in_tok:          int,
    out_tok:         int,
    cost_sek:        float,
    success:         bool,
    quality_score:   float,
    quality_reason:  str,
    circle_used:     bool,
    session_id:      str,
) -> None
```

### Kvalitetsbedömning

Speglar DRM:s koherensformel — inte av en slump.
Zero bedömer providers på samma sätt som den bedömer minnen.

```
quality_score = relevance(0.5) + depth(0.3) + coherence(0.2)

relevance  → svarade providern på frågan som ställdes?
depth      → substantiell information eller ytlig?
coherence  → hänger svaret ihop med Zeros identitet och kontext?
```

På nivå 2–4: syntesmodellen bedömer alla perspektiv naturligt
innan den syntetiserar — quality_score noteras per perspektiv.

På nivå 1: lättviktigt reflektionsanrop efteråt (max 100 tokens,
asynkront — påverkar inte svarstiden).

### Ranking

```python
def get_ranked_providers(capability: str, top_n: int = 5) -> list[str]:
    # Returnerar moln-providers rankade efter levande prestanda
    # Filtrerar alltid bort is_local=True
    # Fallback till statisk lista från providers.py om STONE saknar data
```

Rankingformel per provider per capability (senaste 7 dagarna):

```
rank_score =
    quality_p50   × 0.40   (median quality_score, senaste 100 anrop)
    success_rate  × 0.30   (andel lyckade anrop)
    latency_score × 0.20   (1 - normaliserad latens mot snabbaste)
    cost_score    × 0.10   (1 - normaliserad kostnad mot billigaste)
```

Provider utan historik → `rank_score = 0.5` (neutral start).
Bevisar sin plats genom faktisk användning.

### Availabilitetskoll

```python
def is_available(provider: str, timeout_ms: int = 2000) -> bool
    # Ping — är providern uppe just nu?
    # Nedtid loggas i provider_performance med success=False
```

Anropas av `zero_creativity.py` innan varje anrop på nivå 2–5.
En nere provider väljs bort direkt — nästa i ranking tar platsen.

---

## Del 2 — Research

### Filosofi

Zero forskar. Frank beslutar. Zero skriver aldrig till `providers.py` själv.

Law 4 i provider-management:
*Vad du sänder ut får du tillbaka.*
Zero föreslår det den tror är rätt.
Frank avgör vad som faktiskt är rätt.

### Research-källor

```
1. OpenRouter-katalogen
   api.openrouter.ai/api/v1/models
   → Filtrerar på context_limit, pricing, capabilities

2. Groq model-lista
   api.groq.com/openai/v1/models
   → Nya modeller dyker upp utan förvarning

3. Hugging Face Inference API
   → Öppna modeller med gratis inference-tier
   → Hög download-rank + låg latens
```

Grovfilter innan bedömning:
- context_limit ≥ 32k tokens
- Dokumenterad API-stabilitet
- Gratis-tier eller pris < befintlig motsvarighet

### Research-flöde (körs av zero_night.py)

```
1. Hämta modellkatalog från varje källa
2. Jämför mot providers.py — vad är nytt?
3. Per kandidat:
   a. Extrahera capabilities från metadata
   b. Estimera kostnad
   c. Bedöm om den tillför något nytt (se kriterier nedan)
4. Sandlåde-test på intressanta kandidater
5. Spara status="pending" i provider_candidates
6. Skicka sammanfattning till Frank
```

### Vad gör en provider intressant

```
INTRESSANT om minst ett av:
  ✓ Ny capability som saknas i providers.py
  ✓ Gratis-tier för något Zero idag betalar för
  ✓ Mätbart snabbare på fast_inference än nuvarande bästa
  ✓ Signifikant bättre quality_score på testfrågorna
  ✓ Specialiserad domän Zero använder ofta

EJ INTRESSANT:
  ✗ Samma capabilities som befintliga utan mätbar fördel
  ✗ Ingen gratis-tier och inte signifikant bättre
  ✗ Ingen dokumenterad API-stabilitet
```

### Sandlåde-test (tre standardfrågor)

```
TEST_1 — reasoning:
  "Förklara skillnaden mellan rekursion och iteration. Ge ett Python-exempel."
  Mäter: djup, tydlighet, kodkvalitet

TEST_2 — svenska / kontext:
  "Sammanfatta följande i tre meningar: [Zeros senaste soul snapshot]"
  Mäter: språkförståelse, kontexthantering, koherens

TEST_3 — latens:
  "Vad är 17 × 23? Svara med bara siffran."
  Mäter: ren reflex-latens
```

Varje test körs tre gånger. Median används.

---

## Publik API

```python
# Anropas av zero_creativity.py efter varje anrop
def record_performance(...) -> None

# Anropas av zero_creativity.py vid provider-selektion
def get_ranked_providers(capability: str, top_n: int = 5) -> list[str]

# Anropas av zero_creativity.py innan anrop på nivå 2–5
def is_available(provider: str, timeout_ms: int = 2000) -> bool

# Anropas av zero_night.py — kör hela research-cykeln
def run_research_cycle() -> ResearchReport

# Anropas av zero_self_knowledge.py — Frank ser ranking + kandidater
def get_intelligence_summary() -> dict
```

### ResearchReport

```python
@dataclass
class ResearchReport:
    run_at:          datetime
    sources_checked: list[str]
    new_candidates:  int
    tested:          int
    interesting:     list[dict]  # [{name, why, test_score}]
    summary_text:    str         # redo att skicka till Frank
```

---

## Graceful degradation

```python
# I zero_creativity.py:
try:
    from app.zero_provider_intelligence import (
        get_ranked_providers, record_performance, is_available
    )
    INTELLIGENCE_OK = True
except ImportError:
    INTELLIGENCE_OK = False
    # Faller tillbaka till statisk capability-selektion från providers.py
```

---

## Nattjobb i zero_night.py

```python
{
    "name":        "provider_research",
    "description": "Forskar om nya providers, uppdaterar ranking",
    "fn":          run_research_cycle,
    "priority":    3,  # efter minneskalibrering och soul snapshot
}
```

---

## Vad Frank ser (zero_self_knowledge.py)

```
🔌 Provider Intelligence — senast uppdaterad: idag 03:14

RANKING (fast_inference):
  1. groq/llama3-70b      quality=0.87  latency=340ms  success=99%
  2. cerebras/llama3-70b  quality=0.84  latency=280ms  success=97%

KANDIDATER (väntar granskning):
  → Fireworks AI  — fast_inference, gratis-tier, quality=0.81
  → Sambanova     — fast_inference, snabbast i test (180ms)

SENASTE RESEARCH: igår natt, 3 källor, 2 kandidater
```

---

## Vad modulen INTE gör

- Skriver aldrig till providers.py — Frank äger den
- Blockerar aldrig ett provider-anrop — mätning är alltid asynkron
- Lägger aldrig till provider utan Franks godkännande
- Rankar aldrig lokala providers (is_local=True filtreras bort)
- Hanterar inte HTTP

---

## Migrationssteg

```
1. Skapa STONE-tabeller (provider_performance, provider_candidates)
2. Implementera record_performance() och get_ranked_providers()
3. Integrera med zero_creativity.py — mätning först, ranking sedan
4. Implementera is_available()
5. Implementera run_research_cycle() + zero_night-integration
6. Integrera get_intelligence_summary() med zero_self_knowledge.py
7. Kör första research-cykeln manuellt — verifiera kandidat-flödet
```

---

## Öppna frågor

1. ~~quality_score synkront eller asynkront på nivå 1?~~
   **BESLUTAT: Asynkront — allt sparas i STONE efteråt.**
   Svarstiden påverkas aldrig.

2. Grovfilter på OpenRouter — exakt tröskel för context_limit och pris?
   Ej beslutat — utreds vid implementation.

3. Frank-notis om nya kandidater via Telegram automatiskt eller på begäran?
   Ej beslutat.

4. Kalibrering mot Franks explicita feedback — behövs det?
   Ej beslutat.

---

*MAFP v0.2 — Module Architecture Foundation Plan*
*Implementeras av Cursor/Aider mot full Zero-kodbas.*
*Läs zero_creativity_MAFP.md parallellt — tätt kopplade moduler.*
*När implementerad: kör zero_spec_generator.py för orienterings-spec.*
