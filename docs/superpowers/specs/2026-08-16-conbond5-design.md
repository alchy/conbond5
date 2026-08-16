# conbond5 — konverzační systém s pamětí a logickým hodnocením výroků

**Stav:** návrh schválený J. 16. 8. 2026, před stavbou.
**Vychází z:** conbond4 (formální jádro, poctivost, provenience), conBond3
(„nic se neztrácí“, retrieval jako propad, JSON persistence), conBond2
(korpus + zlaté otázky), a z měření conbond4 na korpusu 16. 8. 2026.

---

## 0 · Jedna věta

Systém, který každou větu textu **zapíše do grafové paměti** jako
strukturovaný výrok s *epistemickým stupněm*, a nad pamětí **logicky
hodnotí výroky** — ANO / NE / NEVÍM s důkazem a citací zdrojové věty —
v dialogu s člověkem, který ho tímtéž dialogem opravuje a doučuje.

## 1 · Proč nový projekt (diagnóza conbond4)

Změřeno 16. 8. 2026 nad 238 větami korpusu (živý UDPipe, model
`cs_all-ud-2.17-251125`):

| stav | vět |
|---|---|
| přečteno (predikát + role) | 220 |
| **zapsáno do báze** | **8** |
| ptá se (3–5 otázek na větu) | 212 |
| nepřečteno | 16 |

Příčina není v čtení — je v **bráně zápisu** (`session._settle`): osm
blokátorů (ztracený člen, čekající relace / uzavření / sdílení / jméno,
přívlastek pod ∀, `∀` z osiva, role s tvarovým jménem) a stačí jeden, aby
se nezapsalo nic. Každý má poctivé zdůvodnění; součtem je systém, který
si věty nepamatuje. Ani „Pes štěká.“, „Jezevčík je pes.“ neprojdou;
„Petr bydlí v Praze.“ se zapíše bez Prahy — a pak na „Bydlí Petr
v Brně?“ odpoví ANO. Poctivost bránou zápisu se obrátila v nepoctivost.

Oprava uvnitř conbond4 by šla proti 22 patrům kaskády, 3 000 řádkům
doložek a 1 348 testům, které tu politiku kodifikují. Proto conbond5:
**syntéza**, ne úprava. conbond4 zůstává jako reference a zdroj
testovacích dat.

## 2 · Tři zásady (pivot)

1. **Čtení se vždy zapíše.** Co se přečetlo, jde do paměti; co se
   nepřečetlo, jde tam také — jako *zbytek* (`residue`) na téže větě,
   viditelný a spočitatelný. Otázky, které conbond4 kladl dopředu, jsou
   *otevřené položky* (`open`, backlog): neblokují nic, kdykoli je lze
   zodpovědět a výrok tím povýšit.
2. **Každý výrok má stupeň** (`grade`): `said` — člověk to řekl v dialogu
   nebo potvrdil; `read` — systémovo čtení textu; `derived` — odvozeno,
   dědí nejslabší premisu. Vedle stupně nese výrok seznam **výchozích
   voleb** (`defaults`), které při čtení padly. Odpověď vždy říká, na čem
   stojí, a cituje větu.
3. **Výchozí volby jsou data**, ne kód: kvantifikátor z tvaru, jméno role
   z předložky + pádu + druhu výplně, kopula → `member`/`subset`/`within`,
   pro‑drop → aktivní uzel. Každá má autoritu `default`, je odvolatelná a
   přeučitelná dialogem. Systém se **neptá dopředu**; ptá se, jen když
   odpověď na otázku člověka na nejisté volbě závisí — a i tehdy nejdřív
   odpoví s doložkou.

**Guard, který se přenáší doslova (I‑8 conbond4):** pravdivost nikdy
neteče po měkké hraně; aktivace nezvyšuje jistotu. Měkká vrstva jen řadí
a navrhuje.

## 3 · Graf jako paměť (§ 4 zadání conbond4, tady postavené)

Paměť **je** jeden multigraf.

**Uzly:** `entity` (anonymní identita se jmény), `group` (množina podle
lemmatu, případně zúžená přívlastky: `mazlíček[domácí]`), `place`,
`time` (bod/interval na ose), `value` (číslo s jednotkou), `statement`
(reifikovaný výrok — vztah s rolemi), `document`, `sentence`.

**Tvrdé hrany** (nesou pravdivost): `role:<jméno>` (statement → term),
`member`, `subset`, `within`, `before`, `name`, `same_as`, `restricts`
(zúžená group → základní group; z ní plyne `subset` strukturálně),
`source` (statement → sentence → document).

**Měkké hrany** (nesou jen aktivaci): `co_mention` (dva termy v téže
větě), `follows` (zmínka po zmínce v dialogu / dokumentu).

