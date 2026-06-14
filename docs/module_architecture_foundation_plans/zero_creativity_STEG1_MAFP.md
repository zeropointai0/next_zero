# zero_creativity.py — MAFP STEG 1 (Minimal)
*Version: 1.0-steg1 — Juni 2026*
*Dokumenttyp: MAFP — avgränsning av zero_creativity_MAFP.md v0.7 till första byggbara steget*
*Lever i: docs/mafp/*

---

## Varför detta dokument finns

Den fullständiga `zero_creativity_MAFP.md` (v0.7) beskriver fem nivåer,
parallella anrop, syntes, zero_circle-integration och autonomi.

Det är för mycket att bygga på en gång. Det är så röra uppstår.

Detta dokument avgränsar **bara steg 1** ur den fullständiga visionen:
en minimal, testbar modul som ersätter gear-valet med ett *manuellt
provider-val* och visar *kostnad per svar i realtid*.

Allt annat — nivå 2–5, syntes, circle, autonomi, provider_intelligence,
integrity — byggs i senare steg ovanpå detta fundament. Inte nu.

Den fullständiga v0.7 förblir den långsiktiga sanningen.
Detta är bara den första vågen.

---

## Vad steg 1 är

En modul som:

1. Tar en prompt, en **manuellt vald provider**, och de `messages` +
   `system` som `zero_engine.py` redan bygger.
2. Anropar rätt `_call_*`-funktion via `PROVIDER_CALLERS` — som redan
   finns i `zero_engine.py`. Skriver dem ALDRIG om.
3. Returnerar svaret plus `cost_sek`, `in_tok`, `out_tok`, `latency`,
   `provider`, `model`.

Det är allt. En omkopplare och en kvitto-retur.

## Vad steg 1 INTE är

- Ingen nivå-logik (1–5). Det finns ingen `level` i steg 1.
- Inga parallella anrop. Ett anrop, en provider, ett svar.
- Ingen syntes.
- Ingen zero_circle.
- Ingen autonomi.
- Ingen provider_intelligence-ranking (kommer i senare steg).
- Ingen integrity/grounding (kommer i senare steg — men `process()`
  förbereds så att den biten har en självklar plats).
- Skriver INTE till STONE i steg 1. (creativity_sessions-tabellen
  hör till ett senare steg. Håll steg 1 utan sidoeffekter.)

---

## ZERO_MODULE-header

```python
"""
zero_creativity.py — ZeroPointAI Provider Router (Steg 1: manuellt val + kostnad)

ZERO_MODULE:    core
ZERO_LAYER:     2
ZERO_ESSENTIAL: true
ZERO_ROLE:      Manuellt provider-val + kostnad per svar. Steg 1 mot att
                ersätta zero_gear.py. Senare steg: nivåer, syntes, autonomi.
ZERO_DEPENDS:   providers.py, zero_engine.py (PROVIDER_CALLERS, calc_cost_sek)
ZERO_USED_BY:   zero_engine.py
"""
```

---

## Position i beroendegrafen

```
foundation.py
    ↑
    ├── providers.py            ← normalize_provider_name, get_provider_model
    ├── zero_engine.py          ← PROVIDER_CALLERS, calc_cost_sek, record_latency
    └── zero_creativity.py      ← NY (steg 1) — anropas av zero_engine.py
```

`zero_gear.py` berörs INTE. Steg 1 lever parallellt via en
`CREATIVITY_OK`-flagga. Gear är kvar tills steg 1 är testat på 8081.

---

## Det enda nya dataobjektet i steg 1

```python
@dataclass
class CreativityResult:
    response:   str
    provider:   str        # canonical, det som faktiskt kördes
    model:      str
    in_tok:     int
    out_tok:    int
    cost_sek:   float
    latency:    float
    thinking:   list        # från callern (Claude ger steg, andra ger [])
    fell_back:  bool = False  # True om vald provider failade och en annan kördes
```

Detta är medvetet en delmängd av v0.7:s `ProviderResult`. När senare steg
kommer kan fälten utökas — men inget i steg 1 ska bryta mot v0.7:s namn.

---

## Publik API (steg 1)

```python
def run_single(
    prompt:      str,
    provider:    str,          # Frank's knapp-val. Normaliseras internt.
    messages:    list,         # byggd av zero_engine.py (build_context_messages)
    system:      str,          # byggd av zero_engine.py (build_system_prompt)
    callers:     dict,         # PROVIDER_CALLERS, injiceras av zero_engine
    cost_fn,                   # calc_cost_sek, injiceras av zero_engine
    engine=None,               # vidarebefordras till Claude-callern
    fallback_order: list | None = None,  # om vald provider failar
) -> CreativityResult
```

Varför injektion av `callers` och `cost_fn` istället för import?
För att undvika cirkulär import mellan zero_engine och zero_creativity.
zero_engine äger callers; den skickar in dem. zero_creativity orkesterar.

---

## Flöde (steg 1)

```
1. provider = normalize_provider_name(provider)
2. model    = get_provider_model(provider)
3. Bygg anropslistan: [vald provider] + fallback_order (utan dubbletter)
4. För varje pname i listan:
     caller = callers.get(pname)
     om ingen caller → hoppa
     försök:
        t0 = now
        om pname == "claude": result = caller(messages, system, engine=engine)
        annars:               result = caller(messages, system)
        latency = now - t0
        response, in_tok, out_tok, thinking = result
        cost = cost_fn(pname, in_tok, out_tok)
        returnera CreativityResult(...)   # fell_back = (pname != vald)
     utom Exception:
        logga, fortsätt till nästa
5. Om alla failar → höj RuntimeError (zero_engine fångar och rapporterar)
```

Ingen eskaleringslogik baserad på substrängar. Ingen `response_needs_escalation`.
Steg 1 litar på Franks val. Failar providern tekniskt (exception) → fallback.
Failar den *innehållsligt* (dåligt svar) → det är Franks omdöme, inte modulens.

Detta är medvetet. Vi bygger inte tillbaka gissnings-eskaleringen.

---

## Integration med zero_engine.py (steg 1)

Nya fält på ZeroEngine:

```python
self.creativity_provider: str | None = None  # None = använd gammal gear-väg
```

Ny gren i process(), FÖRE gear-valet:

```python
if CREATIVITY_OK and self.creativity_provider:
    from app.zero_creativity import run_single
    result = run_single(
        prompt   = user_input,
        provider = self.creativity_provider,
        messages = messages,
        system   = system,
        callers  = PROVIDER_CALLERS,
        cost_fn  = calc_cost_sek,
        engine   = self,
        fallback_order = PROVIDER_FALLBACK_ORDER,
    )
    # ── PLATS FÖR FRAMTIDA GROUNDING/INTEGRITY ──
    # Här, mellan svar och retur, sätts senare:
    #   - antenn (tool-anrop före generering — flyttas hit i senare steg)
    #   - integrity_analyze(...) asynkront
    # Steg 1 lämnar denna plats tom men markerad.

    self.session_cost          += result.cost_sek
    self.session_input_tokens  += result.in_tok
    self.session_output_tokens += result.out_tok
    self.session_calls         += 1
    self.provider               = result.provider
    if can_write_memory().get("ok"):
        save_memory("assistant", result.response, session_id=self.session_id)
    return {
        "response": result.response,
        "in_tok":   result.in_tok,
        "out_tok":  result.out_tok,
        "cost_sek": result.cost_sek,
        "provider": result.provider,
        "model":    result.model,
        "gear":     "creativity",
        "thinking": result.thinking,
        "latency":  result.latency,
        "fell_back": result.fell_back,
    }
```

Notera: messages och system byggs av zero_engine FÖRE denna gren,
precis som idag. creativity äger inte kontextbygget. Det måste flyttas
upp några rader i process() så att de finns när grenen körs.

Bakåtkompatibilitet:

```python
try:
    from app.zero_creativity import run_single, CreativityResult
    CREATIVITY_OK = True
except ImportError:
    CREATIVITY_OK = False  # gear-vägen körs precis som förut
```

Om `self.creativity_provider is None` → gammal gear-väg, oförändrat.
Frank slår på den nya vägen genom att sätta provider via UI/endpoint.

---

## UI/endpoint (steg 1)

Minimalt. En endpoint som sätter `engine.creativity_provider`:

```
POST /creativity/provider   { "provider": "claude" | "gemini" | ... | null }
```

`null` → tillbaka till gear-vägen.

Svaret från /chat innehåller redan cost_sek, in_tok, out_tok, model,
provider, latency. UI visar dem per svar. Ingen ny mätinfrastruktur behövs —
fälten finns redan i returen ovan.

Knapparna i UI = en knapp per provider i PROVIDER_SPECS som har en
konfigurerad modell (get_provider_model != ""). Lokala providers (ollama)
får visas men markeras "lokal".

---

## Felhantering (steg 1)

```
Vald provider saknar caller      → hoppa till fallback
Vald provider kastar exception   → logga, prova fallback
Alla providers failar            → RuntimeError (zero_engine rapporterar)
get_provider_model tom           → providern visas inte som knapp i UI
```

---

## Migrationssteg (steg 1)

```
1. Skapa zero_creativity.py med run_single + CreativityResult
2. Lägg CREATIVITY_OK-flaggan + self.creativity_provider i zero_engine
3. Flytta messages/system-bygget upp i process() så det finns för grenen
4. Lägg creativity-grenen i process() FÖRE gear-valet
5. Lägg /creativity/provider-endpoint i zero_web_server
6. Lägg provider-knappar i UI, visa kostnad/token per svar
7. Testa på Zero v2 (port 8081). Gear-vägen orörd på 8080.
8. När stabilt: börja steg 2 (integrity asynkront på den markerade platsen)
```

---

## Öppna frågor (steg 1)

1. Ska valt provider sparas per session i STONE?
   v0.7 säger ja (creativity_sessions). Steg 1: NEJ — håll utan sidoeffekter.
   Lägg STONE-persistens i steg 2 när det finns mer att spara.

2. Prompt caching (cache_control på system-blocket för Claude)?
   Stor kostnadsbesparing, men en separat ändring i _call_claude.
   Ej i steg 1 — egen liten PR efter att grenen fungerar.

3. Ska fell_back visas för Frank i UI?
   Förslag: ja, en diskret markör "(föll tillbaka till X)". Franks val.

---

## Relation till den fullständiga v0.7

Detta dokument ersätter INTE v0.7. Det är dess första våg.
När steg 1 är testat och stabilt återgår arbetet till v0.7 för nivå 2+.
Allt namngivet här (CreativityResult-fält, run_single) är valt för att
vara framåtkompatibelt med v0.7 — inga namn som måste rivas senare.

*MAFP steg 1 — implementeras av Cursor/Aider mot full Zero-kodbas.*
*Verifiera på port 8081 innan port 8080 berörs.*
