# conbond5 — předávka (průběžně aktualizovaná)

**Poslední aktualizace:** 17. 8. 2026 (HEAD viz `git log -1`).
**Repo:** https://github.com/alchy/conbond5 · **Koncept:** [`KONCEPT.md`](KONCEPT.md) ·
**Návrh v1:** [`superpowers/specs/2026-08-16-conbond5-design.md`](superpowers/specs/2026-08-16-conbond5-design.md) ·
**Plán v1:** [`superpowers/plans/2026-08-16-conbond5-v1.md`](superpowers/plans/2026-08-16-conbond5-v1.md) (10 úkolů, hotovo).

## 1 · Jak to spustit

```bash
cd ~/Projects/conbond5
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pip install -e ~/Projects/viewBase/python          # jen pro živý graf (volitelné)
.venv/bin/python -m pytest -q && .venv/bin/python -m mypy cb5 # hermetické testy (nahrané rozbory), typy
.venv/bin/python -m cb5 chat --pamet moje.json --zurnal rozhovor.jsonl   # REPL; !nápověda
.venv/bin/python -m cb5.viewbase_app --pamet moje.json         # graf + konzole v prohlížeči (ukládá po každém tahu: moje.json + moje.jsonl)
.venv/bin/python -m cb5 replay rozhovor.jsonl                  # deterministické přehrání
.venv/bin/python -m cb5.bench [--dok alois_jirásek] [--vypis|--jen-chyby]   # měření nad korpusem conBond2
```

