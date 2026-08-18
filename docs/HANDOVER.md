# conbond5 — předávka (průběžně aktualizovaná)

**Poslední aktualizace:** 17. 8. 2026 (HEAD viz `git log -1`).
**Repo:** https://github.com/alchy/conbond5 · **Úvod s ukázkami:** [`UVOD.md`](UVOD.md) (výstupy generuje `docs/ukazky.py`) · **Koncept:** [`KONCEPT.md`](KONCEPT.md) ·
**Návrh v1:** [`superpowers/specs/2026-08-16-conbond5-design.md`](superpowers/specs/2026-08-16-conbond5-design.md) ·
**Plán v1:** [`superpowers/plans/2026-08-16-conbond5-v1.md`](superpowers/plans/2026-08-16-conbond5-v1.md) (10 úkolů, hotovo).

## 1 · Jak to spustit

```bash
cd ~/Projects/conbond5
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pip install -e ~/Projects/viewBase2/python         # jen pro živý graf (volitelné)
.venv/bin/python -m pytest -q && .venv/bin/python -m mypy cb5 # hermetické testy (nahrané rozbory), typy
.venv/bin/python -m cb5 chat --pamet moje.json --zurnal rozhovor.jsonl   # REPL; !nápověda
.venv/bin/python -m cb5.viewbase_app --pamet moje.json [--vazby moduly/cas_a_veliciny.txt] [--user workbench]  # graf + konzole v prohlížeči (ukládá po každém tahu: moje.json + moje.jsonl)
.venv/bin/python -m cb5 replay rozhovor.jsonl                  # deterministické přehrání
.venv/bin/python -m cb5.bench [--dok alois_jirásek] [--vypis|--jen-chyby]   # měření nad korpusem conBond2
```

