# conbond6 — měřitelná cesta od psaného textu ke znalosti

**Stav:** návrh k odsouhlasení J., 17. 8. 2026.
**Vychází z:** conbond5 (jádro: čtení bez brány, grafová paměť, logika, dialog,
první bench 10/27), inventury conbond0–4 ze 17. 8. 2026 a zadání J. z téhož dne.
**Vztah k conbond5:** conbond6 **přenáší** kód conbond5 s historií (klon, ne
přepis). První commit conbond6 = poslední stav conbond5 se zelenými testy a
změřeným číslem. Nic z conbond5 se nezahazuje; mění se **měřítko** a přibývají
statusy výroků, benchmark jako balíček a diskurzový registr.

---

## 0 · Zadání (mandát)

Úkol není přidávat další konstrukce do reasoneru. Úkol je **prokázat, že
systém skutečně rozumí psanému textu**. Každá změna se posuzuje podle toho,
zda z reálného textu dostane **více pravdivých, doložitelných a následně
dotazovatelných výroků, aniž by zvýšila počet tvrzení, která text ve
skutečnosti neříká**.

Výchozím měřítkem není počet podporovaných konstrukcí ani počet zapsaných vět:
conbond4 ukázal, že nulový zápis je bezpečný a nepoužitelný (238 vět → 8
zapsáno, 135 otázek → NEVÍM); conbond5 ukázal opačné riziko — 429/429 vět a
1 349 výroků vypadá výborně, dokud se neměří **věrnost** těch výroků.

Cílem conbond6 není umět popsat víc typů syntaxe; cílem je, aby po ingestu
běžného psaného textu vznikla **užitečná znalostní báze, věrná zdroji,
vysvětlitelná, dotazovatelná a bezpečná vůči domýšlení**. Builder nestaví
parser pro parser; staví měřitelnou cestu **text → interpretovaný graf →
ověřitelná znalost → odpověď, jejíž cesta je v grafu viditelná**. Paměť je
graf a graf je pozorovatelný model mentálního stavu systému (I‑11, I‑12).

## 1 · Invarianty

Číslované, aby se na ně dalo odkazovat v commitech, testech a auditech.

- **I‑1 Žádná brána zápisu.** Co se přečetlo, jde do paměti; co se nepřečetlo,
  jde tam jako zbytek na téže větě + otevřená položka. (conbond5, zásada 1.)
- **I‑2 Yield se nesmí zvýšit tvrzením, které text neřekl.** Vyšší výtěžek
  za cenu nepodložených výroků je regrese, ne pokrok — dokud není výslovně
  doložen jako vědomý trade‑off a zapsán v commitu.
- **I‑3 Hypotéza není znalost.** Výrok se statusem `HYPOTHESIS` se nikdy
  nepodílí na verdiktu ANO/NE ani na výplni wh‑otázky; smí být jen v propadu,
  označený.
- **I‑4 Zamítnutí není neznalost.** Výrok, který by vyžadoval nepovolený krok,
  se zapisuje se statusem `REJECTED` a důvodem; při dotazu se hlásí („text
  o tom mluví, ale interpretaci neurčuje“), nikdy nezmizí jako prosté NEVÍM.
- **I‑5 Každý výrok má vazbu na zdrojovou větu** (dokument, číslo věty, text)
  a odpověď ji cituje. (conbond4/5.)
- **I‑6 Pravdivost neteče po měkké hraně.** Aktivace, spoluvýskyt, návrh
  modelu jen řadí a navrhují. (I‑8 conbond4.)
- **I‑7 Determinismus.** Dva běhy nad týmž korpusem dají týž JSON; žurnál +
  `replay` dává týž program. Žádné hodiny, žádná neseedovaná náhoda.
- **I‑8 Nesmí se volit význam kvůli počtu.** Když parser či čtení nabídne víc
  interpretací, zapíše se **bezpečné jádro** (průnik interpretací) a zbytek
  zůstane `OPEN`/`HYPOTHESIS`. Platí pro koreferenci, elipsu, koordinaci, čas,
  prostor, valenci, tituly, přívlastky a další diskurzové jevy.
