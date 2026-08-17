# conbond5 — konverzační systém s grafovou pamětí a logickým hodnocením výroků

Systém, který každou českou větu textu **zapíše do grafové paměti** jako
výrok s epistemickým stupněm a nad pamětí **hodnotí výroky** — ANO / NE /
NEVÍM s důkazem a citací zdrojové věty — v dialogu s člověkem, který ho
tímtéž dialogem opravuje a doučuje.

Syntéza conBond2 (korpus + zlaté otázky, aktivační pole), conBond3
(„nic se neztrácí“, retrieval jako propad nad týmž grafem, JSON
persistence) a conbond4 (reifikované vztahy s rolemi, entita ≠ jméno,
provenience + odvolání, uzávěry, verdikty s důkazem, determinismus).
Návrh: [`docs/superpowers/specs/2026-08-16-conbond5-design.md`](docs/superpowers/specs/2026-08-16-conbond5-design.md),
plán: [`docs/superpowers/plans/2026-08-16-conbond5-v1.md`](docs/superpowers/plans/2026-08-16-conbond5-v1.md).

## Proč (a v čem je to jinak než conbond4)

conbond4 měl nad korpusem 220/238 vět přečteno, ale **8 zapsáno** — brána
zápisu s osmi blokátory nepustila nic, na co zbyla jediná otázka. Vznikl
„interaktivní analyzátor neznalosti“. conbond5 obrací tři věci:

1. **Čtení se vždy zapíše.** Co se přečetlo, jde do paměti; co ne, jde
   tam taky — jako *zbytek* na téže větě, viditelný. Otázky, které by
   conbond4 kladl dopředu, jsou *otevřené položky* (backlog `!otevřené`):
   neblokují nic, kdykoli je lze zodpovědět (`!odpověz o0001 kde`).
2. **Každý výrok má stupeň** — `said` (řekls to) · `read` (přečteno
   z textu) · `derived` (odvozeno; dědí nejslabší premisu) — a seznam
   **výchozích voleb**, které při čtení padly (∀ z generického prézentu,
   `kde` z `v+Loc`, nevyslovený podmět z aktivace, kopula → subset…).
   Odpověď to vždy říká a cituje větu.
3. **Výchozí volby jsou data** (`cb5/defaults.py`), přeučitelná dialogem
   (`!role přes+Acc = kudy`, `!synonymum kázat = hlásat`, `!pravidlo
   jet(kam:X) => být(kde:X)`, `!výjimka létat pták tučňák`).

Guard, který zůstává: **pravdivost neteče po měkké hraně** — aktivace
(sliding window kontextu) jen řadí a navrhuje, nikdy netvrdí.

## Rychlý start

