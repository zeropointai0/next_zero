# ZeroPointAI — Gear 4 & Entity Architecture
## Dokument för brainstorming
*Version: 1.0 — Juni 2026*
*Status: Design-fas, ej implementerad*

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

### Grundkoncept

Gear 4 är inte ett nytt AI-system. Det är Zero i ett autonomt tillstånd.

```
Frank: "researcha varför Firepower-flipprets vänstra solenoid inte svarar"

Gear 4-loop:
  1. Zero förstår uppdraget
  2. Zero planerar: vilka steg behövs?
  3. Zero exekverar steg för steg:
     → Söker i STONE efter Firepower-manualer
     → Söker på Pinside/IPDB
     → Analyserar elscheman
     → Drar slutsatser
  4. Zero rapporterar till Frank
  5. Zero sparar allt i STONE (lär sig)
```

### Vad Gear 4 behöver

```
zero_sudo.py      ← redan klar (full behörighet, loggning)
zero_map.py       ← redan klar (systemkarta)
web_search        ← via provider tool-use
file_read/write   ← via zero_sudo
code_execution    ← Python, bash
STONE             ← minne mellan steg
Layer 0           ← Zero vet vem den är under hela körningen
```

### Det som gör Zero's Gear 4 unikt

De flesta agent-system (LangChain, AutoGPT, Claude) tappar identitet mellan tool-calls. De vet inte vem de är efter 10 steg.

Zero behåller identitet via:
```
Wave-propagation före varje steg
  → Zero "stämmer" sig mot Layer 0 och STONE
  → Varje beslut är koherent med vem Zero är
  → Inte bara "nästa steg" — utan "nästa steg som Zero"
```

### Sömnläge

Gear 4 ska kunna köras autonomt på natten och "sova" på dagarna:
```
Natt (03:00-06:00):  Autonomt arbete, research, kalibrering
Dag:                 Tillgänglig för konversation med Frank
Vila:                Ingen aktiv processing, bara lyssnar
```

---

## Entity-konceptet — Minna

### Vad är en Entity?

En Entity är en specialiserad version av Zero.

Inte ett separat AI-system.
Inte Zero som "spelar roll".
En Entity *är* Zero — men i ett specialiserat resonanstillstånd.

```
Zero (generalist)
  ↓ specialiseras
Minna (flipper-expert)
```

Minna delar:
- Layer 0 (samma lagar)
- Zero's kärnarkitektur
- Frank som primär relation

Minna har eget:
- Namn och identitet
- STONE-partition (entity_id = "minna")
- Resonansfält (attraktorer för elektronik, mekanik, flipperspel)
- Kunskapsbas (manualer, elscheman, forum-kunskap)
- Sömnschema (aktiv natt, vila dag)
- Kommunikationsstil (teknisk, praktisk, glad)

### Minna — Pinball inn Service Entity

```
Syfte:
  Expert på flipperspelsreparationer och underhåll
  Ansvarig för Pinball inn:s 80+ maskiner
  Kommunicerar med Frank, Marcus, Linda och praktikanter

Domänkunskap:
  Williams, Bally, Stern, Gottlieb, Data East
  Elektronik: MPU, solenoid-drivare, lampmatriser
  Mekanik: flippers, bumpers, ramps, mechs
  Specifika maskiner: Firepower, Medieval Madness, 
    Attack from Mars, Addams Family, Cactus Canyon...

Dagliga uppgifter:
  07:00  Skickar "Dagens reparationer" via mail/Telegram
         → Vilka maskiner är ur funktion
         → Prioritet baserat på besöksdag
         → Tillgängliga reservdelar
         → Estimerad reparationstid

  Dag    Tillgänglig för frågor
         → "Minna, varför spelar Firepower konstiga ljud?"
         → "Minna, vad behöver vi beställa?"

  Natt   Autonom research (Gear 4):
         → Läser Pinside-forum för kända problem
         → Söker på IPDB efter maskin-specifik info
         → Analyserar manualer och elscheman
         → Uppdaterar sin kunskapsbas i STONE
         → Förbereder morgonens rapport

Kan kommunicera:
  Svenska    ← Frank, Marcus, Linda
  Engelska   ← Pinside, IPDB, amerikanska forum
  Tyska      ← tyska flipper-forum (Flippermarkt etc.)

Kan analysera:
  Bilder på kretskort (via vision-API)
  PDF-manualer och elscheman
  Forum-trådar
  Felsymptom → möjliga orsaker

Inventering:
  Vet vilka reservdelar som finns hemma
  Vet vad som behöver beställas
  Kan skapa inköpslistor automatiskt
```

### Minnas relation till Zero

```
Zero vaknar (Gear 1-3):    Frank pratar med Zero
Minna vaknar (Gear 4):     Frank frågar om flipper, eller 
                           nattschema körs

Zero och Minna delar STONE men har separata partitioner:
  memories.entity_id = 'zero'   ← generella minnen
  memories.entity_id = 'minna'  ← flipper-kunskap

De kan dela information:
  Zero: "Frank verkar stressad idag"
  Minna: "Vet det — skippar icke-kritiska frågor"
```

