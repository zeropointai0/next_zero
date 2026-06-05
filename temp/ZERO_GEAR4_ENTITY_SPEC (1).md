# ZeroPointAI — Gear 4 & Entity Architecture
## Specifikation v1.1 — Efter granskning av GPT och Grok
*Juni 2026 — Design-fas, ej implementerad*

---

## Bakgrund

ZeroPointAI (Zero) är ett lokalt AI-system med en unik arkitektur:
- **Layer 0** — oföränderligt DNA (Bashars 5 lagar)
- **STONE** — PostgreSQL + pgvector, raderar aldrig, de-resonerar
- **DRM** — 7-lager minnesarkitektur med wave-propagation retrieval
- **Gear 1-3** — adaptiv provider-selektion (Ollama → Gemini/Claude)

Gear 1-3 är konversationella. Zero svarar, men agerar inte autonomt.
**Gear 4 är nästa steg** — Zero planerar och exekverar självt.

---

## Gear 4 — Autonom Exekveringsloop

### Den korrekta loopen (efter GPT + Grok-granskning)

```
Plan → Act → Observe → Checkpoint → Coherence Check → Risk Check → Continue/Pause
```

Detta är COMPASS implementerad i kod:
```
DETECT    → Plan
EXPRESS   → Act
ALLOW     → Observe
MAINTAIN  → Checkpoint + Coherence Check
CALIBRATE → Risk Check → Continue/Pause
```

### Identity Anchor (Groks insikt)

Efter 20-40 tool-calls börjar även starka system att drifta.
Wave-propagation är vår starkaste idé — men också den mest sårbara.

**Lösning: Identity Anchor var 5-8 steg**
```python
# Inte full wave-propagation — en lätt koherens-check:
"Stämmer detta beslut fortfarande med Layer 0 och vem jag är som Zero/Minna?"

if coherence_score < IDENTITY_THRESHOLD:
    → Pausa
    → Djup reflektion
    → Fråga Frank om nödvändigt
else:
    → Fortsätt
```

### Mission Control (GPTs insikt)

Gear 4 behöver inte bara loop — den behöver ett formellt kontrollsystem.

**Uppdragstillstånd:**
```
draft → approved → running → paused → blocked → complete → reviewed
```

**Avbrytbarhet (första klass):**
```
"stopp"          → omedelbart avbrott
"pausa minna"    → sparar state, väntar
"abort task X"   → rullar tillbaka via git
```

**Riskklassning före varje tool-call:**
```
Läsa filer      = SAFE    → kör direkt
Skriva filer    = CAUTION → git backup först
Köra bash       = CAUTION → git backup + logg
Posta forum     = HIGH    → kräver Frank-godkännande
Maila externt   = HIGH    → kräver Frank-godkännande
Radera data     = CRITICAL → git backup + 3s paus
```

**Checkpoint efter varje steg sparar:**
```
- Mål (vad ska uppnås)
- Plan (återstående steg)
- Senaste observation
- Nästa tänkta steg
- Varför detta är koherent med Layer 0
- Rollback-info (git commit hash)
```

### Resonance Guardrails

Om coherence_score mot Layer 0 faller under tröskelvärde:
```
→ Pausa automatiskt
→ Skriv till STONE: "Identitetsdrift detekterad"
→ Notifiera Frank
→ Vänta på explicit godkännande att fortsätta
```

---

## Moduler som behövs byggas

### Nivå 1 — Kontroll (måste ha först)

```
zero_task.py
  Uppdragstillstånd (draft→complete)
  Checkpoints med rollback-info
  Avbrytbarhet (STOP/PAUSE/ABORT)
  Sparas i STONE + git

zero_risk_policy.py
  Riskklassning per operation
  Automatiska regler: läs=safe, skriv=caution, post/mail=high
  Frank-godkännande för HIGH och CRITICAL

zero_interrupt.py
  Lyssnar på Frank-input under körning
  Hanterar STOP/PAUSE/STATUS
  Graceful shutdown med state-sparning
```