**Aktivace:** zmínka vstříkne energii do uzlu, šíří se po hranách
s útlumem, vyhasíná **po tazích** (ne po čase). Stav aktivace = kontext
rozhovoru; používá se pro koreferenci (zájmena, pro‑drop, určité popisy),
pro řazení kandidátů identity a pro propad odpovědi („nevím jistě, ale
o X vím: …“).

**Export:** `Memory.graph()` vrací networkx `MultiDiGraph` s atributy
(`kind`, `label`, `grade`, `activation`, typ hrany) — přímo přijatelný
pro viewBase (`add_graph`, duck typing). Konverzace nad živým grafem
(viewBase `TerminalWindow` + `highlight` podle aktivace) je adaptér mimo
jádro, v1.1.

## 4 · Datový model

```
Node       id, kind, names: set[str], lemma, attrs: {amod lemmata}, sort
Statement  id, pred (lemma; „narodit_se“), neg, modality (None|možnost|nutnost),
           kernel (None|member|subset|within|before|name|same_as),
           roles: {name -> Role(term_id, quant ∀|∃|·, authority)},
           grade said|read|derived, defaults: [str], residue: [(form, deprel)],
           open: [OpenItem], prov: Provenance(doc, sent_no, text, turn, model),
           status active|revoked(reason), derived_from
OpenItem   id, kind (role_name|quantifier|reference|residue|relation),
           about (role/token), question (česky), options, answer
```

Identifikátory jsou deterministické (`s0001`, `e0003`, …) v pořadí
vzniku; **JSON je jediný formát persistence** (`Memory.save/load`),
čitelný a diffovatelný. Uložený program = seznam výroků; graf je jeho
deterministická projekce.

## 5 · Čtení (`read.py`) — rozbor → výrok, nic se neztrácí

Vstup: jeden UD strom (UDPipe přes `oracle.py`; rozbor s proveniencí
modelu, keš rozborů na disku jako JSON — determinismus a rychlost).
Výstup: `Reading` = hlavní predikace + vedlejší predikace + zbytek.

Deterministické, **tabulkové**, žádná patra s pořadím:

| jev | co se stane | autorita |
|---|---|---|
| kořen VERB | `pred` = lemma (+ `expl:pv` „se“ → `_se`); `aux` se pohltí; modální `moci/muset/smět/mít` s `xcomp` → pred = infinitiv, `modality` | strukturální |
| `nsubj` / `nsubj:pass` / `obj` / `iobj` | `kdo` / `co` / `co` / `komu` | strukturální |
| `obl` s `case` | povrch `p+Pád`; **tabulka výchozích** podle výplně: `v+Loc`+místo→`kde`, `v+Loc`+čas→`kdy`, `do+Gen`→`kam`, `z+Gen`→`odkud`, `na+Loc`→`kde`, `na+Acc`→`kam`, `s+Ins`→`s_kým`, holý Ins→`čím`, `od+Gen`+čas→`od_kdy`, `do+Gen`+čas→`do_kdy` … jinak zůstane povrch | `default` (jméno role) |
| `obl:agent` | `kdo` (pasivum) | strukturální |
| `advmod` (ne částice) | `jak: <lemma>` | strukturální |
| `xcomp` / `ccomp` / `csubj` | vnořená predikace jako role `co` / `kdo` (hloubka 1) | strukturální |
| `advcl` s `mark` | vnořená predikace, role `advcl:<mark>` (pokud/aby/když/protože…) | povrch |
| `amod` | atribut termu → zúžená group `X[a]` (`restricts` X) nebo vlastnost entity | strukturální |
| `nmod` (+`case`) | vedlejší výrok `nmod:<p+Pád>(hlava, závislý)` — povrch, nezkoumá směr | povrch |
| `nummod` | `count` na termu | strukturální |
| `appos` | kandidát `same_as`/`name`; u PROPN+NOUN → `member` | `default` |
| `acl` / `acl:relcl` | vedlejší predikace o hlavě (vztažná věta tvrdí) | strukturální |
| `conj` (nominální) | `group{a, b, …}`; u podmětu slovesa distribuce (dva výroky), u předmětu skupina | `default` (distribuce) |
| `conj` (slovesný) | druhý výrok se sdíleným podmětem | strukturální |
| `flat` / `flat:name` | víceslovné jméno = jedna entita | strukturální |
| kopula (`cop`) | `pred=být`; NOUN=NOUN: PROPN/určitý podmět → `member`, obecný → `subset`; `být v+Loc` s místem → `within`; ADJ → `jaký` | `default` (kernel) |
| `Polarity=Neg` na přísudku | `neg=True` | strukturální |
| `det` každý/všichni/žádný → ∀ (žádný + neg); ten/tento → ·; nějaký/některý/jeden → ∃ | kvantifikátor | determinátor |
| holý NOUN podmět, prézens imperf. | ∀ (generické) | `default` |
| holý NOUN podmět, minulý/perf. nebo s časem | · (epizoda, nová instance) | `default` |
| holý NOUN předmět | ∃ | `default` |
| PROPN | · entita; jméno = řetěz `flat`; částečné jméno („Jirásek“) se sceluje s uzlem, jehož jména ho obsahují (jediný kandidát → sceleno; víc → aktivace rozhodne, otevřená položka `reference`) | strukturální / `default` |
| PRON osobní / pro‑drop | poslední aktivní uzel se shodou rodu a čísla; bez kandidáta → téma dokumentu; nic → role zůstane otevřená | `default` (koreference) |
| datum / rok / rozsah | `Chronos`: „23. srpna 1851“, „roku 1851“, „v roce 1851“, „(1851–1930)“ → `time` uzel; „v letech A–B / A nebo B“ → interval / alternativa | strukturální |
| životopisná závorka „X (datum místo – datum místo) byl …“ | `narodit_se(kdo, kdy, kde)`, `zemřít(kdo, kdy, kde)` | `default` (závorka) |
| kořen NOUN bez `cop` (nadpis, fragment) | výrok `kind=fragment` bez predikátu; termy a atributy se zapíší | strukturální |
| cokoli jiného | **zbytek**: `(tvar, deprel-cesta)` na výroku + otevřená položka `residue` | — |