Předpoklad: služba UDPipe `cb-udpipe` na `127.0.0.1:42200` (conBond3 nebo
[conbond4-deps](https://github.com/alchy/conbond4-deps)); model
`cs_all-ud-2.17-251125` (starší služba ho ve `/version` neuvádí — orákulum
doplní a v provenienci to označí `model?=`). Rozbory se kešují v
`data/cache/parses.json` (~70 MB, není v gitu); bez služby se čte jen z keše.
Testy síť nepotřebují (`tests/data/parses.json`; nové věty: přidat do
`tests/data/sentences.txt` a `python -m cb5.record tests/data/sentences.txt tests/data/parses.json`).

## 2 · Kde co je

| modul | odpovědnost |
|---|---|
| `cb5/oracle.py` | UDPipe fasáda s proveniencí, keš (`CachedOracle`), nahrávka pro testy (`RecordedOracle`) |
| `cb5/diakritika.py` | obnova háčků z toho, co už systém četl (slovník `data/cache/diakritika.json`, přestaví se, když je keš novější) |
| `cb5/chronos.py` | čas: datum/rok/interval/století/pojmenované; `before`, `within` |
| `cb5/defaults.py` | **výchozí volby jako data**: role z předložky+pádu, determinátory, částice, modální slovesa, tázací slova, místa, synonyma, inverze vztahů, srovnávací osivo, veličiny |
| `cb5/read.py` | rozbor → predikace (sloveso/kopula/fragment; role; koordinace; vnořené, vztažné, přívlastkové výroky; genitivní zúžení `⟨…⟩`; tituly a cizí jména; závorka; elipsa; věk; srovnání; definice; veličiny; díry); **každý token má místo, jinak zbytek** |
| `cb5/memory.py` | graf výroků: uzly, `attach/revoke/inspect`, uzávěry (`member*/subset*/within*/same_as*`, strukturální ⊆ přes zúžení), disjunktnost, výjimky, pravidla, aktivace (sliding window), měkké hrany, `graph()`, JSON |
| `cb5/ground.py` | čtení → paměť: identita jmen (celé jméno, viděné tvary, třída↔jméno, titul), instance z neurčité zmínky, pro‑drop/zájmena (aktivace, téma dokumentu), přivlastnění, otevřené položky |
| `cb5/logic.py` | hodnocení: shoda dotazu s výroky přes uzávěry, NE/KONFLIKT/MOŽNÁ, wh‑výčty (rodina rolí, místo uvnitř, užší shoda), definice/třídy, meta‑otázky, srovnání, veličiny + můstek, vztahová jména (`rel_members`: přímo, inverze, naučené řetězy), pravidla |
| `cb5/recall.py` | propad „vím: …“ (jen řadí) |
| `cb5/render.py` | verdikt + důvod + zdroj + doložka stupně |
| `cb5/dialog.py` | `Session`: `ingest`, `say` (otázky, tvrzení, opravy „Ne, …“/„To není pravda.“/„Ne každý X.“, konflikt), **učení z vět** (definice srovnávacích slov, vztahových jmen), příkazy `!…` (i bez `!`), backlog, žurnál, `replay` |
| `cb5/bench.py` | měření: míra zápisu + QA přesnost po sadách (ruční × generované), sdílená znalost (`vztahy_příbuzenské` k rodině Novákových), rozklad chyb → `mereni/` |
| `cb5/sablony.py` | **šablony pro vysvětlení vztahu** (`!šablony`, `!uč druh jezevčík pes`, okno „Vysvětlit vztah“ ve viewBase) + **návrh šablony při NEVÍM** (můstek, srovnání, složený vztah, vyloučení) s odpovědí `ano` / `ne` (pamatuje se) / `jen tady` |
| `cb5/cli.py`, `cb5/viewbase_app.py` | REPL a živý graf |

Naučené věci drží **paměť** (`Memory.learned`: `roles`, `synonyms`,
`comparatives`, `rel_defs`) — ne moduly; dvě paměti se neovlivní.

## 3 · Stav měření (17. 8. 2026, `mereni/bench-vse.md`)

| | conbond4 (16. 8.) | conbond5 |
|---|---|---|
| korpus conbond4 (238 vět) zapsáno | 8 | 233 s rolí, zbytek 5,6 % |
| korpus conBond2 (14 354 vět) zapsáno | — | 14 354 (38 987 výroků, zbytek 8,5 %, 10 277 otevřených) |
| **ručně psané otázky (70)** | 0 | **59 (84 %)** — etalon 24/32, conbond 35/38 |
| generované otázky (682, proxy) | 0 | 433 (63 %); 577 má odpověď v textu |
| dialogy A–F ze zadání conbond4 | — | zelené; dialog A vč. „nejvýše 130 km/h“ (výchozí můstek) |
| testy / typy | — | 100 pytest, mypy čistý |

Zbývající ruční chyby (etalon): „Kolik procent je Antarktida větší než
Evropa?“ (procenta + komparativ), „Jaká je nejnižší naměřená teplota na
Zemi?“ (superlativ + míra se záporným číslem), „Jak silný je ledový příkrov?“
(rozsah „1–4,5 km“), „Kde studoval Hrabal práva?“ (koordinace v dlouhé
větě), „Kdy se objevily první sinice?“ („před 2 miliardami let“ = čas), „Kolik
dělnic je v úlu…“ (rozsah 30 000–50 000), „Na kolika polích…“ („8×8“), „Je kůň
šelma?“ → NE (chce disjunktnost tříd), „Kdo napsal R.U.R.?“ (jméno s tečkami),
„Kde se narodila Božena Němcová?“ (víc pramenů, Vídeň v závorce s „rozená“).

## 4 · Rozhodnutí, která se nemají tiše měnit

- Nikdy brána zápisu. Nezapíše se jen šum („nerozumím“) — a řekne to.
- Odpověď vždy nese stupeň + výchozí volby + zdrojovou větu; **nikdy tichá nepravda**:
  role dotazu bez protějšku ve výroku = neshoda.
- Definiční tvar („X je Y Z‑u“) se **zapíše jako fakt a navíc** uloží řetěz
  (týž tvar má „Foton je částice světla“ i „Tchán je otec manžela“).
- Identita jmen: celé jméno / kanonické (nejdelší) jméno / viděný celý tvar;
  **nikdy jednotlivé slovo** („Nováková“ by scelila celou rodinu). Neznámé
  slovo s velkým písmenem na začátku věty = třída s příznakem `cap`; převede se
  na entitu, až se objeví jako vlastní jméno — a nikdy, když bylo viděno s malým
  písmenem. Entity a místa žijí v jednom prostoru jmen.
- Generované otázky conBond2 (`otazky.json`) jsou **proxy, ne měřítko** — hlavní
  číslo je z ručních sad; `mode=unsure` = správně NEVÍM.
- Bez diakritiky se doplní háčky jen z tvarů, které paměť viděla, a přizná se to.
- Sliding window = aktivace v grafu (podmět +0,5, téma dokumentu +0,3 za větu,
  vyhasínání 0,6 za tah); pro‑drop dává přednost tématu, dokud jiný kandidát
  není 3× čerstvější.

## 5 · Otevřené směry (v pořadí, jak dávají smysl)

0. **Vysvětlování vztahů = šablony, ne volný dialog** (rozhodnutí J. 17. 8.): systém
   se ptá sám jen při NEVÍM na otázku člověka, nabídne JEDNU předvyplněnou šablonu
   (hypotéza s evidencí), člověk potvrdí/odmítne. Dál rozšiřovat detekci mezer
   (synonymum predikátu, inverze, role) a šablonu „mez“ (dnes výchozí můstek u veličin).
1. **Můstková pravidla z věty** — dnes `!pravidlo`, šablona a výchozí můstek pro
   veličiny; cíl: „Kdo jede po dálnici, jede nejvýše maximální rychlostí
   dálnice.“ → pravidlo s hodnotou a komparátorem; obecně „Kdo …, ten …“.
2. **Sloučení částečných časů téhož děje** („v dubnu“ + „roku 1975“ → duben 1975).
3. **Tranzitivita umístění přes „být kde“** (sýr v lednici, lednice v Petrovicích).
4. **Disjunktnost tříd** z textu („Šelmy a kopytníci jsou různé řády“) → NE.
5. **Rozsahy a procenta** („1–4,5 km“, „30 000–50 000“, „o 40 %“), „8×8“.
6. Kandidátní čtení u homonym na začátku věty („Jí Ronik maso?“ ↔ zájmeno).
7. viewBase: barvy podle stupně, zvýraznění důkazu odpovědi jako cesty.

## 6 · Souběh s conbond6

conbond6 (`~/Projects/conbond6`, jiné sezení) startoval klonem conbond5 v1
(HEAD `c503b68`) a jde vlastní cestou (statusy výroků, registr referentů,
bench jako balíček). Do conbond5 commituje jen úloha conbond5; obě strany se
mohou inspirovat, nic se nemergeuje automaticky.