**viewBase2 (živý graf).** Adaptér `cb5/viewbase_app.py` jede na modelu
`Project` → `Screen` → okna (dřív jedno `vb.Canvas` a `vb.serve(canvas)`).
Uživatel viewBase2 je v konfiguraci (`VIEWBASE_USER = "workbench"`, přebije
ho `--user`); jeho TOTP tajemství a QR **nejsou v gitu** — vzniknou při první
instanciaci v `~/.viewbase/user-<jméno>/` (0600) a naskenují se do
autentikátoru z `cat ~/.viewbase/user-workbench/totp-workbench.txt`. Odemykají
zabezpečená okna (`secured=True`), která tenhle adaptér zatím nepoužívá.


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
| `cb5/chronos.py` | čas: datum/rok/interval/století/pojmenované/relativní („před 2 miliardami let“); `before`, `within`, `overlap` |
| `cb5/defaults.py` | **výchozí volby jako data**: role z předložky+pádu, determinátory, částice, modální slovesa, tázací slova, místa, synonyma, inverze vztahů, srovnávací osivo, veličiny |
| `cb5/read.py` | rozbor → predikace (sloveso/kopula/fragment; role; koordinace; vnořené, vztažné, přívlastkové výroky; genitivní zúžení `⟨…⟩`; tituly a cizí jména; závorka; elipsa; věk; srovnání; definice; veličiny; číslovky slovem, `8×8`, **rozsahy** „30 000–50 000“ / „1–4,5 km“ (`count` + `hi` + `count_text`), **substantivum veličiny s hodnotou** „do velikosti 12–14 mm“ → role `velikost`; díry; **podmínkové věty** „X, pokud/když Y“ → role `podmínka` (Y se netvrdí, `embedded`); **pravidla z věty s proměnnou** „Každý, kdo …“ / „Kdo …, ten …“ / „Pokud někdo …“ / „Nikdo …“ → term `var` (X); neosobní „prší“, „je mokro“ bez podmětu; účelová věta „aby …“ = role `účel` (netvrdí se, odpovídá na „proč“), časová věta „když/než/jakmile …“ = role `kdy` (odpověď je věta), příčinná „protože/kvůli“ = `proč`; nevyslovený podmět = jméno v podmětu předcházející vedlejší věty téže věty (shoda rodu)); **každý token má místo, jinak zbytek** |
| `cb5/memory.py` | graf výroků: uzly, `attach/revoke/inspect` (odvolání definičního výroku **vypne i naučenou vazbu**), uzávěry (`member*/subset*/within*/same_as*`, strukturální ⊆ přes zúžení, **otec ⊆ rodič ⇒ otec⟨Jana⟩ ⊆ rodič⟨Jana⟩**; `within` i z „leží/nachází se v“ a „je část X“), disjunktnost, výjimky, pravidla, aktivace (sliding window), měkké hrany, `graph()`, JSON, `learned_program()` = **modul vazeb** |
| `cb5/ground.py` | čtení → paměť: identita jmen („Jmenuje se Rex.“ připíše jméno bezejmennému referentu, předmětové zájmeno ≠ podmět věty), (celé jméno, viděné tvary, třída↔jméno, titul; **„Petr má bratra Karla“ → Karel ∈ bratr⟨Petr⟩**, u koordinovaného podmětu ke každému), instance z neurčité zmínky, pro‑drop/zájmena (aktivace, téma dokumentu), přivlastnění, otevřené položky |
| `cb5/logic.py` | hodnocení: shoda dotazu s výroky přes uzávěry, NE/KONFLIKT/MOŽNÁ, **„proč“** (příčinná věta „protože…“ / „kvůli“ = role `proč`, odpověď je vnořený výrok), wh‑otázka nad záporným výrokem („Proč Petr nepřišel?“) hledá záporný výrok, kladná wh‑otázka × záporný výrok → **NE „předpoklad otázky neplatí“**, dotaz `být(kde)` sedí i na slovesa umístění (`LOCATIVE_VERBS`: nacházet_se, ležet…, přiznaně), wh‑výčty (rodina rolí, místo uvnitř, užší shoda, **sloučení částečných časů** „v dubnu“+„roku 1975“, tranzitivita umístění), definice/třídy, meta‑otázky, srovnání, veličiny + můstek, vztahová jména (`rel_members`: přímo, inverze, naučené řetězy), pravidla; **podmínka**: výrok s rolí `podmínka` platí, jen když podmínka (s dosazenými proměnnými, `cond_query`) plyne z paměti — jinak „platí jen pod podmínkou: … — to nevím“; proměnná `X` se váže z dotazu (`X := Petr`) a u wh‑otázky se vyčísluje z podmínky |
| `cb5/recall.py` | propad „vím: …“ (jen řadí) |
| `cb5/render.py` | verdikt + důvod + zdroj + doložka stupně |
| `cb5/dialog.py` | `Session`: `ingest`, `say` (otázky, tvrzení, opravy „Ne, …“/„To není pravda.“/„Ne každý X.“, konflikt), **učení z vět** (definice srovnávacích slov, vztahových jmen), příkazy `!…` (i bez `!`), backlog, žurnál, `replay`, **`!ulož-vazby` / `!načti-vazby`** (modul vazeb) |
| `cb5/bench.py` | měření: míra zápisu + QA přesnost po sadách (ruční × generované), sdílená znalost (`vztahy_příbuzenské` k rodině Novákových), rozklad chyb → `mereni/` |
| `cb5/sablony.py` | **šablony pro vysvětlení vztahu** (`!šablony`, `!uč druh jezevčík pes`, okno „Vysvětlit vztah“ ve viewBase) + **návrh šablony při NEVÍM** (můstek, srovnání, složený vztah, vyloučení, **překryv**, **porovnání**) s odpovědí `ano` / `ne` (pamatuje se) / `jen tady`; při NEVÍM na sloveso, o němž nic není, ale podmět má výrok se stejnými rolemi pod jiným slovesem, navrhne **synonymum** („Kde učil Jirásek?“ → `!uč synonymum učit = působit`). Binární pravidla `Q(A,B) ⇐ TEST(hodnota u A, hodnota u B)`: překryv intervalů (`potkat_se ⇐ žít`), porovnání veličin (`vejít ⇐ délka <=`) — vrstva nad primitivními fakty (§ 5/0) |
| `cb5/cli.py`, `cb5/viewbase_app.py` | REPL a živý graf |
| `moduly/` | **moduly vazeb** (textové programy, viz `moduly/README.md`): `cas_a_veliciny.txt` (starší/mladší, potkat_se ⇐ překryv žít, vejít ⇐ délka <=) |

Naučené věci drží **paměť** (`Memory.learned`: `roles`, `synonyms`,
`comparatives`, `rel_defs`, `inverse`, `binary`, `refused`) — ne kód; dvě paměti
se neovlivní. **Modul vazeb** (`!ulož-vazby vazby.txt`) je textový program
přehratelných příkazů bez faktů (`!role`, `!synonymum`, `!srovnání`, `!uč
složený/inverze/překryv/porovnání`, `!pravidlo`, `!výjimka`); `!načti-vazby`
ho pustí touž cestou jako dialog, takže každá vazba má i v cílové paměti výrok
s proveniencí a dá se odvolat. Tak lze skládat modulární znalost: fakta z textu
+ vrstva vazeb (příbuzenství, časové překryvy, veličiny) z modulu.

## 3 · Stav měření (17. 8. 2026, `mereni/bench-vse.md`)

| | conbond4 (16. 8.) | conbond5 |
|---|---|---|
| korpus conbond4 (238 vět) zapsáno | 8 | 233 s rolí, zbytek 5,6 % |
| korpus conBond2 (14 354 vět) zapsáno | — | 14 354 (38 513 výroků, zbytek 8,3 %, 9 600 otevřených) |
| **ručně psané otázky (70)** | 0 | **60 (86 %)** — etalon 25/32, conbond 35/38 |
| generované otázky (682, proxy) | 0 | 444 (65 %); 581 má odpověď v textu |
| dialogy A–F ze zadání conbond4 | — | zelené; dialog A vč. „nejvýše 130 km/h“ (výchozí můstek) |
| testy / typy | — | 117 pytest, mypy čistý |