Každý token skončí právě v jednom z: predikát, role, atribut, vnořená
predikace, částice (`aux`, `cc`, `mark`, `case`, `det`, `punct`, částice
`ne/také/i/jen/už`), nebo **zbytek**. Test to hlídá pro každý zlatý rozbor.

## 6 · Logika (`logic.py`) — hodnocení výroků

Otázka se čte týmž čtením (mood podle otazníku); tázací slovo označuje
**díru** v roli (`kde` → role kde, `kdy` → kdy, `kdo` → kdo, `co` → co,
`kolik` → count, `jaký/který` → atribut, `proč` → advcl:protože, `čí` → nmod).

**Shoda dotazu s výrokem** (jádro; opravuje chybu „Brno → ANO“):
predikát shodný (nebo naučené synonymum), polarita se porovná, a **každá
role dotazu musí mít protějšek ve výroku** (výrok smí mít role navíc —
§ 3.4 conbond4; dotaz ne). Term dotazu odpovídá termu výroku, když:

- entita: týž uzel přes `same_as*`;
- dotaz `·e` × výrok `∀G`: `e member* G` (distribuce ∀ dolů);
- dotaz `∀Gq` × výrok `∀Gf`: `Gq subset* Gf`; dotaz `∃G` × výrok `∀G`
  nebo `∃G`: shoda group přes `subset*`; dotaz `∀G` × výrok `∃G`: neshoda
  (→ NEVÍM s doložkou „vím o některých“);
- místo: `within*` (Praha ⊆ Česko); čas: bod v intervalu / rok = rok;
- kopula: `member*`, `subset*`, `within*` z uzávěrů (včetně `restricts`).

**Verdikty:** `ANO` s důkazem (výroky + kroky uzávěrů + použité výchozí
volby → stupeň odpovědi = nejslabší); `NE` když existuje shodný výrok
s opačnou polaritou, nebo `disjoint` skupin, nebo `∀` s výjimkou `NOT`;
`KONFLIKT` nese oba důkazy; `NEVÍM` nese, co by rozhodlo (chybějící
článek: „vím: X, Y; chybí: Z“) — a **propad** (§ 7). Modalita: „Může X?“
sedí na výrok s `modality=možnost` i na prostý výrok; prostý dotaz na
výrok s modalitou → „MOŽNÁ — text říká, že může“.

**Wh‑otázky:** výčet výroků, které sedí na všechny nedíravé role; odpověď
= výplně díry, každá se zdrojovou větou; nic → propad. `kolik` → počet
známých prvků s doložkou otevřeného světa. „Kdo/co je X?“ → okolí uzlu:
členství, vlastnosti, výroky s X v roli `kdo`, seřazené podle stupně a
opakování.

**Učení, které logika čte:** `subset`/`member`/`within` z textu i z
dialogu; výjimka jako `NOT` (zúžení `∀` odvoláním a přepsáním);
můstková pravidla `if pred(roles) then pred(roles)` jako data — v1 jen
z dialogu potvrzením nabídnuté hypotézy (dialog A conbond4).

## 7 · Propad (`recall.py`) — conBond3 nad týmž grafem

