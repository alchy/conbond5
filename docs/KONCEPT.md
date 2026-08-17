# conbond5 — koncept

**Jedna věta.** Konverzační systém s pamětí, který se **učí z textu**: každou
českou větu zapíše do grafové paměti jako výrok s epistemickým stupněm, nad
pamětí **logicky hodnotí výroky** (ANO / NE / NEVÍM s důkazem a citací
zdrojové věty) a **vazby mezi pojmy se učí z definic v textu i v dialogu**
— jádro operací je malé a pevné, všechno významové jsou data.

## Odkud přichází

| projekt | co se osvědčilo a přenáší | čeho se conbond5 vzdává |
|---|---|---|
| conBond2 | korpus (66 wiki dokumentů) + zlaté otázky, aktivační pole jako kontext | retrieval jako hlavní odpověď |
| conBond3 | „nic se neztrácí“ (obj + obl + advmod + nmod, jinak *unparsed* s důvodem), retrieval jako **propad** nad týmž substrátem, JSON persistence, učené vzory jako data | formální vrstva, která mlčí, když si není jistá |
| conbond4 | reifikovaný vztah s rolemi, entita ≠ jméno, group, provenience + odvolání (nic se nemaže), uzávěry `member/subset/within/before`, verdikt vždy s důkazem, determinismus, orákulum nad UDPipe, zlaté rozbory jako testovací data | **brána zápisu**: 8 blokátorů, které z 238 vět zapsaly 8 („interaktivní analyzátor neznalosti“) |

## Tři zásady

1. **Čtení se vždy zapíše.** Co se přečetlo, jde do paměti; co ne, jde tam
   také — jako viditelný *zbytek* na téže větě. Otázky, které by conbond4
   kladl dopředu, jsou *otevřené položky* (backlog `!otevřené`): neblokují
   nic, kdykoli je lze zodpovědět. Výjimka: věta bez přísudku, kde většina
   slov skončí ve zbytku → „nerozumím“ a nic se nezapíše.
2. **Každý výrok má stupeň** — `said` (řekls to) · `read` (přečteno
   z textu) · `derived` (odvozeno; dědí nejslabší premisu) — a seznam
   **výchozích voleb**, které při čtení padly (∀ z generického prézentu,
   `kde` z `v+Loc`, podmět z aktivace, kopula → subset, „platí o užší
   třídě“, „role kam — ptal ses kde“, můstek…). Odpověď to vždy říká.
3. **Výchozí volby jsou data** (`cb5/defaults.py`) a **vazby se učí
   z textu i dialogu**: role z předložky+pádu, synonyma predikátů, srovnávací
   slova („Delší je ten, kdo měří víc.“), vztahová jména („Tchán je otec
   manžela nebo manželky.“ → řetěz `otec∘manžel`), můstková pravidla
   (`!pravidlo jet(kam:X) => být(kde:X)`), výjimky (`!výjimka létat pták
   tučňák`). Jádro nikdy nezíská novou sémantiku dialogem — jen se dozví,
   *které slovo spouští kterou už existující operaci* (§ 3.6 zadání conbond4).
   Naučené vazby jsou v paměti (`learned`) s výrokem‑proveniencí; dají se
   vypsat jako **modul vazeb** (`!ulož-vazby`) — program příkazů bez faktů —
   a přehrát do jiné paměti (`!načti-vazby`); tak lze skládat vrstvy: fakta
   z textu + vazby (příbuzenství, časové překryvy, veličiny) z modulů.
   Věta sama může být pravidlo: „Každý, kdo bydlí v Praze, bydlí v Česku.“
   se zapíše jako výrok s proměnnou X a podmínkou (vložený výrok, který se
   netvrdí); dotaz proměnnou váže a podmínku ověří v paměti — odvozený
   verdikt nese obě věty.

Guard, který platí doslova (I‑8 conbond4): **pravdivost neteče po měkké
hraně** — aktivace (sliding window kontextu) jen řadí a navrhuje, nikdy
netvrdí; blízkost není důkaz.

## Paměť je graf

Uzly: entita (anonymní identita se jmény), group (třída podle lemmatu,
případně zúžená přívlastky `mazlíček[domácí]` nebo vztahem
`otec⟨Petr Novák⟩`), místo, čas, hodnota, výrok, dokument, věta.
Tvrdé hrany (pravdivost): `role:<jméno>`, `member`, `subset`, `within`,
`same_as`, `restricts`/`rel` (zúžení ⇒ ⊆ strukturálně), `source`.
Měkké hrany (jen aktivace): spoluvýskyt ve větě, následnost. Export
`Memory.graph()` → networkx → viewBase (`python -m cb5.viewbase_app`:
živý graf + konzole dialogu v prohlížeči).

## Cesta věty

```
text ─(diakritika: obnova z toho, co už četl)─► UDPipe rozbor ─► ČTENÍ (tabulkově:
kořen = sloveso / kopula / fragment; role z deprelů + tabulek; koordinace, vnořené
a vztažné věty, přívlastky jako výroky vedle věty, životopisná závorka, elipsa
přísudku, veličiny; každý token má místo, jinak zbytek)
─► ZAKOTVENÍ (identita jmen i podle viděných tvarů, instance z neurčité zmínky,
pro‑drop/zájmena z aktivace nebo tématu dokumentu, přivlastnění, tituly, otevřené
položky) ─► PAMĚŤ (attach s proveniencí a stupněm; definice → naučené vazby)
```

## Cesta otázky

Táž čtečka (díra = tázací slovo: kde/kdy/kdo/co/kolik/jaký/čím/jak rychle…),
zakotvení bez zápisu (I‑12), pak **logika**: shoda dotazu s výroky — každá
role dotazu musí mít protějšek (proto „Bydlí Petr v Brně?“ → NEVÍM, ne ANO),
termy přes uzávěry (∀ dolů přes ∈/⊆, místa přes within, čas přes obsažení,
zúžení vztahem), negace → NE, disjunktnost, počty, modalita → MOŽNÁ, užší
shoda s přiznáním; wh‑výčty vč. rodiny rolí (kam za kde, přiznaně), místo
uvnitř výplně, definice/třídy, meta‑otázky („Co dělá/umí X?“, „Co víš o X?“,
„Jaké X znáš?“), srovnání a veličiny, vztahová jména s inverzemi a naučenými
řetězy, můstková pravidla. Když logika nedá verdikt: **propad** („vím: …“
z okolí uzlů, jen řadí) a co by rozhodlo.

## Měřítko

Ne počet otázek, ale **znalost získaná z textu**: `python -m cb5.bench` nad
korpusem conBond2 (14 354 vět, 66+ dokumentů) — kolik vět se zapsalo, kolik
zbylo ve zbytku, a hlavně kolik **ručně psaných** zlatých otázek systém zodpoví
z vloženého textu (generovaná sada je jen hrubá proxy). Každý běh vypíše
rozklad chyb; čísla jsou v `docs/HANDOVER.md` a `mereni/`.