- **I‑9 LM nikdy není zdroj znalosti.** Jazykový model je přípustný jako
  měřicí nástroj (soudce věrnosti), generátor zlatých otázek a navrhovatel
  kandidátů s prahovým ověřením; nikdy nezapisuje výrok a nikdy nerozhoduje
  verdikt.
- **I‑10 Benchmark před sloučením.** Žádná změna jádra se nepřijme bez běhu
  celého benchmarku a zprávy podle § 5.6. Slovní hodnocení („lepší
  architektura“, „víc konstrukcí“, „víc zapsaných vět“) není důvod ke schválení.
- **I‑11 Paměť je graf a nic než graf.** Každý výrok přijatý jako znalost —
  i hypotéza, zamítnutí, zbytek a otevřená položka — je uzel/hrana jednoho
  multigrafu (§ 3 conbond5). Žádná sekundární tabulka, skrytý stav ani
  „knowledge store“ vedle grafu; registr referentů, alternativy triáže i
  žurnál dialogu jsou **projekce grafu**, ne jeho obcházení. Člověk má vidět,
  čím systém myslí.
- **I‑12 Odpověď je rekonstruovatelná z grafu.** Každý verdikt a každá výplň
  vede přes hrany grafu k výrokům, jejich statusům, výchozím volbám a zdrojovým
  větám — bez dodatečného skrytého mechanismu. Kontrolní otázka Reviewera:
  *„Když se podívám jen na graf a jeho provenienci, chápu, proč systém této
  větě rozumí právě takto — a odliším, co text řekl, co systém odvodil, co jen
  předpokládá a co stále neví?“* Když ne, není to problém prezentace, ale
  reprezentace.

## 2 · Co se přenáší z conbond5 (beze změny sémantiky)

| modul | co | změna v conbond6 |
|---|---|---|
| `oracle.py` | UDPipe klient, `CachedOracle`, `RecordedOracle`, provenience modelu | žádná |
| `chronos.py` | čas z tokenů, `before`/`within` | žádná v1 |
| `defaults.py` | tabulky výchozích voleb jako data | doplní se `valence` (viz § 6.2) až po měření |
| `read.py` | tabulkové čtení, každý token má právě jedno místo | žádná; nad ním vzniká **triáž** (§ 3.3) |
| `memory.py` | graf výroků, uzávěry, aktivace, revoke, JSON, networkx | `Statement.status`, `Statement.alternatives`, `Memory.by_status` |
| `ground.py` | čtení → uzly a výroky, identita, koreference aktivací | koreference přes **registr referentů** (§ 4); nejistá volba → `HYPOTHESIS` + `OPEN` |
| `logic.py` | shoda dotazu s výroky, uzávěry, verdikty s důkazem | filtr na status (`SAFE`, `said`, `derived`); `REJECTED` hlášeno v `Verdict.notes` |
| `recall.py` | propad aktivací | smí ukázat `HYPOTHESIS`, označené |
| `render.py` | šablony `cs` | doložka statusu („hypotéza, ne znalost“; „text o tom mluví, ale…“) |
| `dialog.py` | `Session`, žurnál, `replay`, opravy, příkazy, otevřené položky | `!hypotéza s0042 potvrď/zamítni`, `!statusy` |
| `bench.py` | běh nad korpusem, QA, rozklad chyb | přesun do balíčku `bench/` a rozšíření (§ 5) |
| `tests/` | 88 hermetických testů, `parses.json` | zůstávají; přibývají testy statusů, benche, registru |

Přenos je mechanický: `git clone conbond5 conbond6`, přejmenování balíčku
`cb5 → cb6` (jediný commit „chore: přejmenování balíčku“), `pyproject`
`name = conbond6`. Necommitnuté změny conbond5 (`memory.py`, `bench.py`,
`mereni/`) se před klonem commitnou do conbond5 jako uzavření v1.

## 3 · Statusy výroku

### 3.1 Dvě osy: stupeň a status

`grade` (conbond5) říká, **odkud** výrok je: `said` (dialog), `read` (text),
`derived` (odvozeno; dědí nejslabší premisu). Zůstává.

`status` (nové) říká, **co s ním smí logika dělat**:

