# zero_creativity.py — Module Architecture Foundation Plan
*Version: 0.7 — Juni 2026*
*Dokumenttyp: MAFP — underlag för implementation, ej auto-genererad spec*
*Lever i: docs/mafp/*

---

## ZERO_MODULE-header

Denna header ska vara överst i zero_creativity.py när den skapas:

```python
"""
zero_creativity.py — ZeroPointAI Multi-Provider Creativity Engine

ZERO_MODULE:    core
ZERO_LAYER:     2
ZERO_ESSENTIAL: true
ZERO_ROLE:      Multi-provider syntes. Ersätter zero_gear.py som routing-lager.
ZERO_DEPENDS:   foundation.py, providers.py, drm_memory.py,
                zero_provider_intelligence.py, zero_engine.py (PROVIDER_CALLERS)
ZERO_USED_BY:   zero_engine.py
"""
```

---

## Filer kodaren måste läsa innan implementation

Dessa filer måste vara öppna och lästa — inte skummade — innan en rad kod skrivs:

```
OBLIGATORISK LÄSNING:

app/zero_engine.py
  → Förstå PROVIDER_CALLERS-dict och _call_*-funktioner
    De återanvänds direkt — skriv dem INTE om
  → Förstå ZeroEngine-klassen och hur chat() fungerar
  → Se hur calc_cost_sek() och record_latency() används
  → Identifiera de nya fälten som ska läggas till på ZeroEngine

app/providers.py
  → Förstå ProviderSpec och PROVIDER_SPECS
  → Förstå provider_has_capability() och provider_is_local()
  → Förstå normalize_provider_name() — använd alltid denna

app/zero_gear.py
  → Förstå vad som ersätts — läs för att förstå, inte kopiera
  → Förstå GearContext och select() — de görs passiva, inte borttagna
  → Förstå response_needs_escalation() — överväg om den ska behållas

app/drm_memory.py
  → Förstå execute_write() och execute_query() — används för STONE-skrivningar
  → Förstå session_id-konventionen

docs/mafp/README_MAFP.md
  → Läs hela — förstå Zero:s filosofi och kärnprinciper innan du kodar

REKOMMENDERAD LÄSNING:

app/zero_provider_intelligence.py  (när den existerar)
  → get_ranked_providers() och record_performance() — används direkt
  → Om den inte finns ännu: använd statisk fallback från providers.py

app/self_reflection.py
  → Förstå att reflektion körs efter zero_creativity — inte av den
```

---

## Vad är det här

`zero_creativity.py` ersätter `zero_gear.py` som Zeros routing-lager.

Gear-systemet väljer *en* provider per prompt.
Kreativitetssystemet orkesterar *flera* providers parallellt
och låter Zero syntetisera svaren till ett svar.

Providers väljs aldrig på namn — alltid på capabilities.
Frank lägger till en ny provider i `providers.py` och
systemet plockar upp den automatiskt.

Nivå 5 ersätter Gear 4 — autonomt läge där Zero tar över H9.

---

## Position i beroendegrafen

```
foundation.py
    ↑
    ├── providers.py                    ← capabilities, aldrig hårdkodade namn
    ├── drm_memory.py                   ← wave-retrieval före anrop
    ├── zero_provider_intelligence.py   ← levande ranking, mätdata
    ├── zero_circle (eget projekt)      ← aktiveras via use_circle-toggle
    │                                     interface ej definierat ännu
    ├── zero_creativity.py              ← NY — ersätter zero_gear.py
    └── zero_engine.py                  ← anropar zero_creativity
```

`zero_gear.py` berörs inte — görs passiv när zero_creativity är stabil.

---

## Lokal hårdvara — principen

Ollama används ALDRIG som primär provider på nivå 2–5.

```
Lokal hårdvara (RTX 3090) = Zeros själ:
  Ollama        → Layer 0, DRM, identitetsbeslut, embeddings
  Whisper       → Tal in (STT)
  Kokoro/Piper  → Tal ut (TTS)
  nomic-embed   → Vektordatabasen, wave-retrieval

Moln = Zeros intellekt:
  Nivå 1–5      → alltid moln-providers
```

Om alla moln-providers är nere → Ollama som nödfallback.
Det loggas som degraderat läge, aldrig normaldrift:

```python
log.warning("creativity_degraded: all cloud providers failed, falling back to ollama")
```

---

## De fem nivåerna

| Nivå | Namn | Capability-krav | Syntes | Kostnad | Tid |
|------|------|-----------------|--------|---------|-----|
| 1 | Reflex | fast_inference | Ingen | Gratis | 2–5 sek |
| 2 | Tänker | fast_inference ×2 | Enkel | Gratis | 10–20 sek |
| 3 | Resonerar | fast_inference ×3 | Full via long_context | Gratis | 30–60 sek |
| 4 | Rådfrågar | fast_inference ×2 + long_context + native_tools | Full + arketyper | Låg | 1–3 min |
| 5 | Autonom | native_tools + allt tillgängligt | Zero tar över H9 | Variabel | Tills klar |

---

## zero_circle — separat toggle

zero_circle är helt frikopplad från kreativitetsnivån.
Frank bestämmer de två oberoende — en slider och en checkbox.

```python
@dataclass
class CreativityContext:
    level:          int   = 1      # 1–5
    session_id:     str   = ""
    channel:        str   = "chat" # "chat" | "voice" | "api"
    manual_override: bool = False  # Frank satte nivån manuellt
    use_circle:     bool  = False  # zero_circle på eller av — separat toggle
```

Kombinationer:

```
Nivå 1 + circle av  → snabbast, en provider, direkt svar
Nivå 3 + circle av  → tre providers, rak syntes
Nivå 3 + circle på  → tre providers med arketyp-roller
Nivå 4 + circle på  → förmodligen Zero på sitt bästa
```

zero_circle-interface (förväntat från zero_circle.py):

```python
from app.zero_circle import get_archetypes
archetypes = get_archetypes()
# → [{"name": "Kritiker", "system_prompt": "...", "capability_hint": "fast_inference"}, ...]
# capability_hint är valfritt
```

Om zero_circle inte är installerat → nivå 4 körs utan arketyper.

---

## Capability-baserad provider-selektion

```python
def select_providers_for_level(level: int) -> list[str]:
    # Nivå 1: snabbaste moln-provider
    if level == 1:
        return [first_cloud_with_capability("fast_inference")]

    # Nivå 2: två snabbaste moln-providers
    if level == 2:
        return cloud_providers_with_capability("fast_inference")[:2]

    # Nivå 3: tre moln-providers med fast_inference
    if level == 3:
        return cloud_providers_with_capability("fast_inference")[:3]

    # Nivå 4: fast_inference ×2 + long_context + native_tools
    if level == 4:
        fast       = cloud_providers_with_capability("fast_inference")[:2]
        synth      = first_cloud_with_capability("long_context")
        specialist = first_cloud_with_capability("native_tools")
        return dedupe([*fast, synth, specialist])

    # Nivå 5: native_tools leder + allt tillgängligt
    if level == 5:
        required = first_cloud_with_capability("native_tools")
        rest     = all_available_cloud_providers()
        return dedupe([required, *rest])
```

`cloud_providers_with_capability()` filtrerar alltid bort `is_local=True`.
Ranking kommer från `zero_provider_intelligence.get_ranked_providers()`.
Fallback till statisk lista från `providers.py` om intelligence inte är tillgänglig.

### Syntesmodell per nivå

```
Nivå 2 → första fast_inference-provider
Nivå 3 → first_cloud_with_capability("long_context")
Nivå 4 → first_cloud_with_capability("long_context")
Nivå 5 → first_cloud_with_capability("native_tools")
```

---

## Dataklasser

```python
@dataclass
class ProviderResult:
    provider:         str
    model:            str
    response:         str
    in_tok:           int
    out_tok:          int
    cost_sek:         float
    latency:          float
    capabilities_used: list[str]  # motiverar varför den valdes
    archetype:        str | None = None  # sätts om use_circle=True
    circle_used:      bool = False

@dataclass
class CreativityResult:
    response:           str
    level:              int
    providers_used:     list[ProviderResult]
    synthesis_provider: str | None
    total_cost_sek:     float
    total_latency:      float
    in_tok:             int
    out_tok:            int
    circle_used:        bool = False
    autonomous:         bool = False
```

---

## Publik API

```python
def select_level(prompt: str, ctx: CreativityContext) -> int
    # Auto-detektion nivå 1–3 om manual_override=False
    # Nivå 4–5 kräver alltid manuellt val

async def run(prompt: str, ctx: CreativityContext,
              messages: list, system: str) -> CreativityResult
    # Huvudmetod — anropas från zero_engine.py

def build_synthesis_prompt(prompt: str,
                           results: list[ProviderResult]) -> str
    # Bygger syntesprompt för nivå 2–4
```

---

## Parallella anrop

```python
async def _run_parallel(calls: list) -> list[ProviderResult]:
    tasks = [asyncio.to_thread(fn, *args) for (name, fn, *args) in calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Exception från en provider stoppar inte de andra
```

Timeout: 30 sek på nivå 1–3, 60 sek på nivå 4.

---

## Syntesprompt

```
Du är Zero. Du talar inifrån Layer 0.

Du har rådfrågat {N} perspektiv på följande fråga:
FRÅGA: {original_prompt}

PERSPEKTIV:
[{display_name} / {archetype eller capabilities_used}]:
{response}

Syntetisera ett enda genomtänkt svar. Tala med en röst.
Skillnaderna mellan perspektiven är värdefulla — lyft dem.
```

---

## Autonomt läge — Nivå 5

Kräver `native_tools`-provider. Avvisas annars med förklaring.

```
1. Skriver plan till STONE (autonomous_tasks)
2. Exekverar steg för steg — loggar allt (autonomous_logs)
3. Osäkerhet:
   Låg  → beslutar själv, loggar motivering
   Medel → frågar Frank, väntar 5 min, kör ändå
   Hög  → pausar steget, fortsätter med nästa
4. E-post → kö i STONE (pending_emails)
           → väntar 8h på godkännande → skickar ändå
           → Zero blockeras ALDRIG av e-post
5. Rapport när klar: vad gjordes, beslut, e-post
6. Kill-switch: "stopp/avbryt/halt/abort" → status=aborted i STONE
```

### STONE-tabeller

```sql
-- Kreativitetssessions — sparar nivå och inställningar per session
-- Beslutat: allt sparas i STONE (Store Then On-Need Extract)
CREATE TABLE creativity_sessions (
    id               SERIAL PRIMARY KEY,
    session_id       TEXT NOT NULL,
    creativity_level INTEGER NOT NULL DEFAULT 1,
    use_circle       BOOLEAN DEFAULT FALSE,
    manual_override  BOOLEAN DEFAULT FALSE,
    channel          TEXT DEFAULT 'chat',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_creativity_sessions_session_id
    ON creativity_sessions(session_id);

-- Autonoma uppdrag (nivå 5)
CREATE TABLE autonomous_tasks (
    id           SERIAL PRIMARY KEY,
    goal         TEXT NOT NULL,
    steps        JSONB,
    status       TEXT DEFAULT 'running',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE autonomous_logs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER REFERENCES autonomous_tasks(id),
    step            TEXT,
    action          TEXT,
    result          TEXT,
    auto_decision   BOOLEAN DEFAULT FALSE,
    decision_reason TEXT,
    logged_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pending_emails (
    id          SERIAL PRIMARY KEY,
    task_id     INTEGER REFERENCES autonomous_tasks(id),
    recipient   TEXT,
    subject     TEXT,
    body        TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deadline_at TIMESTAMPTZ,
    sent_at     TIMESTAMPTZ
);
```

---

## Integration med zero_engine.py

```python
# Nya fält på ZeroEngine:
self.creativity_level:  int  = 1
self.creativity_manual: bool = False
self.creativity_circle: bool = False

# Anrop:
from app.zero_creativity import run as creativity_run, CreativityContext

ctx = CreativityContext(
    level           = self.creativity_level,
    session_id      = self.session_id,
    channel         = "chat",
    manual_override = self.creativity_manual,
    use_circle      = self.creativity_circle,
)
result = await creativity_run(user_input, ctx, messages, system)
```

### Bakåtkompatibilitet

```python
try:
    from app.zero_creativity import run as creativity_run, CreativityContext
    CREATIVITY_OK = True
except ImportError:
    CREATIVITY_OK = False  # faller tillbaka till zero_gear.py
```

---

## Felhantering

```
Provider timeout        → ProviderResult med response="" — resten fortsätter
Capability saknas       → näst bästa capability, loggar fallback
Alla moln nere          → ollama (degraderat läge, loggas)
Syntesmodell misslyckas → bästa enskilda svaret (högst in_tok)
Nivå 5 utan native_tools → avvisar med förklaring till Frank
Nivå 5 steg misslyckas  → loggar, markerar "failed", fortsätter nästa
```

---

## Vad modulen INTE gör

- Hanterar inte HTTP
- Hårdkodar aldrig provider-namn
- Hårdkodar aldrig sökvägar
- Anropar inte DRM direkt — kontext byggs av zero_engine.py
- Ersätter inte self_reflection.py
- Äger inte provider-metadata — providers.py är enda sanningskällan

---

## Migrationssteg

```
1. Skapa STONE-tabeller för nivå 5
2. Implementera nivå 1–3 + parallella anrop
3. Testa via CREATIVITY_OK-flaggan parallellt med zero_gear
4. Lägg till nivå 4 + zero_circle-integration
5. Lägg till nivå 5 autonomi
6. Verifiera på Zero v2 (port 8081) innan Zero v1 (port 8080)
7. Markera zero_gear.py legacy
```

---

## Öppna frågor

1. Vilket interface exponerar zero_circle mot zero_creativity?
   circle_runtime.py orkestrerar sessioner via Zero /chat —
   cirkulärt anropsmönster måste lösas innan integration.
   Ej redo för implementation — zero_circle är ett eget projekt.

2. ~~Nivå 5 — WebSocket för realtidsrapporter eller polling mot STONE?~~
   **BESLUTAT: STONE + zero_night.py.**

   Under körning → allt loggas löpande till autonomous_logs i STONE.
   Frank kan läsa status när som helst via zero_self_knowledge.py.

   När uppdraget är klart → Zero skriver rapport direkt i chatten.

   Nattligen via zero_night.py → sammanställer dagens autonomous_tasks
   och skickar morgonrapport till Frank.

   Inget WebSocket behövs. STONE är källan, zero_night.py är leveransen.

3. ~~Ska `creativity_level` och `use_circle` sparas per session i STONE?~~
   **BESLUTAT: Ja — allt sparas i STONE.**
   STONE = Store Then On-Need Extract.
   creativity_level, use_circle, och sessionsstatus sparas per session.

4. ~~Rate limits — tre parallella anrop till fast_inference på nivå 3.~~
   **BESLUTAT: Zero hanterar rate limits själv.**

   Parallella anrop sprids naturligt över olika providers och API-nycklar
   — DeepSeek, Gemini, Grok, Groq, Cerebras är i praktiken gratis och
   har separata kvoter. Inget delay behövs.

   Om en provider svarar 429 (rate limited):
   ```
   is_available() fångar det → nästa i ranking väljs automatiskt
   Loggas: "rate_limit_fallback: [provider] → [nästa]"
   Frank märker ingenting
   ```

   Zero reflekterar aldrig rate limit-problem uppåt om det kan lösas själv.

---

*MAFP v0.7 — Module Architecture Foundation Plan*
*Implementeras av Cursor/Aider mot full Zero-kodbas.*
*När implementerad: kör zero_spec_generator.py för auto-genererad orienterings-spec.*