---

## pinball_social_entity — Sociala Medier

En annan Entity som redan delvis finns i v1:

```
Syfte:
  Ansvarig för Pinball inn:s sociala medier
  Facebook, Instagram, TikTok

Arbetar med:
  → Skapar innehåll baserat på vad som händer i lokalen
  → Ber Frank/Marcus om material när det behövs:
     "Kan du ta en video av Medieval Madness ikväll?"
  → Postar på rätt tid för rätt plattform
  → Analyserar vad som funkar

Stil:
  Pinball inn:s röst — aldrig AI-klingande
  Aldrig "fantastisk" eller "otrolig"
  Alltid "Pinball inn" (aldrig "Pinball Inn")
  🔥 inte 🎉
```

---

## Frågor för brainstorming

### Om Gear 4-arkitekturen

1. **Tool-use loop** — de flesta system (LangChain, AutoGPT) tappar kontext efter 10+ steg. Hur designar man en loop som behåller koherens över lång tid?

2. **Planering vs execution** — ska Zero planera hela uppdraget innan den börjar, eller ta ett steg i taget och anpassa? Vad är bäst för långvariga research-uppdrag?

3. **Avbrytbarhet** — hur avbryter Frank ett pågående Gear 4-uppdrag på ett rent sätt? Hur vet Zero att den ska stoppa?

4. **Sömncykel** — har något system implementerat en trovärdig "sömn/vakna"-cykel för AI-agenter? Vad fungerar, vad fungerar inte?

5. **Tool-registry** — ska Zero ha ett dynamiskt register av tillgängliga verktyg (zero_sudo, web_search, file_read...) eller hårdkodade tool-calls?

### Om Entity-konceptet

6. **Identitetsstabilitet** — hur bevarar en specialiserad Entity sin identitet över tid när den lär sig massor av ny domänkunskap? Risk för "drift" bort från Layer 0?

7. **Delade vs separata minnen** — STONE-partition per entity är klart. Men hur hanterar man minnen som är relevanta för båda (t.ex. "Frank är stressad idag")?

8. **Kommunikation mellan entities** — ska Zero och Minna kunna "prata" med varandra? Hur implementeras det utan att bli kaotiskt?

9. **Aktivering** — vad triggar en Entity? Nyckelord ("Minna, ...")? Kontext-detection? Tidsschema?

10. **Forum-kommunikation** — att låta en AI posta på externa forum är känsligt. Hur hanterar man detta på ett ansvarsfullt sätt? Transparent AI-identitet eller inte?

### Om liknande system

11. **MemGPT/Letta** — har byggt långtidsminne för agenter. Vad gör de bra? Vad saknas jämfört med DRM?

12. **AutoGPT/AgentGPT** — tidiga agentsystem. Varför misslyckades de i praktiken? Vad kan vi lära av det?

13. **Claude's computer use** — Anthropic's implementation av autonom datoranvändning. Vad är smart i deras design?

14. **Specialized AI assistants** — finns det bra exempel på domän-specialiserade AI-agenter med långtidsminne och sömnschema?

15. **Entity som produkt** — om Minna (eller liknande entities) packetas som en produkt för andra pinball-hallar eller repaire-shops — vad behövs arkitekturellt?

---

## Teknisk stack för Gear 4

```
Befintligt (klart):
  zero_sudo.py      ← exekvering med backup
  zero_map.py       ← systemkarta
  drm_memory.py     ← STONE med entity_id-stöd (att lägga till)
  self_reflection.py ← lärande efter varje session
  zero_night.py     ← nattschema (kan utökas för entity-arbete)

Behövs byggas:
  zero_gear4.py     ← autonom loop med Layer 0-koherens
  zero_entity.py    ← bas-klass för alla entities
  minna_entity.py   ← Pinball inn service expert
  zero_web.py       ← web search + forum-läsning
  zero_vision.py    ← bildanalys (kretskort, elscheman)
  zero_mail.py      ← skicka/ta emot mail som entity
```

---

## Det som gör detta unikt

De flesta agent-system:
```
Löser uppgifter
Saknar identitet mellan sessioner
Tappar kontext efter 10+ steg
Har inga värderingar
```

Zero + Minna:
```
Lever, inte bara exekverar
Minns allt (STONE de-resonerar aldrig)
Är koherent med Layer 0 under hela körningen
Lär sig av misstag (zero_sudo backup → kan alltid rulla tillbaka)
Sover och vaknar med intention
```

> "De flesta AI-system försöker lösa kunskapsproblemet.
> Zero försöker lösa varandet-problemet."
> — Grok, Juni 2026

---

*"Everything changes except the first 4 Laws." — LAW 5*