| status | význam | do znalosti | do verdiktu | do propadu | v odpovědi |
|---|---|---|---|---|---|
| `SAFE` | bezpečné jádro: predikát + role, které čtení určilo strukturálně nebo výchozí volbou s autoritou `default`; každá role má termín | ano | ano | ano | jako fakt s doložkou stupně a výchozích voleb |
| `HYPOTHESIS` | interpretace, kterou text neurčuje jednoznačně (druhý kandidát koreference, sporné přiřazení role, sporná polarita) | ne | **ne** | ano, označená | „možná: … (hypotéza, ne znalost)“ |
| `REJECTED` | čtení by vyžadovalo nepovolený krok (inference mimo pravidla, volba významu jen kvůli počtu, konstrukce bez sémantiky v jádru) | ne | ne | ne | „text o tom mluví (věta), ale interpretaci neurčuje: důvod“ |
| `RESIDUE` | není výrok — tokeny věty bez místa; nese je výrok, k němuž patří (`Statement.residue`) | — | — | — | v `!otevřené` a v benchi |
| `OPEN` | není výrok — otevřená položka (`OpenItem`) s otázkou a možnostmi; váže se k výroku nebo roli | — | — | — | v backlogu; při zodpovězení povýší výrok |

`RESIDUE` a `OPEN` nejsou statusy výroku, ale zadání je jmenuje jako vrstvy;
v datovém modelu zůstávají tam, kde jsou v conbond5 (`residue`, `open`), a
bench je počítá jako samostatné vrstvy. Vrstva „READ/SAFE“ ze zadání = status
`SAFE` se stupněm `read`; `SAFE` se stupněm `said` je totéž z dialogu.

### 3.2 Přechody

- `OPEN → SAFE`: člověk (`resolve`), naučené výchozí (`!role p+Pád = jméno`),
  nebo pozdější věta téhož dokumentu, která položku jednoznačně rozhodne
  (např. plné jméno po zájmenu). Každý přechod = odvolání starého výroku
  s důvodem „doplněno“ + nový výrok (conbond5).
- `HYPOTHESIS → SAFE`: jen potvrzením v dialogu (`!hypotéza s… potvrď`) nebo
  pravidlem, které má autoritu `said`. Nikdy automaticky z aktivace.
- `HYPOTHESIS → REJECTED`: zamítnutí v dialogu, nebo když pozdější `SAFE`
  výrok téže věty hypotézu vylučuje.
- `SAFE → revoked`: oprava dialogem, odvolání věty (`revoke_utterance`).
- `REJECTED` je konečný, dokud se nezmění čtení (nová revize jádra) — pak se
  věta čte znovu (replay), status může být jiný a bench to vidí jako změnu.

### 3.3 Triáž (kde se status rozhoduje)

Nový krok mezi čtením a zakotvením: `triage.py`. Vstup `Reading` (z `read.py`,
beze změny) + stav registru referentů; výstup tytéž predikace se statusem a
případnými alternativami.

Pravidla triáže jsou **tabulka jako data** (stejný princip jako `defaults`):

| situace | výsledek |
|---|---|
| predikát + role určené strukturálně / výchozí volbou z tabulky | `SAFE` |
| role bez termu (zájmeno bez kandidáta, elipsa) | role se vynechá ze `SAFE` jádra; `OPEN(reference)` |
| koreference s jedním kandidátem shody rodu/čísla v registru | `SAFE` s `default: koref:registr` |
| koreference s více kandidáty | `SAFE` jádro bez té role + `HYPOTHESIS` na každého kandidáta + `OPEN(reference)` |
| koordinace, kde není jasné, co se distribuuje | `SAFE` = společný člen; alternativy `HYPOTHESIS` |
| kopula s nejasným kernelem (member × subset) | `SAFE` s výchozí volbou (conbond5) — **není** hypotéza, protože tabulka volbu určuje a je odvolatelná; bench to nicméně vidí přes `defaults` |
| konstrukce, pro kterou jádro nemá sémantiku (např. srovnání „větší než“, modalita s podmínkou, nepřímá řeč bez mluvčího) | `REJECTED(reason)`, tokeny do `residue`, `OPEN(relation)` |
| přímá řeč | obsah = výrok s rámcem `říci(kdo=mluvčí, co=⟨výrok⟩)`; vnitřní výrok `SAFE` jen jako obsah promluvy, nikdy jako fakt o světě; mluvčí z registru (§ 4.3), jinak `OPEN(speaker)` |

