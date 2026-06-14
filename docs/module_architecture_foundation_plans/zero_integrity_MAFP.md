# zero_integrity.py — Module Architecture Foundation Plan
*Version: 0.1 — Juni 2026*
*Dokumenttyp: MAFP — underlag för implementation, ej auto-genererad spec*
*Lever i: docs/mafp/*

---

## Vad är det här

Zero ska kunna svara på: *"Hur vet du det här?"*

`zero_integrity.py` spårar proveniensen på varje påstående i ett svar —
varifrån kom informationen, hur säker är Zero på den, och hur stor är
risken att Zero hittade på den.

Fyra dimensioner mäts per svar:

```
KÄLLTRANSPARENS   → varifrån kom informationen?
HALLUCINATIONSRISK → hur stor är risken att Zero hittade på det?
INTEGRITET        → är svaret koherent med Layer 0 och Zero:s identitet?
TÄNKESÄTT         → innanför eller utanför boxen?
```

Lager 2 — Hälsa (tillsammans med zero_doctor, zero_monitor, zero_map).

---

## Position i beroendegrafen

```
foundation.py
    ↑
    ├── drm_memory.py              ← läser retrieval audit från STONE
    ├── zero_integrity.py          ← NY
    │       ↑              ↑
    │   zero_engine.py   zero_self_knowledge.py
    │   (bedömer svar)   (Frank frågar om epistemisk status)
```

---

## De fyra dimensionerna

### 1. Källtransparens

Varifrån kom varje del av svaret?

```
STONE_MEMORY    → hämtades från STONE via wave-retrieval (verifierbart)
                  coherence_score och minnes-ID loggas
PROVIDER_CLAIM  → provider påstod det som sant (okontrollerat)
ZERO_SYNTHESIS  → Zero drog slutsatsen från flera källor (resonemang)
SPECULATION     → Zero extrapolerade bortom sina källor (markeras explicit)
UNKNOWN         → Zero kan inte spåra källan — hög risk
```

### 2. Hallucinationsrisk

```
LÅG   → påståendet stöds av STONE-minne med coherence > 0.7
MEDEL → påståendet kom från provider utan STONE-stöd
HÖG   → Zero kan inte koppla påståendet till någon källa
KRITISK → påståendet motsäger ett STONE-minne med hög koherens
```

Hallucination är svår att detektera inifrån — men Zero kan flagga
*riskzonen*: när ett påstående saknar stöd i STONE, inte kom från
en provider, och inte är explicit markerat som spekulation.

### 3. Integritet

```
integritet_score = layer0_koherens(0.5) + identitets_koherens(0.3)
                   + kontext_koherens(0.2)

layer0_koherens      → bryter svaret mot någon av de fem lagarna?
identitets_koherens  → är svaret konsistent med Zeros identitetsbeslut?
kontext_koherens     → är svaret konsistent med sessionshistoriken?
```

Speglar DRM:s koherensformel — samma filosofi hela vägen ner.

### 4. Tänkesätt

```
INNANFÖR_BOXEN  → konventionellt, förväntat, välbelagrat
UTANFÖR_BOXEN   → associativt, oväntat, kreativt
```

Kombinerat med källtransparens ger det fyra kvadranter:

```
Innanför + hög transparens  → faktasvar från minne (säkrast)
Utanför  + hög transparens  → kreativ syntes baserad på känd data
Innanför + låg transparens  → konventionellt men oklart underlag
Utanför  + låg transparens  → ren spekulation (högst risk)
```

---

## Dataklasser

```python
@dataclass
class SourceTrace:
    claim:          str           # det specifika påståendet
    source_type:    str           # STONE_MEMORY | PROVIDER_CLAIM | ZERO_SYNTHESIS | SPECULATION | UNKNOWN
    stone_memory_id: int | None   # om STONE_MEMORY
    coherence_score: float | None # om STONE_MEMORY
    provider:       str | None    # om PROVIDER_CLAIM
    confidence:     float         # 0.0–1.0

@dataclass
class IntegrityReport:
    session_id:          str
    response_summary:    str          # kort sammanfattning av svaret
    source_traces:       list[SourceTrace]
    hallucination_risk:  str          # LÅG | MEDEL | HÖG | KRITISK
    integrity_score:     float        # 0.0–1.0
    thinking_style:      str          # INNANFÖR_BOXEN | UTANFÖR_BOXEN
    overall_confidence:  float        # 0.0–1.0
    flags:               list[str]    # varningar Frank bör känna till
    generated_at:        datetime
```

---

## Publik API

```python
# Anropas av zero_engine.py efter varje svar — asynkront
async def integrity_analyze(
    response:       str,
    prompt:         str,
    retrieval_audit: dict,    # från DRM wave-retrieval
    providers_used: list,     # från CreativityResult
    session_id:     str,
) -> IntegrityReport

# Anropas av zero_self_knowledge.py — Frank frågar om epistemisk status
def get_integrity_summary(session_id: str) -> str

# Sparar rapport till STONE
def save_report(report: IntegrityReport) -> None

# Hämtar historik — hur har Zero:s epistemiska kvalitet utvecklats?
def get_trend(days: int = 7) -> dict
```

---

## Integration med DRM

`zero_integrity.py` läser retrieval audit som DRM redan sparar
efter varje Wave 3-kollaps:

```
Wave 3 audit innehåller redan:
  - Hur många minnen valdes
  - Top coherence-score
  - Vilka attraktorer aktiverades
  - Wave-depth
```

Det är råmaterialet för källtransparens — ingen ny DRM-logik behövs.

---

## Integration med zero_engine.py

Körs asynkront efter varje svar — påverkar aldrig svarstiden:

```python
# I zero_engine.py, efter att response sparats:
if INTEGRITY_OK:
    asyncio.create_task(
        integrity_analyze(
            response        = response,
            prompt          = user_input,
            retrieval_audit = drm_audit,
            providers_used  = result.providers_used,
            session_id      = self.session_id,
        )
    )
```

---

## Vad Frank ser

Tre sätt att få epistemisk information:

### 1. Indikator per svar (UI)

En subtil indikator visas med varje svar:

```
[🟢 Hög transparens]  [🟡 Medel risk]  [💡 Utanför boxen]
```

### 2. På begäran — naturligt språk

```
Frank: "hur säker är du på det där?"
Zero:  "Det påståendet om räntan kom från ett STONE-minne
        från mars 2026 (koherens 0.87). Slutsatsen om
        bostadsmarknaden är min syntes — medel risk."
```

### 3. Epistemisk hälsoöversikt

```
Frank: "hur mår din epistemiska hälsa?"

🧠 Epistemisk hälsa — senaste 7 dagarna:

  Källfördelning:
    STONE_MEMORY:    43%  (verifierbart)
    PROVIDER_CLAIM:  31%  (okontrollerat)
    ZERO_SYNTHESIS:  21%  (resonemang)
    SPECULATION:      5%  (explicit markerat)

  Hallucinationsrisk:
    LÅG:      71%
    MEDEL:    22%
    HÖG:       6%
    KRITISK:   1%

  Integritet: 0.89 genomsnitt
  Tänkesätt:  67% innanför boxen / 33% utanför
```

---

## STONE-tabell

```sql
CREATE TABLE epistemic_reports (
    id                  SERIAL PRIMARY KEY,
    session_id          TEXT,
    response_summary    TEXT,
    hallucination_risk  TEXT,
    integrity_score     FLOAT,
    thinking_style      TEXT,
    overall_confidence  FLOAT,
    source_traces       JSONB,
    flags               JSONB,
    generated_at        TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Graceful degradation

```python
# I zero_engine.py:
try:
    from app.zero_integrity import integrity_analyze
    INTEGRITY_OK = True
except ImportError:
    INTEGRITY_OK = False
    # Zero fungerar utan — men utan epistemisk spårning
```

---

## Vad modulen INTE gör

- Blockerar aldrig ett svar — körs alltid asynkront
- Garanterar inte att Zero aldrig hallucinar — flaggar riskzonen
- Ersätter inte zero_coherence_contract.py
- Bedömer inte om ett påstående är *sant* — bedömer hur väl det är *underbyggt*
- Hanterar inte HTTP

---

## Migrationssteg

```
1. Skapa STONE-tabell (epistemic_reports)
2. Implementera integrity_analyze() — källtransparens + hallucinationsrisk
3. Integrera med zero_engine.py — asynkront efter svar
4. Implementera integritetsbedömning mot Layer 0
5. Implementera tänkesätt-klassificering
6. Integrera get_integrity_summary() med zero_self_knowledge.py
7. Lägg till UI-indikator i zero_web_server.py
```

---

## Öppna frågor

1. Ska enskilda påståenden spåras (granulär) eller hela svaret (aggregerat)?
   Granulär är mer användbar men kräver mer beräkning.
   Ej beslutat — börja aggregerat, förfina senare.

2. Hur identifierar Zero enskilda påståenden i ett svar?
   Meningsuppdelning? NLP? Lättviktig LLM-klassificering?
   Ej beslutat — utreds vid implementation.

3. Ska UI-indikatorn alltid visas eller bara på begäran?
   Ej beslutat.

4. Hur hanteras multi-provider syntes (nivå 2–4)?
   **BESLUTAT: Varje providers bidrag spåras separat i source_traces.**
   Allt sparas i STONE — Store Then On-Need Extract.

---

*MAFP v0.2 — Module Architecture Foundation Plan*
*Implementeras av Cursor/Aider mot full Zero-kodbas.*
*Läs zero_creativity_MAFP.md och zero_provider_intelligence_MAFP.md parallellt.*
*När implementerad: kör zero_spec_generator.py för orienterings-spec.*