Předpoklad: služba UDPipe `cb-udpipe` na `127.0.0.1:42200`
([conbond4-deps](https://github.com/alchy/conbond4-deps) nebo conBond3).

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                 # 89 testů, hermeticky (nahrané rozbory)
.venv/bin/python -m cb5 chat                  # REPL
.venv/bin/python -m cb5.bench --dok alois_jirásek --vypis   # měření nad korpusem
```

```
» Alois Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha) byl český prozaik, dramatik, středoškolský učitel, a politik.
✓ zapsáno [s0001] být(kdo: Alois Jirásek, co: ∃prozaik (český) + ∃dramatik + ∃učitel (středoškolský) + ∃politik) ⟨member⟩
✓ zapsáno [s0002] narodit_se(kdo: Alois Jirásek, kdy: 23. 8. 1851, kde: Hronov)   [životopisná závorka]
✓ zapsáno [s0003] zemřít(kdo: Alois Jirásek, kdy: 12. 3. 1930, kde: Praha)        [životopisná závorka]
» Celý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.
✓ zapsáno [s0004] pracovat(kdo: Alois Jirásek, jak dlouho: život, jako: ∃učitel, kde: ∃gymnázium + ∃Litomyšl + ∃Praha, pořadí: nejprve + poté)
   [kdo:pro-drop z kontextu; kdo: „nevyslovený podmět“ = Alois Jirásek (z aktivace)]
» Kde pracoval Alois Jirásek?
→ gymnázium; Litomyšl; Praha
   - pracovat(kdo: Alois Jirásek, …)  [s0004]
       zdroj: „Celý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.“ (dialog, věta 2)
   [řekls to; kdo: „nevyslovený podmět“ = Alois Jirásek (z aktivace)]
» Pes štěká.            » Jezevčík je pes.
» Štěká jezevčík?
→ ANO
   - štěkat(kdo: ∀pes)  [s0005]     - být(kdo: ∀jezevčík, co: ∃pes) ⟨subset⟩  [s0006]
   ↳ jezevčík ⊆ pes (∀ se přenáší dolů)
   [odvozeno z: řekls to; kdo:∀ generický prézens]
» Petr bydlí v Praze.   » Bydlí Petr v Brně?
→ NEVÍM
   chybí: o Brno nevím nic
   vím:  - bydlet(kdo: Petr, kde: Praha)  — zdroj: „Petr bydlí v Praze.“
```

## Moduly

| modul | co dělá |
|---|---|
| `cb5/oracle.py` | UDPipe fasáda s proveniencí modelu; `CachedOracle` (JSON keš), `RecordedOracle` (testy bez sítě) |
| `cb5/chronos.py` | čas jako data: datum, rok, interval, století, pojmenované časy; `before`, `within` |
| `cb5/defaults.py` | výchozí volby jako data: role z předložky + pádu + druhu výplně, determinátory → kvantifikátor, částice, modální slovesa, tázací slova, synonyma predikátů |
| `cb5/read.py` | rozbor → predikace: sloveso / kopula / fragment, role, negace, modalita, koordinace, vnořené a vztažné věty, přívlastky jako výroky vedle věty, životopisná závorka; **každý token má místo**, jinak je ve zbytku |
| `cb5/memory.py` | graf výroků: uzly (entita, group i zúžená, místo, čas), `attach/revoke/inspect`, uzávěry `member*/subset*/within*/same_as*`, čas, disjunktnost, výjimky, pravidla, aktivace, měkké hrany, `graph()` (networkx → viewBase), JSON |
| `cb5/ground.py` | čtení → paměť: identita (částečná jména), instance z neurčité zmínky, koreference aktivací / téma dokumentu, přivlastnění, otevřené položky |
| `cb5/logic.py` | shoda dotazu s výroky (každá role dotazu musí mít protějšek), distribuce ∀ dolů, negace → NE, disjunktnost, počty, modalita → MOŽNÁ, wh‑výčty vč. rodiny rolí místa/času, definice, pravidla, výjimky |
| `cb5/recall.py` | propad: co paměť o uzlech z otázky ví (jen řadí) |
| `cb5/render.py` | verdikt + důvod + zdroj + doložka stupně (šablony jako data) |
| `cb5/dialog.py` | `Session`: `ingest`, `say`, opravy („Ne, …“, „To není pravda.“, „Ne každý X.“), hlášení konfliktu, příkazy, backlog, žurnál a `replay` |
| `cb5/bench.py` | měření nad korpusem conBond2 (66 wiki dokumentů, 682 + 135 zlatých otázek) |

## Měření (17. 8. 2026, `mereni/bench-vse.md`)

`python -m cb5.bench` klonuje conBond2 do `data/corpus/`, každý dokument
vloží do čerstvé paměti a položí k němu zlaté otázky. **Sady se hlásí
zvlášť a nesčítají**: `etalon.json` a `conbond.json` jsou psané ručně
(smysluplné otázky — hlavní metrika); `otazky.json` (682) si conBond2
vygeneroval šablonou „Kdy/Kde + sloveso + jméno“ a jsou často
kostrbaté až nesmyslné („Kdy trávil Arnošt Lustig?“) — slouží jen jako
hrubá proxy „dostal se fakt z věty do paměti“. Rozbory se kešují, druhý
běh trvá vteřiny; bible z ručních sad v korpusu není (vypíše se).

| | conbond4 (16. 8.) | conbond5 v1 (17. 8.) |
|---|---|---|
| korpus conbond4 (238 vět): zapsáno | 8 | **233 s rolí**, zbytek 5,6 % tokenů |
| korpus conBond2 (73 dok., 14 354 vět): zapsáno | — | **14 354** (40 590 výroků, zbytek 8,6 % tokenů, 12 063 otevřených položek) |
| **ručně psané otázky (70): správně** | 0 | **46 (66 %)** — etalon 19/32, conbond 27/38; 57 má odpověď aspoň v „vím: …“; u `mode=unsure` je správně NEVÍM (jednou odpověděl navíc: „S kým se oženil Hrabal?“ → Eliška Plevová — pravdivě) |
| generované otázky (682): správná výplň | 0 | 421 (62 %); 577 v textu odpovědi |
| rozklad chyb (všech 752) | — | role/logika 117 · špatná výplň 114 · bez výroku 45 · entita neznámá 7 · predikát chybí 1 · odpověděl navíc 1 |
| dialogy A–F ze zadání conbond4 | — | zelené (`tests/test_dialogues_af.py`) |
| „Bydlí Petr v Brně?“ po „Petr bydlí v Praze.“ | ANO (nepravda) | NEVÍM + „vím: bydlí v Praze“ |

Čas: celý korpus se z keše vloží za ~10 s a 752 otázek se zodpoví za
~4 s. Poctivost zůstává: každá odpověď cituje větu a přiznává výchozí
volby (∀ z generického prézentu, podmět z aktivace, „platí o užší třídě“,
„role kam — ptal ses kde“…).

## Meze v1 (řečené, ne mlčené)

Koreference jen aktivací (rod/číslo + čerstvost) a tématem dokumentu; čas
jen body / roky / intervaly; bez plné predikátové logiky (algebra skupin +
reifikace hloubky 1); modalita jako příznak výroku; čeština na výstupu
strukturovaně (role: výplň), ne volnou větou; bez rankeru čtení. Každá mez
se v odpovědi hlásí, nikdy tiše.