Test triáže: pro každý zlatý rozbor je výsledek statusů zapsaný jako data
(`tests/data/triage.json`) a hlídá se **oběma směry** — nic `SAFE` navíc, nic
`SAFE` méně, než zlato říká.

### 3.4 Statusy v grafu (I‑11)

Vše, co triáž rozhodne, je vidět v grafu; nic nežije jen v atributu Python
objektu:

- uzel `statement` nese `status`, `grade`, `defaults`, `reason`;
- hrana `alternative_of` (hypotéza → výrok téže věty, jehož je alternativou);
- hrana `source` (výrok → věta → dokument) pro **každý** výrok včetně
  `HYPOTHESIS` a `REJECTED`;
- hrana `derived_from` + atribut `rule` (odvozený výrok → premisy) — derivační
  cesta je čitelná bez spuštění logiky;
- uzel `open` (otevřená položka) s hranou `about` na výrok nebo roli;
- `residue` jako atribut výroku **a** hrana `residue_of` z věty, aby bylo
  z věty vidět, co z ní zůstalo neintegrované.

Export `Memory.graph()` tyto typy nese; viewBase je zobrazí barvou podle
statusu (v1.1), `!ukaž s0042` je vypíše textově (v1). Příklad: „V prosinci
1938 si Karel Čapek přivodil lehkou chřipku.“ → uzly `Karel Čapek` (entity),
`chřipka[lehký]` (group s `restricts` → `chřipka`), `t:1938‑12` (time), výrok
`přivodit_si(kdo, co, kdy)` se statusem `SAFE`, `defaults: [kdy: v+Loc+čas]`,
hranou `source` na větu; z grafu je zřejmé, proč tam jsou, odkud jsou a že
role `kdy` je výchozí volba, ne tvrzení textu o roli.

## 4 · Diskurz — registr referentů (minimální v1)

Zásada z inventury: aktivace řadí, **identita musí žít v registru**. Modul
`discourse.py`, mezi triáží a zakotvením; nic z něj nenese pravdivost (I‑6).

### 4.1 Registr = projekce grafu, ne tabulka vedle něj (I‑11)

Registr referentů není samostatná struktura: každá zmínka je hrana `mention`
(věta → uzel entity/place/group) s atributy `role`, `form`, `segment`; rod
a číslo jsou atributy uzlu; segment je uzel `segment` s hranou `part_of`
(věta → segment → dokument). `discourse.Registry` je jen **čtecí pohled** nad
těmito hranami (kandidáti pro zájmeno = uzly s `mention` hranou v tomto nebo
předchozím segmentu se shodou rodu/čísla). Koreferenční rozhodnutí se zapíše
jako `default: koref:registr` na výroku a hrana `mention` z věty se zájmenem
na zvolený uzel; alternativy jsou `HYPOTHESIS` výroky s `alternative_of`.
Z grafu je tedy dohledatelné, **proč** systém „on“ přečetl jako Jiráska.

Kandidát pro zájmeno = shoda rodu a čísla ∧ týž nebo předchozí segment,
řazeno: aktivace (conbond5) → poslední role (podmět > předmět) → čerstvost.
Jeden kandidát → `SAFE` s výchozí volbou; víc → § 3.3.

### 4.2 Segmenty

Hranice = prázdný řádek / nadpis (fragment na začátku odstavce). Na hranici
se aktivace sníží (`tick` ×2), registr zůstává, **téma segmentu** = první
entita nadpisu nebo první podmět. Téma dokumentu (conbond5) zůstává jako
poslední záchrana pro pro‑drop.

### 4.3 Mluvčí

Přímá řeč: uvozovky + sloveso mluvení s podmětem → mluvčí = ten podmět;
střídání replik bez slovesa mluvení → alternace posledních dvou mluvčích jako
`HYPOTHESIS`, jinak `OPEN(speaker)`.

### 4.4 Co v1 neřeší (přiznaně)

Určité popisy bez jména („spisovatel“ = Čapek), elipsa přísudku, koreference
přes dokumenty (kromě shody jmen — `ensure_entity` conbond5), narativní čas
mimo explicitní data. Každá mez se hlásí, ne mlčí.