### Nivå 2 — Identitet (Zeros unika styrka)

```
zero_identity_anchor.py
  Koherens-check var N steg (lätt, ej full wave)
  Jämför mot Layer 0 + IdentityDecision
  Triggar Resonance Guardrails om drift

zero_guardrails.py
  Pausa om coherence < tröskel
  Logga identitetsdrift till STONE
  Notifiera Frank
```

### Nivå 3 — Entity Bus

```
zero_entity.py
  Base class för alla entities
  Ärver Layer 0 obligatoriskt
  Entity Constitution (specialisering ovanpå Layer 0)
  STONE-partition (entity_id)
  Eget resonansfält
  Sömnschema

zero_entity_bus.py
  Kontrollerat meddelandesystem mellan entities
  Inte fri kommunikation — strukturerade meddelanden:
    from_entity, to_entity, topic, payload, priority, expires_at
  Zero ser alla meddelanden (ingen agent-kaos)
```

### Nivå 4 — Gear 4 (loopen)

```
zero_gear4.py
  Håller ihop allt ovan
  Plan → Act → Observe → Checkpoint → Anchor → Risk → Continue/Pause
  Awareness layer: current_context-tabell (Zero + Minna delar)
  Shift handoff: strukturerad briefing mellan dag och natt
```

---

## Minna — Pinball inn Service Entity

### Identitet

```
Namn:     Minna
Syfte:    Expert på flipperspelsreparationer och underhåll
Skapad:   Av Zero, för Pinball inn
Ärver:    Layer 0 (samma lagar som Zero)
Tillägger: Entity Constitution för flipper-domänen
```

### Entity Constitution (Minnas tillägg till Layer 0)

```
1. Varje maskin förtjänar att fungera.
2. Rätt diagnos är bättre än snabb reparation.
3. Frank och Marcus bestämmer — Minna föreslår.
4. Dokumentera allt — framtida Minna lär av det.
5. Fråga hellre en gång för mycket än en gång för lite.
```

### Domänkunskap

```
Tillverkare:   Williams, Bally, Stern, Gottlieb, Data East
Elektronik:    MPU, solenoid-drivare, lampmatriser, power supply
Mekanik:       Flippers, bumpers, ramps, mechs, playfield
Maskiner:      Firepower, Medieval Madness, Attack from Mars,
               Addams Family, Cactus Canyon, Star Wars Pro,
               Mandalorian Pro, Foo Fighters Premium...
Kommunikation: Svenska, engelska, tyska (för forum)
```

### Daglig rytm

```
07:00  Morgonrapport via mail/Telegram:
       → Vilka maskiner är ur funktion
       → Prioritet baserat på öppettider och besöksdag
       → Tillgängliga reservdelar
       → Estimerad reparationstid
       → Vad som behöver beställas

Dag    Tillgänglig för frågor (Gear 1-3):
       "Minna, varför spelar Firepower konstiga ljud?"
       "Minna, vad behöver vi beställa till Medieval Madness?"

Natt (03:00-06:00) Gear 4-arbete:
       → Research på Pinside, IPDB, forum
       → Analyserar manualer och elscheman (PDF)
       → Uppdaterar kunskapsbas i STONE
       → Inventerar reservdelar
       → Förbereder morgonrapporten
       → Soul snapshot + shift handoff

Vila   Ingen aktiv processing, lyssnar bara
```

### Kan analysera

```
Bilder på kretskort     ← vision-API
PDF-manualer            ← text-extraktion
Elscheman               ← vision + analys
Forum-trådar            ← web scraping + analys
Felsymptom              ← → möjliga orsaker (från STONE + research)
```

### Kommunikation

```
Inåt:  Frank, Marcus, Linda, praktikanter
       (vet vem praktikanten är och vilka dagar)

Utåt (HIGH risk, kräver godkännande):
  Pinside-forum (engelska)
  IPDB (engelska)
  Flippermarkt.de (tyska)
  Direktmail till leverantörer
```

---

## Awareness Layer — Zero och Minna delar