Zbývající ruční chyby (etalon): „Kolik procent je Antarktida větší než
Evropa?“ (procenta + komparativ), „Jaká je nejnižší naměřená teplota na
Zemi?“ (superlativ + míra se záporným číslem), „Kde studoval Hrabal práva?“ (koordinace v dlouhé
větě), „Na kolika polích…“ (šachovnice ∈ deska rozdělená na 64 polí — řetěz přes appos), „Je kůň
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
- Nic se nemaže, jen odvolá — **i vazby**: `!zapomeň s0004` na výrok
  `definice`/`definice_vztahu`/`inverze`/`binární_pravidlo` vypne příslušnou
  naučenou vazbu (`Memory._unlearn`); modul vazeb je proto program, ne výpis
  slovníku (`learned` se nikdy nekopíruje slepě).
- Vložená věta pod „pokud/jestliže/když(přít.)/aby/než/dokud/aniž“ se **netvrdí**
  (`status=embedded`, v `!program` ✗(podmínka)); věta pod „protože/přestože/když(min.)/že“
  se tvrdí; pod slovesem mluvení/myšlení („Ježíš kázal, že Bůh je láska“) se tvrdí
  **s doložkou „podle Ježíš (kázat)“**, kterou odpověď vždy vypíše (`SPEECH_VERBS`).
- Sliding window = aktivace v grafu (podmět +0,5, téma dokumentu +0,3 za větu,
  vyhasínání 0,6 za tah); pro‑drop dává přednost tématu, dokud jiný kandidát
  není 3× čerstvější.

## 5 · Otevřené směry (v pořadí, jak dávají smysl)

Co už je (rozhodnutí J. 17. 8.: **vysvětlování vztahů = šablony, ne volný dialog**;
systém se ptá sám jen při NEVÍM, JEDNA předvyplněná šablona s evidencí, `ano`/`ne`/`jen tady`):
vrstvy znalostní báze (jádro → primitivní fakta z textu → odvozené predikáty jako
pravidla nad nimi; návrh při NEVÍM nabízí jen to, co má vstupy v nižší vrstvě; každý
odvozený verdikt nese řetěz až k větám), moduly vazeb (`moduly/`, `!ulož-vazby`,
`--vazby`), odvolání vazby, **pravidla z věty** („Kdo …, ten …“, „Každý, kdo …“,
„Každý pes, který štěká, …“, „Pokud někdo …“, „X, pokud Y“, „Nikdo …“), podmínkové/
účelové/časové/příčinné věty jako role, „proč“, rozsahy, veličiny se synonymy,
vztahová jména (⊆ přenos na cíl, „má bratra Karla“), doložka „podle koho“.

1. **Pravidlo s hodnotou a komparátorem** z věty: „Kdo jede po dálnici, jede nejvýše
   maximální rychlostí dálnice.“ (dnes výchozí můstek u veličin + `!pravidlo`); víc
   proměnných najednou („Kdo koho …“); „ten“ jako podmět bez vztažné věty; podmínky
   s časem („dokud“, „než“) — dnes jen `embedded`/`kdy`.
2. Mezera pro **inverzi/roli** v návrhu při NEVÍM; šablona „mez“; víc testů (překryv
   i „před/po“, porovnání s tolerancí, víc veličin najednou); modul `moduly/pribuzenstvi.txt`.
3. Otázka nemá zakládat uzly: „Kdo je Karel Čapek?“ dnes vytvoří entitu bez výroků
   (v grafu se nezobrazuje, v paměti je jako referent pro další tah — I‑12 jen zčásti).
4. Překlepy ve slovech mimo jména („mezil lety“) — dnes zbytek/role `jak`; kandidát:
   oprava z tvarů, které paměť viděla (jako diakritika), přiznaná v odpovědi.
5. **Disjunktnost tříd** z textu („Šelmy a kopytníci jsou různé řády“) → NE.
6. Procenta a rozdíly („o 40 % větší“); superlativy („nejnižší naměřená teplota“).
7. Kandidátní čtení u homonym na začátku věty („Jí Ronik maso?“ ↔ zájmeno).
8. Časově ohraničená pravda („bydlel v Praze do roku 2000“ × „Kde bydlí?“) — dnes
   se čas jen ukládá jako role, verdikt ho neváží.
9. viewBase: barvy podle stupně, zvýraznění důkazu odpovědi jako cesty.

## 6 · Souběh s conbond6

conbond6 (`~/Projects/conbond6`, jiné sezení) startoval klonem conbond5 v1
(HEAD `c503b68`) a jde vlastní cestou (statusy výroků, registr referentů,
bench jako balíček). Do conbond5 commituje jen úloha conbond5; obě strany se
mohou inspirovat, nic se nemergeuje automaticky.