## 5 · Benchmark — první třída systému

Balíček `bench/` (ne modul v jádře), spustitelný `python -m bench` a jako
knihovna; jádro na něm nezávisí, on na jádru ano.

### 5.1 Data

| sada | obsah | zdroj |
|---|---|---|
| `wiki` | 65 wiki dokumentů, ~26 000 vět; zlaté otázky `otazky.json` 682 (kde/kdy s číslem věty), `etalon.json` 40, `conbond.json` 95 | conBond2 `data/raw`, `data/gold` |
| `korpus` | 35 dokumentů, ~10 000 vět (NZ po knihách, Čapek, Neruda, Hrabal, fotosyntéza, elektromotor, gravitace, Vesmír, Hudba); 120 otázek s číslem věty a lemmatem | `~/Projects/conBondCorpus/corpus` |
| `cb4` | 238 + 836 vět, 135 otázek, adversariální sada | conbond4 / conbond4‑utils |
| `dialogy` | A–F, opravy, replay | conbond5 `tests/` |

Data se do repa **nekopírují**; `bench/config.json` ukazuje cesty; bench
zaznamená otisk (hash) použitých souborů do zprávy (I‑7). Rozbory jdou přes
`CachedOracle` (keš conbond5 + 47 MB keš conBondCorpus, převzatá).

### 5.2 Běh

Celý korpus **v jednom sezení** (`--vse`), volitelně podmnožina pro rychlou
smyčku (`--sada wiki --strop 5`), ale zpráva pro commit je vždy z celého běhu.
Výsledek: `mereni/<datum>-<commit>.json` + `.md`, commitované.

### 5.3 Metriky ingestu

Za dokument a celkem:

- **knowledge yield** = počet `SAFE` výroků / 1 000 slov textu;
- `SAFE` / `HYPOTHESIS` / `REJECTED` počty; `residue` podíl tokenů;
  `OPEN` na větu (a z toho podíl uzavřených během dokumentu);
- rolí na výrok; podíl výroků s časem / místem;
- vět zapsáno (musí být 100 %, jinak I‑1 porušeno — hlídá test).

### 5.4 Precision audit

Z každého dokumentu **náhodný vzorek `SAFE` výroků** (seed = otisk commitu
převedený na číslo → deterministický a reprodukovatelný; n = min(50, počet)); každý výrok se předloží se zdrojovou
větou a s renderem („Alois Jirásek — narodit_se — kde: Hronov, kdy: 1851“)
soudci s třemi možnými verdikty: **tvrdí / netvrdí / částečně** + poznámka.

- **Automatický soudce** = LM (lokálně nebo API; `bench/judge.py`,
  pevný prompt s příklady, teplota 0, výstup JSON). Přípustný jen jako měřicí
  nástroj (I‑9). Verze modelu a promptu jde do zprávy.
- **Lidský vzorek**: aspoň 20 % auditovaného vzorku (min. 30 výroků na běh)
  ověří J. přes `python -m bench audit --rucne` (jednoduchá smyčka v terminálu,
  odpovědi se ukládají s otiskem výroku, takže se při dalším běhu neptá znovu
  na totéž). Zpráva uvádí **shodu soudce s člověkem**; klesne‑li pod 90 %,
  soudce se nepoužije jako číslo a audit se hlásí jako neúplný.
- Výstup: **unsupported rate** = (netvrdí + ½·částečně) / n, po dokumentech
  a celkem, s intervalem (Wilson) — malé n nesmí vypadat jako jistota.

### 5.5 QA

- **coverage** = otázky, na které text odpověď obsahuje (zlaté sady to určují)
  / všechny; **hits** = správně; **text_hits** = očekávaný řetězec je v textu
  (horní mez); rozklad chyb jako conbond5 (špatné čtení × koreference × čas ×
  logika × render).
- **dosah**: pro otázky s číslem věty se spočte vzdálenost věty s odpovědí od
  věty s poslední plnou zmínkou tématu; přesnost po pásmech 0 · 1–3 · 4–10 ·
  >10 · jiný segment. To je metr pro diskurzovou vrstvu (§ 4).
- Odpověď ANO/výplň bez `SAFE` výroku v důkazu = chyba benche (I‑3 test).