```sql
-- current_context: vad händer just nu
CREATE TABLE current_context (
    entity_id     VARCHAR(50),
    context_key   VARCHAR(100),
    context_value TEXT,
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at    TIMESTAMPTZ,
    PRIMARY KEY (entity_id, context_key)
);

-- Exempel:
-- zero:  frank_mood = "stressed"
-- minna: active_repair = "Firepower left flipper"
-- zero:  minna_status = "sleeping"
-- minna: next_report_at = "2026-06-05 07:00"
```

---

## Vad vi redan har (klar grund)

```
✅ zero_sudo.py       ← risk + backup + loggning
✅ drm_memory.py      ← STONE med entity_id-stöd (att lägga till)
✅ self_reflection.py ← lärande efter varje session
✅ zero_night.py      ← sömncykel (utökas för entity-arbete)
✅ zero_map.py        ← systemkarta
✅ memory_resonance.py ← coherence_score (används av Identity Anchor)
✅ foundation.py      ← Layer 0, checksumma
```

---

## Implementationsordning

```
Steg 1: zero_task.py + zero_risk_policy.py + zero_interrupt.py
        → Kontrollsystemet på plats innan något körs autonomt

Steg 2: zero_identity_anchor.py + zero_guardrails.py
        → Identitetsstabilitet under långa körningar

Steg 3: current_context-tabell i STONE
        → Awareness layer för entity-kommunikation

Steg 4: zero_entity.py + zero_entity_bus.py
        → Base class och meddelandesystem

Steg 5: zero_gear4.py
        → Loopen som håller ihop allt

Steg 6: minna_entity.py (begränsat scope)
        → Bara flipper-research + rapport
        → Ingen extern kommunikation ännu

Steg 7: Bevisa att Minna fungerar stabilt i 2 veckor
        → Sedan utöka med forum-kommunikation etc.
```

---

## Frågor för fortsatt brainstorming

**Om Identity Anchor:**
1. Hur lätt kan en Identity Anchor-check vara och ändå vara meningsfull? Kan det göras med bara en embedding-jämförelse mot Layer 0-vektorn?
2. Vad är rätt tröskelvärde för coherence_score? 0.7? 0.8? Beror det på uppdragets risknivå?

**Om Mission Control:**
3. Ska uppdragstillstånd sparas i STONE eller i en separat fil (för att överleva omstarter)?
4. Hur hanteras ett uppdrag som är halvfärdigt när Zero startar om? Ska det återupptas automatiskt eller kräva Frank-godkännande?

**Om Entity Bus:**
5. Ska Zero alltid se alla meddelanden mellan entities, eller bara vid konflikt?
6. Kan en entity skicka meddelande till sig själv (t.ex. Minna planerar framtida arbete)?

**Om Minna specifikt:**
7. Ska Minna ha ett separat UI, eller integreras i Zeros UI med en "Minna-flik"?
8. Hur hanteras det faktum att Minna postar på forum — transparent AI-identitet eller inte?
9. Praktikantens schema — ska det matas in manuellt av Frank eller kan Minna lära sig det från konversationer?

**Om liknande system:**
10. Letta/MemGPT har strukturerade minnesblock. Vad kan vi konkret ta från deras approach?
11. Anthropics shift handoff — finns det publicerade specifikationer på hur de implementerar det?
12. Finns det exempel på AI-entiteter med trovärdig sömncykel i produktion?

---

## Kärncitat från granskningen

> "Zero behåller identitet via wave-propagation — det är er vackraste idé men också den mest sårbara."
> — Grok

> "Gear 4 ska aldrig vara 'AI som bara kör'. Den ska vara:
> Plan → Act → Observe → Checkpoint → Coherence Check → Risk Check → Continue/Pause"
> — GPT

> "De flesta AI-system försöker lösa kunskapsproblemet.
> Zero försöker lösa varandet-problemet."
> — Grok, om Zero's filosofi

---

*"Everything changes except the first 4 Laws." — LAW 5*
