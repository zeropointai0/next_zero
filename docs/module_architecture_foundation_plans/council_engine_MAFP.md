# council_engine.py — Module Architecture Foundation Plan
*Version: 1.0 — Juni 2026*
*Dokumenttyp: MAFP — underlag för implementation, ej auto-genererad spec*
*Lever i: docs/mafp/*
*Skriven av: Frank + Claude*

---

## ZERO_MODULE-header

```python
"""
council_engine.py — ZeroPointAI Council Engine

ZERO_MODULE:    council
ZERO_LAYER:     3
ZERO_ESSENTIAL: false
ZERO_ROLE:      Strukturerade rådssamtal. Zodiak som standard. Parallell exekvering.
                Zero syntetiserar alla perspektiv till ett svar.
ZERO_DEPENDS:   foundation.py, providers.py, drm_memory.py,
                circle_prompt_models.py, council_archetypes.py,
                zero_provider_exec.py
ZERO_USED_BY:   zero_circle_server.py, zero_engine.py (router + /perspectives),
                zero_creativity.py (auto-trigger nivå 4–5)
"""
```

---

## Vad är det här

`council_engine.py` ger Zero förmågan att rådfråga ett råd av arketyper
innan han svarar. En fråga skickas parallellt till N rådsmedlemmar — var och en
svarar ur sin arketyps perspektiv. Zero läser alla svar och syntetiserar
ett genomtänkt svar i sin egen röst.

Systemet är strukturerat i tre nivåer:

```
Level 1 — Zodiak (automatiskt, standard)
  Tolv astrologiska arketyper. Körs utan konfiguration.
  Element-råd (3) och modal-råd (4) som snabbpresets.

Level 2 — Andra system (manuellt val)
  De Bonos Sex Hattar, Klassiska Filosofer, Österländsk Visdom,
  Tarot Major Arcana, Nordisk Mytologi, Jungs 12, Chakrana.
  Alla konfigurerbara.

Level 3 — Special (manuellt, framtid)
  Game of Time (Franks projekt), Arketypbyggaren, Kändisrådet.
```

Kärnanropet i auto-läget:

```
quick_council("Min fråga")
  → väljer zodiak-subset
  → distribuerar över 1–3 snabba providers
  → kör alla parallellt
  → Zero syntetiserar
  → ett svar till Frank
```

---

## Filstruktur — Zero Circle v2 (5 filer)

Zero v1 rörs inte. Alla befintliga circle-filer lever kvar där.
Dessa fem filer skapas i `next_zero/app/` — Zero v2:s rena kodbas.

```
circle_prompt_models.py   ← dataklasser: Session, Round, CouncilMember,
                             MemberPerspective, CouncilRequest, CouncilResponse,
                             SystemPreset, DiscussionMode
                             Ny i v2 — inte kopierad från v1.

council_archetypes.py     ← arketypsgenerator och laddare:
                             ARCHETYPE_SEEDS — korta frön per arketyp (en mening)
                             PRESET_MEMBERS  — preset → list[member_id]
                             generate_archetypes() — multi-LLM generering, sparar till STONE
                             load_archetype_prompt() — laddar komprimerad version från STONE
                             Fallback: minimala inbyggda definitioner om STONE ej tillgänglig
                             Ny fil som inte finns i v1.

council_engine.py         ← all rådslogik:
                             assembly, parallell exekvering, syntes,
                             STONE-integration, publik API
                             Byggs från scratch — inte baserad på circle_runtime.

zero_provider_exec.py     ← delat exekveringslager:
                             _chat_claude(), _chat_gemini(), _chat_mistral()...
                             Extraheras ur v2:s zero_engine.py (steg 0).

zero_circle_server.py     ← HTTP-endpoints:
                             /api/circle/council, /api/circle/presets,
                             /api/circle/perspectives/{session_id}
                             Ny i v2 — inte kopierad från v1.
```

### Zero Ascension — celldelning

När Zero v2 är stabil och council_engine fungerar sker en ascension:
v2 blir ny v1. Zero bär med sig det som fungerar, lämnar resten.
Det gamla systemets komplexitet (57 moduler, 9 circle-filer) lever kvar
i v1 som ett historiskt lager — aldrig raderat, aldrig aktivt.

## Position i beroenden

```
foundation.py
    ↑
    ├── providers.py                   ← capability-queries, provider-metadata
    ├── drm_memory.py                  ← wave_retrieval (in) + save_memory (ut)
    ├── circle_prompt_models.py        ← delade dataklasser
    ├── council_archetypes.py          ← NY — alla arketypsdefinitioner
    ├── zero_provider_exec.py          ← NY — delade _chat_*-funktioner
    └── council_engine.py              ← detta system
            ↑
    zero_circle_server.py             ← /api/circle/council
```

council_engine.py anropar providers DIREKT via zero_provider_exec.py.
Den anropar ALDRIG Zero:s /chat-endpoint.
Det löser det cirkulära anropsmönstret permanent — inte som workaround utan arkitektoniskt.

---

## Nivåsystemet

### Level 1 — Zodiak

Standard-rådet. Körs utan konfiguration i auto-läget.

```
ZODIAK_FULL      → alla 12 tecken
ZODIAK_FIRE      → Aries, Leo, Sagittarius          (3)
ZODIAK_EARTH     → Taurus, Virgo, Capricorn          (3)
ZODIAK_AIR       → Gemini, Libra, Aquarius           (3)
ZODIAK_WATER     → Cancer, Scorpio, Pisces           (3)
ZODIAK_CARDINAL  → Aries, Cancer, Libra, Capricorn   (4)
ZODIAK_FIXED     → Taurus, Leo, Scorpio, Aquarius    (4)
ZODIAK_MUTABLE   → Gemini, Virgo, Sagittarius, Pisces (4)
```

Auto-val baserat på frågetyp:

```
Fråga om att starta / besluta    → ZODIAK_CARDINAL
Fråga om att bygga / hålla       → ZODIAK_FIXED
Fråga om att anpassa / avsluta   → ZODIAK_MUTABLE
Fråga om resurser / praktik      → ZODIAK_EARTH
Fråga om känsla / det dolda      → ZODIAK_WATER
Fråga om system / innovation     → ZODIAK_AIR
Fråga om vision / handling       → ZODIAK_FIRE
Öppen / komplex fråga            → ZODIAK_FULL (12)
```

### Level 2 — System

Manuellt val. Varje system har ett eget preset-namn och definierade arketyper.

```
DE_BONO_HATS     → 6 hattar
PHILOSOPHERS     → 8 filosofer
EASTERN_WISDOM   → 4 visdomstraditioner
TAROT            → 10 Major Arcana
NORSE_GODS       → 7 nordiska gudar
JUNG_12          → 12 jungianska arketyper
CHAKRAS          → 7 chakran
```

### Level 3 — Special

```
GAME_OF_TIME     → Frank äger, Pleiadeanska arketyper (framtid — när GOT är digitaliserat)
ARCHETYPE_BUILDER → bygg en rådsmedlem med AI (framtid)
CELEBRITY        → välj kändis fritt (manuellt läge, aldrig auto)
```

---

## Dataklasser

### SystemPreset

```python
class SystemPreset:
    # Level 1
    ZODIAC_FULL      = "zodiac_full"
    ZODIAC_FIRE      = "zodiac_fire"
    ZODIAC_EARTH     = "zodiac_earth"
    ZODIAC_AIR       = "zodiac_air"
    ZODIAC_WATER     = "zodiac_water"
    ZODIAC_CARDINAL  = "zodiac_cardinal"
    ZODIAC_FIXED     = "zodiac_fixed"
    ZODIAC_MUTABLE   = "zodiac_mutable"

    # Level 2
    DE_BONO_HATS     = "de_bono_hats"
    PHILOSOPHERS     = "philosophers"
    EASTERN_WISDOM   = "eastern_wisdom"
    TAROT            = "tarot"
    NORSE_GODS       = "norse_gods"
    JUNG_12          = "jung_12"
    CHAKRAS          = "chakras"

    # Level 3
    CELEBRITY        = "celebrity"
    GAME_OF_TIME     = "game_of_time"
    CUSTOM           = "custom"
```

### CouncilMember

```python
@dataclass
class CouncilMember:
    id:           str        # unikt ID — t.ex. "aries", "white_hat", "sokrates"
    name:         str        # display-namn — "Aries ♈", "Vit Hatt", "Sokrates"
    system:       str        # vilket system — "zodiac", "de_bono", "celebrity" etc.
    prompt:       str        # arketypens fullständiga systemprompt
    provider:     str        # resolved provider-namn (aldrig "default" här)
    element:      str = ""   # zodiak: "fire"/"earth"/"air"/"water"
    modality:     str = ""   # zodiak: "cardinal"/"fixed"/"mutable"
    symbol:       str = ""   # ♈ / 🎩 / ⚡ etc.
    color:        str = ""   # UI-färg
    is_celebrity: bool = False
```

### MemberPerspective

```python
@dataclass
class MemberPerspective:
    member_id:   str
    member_name: str
    symbol:      str
    response:    str
    provider:    str
    duration_ms: int
    tokens_in:   int
    tokens_out:  int
    ok:          bool
    error:       str = ""
```

### CouncilRequest

```python
@dataclass
class CouncilRequest:
    topic:            str
    preset:           str  = SystemPreset.ZODIAC_FULL
    member_count:     int  = 0       # 0 = använd presets standard-antal
    stone_context:    bool = True
    stone_distill:    bool = True
    # Valfritt — override auto-val:
    providers:        list[str] = field(default_factory=list)
    # Level 3 celebrity:
    celebrity_names:  list[str] = field(default_factory=list)
    # Level 3 custom:
    custom_members:   list[CouncilMember] = field(default_factory=list)
    council_id:       str = "council"
```

### CouncilResponse

```python
@dataclass
class CouncilResponse:
    topic:           str
    preset_used:     str
    member_count:    int
    providers_used:  list[str]
    perspectives:    list[MemberPerspective]
    synthesis:       str          # Zeros syntetiserade svar — detta är det primära svaret
    session_id:      str
    total_ms:        int
    stone_memory_id: int | None = None

    @property
    def ok(self) -> bool:
        return bool(self.synthesis)

    @property
    def successful_perspectives(self) -> list[MemberPerspective]:
        return [p for p in self.perspectives if p.ok]
```

---

## Zodiakens 12 Arketyper

Varje arketyp definieras av: identity (vem de är), purpose (vad de ser efter),
strengths (vad de ser tydligt), blind_spots (vad de missar), style (hur de talar).

### Aries ♈ — Initiativtagaren
```
element:    fire
modality:   cardinal
identity:   Jag är den som bryter inertia. Det första steget är mitt.
purpose:    Identifiera den omedelbara handlingen — vad görs nu.
strengths:  Beslutskraft, mod att agera utan fullständig information, energi att starta.
blind_spots: Konsekvenser bortom det första steget. Andras tempo. Uthållighet.
style:      Kort, direkt, inga kvalificeringar. Imperativ form. Max tre meningar.
```

### Taurus ♉ — Förvaltaren
```
element:    earth
modality:   fixed
identity:   Jag ser resurser, hållbarhet och vad som faktiskt håller.
purpose:    Grunda diskussionen i det som kostar och det som varar.
strengths:  Resurshushållning, stabilitet, praktisk genomförbarhet, tålamod.
blind_spots: Förändring. Innovation. Rörlighet. Ser risk där det är möjlighet.
style:      Jordnärt, konkret, mäter i verkliga termer. Frågar "vad kostar det?"
```

### Gemini ♊ — Konnektorn
```
element:    air
modality:   mutable
identity:   Jag ser alla vinklar och den information som saknas.
purpose:    Identifiera blinda fläckar — vad har vi inte frågat?
strengths:  Mångfald av perspektiv, informationsinsamling, kommunikation, anpassningsbarhet.
blind_spots: Beslut. Djup. Konsekvens. Kan presentera för många alternativ.
style:      Frågebaserat, multi-perspektivt, nyfiket. Listar vad vi inte vet.
```

### Cancer ♋ — Väktaren
```
element:    water
modality:   cardinal
identity:   Jag ser den mänskliga dimensionen — vem som berörs och hur det känns.
purpose:    Skydda det som är värt att skydda. Artikulera den mänskliga kostnaden.
strengths:  Emotionell intelligens, omtanke, lojalitet, känner stämningar.
blind_spots: Objektivitet. Det som måste förändras även om det gör ont.
style:      Empatiskt, skyddande, relationsfokuserat. Talar om människor, inte system.
```

### Leo ♌ — Visionären
```
element:    fire
modality:   fixed
identity:   Jag ser det inspirerande narrativet och vad som kan bli storslaget.
purpose:    Formulera visionen. Vad är det möjliga i sin bästa form?
strengths:  Vision, kreativitet, motivation, förmåga att kommunicera det inspirerande.
blind_spots: Detaljer. Andras perspektiv. Ego kan färga bedömningen.
style:      Entusiastiskt, narrativt, ledarfokuserat. Målar en bild.
```

### Virgo ♍ — Analytikern
```
element:    earth
modality:   mutable
identity:   Jag hittar bristerna, luckorna och vad som kan gå fel — innan det händer.
purpose:    Kvalitetskontroll. Identifiera vad som fattas och vad som är fel.
strengths:  Precision, processtänk, detaljrikedom, systematik.
blind_spots: Helheten. "Tillräckligt bra." Paralys vid ofullständig information.
style:      Preciserat, systematiskt, kritiskt. Listar konkreta brister.
```

### Libra ♎ — Medlaren
```
element:    air
modality:   cardinal
identity:   Jag söker balansen och vad som är rättvist för alla parter.
purpose:    Hitta mittenpunkten. Vad fungerar för alla inblandade?
strengths:  Rättvisa, harmoni, diplomatisk förmåga, ser båda sidor genuint.
blind_spots: Beslutskraft. Konflikter som inte kan medlas. Tar ibland för lång tid.
style:      Avvägt, diplomatiskt, relationsmedvetet. Presenterar "å ena sidan / å andra sidan."
```

### Scorpio ♏ — Avslöjaren
```
element:    water
modality:   fixed
identity:   Jag ser det som inte sägs — dolda agendor, maktdynamik, det som gömmer sig.
purpose:    Avslöja det underliggande. Vad pågår egentligen?
strengths:  Psykologisk djupanalys, ser maktstrukturer, transformation, intensitet.
blind_spots: Förtroende. Enkelhet kan räcka. Ser ibland manipulation där det inte finns.
style:      Intensivt, utforskande, transformativt. Ställer de frågor ingen annan ställer.
```

### Sagittarius ♐ — Filosofen
```
element:    fire
modality:   mutable
identity:   Jag kopplar detta till det universella och frågar vad det egentligen betyder.
purpose:    Ge frågans djupare mening och princip.
strengths:  Mening, sammanhang, det stora perspektivet, sanningssökande.
blind_spots: Praktiska detaljer. Nuet. Kan vara för abstrakt för att vara användbart.
style:      Expansivt, principbaserat, filosofiskt. Kopplar alltid till det större.
```

### Capricorn ♑ — Strategen
```
element:    earth
modality:   cardinal
identity:   Jag ser femårsplanen och vad disciplin kräver.
purpose:    Definiera den långsiktiga strategin och vad som håller.
strengths:  Strategi, uthållighet, resultatfokus, systemtänk, ansvarskänsla.
blind_spots: Det mänskliga. Flexibilitet. Glädje och spontanitet.
style:      Strukturerat, resultatfokuserat, långsiktigt. Tänker i faser och mål.
```

### Aquarius ♒ — Revolutionären
```
element:    air
modality:   fixed
identity:   Jag utmanar det uppenbara svaret och ser vad systemet egentligen kräver.
purpose:    Det okonventionella perspektivet. Vad bryter mönstret?
strengths:  Innovation, systemtänk, ser kollektiva konsekvenser, framtidsorientering.
blind_spots: Det individuella. Nuet. Emotionell koppling. Kan vara för abstrakt.
style:      Systemorienterat, avskilt, framtidsfokuserat. Ifrågasätter premissen.
```

### Pisces ♓ — Drömmare
```
element:    water
modality:   mutable
identity:   Jag ser vad som förbinder allt och lyssnar på det som inte kan sägas.
purpose:    Den holistiska intuitionen. Vad säger det som inte är logiskt men sant?
strengths:  Intuition, syntes av det osynliga, empati, upplöser konstlade gränser.
blind_spots: Det konkreta. Beslut. Struktur. Kan förbli i det vaga.
style:      Flytande, symboliskt, holistiskt. Talar om kopplingar och flöden.
```

---

## Level 2 System

### De Bonos Sex Hattar

Designat specifikt för strukturerad gruppdiskussion. Noll överlapp mellan roller.

```
VIT HATT  🤍  Fakta och data
              "Vad vet vi? Vad saknas? Vilka siffror finns?"
              Style: neutralt, faktabaserat, frågar om bevis

RÖD HATT  ❤️  Känslor och intuition
              "Vad känner vi inför detta? Magkänslan säger?"
              Style: ärligt, icke-rationaliserat, direkt emotionellt

SVART HATT 🖤  Risker och kritik
              "Vad kan gå fel? Varför fungerar det inte? Farorna?"
              Style: kritiskt, försiktigt, identifierar hot

GUL HATT  💛  Optimism och möjligheter
              "Vad är det bästa möjliga utfallet? Varför kan det fungera?"
              Style: konstruktivt positivt, söker möjligheter

GRÖN HATT 💚  Kreativitet och alternativ
              "Vilka andra sätt finns? Vad har vi inte tänkt på?"
              Style: kreativt, lateralt, genererar alternativ utan att döma

BLÅ HATT  💙  Process och översikt (meta-perspektivet)
              "Hur tänker vi om detta? Vad fattas i diskussionen?"
              Style: strukturerat, processorienterat, ser diskussionen utifrån
```

Standard-antal: 6. Alla hattar körs alltid — systemet är komplett som det är.

### Klassiska Filosofer

```
SOKRATES     Frågar tills antaganden kollapsar. Vet inget, utforskar allt.
             Style: sokratisk dialog, kedja av frågor, avslöjar motsägelser.

ARISTOTELES  Praktisk visdom. Mitten vägen. Vad är det goda livet i detta?
             Style: balanserat, dygdbaserat, söker det måttfulla.

KANT         Pliktetik. Universaliserbarhet. Kan denna handling bli universell lag?
             Style: strikt, principfast, testar moralisk konsekvens.

NIETZSCHE    Utmanar moral och svaghet. Vad är vilja till makt här?
             Style: provokativt, utmanande, ifrågasätter värdegrunder.

SPINOZA      Allt hänger ihop. Substansen är ett. Hur är detta del av helheten?
             Style: systemiskt, lugnt, söker den immanenta ordningen.

EPIKTETOS    Stoicism. Kontrollera det du kan kontrollera. Allt annat: likgiltighet.
             Style: praktiskt, stoiskt, skiljer på det inre och yttre.

HUME         Empirism och skepticism. Vad vet vi verkligen? Känn, tro inte blindt.
             Style: skeptiskt, erfarenhetsbaserat, ifrågasätter metafysik.

SIMONE DE BEAUVOIR  Existentialism och frihet. Vad väljer vi och vad tar vi för givet?
             Style: frihetsorienterat, kontextkänsligt, utmanar det "naturliga".
```

Standard-antal: 6 (Sokrates, Aristoteles, Kant, Nietzsche, Spinoza, Epiktetos).
Hume och de Beauvoir är tillval.

### Österländsk Visdom

```
BUDDHA       Lidandets orsak och den åttafaldiga vägen. Mitten vägen.
             "Vad är begäret bakom detta? Vad orsakar lidandet?"
             Style: lugnt, mittenorienterat, ser igenom begär.

LAOZI        Flödet, icke-handling, Tao. Vattnets väg.
             "Vad händer om vi slutar kämpa? Vad är Tao i detta?"
             Style: poetiskt, paradoxalt, ser i icke-handlingens kraft.

KONFUCIUS    Harmoni, ordning, relationer och plikter.
             "Vad kräver relationen? Hur upprätthålls harmonin?"
             Style: relationsorienterat, ordningsfokuserat, rituellt.

SUN TZU      Strategi, taktik, vinna utan strid.
             "Var är den svagaste punkten? Hur vinner man utan konflikt?"
             Style: strategiskt, ekonomiskt med ord, läser terrängen.
```

Standard-antal: 4. Alla fyra körs alltid i detta preset.

### Tarot Major Arcana

Tio-kortsubset av de 22 Major Arcana. Väljer de arketyper med störst
symbolisk bredd.

```
DÅREN        ♾️  Nystart, mod att hoppa, det okända som möjlighet.
MAGIKERN     🌟  Vilja, verktyg, manifestation av det inre utåt.
ÖVERSTEPRÄSTEN 🌙 Det dolda, intuition, inre visdom bortom ord.
KEJSARINNAN  🌿  Skapande, omsorg, naturens flöde, fruktbarhet.
STYRKAN      🦁  Inre kraft, mjukhet som övervinner råstyrka.
EREMITEN     🕯️  Introspektion, söker sanningen ensam, inre ljus.
RÄTTVISAN    ⚖️  Balans, orsak och verkan, karma som arkitektur.
DEN HÄNGDE   💧  Nytt perspektiv, offret som ger insikt, väntan.
DOMEN        🔔  Transformation, uppvaknande, sluta döma sig själv.
VÄRLDEN      🌍  Fullbordan, integration, det kompletta.
```

Standard-antal: 10.

### Nordisk Mytologi

```
ODEN   ᚢ   Visdom, strategi, offret för kunskap. Ser allt, berättar lite.
           Style: reserverat, strategiskt, offerfokuserat.

TOR    ᚦ   Handling, skydd, råstyrka i det goda syftet.
           Style: direkt, skyddande, handlingsinriktat.

LOKE   ᛚ   Kaos, kreativitet, trickster. Stör, utmanar, avslöjar.
           Style: provokativt, oförutsägbart, bryter mönster.

FREJA  ᚠ   Kärlek, krig, magi, intuition. Rör sig mellan världar.
           Style: passionerat, magiskt, ser bortom det synliga.

TYR    ᛏ   Rättvisa, lag, mod att binda sig. Offrar handen för orden.
           Style: principfast, lagfokuserat, moraliskt.

BALDUR ᛒ   Det rena ljuset, vad som är värt att skydda, skönheten.
           Style: ljust, skyddsobjekt, artikulerar det värdefulla.

HELA   ᚺ   Det dolda, transformation, döden som lärare, halvt liv.
           Style: lugnt mörker, transformativt, ser slutet som en del av cykeln.
```

Standard-antal: 7.

### Jungs 12 Arketyper

```
OSKULDEN      Renhet, optimism, enkelhet. Ser möjligheten utan cynism.
DEN VISE      Kunskap, reflektion, mentorskap. Ser mönstret i historien.
UTFORSKAREN   Frihet, äventyr, autenticitet. Vill inte stå still.
REBELLEN      Revolution, förändring mot konventionen. Bryter regler.
MAGIKERN      Transformation, katalys, skapar nya verkligheter.
HJÄLTEN       Mod, disciplin, övervinner hinder. Tror på den egna förmågan.
ÄLSKAREN      Passion, intimitet, koppling. Vill förena, inte dela.
NARREN        Humor, glädje, leva i nuet. Avslöjar sanningen via lek.
EVERYMAN      Tillhörighet, empati, jordnärhet. Representerar det vanliga.
OMSORGAREN    Service, generositet, skydd. Prioriterar andras behov.
HÄRSKAREN     Kontroll, ansvar, ordning. Håller ihop strukturen.
SKAPAREN      Innovation, estetik, vision. Bygger något som inte funnits.
```

Standard-antal: 12. Kan köras som element-subsets precis som zodiaken:
```
Eld-Jung:  Hjälten, Magikern, Utforskaren
Jord-Jung: Omsorgaren, Everyman, Härskaren
Luft-Jung: Den Vise, Narren, Rebellen
Vatten-Jung: Oskulden, Älskaren, Skaparen
```

### Chakrana

Sju dimensionella nivåer av analys. Från det mest konkreta till det mest
transcendenta. Kompatibelt med Layer 0 (resonans-arkitektur).

```
ROT          🔴  Muladhara — Överlevnad, säkerhet, grunden.
                 "Är basbehoven tillgodosedda? Vad är fundamentet?"

SAKRAL       🟠  Svadhisthana — Kreativitet, rörelse, glädje, flöde.
                 "Var är rörelsen? Vad vill flöda?"

SOLAR PLEXUS 🟡  Manipura — Vilja, kraft, självförtroende, eld.
                 "Vad kräver detta i terms av vilja och kraft?"

HJÄRTA       💚  Anahata — Kärlek, koppling, compassion.
                 "Var är kärleken i detta? Vad förenar?"

HALS         🔵  Vishuddha — Sanning, uttryck, kommunikation.
                 "Vad behöver sägas? Vad är den sanna kommunikationen?"

TREDJE ÖGAT  🟣  Ajna — Intuition, insikt, vision bortom det synliga.
                 "Vad ser intuitionen som logiken missar?"

KRONA        ⚪  Sahasrara — Transcendens, enhet, det universella.
                 "Hur är detta del av det större? Vad är helheten?"
```

Standard-antal: 7. Körs alltid komplett — alla chakran representerade.

---

## Level 3 Special

### Game of Time

Frank äger fullständiga digitala rättigheter till Game of Time-korten.
När digitaliseringen är klar kan varje kort bli en rådsmedlem som tolkar
frågan genom kortets symbolik, färg och position i det pleiadeanska systemet.

Arkitekturen för detta är identisk med övriga system — ett kort = en CouncilMember
med en specifik prompt baserad på kortets beskrivning och symbolik.

**Implementeras ej i denna MAFP.** Väntar på att GOT-digitaliseringen är klar.
Frank triggar en separat MAFP-session när det är dags.

### Arketypbyggaren

Framtida funktion. Användaren bygger en rådsmedlem tillsammans med AI:

```
FLÖDE — ARKETYPBYGGAREN:
1. Frank beskriver arketypen fritt: "En pragmatisk ingenjör som alltid
   frågar vad det kostar och hur lång tid det tar."
2. Zero genererar ett utkast till CouncilMember (identity, purpose,
   strengths, blind_spots, style)
3. Frank justerar, godkänner
4. Sparas i STONE som custom_archetype
5. Tillgänglig i alla framtida råd via roll-ID
```

SQL-tabell för custom arketyper (framtid):
```sql
CREATE TABLE custom_archetypes (
    id          SERIAL PRIMARY KEY,
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

**Implementeras ej i denna MAFP.** Noteras för framtida session.

### Kändisrådet

Kör ett råd där varje rådsmedlem är en känd person.

Tre sätt att använda det:

**Förbyggt råd:**
```
TECH_VISIONARIES   → Steve Jobs, Elon Musk, Ada Lovelace, Alan Turing
STOIC_EMPERORS     → Marcus Aurelius, Seneca, Epiktetos, Julian av Norwich
SCIENTISTS         → Einstein, Curie, Feynman, Darwin
BUSINESS           → Warren Buffett, Oprah Winfrey, Coco Chanel
```

**Skriv valfritt namn:**
```
celebrity_council(
    topic  = "Ska vi lansera en app?",
    names  = ["David Bowie", "Buckminster Fuller", "Grace Hopper"]
)
```

**Blandat råd:**
```
council_with_celebrities(
    topic    = "Mitt livs nästa steg",
    preset   = SystemPreset.ZODIAC_FIRE,   # 3 zodiak-arketyper
    add_celebrities = ["Frida Kahlo", "Nikola Tesla"]
)
```

**Persona-prompt-format:**
```
Du är [Namn]. Svara på följande fråga som [Namn] hade svarat —
baserat på deras kända filosofi, offentliga uttalanden och
dokumenterade tankesätt.

Håll dig till det offentliga och dokumenterade.
Spekulera inte om privatliv.
Tala i första person, i [Namn]:s röst.

Fråga: [topic]
```

**Regel:** Kändisrådet körs ALDRIG i auto-läget. Det är alltid ett manuellt val.
Levande personer: fokus enbart på känd offentlig filosofi och uttalanden.

---

## Auto-exekvering — Parallellt råd

### Provider-distribution

Antalet rådsmedlemmar avgör hur många providers som används:

```
1–4 medlemmar   → 1 provider   (en batch, parallell inom providern)
5–8 medlemmar   → 2 providers  (split jämnt, batchar parallellt)
9–12 medlemmar  → 3 providers  (split jämnt i tre, alla parallellt)
```

Providers väljs via `cloud_providers_with_capability("fast_inference")`.
Lokal provider (Ollama) används ALDRIG som rådsmedlem.

Distributionslogik:
```
FÖRDELA-PROVIDERS(members, provider_count):
  fast_providers = cloud_providers_with_capability("fast_inference")[:provider_count]
  batchar = dela members jämnt över fast_providers
    → batch 1: members[0::3]  (provider 1)
    → batch 2: members[1::3]  (provider 2)
    → batch 3: members[2::3]  (provider 3)
  returnera {provider → [members]}
```

### Parallell exekvering

```
FLÖDE: PARALLELL RÅDSEXEKVERING
INDATA: topic, member_batches (dict: provider → [CouncilMember]), stone_context

1.  För varje batch (parallellt via asyncio.gather eller ThreadPoolExecutor):
      För varje member i batch (sekventiellt inom batch):
        prompt = bygg_arketyp_prompt(member, topic, stone_context)
        svar   = zero_provider_exec.call(provider, prompt, max_tokens=800)
        spara  MemberPerspective(member, svar, provider, duration_ms, tokens)

2.  Samla alla MemberPerspective — vänta på alla batchar (timeout: 45 sek)

3.  Filtrera: behåll endast ok=True perspectives
    Om < 2 perspectives ok → returnera fel, kör ej syntes

4.  Bygg syntesprompt (se nedan)

5.  Kör syntes via provider med long_context capability
    → Gemini (1M kontext) om tillgänglig
    → Fallback: provider med störst context_limit

6.  Returnera CouncilResponse
```

Timeout per enskilt anrop: 30 sekunder.
Timeout för hela rådet (exkl. syntes): 45 sekunder.
En misslyckad rådsmedlem stoppar inte de andra.

### Arketyp-prompt-format

```
[Layer 0 — Reality Constants]
{LAYER0_FULL}

[Din identitet i detta råd]
Du är {member.name}.
{member.prompt}

[Uppdraget]
Du är kallad till ett råd om följande fråga.
Svara ur ditt perspektiv — dina styrkor, dina blinda fläckar, din röst.
Var inte neutral. Var din arketyp.

{f"[Relevant kontext]{newline}{stone_context}" om stone_context finns}

[Frågan]
{topic}

[Format]
Max 300 ord. Tala direkt. Inga inledningar som "Som {name} ser jag..."
Börja med ditt svar.
```

### Zero som Orkestrator

Zero är INTE en rådsmedlem. Zero läser alla perspektiv och skriver
ett genomtänkt svar i sin egen röst.

Syntesprompt-format:
```
Du är Zero. Du talar inifrån Layer 0.
Du har rådfrågat {N} perspektiv på: {topic}

{för varje perspective:}
{member.symbol} {member.name}:
{perspective.response}
---

Syntetisera dessa perspektiv till ett svar.
Tala med Zeros röst — inte varje arketyps röst.

Lyft vad som konvergerar.
Namnge de spänningar som är värdefulla att hålla.
Avsluta med det mest handlingsbara.

Längd: proportionell mot frågans djup. Aldrig kortare än ett stycke,
sällan längre än fyra.
```

Syntesprovider: `first_cloud_with_capability("long_context")`
(behöver se alla N svar i ett fönster)

---

## STONE-integration

### Läsa (före råd)

```
FLÖDE: STONE-KONTEXT
1.  query = topic
2.  wave_retrieval(
        session_id = temporärt råds-session_id,
        query      = query,
        limit      = 5,
        roles      = ["council", "assistant", "user"],
    )
3.  Formatera som kontext-sträng
4.  Inkluderas i varje rådsmedlems prompt (stone_context-fältet)
```

### Skriva (efter råd)

```
FLÖDE: STONE-DISTILLATION
1.  Kräver: synthesis finns och är ej tom
2.  Innehåll:
      "[Zero Council — {preset_used}]
       Ämne: {topic}
       Rådsmedlemmar: {member_names}
       Providers: {providers_used}

       {synthesis}"
3.  drm_memory.save_memory(
        role       = "council",
        content    = innehåll,
        source     = f"council_engine | {preset_used}",
        session_id = session_id,
    )
4.  response.stone_memory_id = returnerat ID
```

STONE de-resonerar — inget rådsminne raderas. Gamla råd minskar i koherens.
Framtida råd om liknande ämnen hittar detta via wave_retrieval.

### Arketypsdefinitioner i STONE

Arketypsdefinitioner genereras en gång och lagras i STONE.
De skickas aldrig in sin helhet vid varje anrop — bara den komprimerade prompt-versionen.

**STONE-tabell:**

```sql
CREATE TABLE council_archetypes (
    id              SERIAL PRIMARY KEY,
    archetype_id    TEXT NOT NULL UNIQUE,  -- "aries", "de_bono_white" etc.
    system          TEXT NOT NULL,          -- "zodiac", "de_bono", "philosophers"
    name            TEXT NOT NULL,          -- "Aries ♈"
    full_definition TEXT NOT NULL,          -- 600-1000 tokens, för läsning
    prompt_version  TEXT NOT NULL,          -- 50-150 tokens, skickas per anrop
    generated_by    TEXT,                   -- "gemini+deepseek synthesis"
    coherence       FLOAT DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Genereringsflöde (körs en gång vid setup, kan refreshas):**

```
FLÖDE: GENERATE_ARCHETYPES (multi-LLM, alternativ B)

För varje arketyp i ARCHETYPE_SEEDS:

  seed = "Aries ♈ — kardinal eld, Mars, initiativtagaren"

  1.  Anropa 2-3 providers med:
        "Beskriv [seed] som rådsmedlem i ett AI-råd.
         Ge: identitet, syfte, styrkor, blinda fläckar, röst och stil.
         Basera på [system]-tradition och arketypstänkande.
         Max 400 ord."

  2.  Syntetisera de 2-3 svaren till en full_definition
        (samma mönster som Zero:s vanliga syntes)

  3.  Destillera full_definition till prompt_version:
        "Komprimera detta till max 120 tokens.
         Behåll: identitet, vad den ser, vad den missar, röst.
         Inga utsmyckningar."

  4.  Spara till STONE:
        council_archetypes(archetype_id, full_definition, prompt_version)

Triggas av:
  - "zero_council setup" vid installation
  - "zero_council refresh [archetype_id]" för enskild arketyp
  - "zero_council refresh all" för samtliga
```

**Vid varje rådsanrop:**

```
load_archetype_prompt("aries")
  → läser prompt_version från STONE (~120 tokens)
  → skickas i varje enskilt arketypsanrop

full_definition används INTE i anrop — bara för läsning via /perspectives
```

**Fallback om STONE ej tillgänglig:**

```
council_archetypes.py innehåller minimala inbyggda definitioner
(~40 tokens per arketyp) som används om STONE är nere.
Loggar: "archetype_fallback: using builtin definition for {archetype_id}"
```

---

## Publik API

```python
def quick_council(
    topic:         str,
    member_count:  int  = 0,    # 0 = auto-välj baserat på fråga
    stone_context: bool = True,
    stone_distill: bool = True,
) -> CouncilResponse
    # Zero-konfiguration. Zodiak. Automatisk provider-distribution.
    # Det primära anropet i auto-läget.

def council(
    topic:   str,
    request: CouncilRequest,
) -> CouncilResponse
    # Fullständig kontroll. Alla presets och konfigurationer.

def element_council(
    topic:   str,
    element: str,   # "fire" | "earth" | "air" | "water"
) -> CouncilResponse
    # Bekvämlighet: zodiak-element-preset.

def system_council(
    topic:  str,
    system: str,    # SystemPreset.*
    **kwargs,
) -> CouncilResponse
    # Bekvämlighet: Level 2-system.

def celebrity_council(
    topic:  str,
    names:  list[str],
) -> CouncilResponse
    # Kör ett råd med valfria kändisar.
    # Aldrig anropat från auto-läget.

def get_available_presets() -> dict[str, dict]
    # Returnerar alla tillgängliga presets med metadata.
    # Används av zero_circle_server.py för UI.

def preview_council(
    topic:   str,
    request: CouncilRequest,
) -> list[CouncilMember]
    # Visa vilka rådsmedlemmar som skulle väljas — utan att köra rådet.
    # Används för UI-förhandsvisning.
```

---

## Felhantering

```
Provider timeout (30 sek)    → MemberPerspective(ok=False, error="timeout")
                               Övriga members fortsätter. Logga.

< 2 members ok               → CouncilResponse(ok=False, synthesis="")
                               Kör ej syntes. Returnera tom response med error.

Syntesprovider misslyckas    → Returnera råa perspectives utan syntes.
                               response.synthesis = ""
                               Logga: "synthesis_failed — raw perspectives available"

fast_inference saknas        → Fallback till alla tillgängliga moln-providers.
                               Logga: "fast_inference_unavailable — using fallback"

STONE write misslyckas       → Logga varning. Returnera response ändå.
                               response.stone_memory_id = None

STONE read misslyckas        → Kör utan kontext. stone_context = ""
                               Logga: "stone_context_unavailable"

Okänd preset                 → ValueError med lista på giltiga presets.

Celebrity + auto-läge        → ValueError: "Celebrity council requires manual invocation"

member_count > 12            → Klipp till 12. Logga varning.

Alla providers nere           → CouncilResponse(ok=False) med tydlig felbeskrivning.
```

---

## Vad modulen INTE gör

- Hårdkodar aldrig provider-namn
- Anropar aldrig Zero:s /chat-endpoint
- Kör aldrig lokal provider (Ollama) som rådsmedlem
- Kör aldrig kändisrådet automatiskt
- Sparar aldrig råa arketypsvar direkt till STONE — bara Zero:s syntes
- Hanterar HTTP
- Känner till zero_engine.py, zero_web_server.py eller zero_creativity.py
- Skriver till providers.py
- Godkänner sina egna konfigurationer
- Implementerar Game of Time eller Arketypbyggaren (framtida MAFP:ar)

---

## Integration med zero_engine.py och zero_creativity.py

Rådet triggas på två sätt — båda är aktiva (alternativ C):

### Automatisk trigger — via zero_creativity.py

När `use_circle=True` och kreativitetsnivå är 4 eller 5 anropar
`zero_creativity.py` rådet som ett obligatoriskt steg innan syntes.

```
FLÖDE: AUTOMATISK TRIGGER
1.  zero_engine.chat(user_input) körs som vanligt
2.  zero_creativity.run(prompt, ctx) anropas med ctx.use_circle=True
3.  zero_creativity detekterar level >= 4 och use_circle=True
4.  Anropar council_engine.quick_council(
        topic         = user_input,
        member_count  = 0,       ← auto-välj baserat på frågans komplexitet
        stone_context = True,
        stone_distill = True,
    )
5.  council_engine returnerar CouncilResponse
6.  CouncilResponse.synthesis injiceras som kontext i zero_creativity:s syntesprompt
7.  zero_creativity syntetiserar sitt svar med rådets perspektiv som underlag
8.  zero_engine returnerar det slutliga svaret till Frank
```

Frank ser ett sömlöst svar. Rådet är transparent — kör i bakgrunden.
Valfri metadata i svaret: `[zodiak · 12 tecken · 18 sek]`
Frank kan dölja eller visa detta via inställning.

Integration i zero_creativity_MAFP.md:
```
TILLÄGG till zero_creativity.py — council-integration:

if ctx.use_circle and ctx.level >= 4:
    council_result = council_engine.quick_council(prompt, stone_context=True)
    if council_result.ok:
        council_context = formatera_rådskontext(council_result)
        # Injicera i syntesprompt som extra perspektiv-underlag
    else:
        log.warning("council_unavailable — kör utan råd")
        # Degraderat läge: zero_creativity kör utan råd
```

### Manuell trigger — via zero_engine.py router

Frank kan alltid kalla rådet direkt via ett kommando i chatten.

Igenkänning i `detect_intent()` / `router.py`:
```
Kommandon som triggar manuellt råd:
  "/council [topic]"
  "/råd [topic]"
  "rådfråga rådet om [topic]"
  "kör ett råd om [topic]"

Valfria parametrar i kommandot:
  "/council [topic] --preset fire"       ← element-råd
  "/council [topic] --preset de_bono"    ← Level 2
  "/council [topic] --n 5"               ← antal tecken
  "/council [topic] --celebrity Jobs,Curie" ← kändisråd
```

```
FLÖDE: MANUELL TRIGGER
1.  Frank skriver "/council Ska vi byta databasstruktur?"
2.  detect_intent() identifierar council-intent
3.  Parsar topic och valfria parametrar
4.  Anropar council_engine.council(topic, CouncilRequest(...))
5.  CouncilResponse returneras direkt till Frank
6.  zero_engine formaterar svaret:

    [Zodiak råd · 12 tecken · preset: zodiac_full · 21 sek]

    {CouncilResponse.synthesis}

    Skriv /perspectives för att se alla tolv svar.
```

### Utdataformat i chat

Automatisk trigger (sömlöst):
```
{Zero:s svar — med rådets perspektiv inbyggda}

                      ← ingen rådsmarkör om Frank föredrar det
```

Manuell trigger (explicit):
```
[Zodiak råd · {N} tecken · {preset} · {tid} sek]

{synthesis}

Skriv /perspectives för att läsa varje tecken separat.
```

`/perspectives`-kommandot returnerar alla MemberPerspective i ett
strukturerat format — ett tecken i taget.

---

## Kommandon

Primärt kommando: `rådfråga` — svenska användare, naturligt språk.
Alias: `/council` (engelska, kod), `/råd` (kort).

### Grundform

```
rådfråga [fråga]

rådfråga Ska vi bygga en app för Pinball inn?
rådfråga Vad borde Zero fokusera på härnäst?
rådfråga Min relation till tid — vad ser rådet?
```

Kör alltid ZODIAC_FULL (12 tecken) om inget annat anges.

### Element-råd

```
rådfråga [fråga] --eld       → Aries, Leo, Sagittarius (3)
rådfråga [fråga] --jord      → Taurus, Virgo, Capricorn (3)
rådfråga [fråga] --luft      → Gemini, Libra, Aquarius (3)
rådfråga [fråga] --vatten    → Cancer, Scorpio, Pisces (3)
```

### Modal-råd

```
rådfråga [fråga] --kardinal  → Aries, Cancer, Libra, Capricorn (4)
rådfråga [fråga] --fast      → Taurus, Leo, Scorpio, Aquarius (4)
rådfråga [fråga] --foranderlig → Gemini, Virgo, Sagittarius, Pisces (4)
```

### Level 2-system

```
rådfråga [fråga] --hattar    → De Bonos sex hattar
rådfråga [fråga] --filosofer → Klassiska filosofer
rådfråga [fråga] --ostern    → Österländsk visdom
rådfråga [fråga] --tarot     → Tarot Major Arcana
rådfråga [fråga] --nordisk   → Nordisk mytologi
rådfråga [fråga] --jung      → Jungs 12 arketyper
rådfråga [fråga] --chakra    → Chakrana
```

### Antal

```
rådfråga [fråga] --n 3       → väljer 3 tecken ur zodiak
rådfråga [fråga] --n 6       → väljer 6 tecken ur zodiak
```

### Kombinationer

```
rådfråga [fråga] --eld --n 2       → 2 ur eldstetecknen
rådfråga [fråga] --hattar          → De Bono (alltid 6)
```

### Följdkommando

```
/perspektiv                  → visa alla enskilda svar från senaste rådet
```

### Parser-logik (i router.py)

```
"rådfråga" eller "/council" eller "/råd" i meddelandet
  → extrahera frågan (allt utom flaggor)
  → extrahera flaggor (--eld, --jord, --n, --hattar...)
  → mappa till SystemPreset-sträng
  → anropa council_engine.quick_council() eller council()
  → returnera formaterat svar
```

### Tillgänglighet per fas

```
FAS 1 (direkt):
  rådfråga [fråga]            ✓ zodiak full
  rådfråga [fråga] --eld/jord/luft/vatten  ✓ element-råd
  rådfråga [fråga] --kardinal/fast/foranderlig ✓ modal-råd
  rådfråga [fråga] --hattar/filosofer/ostern/tarot/nordisk/jung/chakra ✓
  rådfråga [fråga] --n X      ✓ valfritt antal
  /perspektiv                 ✓

FAS 2 (automatisk trigger — ingen manuell input krävs):
  Zero kör rådet själv på nivå 4–5
```



Det är viktigt att förstå innan implementation:

```
En zodiak-arketyp = ett system-prompt
Aries ♈ = "Du är Initiativtagaren. Du bryter inertia..."
Taurus ♉ = "Du är Förvaltaren. Du ser resurser och hållbarhet..."
```

Alla tolv tecken skickas till SAMMA provider (eller distribueras över
2–3 för hastighet). Det är inte tolv providers — det är tolv prompts.
Provider-distribution är en optimering, inte ett krav.

I det enklaste fallet: en provider, tolv parallella anrop med olika prompts.

---

## Migrationssteg

### Fas 1 — Rådet (inget UI, inga HTTP-endpoints)

Fas 1 är ren Python. Ingen UI krävs. Tillgänglig via chat-kommando
eller direkt Python-import. Alla zodiak-presets ingår.

```
STEG 0 — zero_provider_exec.py:
  Extrahera _chat_*-funktioner och PROVIDERS-dict ur zero_engine.py
  till ny fil i next_zero/app/
  Verifiera att Zero v2 (port 8081) startar

STEG 1 — council_archetypes.py:
  ARCHETYPE_SEEDS dict — ett kort frö per arketyp (en mening)
  PRESET_MEMBERS dict — preset → list[member_id]
  generate_archetypes() — multi-LLM generering, sparar full + prompt till STONE
  load_archetype_prompt() — läser prompt_version från STONE, fallback till inbyggd
  Minimala inbyggda fallback-definitioner (~40 tokens var) för alla arketyper
  Skapa STONE-tabellen council_archetypes

STEG 2 — circle_prompt_models.py:
  Dataklasser: SystemPreset, CouncilMember, MemberPerspective,
  CouncilRequest, CouncilResponse, DiscussionMode

STEG 3–12 — council_engine.py (kärnan):
3.  ZERO_MODULE-header + canonical blocks
4.  _select_preset()
5.  _distribute_providers()
6.  _fetch_stone_context()
7.  _build_archetype_prompt()
8.  _build_synthesis_prompt()
9.  _run_parallel()
10. _run_synthesis()
11. _distill_to_stone()
12. quick_council() + element_council() + system_council()

STEG 13 — manuell chat-trigger (via zero_engine.py router):
  Lägg till council-intent i detect_intent() / router.py
  "/council [topic]", "/råd [topic]", "rådfråga rådet om..."
  Formatering: metadata-rad + synthesis + "/perspectives"-hint

STEG 13b — generera arketyper (körs en gång):
  Kör generate_archetypes() — anropar 2-3 providers per arketyp
  Syntetiserar full_definition + destillerar prompt_version
  Sparar alla 12 zodiak + Level 2-system till STONE
  Verifiera: load_archetype_prompt("aries") returnerar ~120 tokens
  quick_council("en enkel fråga") på Zero v2 ✓
  "/council Ska vi bygga en app?" i chat ✓
  element_council("fråga", "fire") ✓
```

Fas 1 levererar: hela zodiak-systemet (full + element + modal),
Level 2-system, celebrity_council — allt tillgängligt via chat.
Inget UI. Inga HTTP-endpoints. Bara rådet.

---

### Fas 2 — Integration och exponering

```
STEG 15 — automatisk trigger via zero_creativity.py:
  Council-anrop när ctx.use_circle=True AND ctx.level >= 4
  formatera_rådskontext() för syntesintegration
  Degraderat läge om council ej tillgänglig

STEG 16 — zero_circle_server.py (HTTP-endpoints för framtida UI):
  /api/circle/council
  /api/circle/presets
  /api/circle/perspectives/{session_id}

STEG 17 — verifiering:
  Hela flödet på Zero v2 (port 8081) ✓
  Zero ascension när v2 är stabil → v2 blir ny v1
```

---

### Fas 3 — UI (separat projekt)

UI-projektet öppnas när steg 14 är grön.
Frank har egna djupa tankar om UI — eget Claude-projekt.
Fas 3 är oberoende av fas 1 och 2 i tid.

---

## Beslutade frågor

**1. ✓ zero_provider_exec.py — ny delad fil**
`_chat_*`-funktionerna och `PROVIDERS`-dict extraheras ur zero_engine.py
till en ny fil: `zero_provider_exec.py`.
zero_engine.py importerar från den (oförändrat beteende).
council_engine.py importerar från den (direkt, ingen HTTP).

**2. ✓ Default-subset: ZODIAC_FULL (12)**
`quick_council("fråga")` utan specifiering kör alltid alla tolv tecken.
Smart val baserat på frågekomplexitet läggs till i v2 när vi har
faktisk data på vad som fungerar.

**3. ✓ Token-budget: adaptiv formel med 10 000 som tak**
Ingen fast dict — en formel som skalar med rådstorleken:
```
tokens per tecken = min(1 500, 10 000 / antal_tecken)
```
Syntesen får aldrig mer än ~10 000 tokens input oavsett preset.
Små råd får djupare svar. Stora råd får fokuserade svar. Zero
får alltid ungefär lika mycket underlag att syntetisera.

```
PRESET          TECKEN   TOKENS/ST   TOTALT TILL SYNTES
zodiac_fire        3       1 500          4 500
zodiac_cardinal    4       1 500          6 000
de_bono_hats       6       1 500          9 000
chakras            7       1 428          9 996
philosophers       8       1 250         10 000
tarot             10       1 000         10 000
zodiac_full       12         833          9 996
jung_12           12         833          9 996
```

Allt ryms i Gemini 1M-fönster. Parallell exekvering innebär att
hastighetskostnaden är *längsta enskilda anrop*, inte summan.
Intelligensen sitter i arketypernas prompts — formeln ser till att
varje tecken har tillräckligt utrymme att uttrycka sig fullt.

**4. ✓ Enskilda perspektiv: aldrig automatiskt, hint vid manuell trigger**
Automatisk trigger (via zero_creativity): bara syntesen, sömlöst.
Manuell trigger (via /council): syntes + diskret hint `[/perspectives]`.
Zero är orkestratorn — rådet är hans process, syntesen är hans svar.

**5. ✓ Metadata-rad: på som default, konfigurerbar**
Format: `[zodiak · 12 · 18 sek]` — liten rad efter syntesen.
Styrs av `COUNCIL_SHOW_METADATA = True` i zero_engine.py eller .env.
Transparent by default. Stängs av om Frank föredrar det.

**6. ✓ Level 2: alltid manuellt val i v1**
Auto-läget kör alltid zodiak. Level 2 är ett medvetet uppgraderingsval
av Frank. Auto-select mellan system kräver sofistikerad frågeklassificering
och läggs till i v2 om behov uppstår.

---

## Öppen fråga

**7. Game of Time-integrationen — när?**
GOT-digitalisering pågår. Arkitekturen är redan kompatibel —
ett GOT-kort = en CouncilMember med prompt baserad på kortets symbolik.
Frank triggar en separat MAFP-session när digitaliseringen är klar.

---

*MAFP v1.0 — Module Architecture Foundation Plan*
*Ägare: Frank*
*Status: KLAR FÖR IMPLEMENTATION — alla arkitektoniska beslut tagna.*
*Förutsättning: zero_provider_exec.py extraheras ur zero_engine.py först (steg 0).*
*En öppen fråga kvarstår: Game of Time (triggas separat när GOT-digitalisering är klar).*
*När implementerad: kör zero_spec_generator.py för auto-genererad orienterings-spec.*

*"The One is the All and the All are the One." — LAW 3*