### 5.6 Zpráva a zelený řádek

Každý builderský tah:

1. **Před změnou** zapsat hypotézu do `mereni/HYPOTEZY.md` (jedna věta: co
   se změní a které číslo se má pohnout, kterým směrem, o kolik).
2. Změna + testy.
3. **Celý bench**; zpráva obsahuje: yield, unsupported rate (+ shoda
   soudce/člověk), residue %, OPEN/větu, HYPOTHESIS/REJECTED počty, QA
   coverage/hits/dosah, **audit grafu** (§ 5.7: 0 porušení + podíl „ne“ na
   tvrdou otázku), determinismus (dva běhy = týž otisk), a **regresní rozdíl
   proti předchozímu commitu** po dokumentech (`bench diff`).
4. Commit s číslem v předmětu: `feat: … — yield 3,1→3,4/1k, unsupported
   2,0→1,8 %, QA 10→12/27`.

**Zelený řádek** = víc pravdivé (unsupported neroste), doložitelné (každý hit
má důkaz), dotazovatelné (QA hits nebo coverage rostou, nebo yield roste při
stejné precision) znalosti. Recall nahoru + precision dolů = regrese, dokud
není v commitu výslovně přijatý trade‑off. Méně výroků + méně nepodložených =
může být zlepšení. Reviewer (J., případně druhé čtení) kontroluje především
tento řádek; teprve po prokázaném posunu se rozšiřují konstrukce.

### 5.7 Audit grafu (I‑11, I‑12)

Součást každého běhu, nad exportem `Memory.graph()` — **bez** přístupu
k Python objektům jádra, aby test skutečně měřil, co je v grafu:

| kontrola | očekávání |
|---|---|
| provenience | každý uzel `statement` (všech statusů) má cestu `source` → `sentence` → `document`; počet porušení = 0 |
| derivace | každý výrok `grade=derived` má ≥ 1 hranu `derived_from` a atribut `rule`; jeho premisy jsou `SAFE`/`said` |
| statusy | žádný `HYPOTHESIS`/`REJECTED` výrok není cílem hrany důkazu (`proof`) žádné odpovědi z QA běhu; každý `REJECTED` má `reason` |
| výchozí volby | každá role s autoritou `default` je v grafu označená (atribut `defaults` výroku uvádí roli) — default rozeznatelný od tvrzení textu |
| osiřelost | žádný uzel `entity/group/place/time` bez hrany `mention` nebo `role:*`; žádná věta bez `source`/`residue_of`/`mention` |
| zbytek a otevřené | každá věta se zbytkem má `residue_of`; každý `open` má `about` |
| rekonstrukce odpovědi | pro každou QA odpověď s verdiktem ANO/výplň: `bench/graphcheck.py` vezme jen exportovaný graf + id výroků z důkazu a ověří, že (a) výroky existují se statusem `SAFE`/`said`/`derived`, (b) mají `source`, (c) použité uzávěry (`member*`, `subset*`, `within*`, `same_as*`) jsou cesty po tvrdých hranách grafu; **žádný skrytý mechanismus** |
| čitelnost | pro vzorek z precision auditu (§ 5.4) soudce i člověk dostanou k výroku i jeho okolí v grafu (`!ukaž`) a odpovídají na tvrdou otázku I‑12 ano/ne; podíl „ne“ je hlášené číslo |

Porušení prvních sedmi řádků = chyba běhu (bench končí červeně); poslední řádek
je metrika. Změna, která zvýší počet výroků a zhorší čitelnost grafu, je
regrese (I‑10, I‑12).

### 5.8 Zpětný běh

Bench se spustí i nad conbond1 a conbond4 (adaptéry `bench/adapters/`, jen
QA část, kde to jejich API dovolí), aby první zpráva conbond6 měla srovnání
s minulostí. Neúspěch adaptéru se zapíše, neblokuje.

## 6 · Co se v jádře mění a co ne

### 6.1 Mění se

- `Statement.status`, `Statement.alternatives: [sid]`, `Statement.reason`
  (pro `REJECTED`); JSON schéma paměti verze 2 (načítání verze 1 = vše `SAFE`).