Když logika nedá ANO/NE: aktivuj uzly z otázky, seber aktivní výroky
v jejich okolí, seřaď (překryv predikátu a rolí, stupeň, čerstvost) a
vrať nejvýš tři jako „nevím jistě; o X vím: …“. **Nikdy netvrdí** —
render to říká výslovně a verdikt zůstává NEVÍM.

## 8 · Dialog (`dialog.py`)

`Session(memory, oracle)`:

- `ingest(text, doc=…)` — dokument → věty (segmentace službou) → čtení →
  zápis (`grade=read`); vrací zprávu za větu: zapsáno / fragment /
  zbytek / otevřené položky. Aktivace a diskurz běží přes celý dokument
  (téma dokumentu = první entita nadpisu/první věty).
- `say(text)` — tah dialogu: `?` → otázka → odpověď (`Answer` s verdiktem,
  důkazem, stupněm, zdroji, propadem); jinak tvrzení → čtení → zápis
  (`grade=said`); opravy: „Ne, …“ / „To není pravda.“ → odvolání
  posledního tvrzení s důvodem a zápis opravy; „Ne každý pes.“ → přepis
  kvantifikátoru poslední věty; příkazy `!zapomeň s0042`, `!role v+Loc =
  kde` (naučí výchozí), `!otevřené`, `!odpověz o12 kde`.
- `open()` — backlog otevřených položek; `resolve(item, value)` povýší
  výrok (odvolá s důvodem „doplněno“, zapíše nový).
- žurnál tahů, `replay(journal)` ⇒ týž program (determinismus: „teď“ =
  číslo tahu).

## 9 · Render (`render.py`)

Šablony jako data (`cs` profil). Odpověď = verdikt / výplň + důvod
(zdrojová věta, řetěz) + doložka stupně („přečteno z textu; role kde
z tvaru v+Loc [výchozí]“; „řekls to“; „odvozeno: jezevčík ⊆ pes,
psi štěkají [∀ výchozí]“). Chybějící šablona je chyba, ne fallback.

## 10 · Měření (`bench.py`) — hlavní metrika je znalost získaná z textu

Korpus conBond2 (`data/raw/*.txt`, 66 dokumentů) a zlaté otázky
(`otazky.json` 682 kde/kdy s číslem zdrojové věty; `etalon.json` 40;
`conbond.json` 95):

1. **Míra zápisu:** vět / zapsaných výroků / rolí na výrok / podíl
   tokenů ve zbytku / otevřených položek na větu — po dokumentech.
2. **QA přesnost:** dokument se vloží, otázky se položí; odpověď sedí,
   když očekávaný řetězec (nebo jeho lemma) je mezi výplněmi / v odpovědi.
   Rozklad chyb: špatné čtení × chybějící koreference × chybějící čas
   × logika × render.
3. **Dialogy A–F ze zadání conbond4** jako testy chování (učení můstku,
   „co neplyne“, sylogismus, prostor a čas, výjimka NOT, instance a jméno).
4. **Adversariální sada z conbond4** přenesená s novým očekáváním: kde
   conbond4 „nezapsal“, conbond5 zapíše a odpověď nese stupeň; **nikde
   tichá nepravda** („Bydlí Petr v Brně?“ → NEVÍM).
5. Determinismus: dva běhy nad týmž korpusem dají týž JSON.

Cíl v1: ≥ 90 % vět korpusu zapsáno (výrok + ≥ 1 role); QA přesnost
měřená a vypsaná s rozkladem (dnes conbond4 = 0 %); dialogy A–F zelené.

## 11 · Meze v1 (řečené, ne mlčené)

Koreference jen aktivací (rod/číslo + čerstvost); čas jen body / roky /
intervaly s `before` a obsažením; bez plné predikátové logiky (algebra
skupin + reifikace hloubky 1); modalita jako příznak výroku, ne operátor;
generování češtiny šablonami; bez učení rankeru. Každá mez se v odpovědi
hlásí („trvání stavů neumím“), nikdy tiše.

## 12 · Uspořádání repa

```
conbond5/
  cb5/ oracle.py read.py chronos.py memory.py logic.py recall.py
       dialog.py render.py bench.py cli.py
  tests/ (pytest; zlaté rozbory jako JSON data; renaming testy)
  data/ (odkaz na conBond2 korpus — klonuje bench; keš rozborů)
  docs/superpowers/specs/, docs/superpowers/plans/
  README.md
```

Python 3.11, závislosti: `networkx` (graf, export pro viewBase); dev:
`pytest`, `mypy`. Docstringy česky, bohaté (proč / vstup / výstup).
Testy hermetické: UDPipe jen přes nahrané rozbory; živý běh je `bench`.
