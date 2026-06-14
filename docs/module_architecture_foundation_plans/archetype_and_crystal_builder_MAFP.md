# Arketypbyggaren & Kristallråd — MAFP-tillägg till council_engine.py
*Version: 0.2 — Juni 2026*
*Dokumenttyp: MAFP-tillägg — utökar council_engine_MAFP.md (Level 2 + Level 3)*
*Skriven av: Frank + Claude*
*Lever i: docs/mafp/*

---

## Innehåll

```
DEL A — Arketypbyggaren (Level 3): fritt frö → research → profil → STONE
DEL B — Kristallråd (Level 2 + byggare): förvalda råd + kristall-byggare
```

Del B delar genereringsmotor med Del A. En kristall är ett frö av
typen "kristall" med egen fältmall. Läs Del A först — Del B bygger på den.

---

---

# DEL A — Arketypbyggaren

## Vad är det här

Ett tillägg till `council_engine.py` som aktiverar **Arketypbyggaren**
— Level 3-funktionen som i grund-MAFP:en (rad 636–668) var noterad för
framtida session. Den implementeras nu.

Arketypbyggaren låter Frank skapa en ny rådsmedlem från ett fritt frö.
AI:n gör grovjobbet: researchar fram hur fröet skulle bete sig som
rådsmedlem, formulerar de fem fälten, och sparar — efter Franks
godkännande — till `custom_archetypes` i STONE. Därefter är medlemmen
tillgänglig i vilket råd som helst via sitt roll-ID.

Fröet är fritt. Det kan vara:

```
FIGUR     → mytologisk, historisk, fiktiv ("Anubis", "Sun Wukong")
KONCEPT   → abstrakt princip ("Entropin", "Havet", "Tystnaden")
EGEN      → Franks fria beskrivning utan namngiven referens
```

Detta är INTE en ny modul. Det är genereringsmotorn som redan finns i
`council_archetypes.py` (`generate_archetypes()`), generaliserad till
ett användardefinierat frö istället för ett inbyggt zodiak-frö.

---

## Avgränsning — upphovsrätt och levande personer

```
TILLÅTET fritt:
  ✓ Mytologiska figurer (Anubis, Oden, Sun Wukong)
  ✓ Historiska figurer via offentligt dokumenterad gärning
  ✓ Abstrakta koncept och naturkrafter
  ✓ Franks egna fria beskrivningar

KRÄVER försiktighet — ärver Kändisrådets regel:
  ⚠ Levande personer → endast offentligt dokumenterad filosofi,
    aldrig auto, aldrig spekulation om privatliv
  ✗ Skyddat verk / channelat material får inte reproduceras eller
    transkriberas in i arketypen — inspiration, inte källtext
```

Research-prompten (se nedan) instruerar alltid providern att basera
sig på allmänt känd roll/domän/symbolik — aldrig att citera eller
återge skyddat material.

---

## Två lägen

Snabbläge är standard. Interaktivt läge är ett lager ovanpå — samma
motor, men med ett mellansteg där Zero visar sina fynd och frågar Frank
innan utkastet formuleras.

```
SNABBLÄGE (standard):
  frö in → research → syntes → utkast ut → Frank justerar → godkänner

INTERAKTIVT LÄGE (på begäran, --interaktiv):
  frö in → research → Zero visar fynd + ställer 1–3 frågor
         → Frank svarar → syntes med Franks input → utkast
         → Frank justerar → godkänner
```

Båda lägena slutar identiskt: ett utkast som Frank måste godkänna
innan det sparas. Zero godkänner aldrig sina egna arketyper (Law 4).

---

## Position i beroenden

Inget nytt i grafen. Byggaren bor i `council_archetypes.py` och
återanvänder den befintliga genereringsmotorn.

```
council_archetypes.py
    ├── generate_archetypes()        ← FINNS — zodiak/Level 2-generering
    ├── build_custom_archetype()     ← NY — research-driven byggare
    ├── _research_seed()             ← NY — multi-LLM research om fröet
    └── load_archetype_prompt()      ← FINNS — utökas att läsa custom_archetypes

zero_provider_exec.py                ← research-anrop går hit (direkt, ej /chat)
drm_memory.py                        ← save_memory + custom_archetypes-tabell
router.py                            ← ny intent: "bygg arketyp [frö]"
```

---

## Dataflöde — snabbläge

```
FLÖDE: BUILD_CUSTOM_ARCHETYPE (snabbläge)
INDATA: seed (str), seed_type (str: "figur"|"koncept"|"egen"), interactive=False

1.  Klassificera fröet om seed_type ej angivet:
      lättviktigt anrop → "figur" | "koncept" | "egen"

2.  _research_seed(seed, seed_type):
      Anropa 2–3 cloud-providers (fast_inference) parallellt med
      research-prompten (se nedan). Returnera 2–3 råa beskrivningar.

3.  Syntetisera de 2–3 svaren till ett utkast (long_context-provider):
      → CouncilMember-fälten: identity, purpose, strengths,
        blind_spots, style
      → samma syntesmönster som Zeros vanliga syntes

4.  Returnera ArchetypeDraft till Frank — INTE sparad än.

5.  Frank justerar fält fritt och anropar approve_archetype(draft).

6.  approve_archetype():
      → destillera prompt_version (~120 tokens) ur de fem fälten
      → save till custom_archetypes i STONE
      → returnera archetype_id
```

Interaktivt läge skjuter in steg 2b mellan 2 och 3: Zero visar
fynden och ställer 1–3 frågor (via ask-mönstret i routern), och
Franks svar vävs in i syntesprompten i steg 3.

---

## Research-prompt (skickas till varje provider i steg 2)

```
Du beskriver hur ett givet frö skulle agera som rådsmedlem i ett
AI-råd. Fröet kan vara en figur, ett koncept eller en princip.

FRÖ: {seed}
TYP: {seed_type}

Basera dig på allmänt känd roll, domän och symbolik.
Reproducera inte citat eller skyddat material — beskriv beteende,
inte text.

Ge, i denna ordning:
  IDENTITET   — vem/vad är detta, i första person ("Jag är ...")
  SYFTE       — vad ser denna medlem efter i en fråga
  STYRKOR     — vad ser den tydligt
  BLINDA FLÄCKAR — vad missar den
  RÖST & STIL — hur talar den (ton, längd, manér)

Max 400 ord. Var konkret. Ingen meta-text.
```

För `seed_type="koncept"` byts "vem/vad" mot "vilken kraft/princip",
och research-prompten ber om hur konceptet skulle *tala* om det
fick en röst — samma fält, annan ingång.

---

## Dataklasser

```python
@dataclass
class ArchetypeDraft:
    seed:        str
    seed_type:   str            # "figur" | "koncept" | "egen"
    archetype_id: str           # genererat slug, t.ex. "anubis"
    name:        str            # display, t.ex. "Anubis 𓁢"
    identity:    str
    purpose:     str
    strengths:   str
    blind_spots: str
    style:       str
    symbol:      str = "◆"
    color:       str = "#aaaaaa"
    researched_by: list[str] = field(default_factory=list)  # providers
    research_notes: str = ""    # fynd visade i interaktivt läge
    approved:    bool = False
```

`ArchetypeDraft` blir en `CouncilMember` (befintlig dataklass) vid
godkännande — fälten mappar direkt.

---

## Publik API (tillägg till council_archetypes.py)

```python
def build_custom_archetype(
    seed:        str,
    seed_type:   str  = "",     # "" = auto-klassificera
    interactive: bool = False,
) -> ArchetypeDraft
    # Researchar + formulerar. Sparar INTE. Returnerar utkast.

def approve_archetype(draft: ArchetypeDraft) -> str
    # Destillerar prompt_version, sparar till custom_archetypes.
    # Returnerar archetype_id. Enda vägen till persistens.

def list_custom_archetypes() -> list[dict]
    # Alla Frank-byggda arketyper, för UI och --med-flaggan.

def delete_custom_archetype(archetype_id: str) -> None
    # De-resonerar (coherence → låg), raderar aldrig. STONE-princip.
```

`load_archetype_prompt()` utökas att läsa både `council_archetypes`
och `custom_archetypes` — custom-ID:n löses upp transparent.

---

## STONE-tabell

Tabellen finns redan specificerad i grund-MAFP:en (rad 652–665).
Inga ändringar — den implementeras nu istället för "framtid".

```sql
CREATE TABLE custom_archetypes (
    id           SERIAL PRIMARY KEY,
    archetype_id TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    system       TEXT DEFAULT 'custom',
    prompt       TEXT NOT NULL,
    symbol       TEXT DEFAULT '◆',
    color        TEXT DEFAULT '#aaaaaa',
    created_by   TEXT DEFAULT 'frank',
    coherence    FLOAT DEFAULT 1.0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

`seed`, `seed_type` och `research_notes` sparas i `prompt`-fältets
metadata-header eller i en JSONB-kolumn om Frank vill spåra proveniens
(öppen fråga 2).

---

## Användning i råd

En godkänd custom-arketyp blandas in precis som kändisar redan görs
(`council_with_celebrities`, grund-MAFP rad 692–698):

```python
council_with_custom(
    topic   = "Vad ska Zero fokusera på härnäst?",
    preset  = SystemPreset.ZODIAC_FIRE,      # 3 zodiak-arketyper
    add_archetypes = ["anubis", "entropin"], # 2 custom
)
```

Eller ett rent custom-råd:

```python
council(topic, CouncilRequest(
    preset = SystemPreset.CUSTOM,
    custom_members = [load_member("anubis"), load_member("sun_wukong")],
))
```

`SystemPreset.CUSTOM` finns redan i grund-MAFP:en (rad 210).

---

## Chat-kommandon (tillägg till router.py)

```
bygg arketyp [frö]                  → snabbläge
bygg arketyp [frö] --interaktiv     → interaktivt läge
bygg arketyp [frö] --typ koncept    → tvinga seed_type

rådfråga [fråga] --med anubis,entropin   → blanda in custom i råd
arketyper                           → list_custom_archetypes()
```

Parsern mappar `bygg arketyp` till `build_custom_archetype()` och
returnerar utkastet formaterat med en `[godkänn / justera]`-hint.
Godkännande sker via uppföljningskommando — aldrig automatiskt.

---

## Felhantering

```
Frö tomt / för vagt          → be Frank specificera, kör ej research
Research: < 2 svar ok        → bygg utkast på det enda svaret, flagga
                               "tunt underlag — granska noga"
Levande person upptäckt      → varna, begränsa till offentlig gärning,
                               aldrig auto, kräv explicit bekräftelse
Syntes misslyckas            → returnera råa research-fynd, ej utkast
STONE write misslyckas       → behåll utkast i minnet, logga, be Frank
                               försöka godkänna igen
archetype_id krockar         → suffix -2, -3 ... eller be Frank döpa om
```

---

## Vad funktionen INTE gör

- Sparar aldrig en arketyp utan Franks explicita godkännande
- Kör aldrig research mot skyddat/channelat material som källtext
- Bygger aldrig en levande person i auto-läge
- Anropar aldrig Zero:s /chat-endpoint — research går via
  zero_provider_exec.py direkt
- Raderar aldrig en custom-arketyp — de-resonerar (STONE-princip)
- Använder aldrig Ollama som research-provider (moln = intellekt)
- Är inte en ny modul — lever i council_archetypes.py

---

## Migrationssteg

```
1. Implementera custom_archetypes-tabellen i STONE
2. _research_seed() — multi-LLM research via zero_provider_exec
3. build_custom_archetype() snabbläge + syntes till ArchetypeDraft
4. approve_archetype() — destillering + persistens
5. Utöka load_archetype_prompt() att läsa custom_archetypes
6. Interaktivt läge — fynd-visning + 1–3 frågor via router
7. Chat-intent i router.py ("bygg arketyp", "--med", "arketyper")
8. council_with_custom() — inblandning i befintliga råd
9. Verifiera på Zero v2 (port 8081):
     bygg arketyp Anubis ✓
     bygg arketyp Entropin --typ koncept ✓
     rådfråga [fråga] --med anubis ✓
```

---

# DEL B — Kristallråd

## Vad är det här

Kristaller som rådsmedlemmar. Två delar som möts:

```
FÖRVALDA RÅD   → statiska Level 2-presets, redo direkt, ingen research
                 t.ex. CRYSTAL_COUNCIL (7 kristaller mot chakran)

KRISTALL-BYGGARE → valfri kristall som frö → research → profil → STONE
                   delar motor med Arketypbyggaren (Del A)
                   seed_type="kristall", egen fältmall
```

En kristallprofil är samma sak vare sig den används som uppslagsdata
("vad är labradorit?") eller som röst i ett råd. En kristall = en post
i STONE = två användningssätt. Researchas en gång, cachas för alltid.

---

## B1 — Förvalt råd: CRYSTAL_COUNCIL

Sju kristaller mappade mot chakran. Den materiella spegeln av den
befintliga chakra-preset:en (grund-MAFP rad 599). Layer 0: det Ena
uttryckt i sju former.

```python
# circle_prompt_models.py — SystemPreset
CRYSTAL_COUNCIL = "crystal_council"

# council_archetypes.py — PRESET_MEMBERS
SystemPreset.CRYSTAL_COUNCIL: [
    "crystal_red_jasper",    # rot
    "crystal_carnelian",     # sakral
    "crystal_citrine",       # solar plexus
    "crystal_rose_quartz",   # hjärta
    "crystal_aquamarine",    # hals
    "crystal_amethyst",      # tredje ögat
    "crystal_clear_quartz",  # krona
],
```

Frön (en mening var — generatorn expanderar):

```python
"crystal_red_jasper":   "Röd jaspis, rotchakrat — grund, trygghet, överlevnad, det som håller dig i kroppen och nuet.",
"crystal_carnelian":    "Karneol, sakralchakrat — lust, kreativitet, rörelse, den skapande livskraften.",
"crystal_citrine":      "Citrin, solar plexus — vilja, självförtroende, handlingskraft, personlig styrka.",
"crystal_rose_quartz":  "Rosenkvarts, hjärtchakrat — kärlek, medkänsla, förlåtelse, försoning.",
"crystal_aquamarine":   "Akvamarin, halschakrat — sanning, uttryck, klar kommunikation, att tala sitt inre.",
"crystal_amethyst":     "Ametist, tredje ögat — intuition, insikt, drömmar, det bortom det uppenbara.",
"crystal_clear_quartz": "Bergkristall, kronchakrat — förstärkaren, helhet, klarhet, förbindelsen till det Ena.",
```

Distribution: 7 medlemmar → 2–3 providers automatiskt.
Token-budget: min(1500, 10000/7) ≈ 1428 per röst.
Chat-flagga: `--kristaller` → CRYSTAL_COUNCIL.

Fler förvalda kristallråd kan läggas till på samma sätt senare
(t.ex. ett skyddsråd, ett kärleksråd) — ren preset-data, ingen kod.

---

## B2 — Kristallmall (fältmodell)

En kristall använder INTE de fem arketyp-fälten (identity/purpose/
strengths/blind_spots/style). Den har en egen mall:

```python
@dataclass
class CrystalProfile:
    crystal_id:   str            # slug, "labradorit"
    name:         str            # "Labradorit"
    chakra:       str            # vilket/vilka chakra
    element:      str            # jord/vatten/eld/luft/ande
    color:        str            # fysisk färg
    properties:   str            # egenskaper/verkan (tillskrivna)
    sees:         str            # vad den ser i en fråga (rådsröst)
    misses:       str            # vad den missar (rådsröst)
    voice:        str            # ton/stil när den talar
    symbol:       str = "◈"
    coherence:    float = 1.0
    researched_by: list[str] = field(default_factory=list)
```

`sees`/`misses`/`voice` gör profilen direkt användbar som rådsröst —
ingen separat översättning behövs. `chakra`/`element`/`color`/
`properties` gör den uppslagbar som faktabas. Samma post, två syften.

---

## B3 — Kristall-byggare (delar motor med Del A)

Samma flöde som `build_custom_archetype()`, men:
  - seed_type = "kristall"
  - research-prompt anpassad för stenar (nedan)
  - syntes till CrystalProfile istället för ArchetypeDraft
  - sparas i crystals-tabellen (nedan)

```python
def build_crystal(
    name:        str,
    interactive: bool = False,
) -> CrystalProfile
    # Cache först: finns kristallen redan i STONE? → returnera den.
    # Annars: research via zero_provider_exec → syntes → utkast.
    # Sparar INTE förrän approve_crystal().

def approve_crystal(profile: CrystalProfile) -> str
    # Sparar till crystals-tabellen. Enda vägen till persistens.

def get_crystal(name: str) -> CrystalProfile | None
    # Uppslag i faktabasen. None om ej researchad än.

def list_crystals() -> list[dict]
```

Research-prompt (per provider, fast_inference):

```
Beskriv kristallen {name} som rådsmedlem och uppslagspost.
Basera dig på allmänt känd kristall-tradition och egenskaper.

Ge:
  CHAKRA      — vilket/vilka energicentra
  ELEMENT     — jord/vatten/eld/luft/ande
  FÄRG        — fysisk färg
  EGENSKAPER  — tillskriven verkan och symbolik
  SER         — vad denna sten ser tydligt i en fråga
  MISSAR      — vad den är blind för
  RÖST        — hur den talar om den fick en röst (ton, längd)

Max 350 ord. Konkret. Ingen meta-text.
```

Cache-logiken är poängen: `build_crystal("ametist")` när ametist
redan finns (från CRYSTAL_COUNCIL) returnerar den befintliga profilen
direkt — researchas aldrig om i onödan. Store Then On-Need Extract.

---

## B4 — STONE-tabell

```sql
CREATE TABLE crystals (
    id            SERIAL PRIMARY KEY,
    crystal_id    TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    chakra        TEXT,
    element       TEXT,
    color         TEXT,
    properties    TEXT,
    sees          TEXT,
    misses        TEXT,
    voice         TEXT,
    prompt        TEXT NOT NULL,     -- destillerad rådsprompt (~120 tok)
    symbol        TEXT DEFAULT '◈',
    researched_by JSONB,
    coherence     FLOAT DEFAULT 1.0, -- de-resoneras, raderas aldrig
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
```

De sju förvalda kristallerna seedas hit vid första
`generate_archetypes()`-körningen så de är uppslagbara från start.

---

## B5 — Egna kristallråd (välj själv)

Utöver förvalda råd kan Frank sätta ihop ett eget:

```python
council_with_crystals(
    topic    = "...",
    crystals = ["ametist", "labradorit", "svart_turmalin"],
)
# Saknad kristall? → build_crystal() körs först, Frank godkänner,
# sedan ingår den i rådet. Nästa gång finns den redan.
```

Chat:

```
kristallråd ametist, labradorit, obsidian   → eget råd
kristall labradorit                          → bygg/slå upp en profil
kristaller                                   → list_crystals()
rådfråga [fråga] --kristaller                → förvalt CRYSTAL_COUNCIL
```

---

## B6 — Vad kristall-delen INTE gör

- Påstår aldrig medicinsk/terapeutisk verkan som faktum — kristallers
  egenskaper formuleras som tradition/symbolik, aldrig som hälsoråd
- Researchar aldrig om en kristall som redan finns i STONE (cache)
- Sparar aldrig en profil utan Franks godkännande
- Använder aldrig Ollama som research-provider

---

## B7 — Migrationssteg (efter Del A)

```
10. Skapa crystals-tabellen i STONE
11. CrystalProfile + build_crystal() (återanvänder _research_seed)
12. approve_crystal() + get_crystal() + cache-logik
13. Seeda de 7 förvalda + CRYSTAL_COUNCIL-preset
14. council_with_crystals() + chat-intents
15. Verifiera på Zero v2:
      rådfråga [fråga] --kristaller ✓   (förvalt råd)
      kristall labradorit ✓             (bygger + sparar)
      kristall ametist ✓                (cache-träff, ingen research)
      kristallråd ametist, labradorit ✓ (eget råd)
```

---

## Öppna frågor

1. Auto-klassificering av seed_type — egen lättviktig LLM-anrop eller
   regelbaserat (känd figur-lista)? Ej beslutat — börja med LLM-anrop.

2. Ska seed + research_notes sparas som proveniens (JSONB) för
   spårbarhet via zero_integrity.py? Ej beslutat — trolig ja, billigt.

3. Får en custom-arketyp ingå i auto-läget någonsin, eller alltid
   manuellt val (som Level 2/3)? Förslag: alltid manuellt — matchar
   befintlig regel. Ej beslutat.

4. Refresh av en custom-arketyp (kör om research) — egen funktion
   eller delgenerering via generate_archetypes()? Ej beslutat.

5. Kristall vs arketyp i samma råd — kan ett råd blanda en CrystalProfile
   (kristallmall) med en ArchetypeDraft (fem fält)? Syntesen klarar det,
   men ska det tillåtas? Förslag: ja, fritt. Ej beslutat.

---

*MAFP-tillägg v0.2 — utökar council_engine_MAFP.md*
*Del A: Arketypbyggaren (Level 3). Del B: Kristallråd (Level 2 + byggare).*
*Implementeras av Cursor/Aider mot full Zero-kodbas.*
*Förutsättning: council_engine Fas 1 (steg 0–13b) är implementerad.*
*Del B förutsätter Del A (delad genereringsmotor).*
*När implementerad: kör zero_spec_generator.py för orienterings-spec.*

*"What you put out is what you get back." — LAW 4*