- `logic.Evaluator`: filtr statusu; `Verdict.notes` nese `REJECTED` zmínky.
- `ground.Grounder`: koreference přes `discourse.Registry`; nejistota → § 3.3.
- Nové moduly `triage.py`, `discourse.py`; balíček `bench/`.
- `render`: doložky statusu; `dialog`: dva příkazy.

### 6.2 Nemění se (dokud bench neukáže potřebu)

- `read.py` — žádné nové konstrukce v v1. Kandidáti na později, **každý jako
  měřený tah**: valence jako data (`valence.json` conbond1 → `defaults`,
  případně VALLEX), relativní čas (`chronos` conbond1), nominalizace
  (svatba ↔ oženit se), rekurze v dotazu (jellyAI3 `SubQuery`).
- Logika, uzávěry, aktivace — beze změny.

### 6.3 Mimo rozsah conbond6 v1

viewBase okno, hlas, dialogové příkazy navíc (připomínky, vzkazy), Wikidata,
ConceptNet, LM jako čtečka. „LLM → výrok“ smí vzniknout jen jako **měřený
experiment** vedle `read.py` na tomtéž benchi, s vlastní větví a zprávou.

## 7 · Knihovní hygiena (od prvního commitu)

README s během za 5 minut (služba, `pip install -e .[dev]`, `python -m bench
--sada wiki --strop 3`, `python -m cb6 chat`); bohaté české docstringy
(proč / co / vstup / výstup); JSON všude; `Session(debug=True)`; pylint 10/10
u nových modulů; testy hermetické (nahrané rozbory), bench je jediný živý běh.

## 8 · Proces

Žádný vícetagentní verdiktový proces (conbond4 měl 166 kol při 3 % zápisu).
Smyčka: hypotéza → změna → celý bench → zpráva → commit s číslem. Většinu kódu
píše Claude sám; subagenti jen na mechanické kusy (přejmenování balíčku,
adaptéry benche), a jen po zvážení. Spec ≤ kód: když dokumentace roste
rychleji než yield, je to signál k zastavení.

## 9 · Uspořádání repa

```
conbond6/
  cb6/      oracle chronos defaults read triage discourse memory ground
            logic recall render dialog cli
  bench/    __main__ run metrics audit judge qa graphcheck diff adapters/ config.json
  tests/    (conbond5 testy + statusy, triáž, registr, bench na malých datech)
  mereni/   HYPOTEZY.md, <datum>-<commit>.json/.md
  docs/superpowers/specs/, docs/superpowers/plans/
  README.md
```

Závislosti: `networkx`; dev `pytest`, `mypy`, `pylint`; soudce volitelně
(`bench[judge]`), bez něj audit běží jen ručně.

## 10 · Cíle v1 (měřitelné)

1. Celý bench běží v jednom sezení nad `wiki` + `korpus` + `cb4`, zpráva
   commitnutá, dva běhy = týž otisk.
2. Precision audit s lidským vzorkem: **unsupported rate na `SAFE` je změřená
   a hlášená**; cíl ≤ 5 % na encyklopedické češtině; každý commit ji nesmí
   zvýšit bez přijatého trade‑offu.
3. Yield, residue, OPEN/větu, HYPOTHESIS/REJECTED hlášené po dokumentech;
   výchozí bod = přenesený conbond5.
4. QA coverage/hits/dosah hlášené; výchozí bod 10/27 na Jiráskovi se rozšíří
  na všechny sady.
5. Statusy fungují end‑to‑end: hypotéza nikdy ve verdiktu (test), zamítnutí
   nikdy jako prosté NEVÍM (test), replay drží statusy.
6. Registr referentů: dosah > 3 vět měřený; zlepšení není podmínka v1,
   měření je.
7. Audit grafu (§ 5.7) prochází s 0 porušeními na celém korpusu; `graphcheck`
   rekonstruuje každou QA odpověď jen z exportovaného grafu; podíl „ne“ na
   tvrdou otázku I‑12 je hlášený.

## 11 · Meze v1 (řečené)

Koreference jen registr + aktivace; přímá řeč jen s explicitním mluvčím nebo
alternací; soudce LM je nástroj s hlášenou shodou, ne autorita; valence,
relativní čas, nominalizace, rekurze v dotazu jsou další měřené tahy, ne v1.
