# conbond5 — úvod a průvodce ukázkami

Tento text je pro čtenáře, který zná záměr projektu, ale ztratil přehled o tom, *jak* to dnes
funguje. Napřed principy (co je v paměti, jak se čte věta, jak se odpovídá), pak anatomie jedné
odpovědi, pak ukázky po tématech — **všechny výpisy níže jsou skutečné výstupy systému**
(vygenerované skriptem `docs/ukazky.py` nad aktuálním kódem, ne psané rukou; po změně kódu
ho pusť znovu a bloky vyměň). Podrobný stav, čísla a otevřené
směry jsou v [`HANDOVER.md`](HANDOVER.md), stručný koncept v [`KONCEPT.md`](KONCEPT.md).

Spuštění: `python -m cb5 chat` (terminál) nebo `python -m cb5.viewbase_app --pamet moje.json`
(živý graf + konzole v prohlížeči). Předpokládá běžící UDPipe na `127.0.0.1:42200`.

---

## 1 · Tři zásady (proč to vypadá, jak to vypadá)

1. **Čtení se vždy zapíše.** Každá věta skončí jako *výrok* v paměti. Co čtečka nezvládla
   zařadit, neztratí se — visí u výroku jako **zbytek** a v backlogu **otevřených položek**
   (`!otevřené`), které nic neblokují. Jediná výjimka je šum bez přísudku → „nerozumím“.
2. **Každý výrok má stupeň a seznam výchozích voleb.** Stupeň: `řekls to` (said) · `přečteno
   z textu` (read) · `odvozeno` (derived, dědí nejslabší premisu). Výchozí volba je každé
   rozhodnutí, které čtečka udělala „na dobrou víru“ (kvantifikátor ∀ z generického prézentu,
   `kde` z předložky+pádu, nevyslovený podmět z kontextu, kopula → ∈/⊆ …). Odpověď je vždy
   vypíše v hranaté závorce, takže je vidět, čemu věříš.
3. **Výchozí volby jsou data, vazby se učí.** Tabulky jsou v `cb5/defaults.py`; vazby mezi
   slovy (synonyma, vztahová jména, srovnávací slova, pravidla) se učí z textu, z dialogu a ze
   šablon — a drží je **paměť**, ne kód. Jádro operací (∈, ⊆, uvnitř, čas, počet, porovnání)
   se dialogem nemění; dialog jen říká, *které slovo spouští kterou operaci*.

Guard, který platí doslova: **pravdivost neteče po měkké hraně** — aktivace (kontext, sliding
window) jen řadí a navrhuje, nikdy netvrdí.

## 2 · Co je v paměti

Paměť (`cb5/memory.py`) je graf:

| uzel | příklad | poznámka |
|---|---|---|
| entita | `Alois Jirásek`, `Rex`, `e0002` (bezejmenný pes) | identita ≠ jméno; jména se připisují |
| třída (group) | `pes`, `prášek[prací]`, `otec⟨Petr Novák⟩` | zúžení přívlastkem `[…]` nebo vztahem `⟨…⟩` |
| místo, čas, hodnota | `Praha`, `1851`, `1900 – 2000`, `10 cm`, `30 000–50 000` | čas má osu (před/uvnitř/překryv) |
| výrok | `narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)` | predikát + role + polarita + modalita + stupeň + provenience |

**Role** výroku jsou pojmenované sloty (`kdo`, `co`, `kde`, `kdy`, `komu`, `čím`, `jako`,
`proč`, `účel`, `podmínka`, …). Role může držet uzly, **kvantifikátor** (`∀` třída obecně,
`∃` nějaký, `·` konkrétní), **počet** (`∃2 dcera`, `#40000`), **vnořený výrok** (věta v roli:
`kdy: [odejít(kdo: Jana)]`) nebo **proměnnou** pravidla (`kdo: X`).

**Jádrové vztahy** (kernel) jsou u kopuly: `⟨member⟩` X ∈ třída, `⟨subset⟩` třída ⊆ třída,
`⟨within⟩` místo uvnitř místa, `⟨same_as⟩` dvě jména téže věci. Nad nimi běží uzávěry
(∈ přes ⊆, ⊆ řetězem, uvnitř řetězem) — proto „Rex je pes“ + „Pes je šelma“ ⇒ Rex ∈ šelma.

Nic se **nemaže**: oprava nebo `!zapomeň` výrok *odvolá* (zůstane v `!program` s ✗ a
důvodem); odvolání definičního výroku vypne i naučenou vazbu. Vložené věty, které se
netvrdí (podmínky, účel), mají v `!program` značku ⊂.

## 3 · Cesta věty a otázky

```
text ─► (obnova diakritiky z toho, co už četl) ─► UDPipe rozbor
     ─► ČTENÍ (cb5/read.py): kořen = sloveso / kopula / fragment; role z deprelů + tabulek;
        koordinace, vnořené a vztažné věty, přívlastky, závorky, elipsa, věk, srovnání,
        definice, veličiny, číslovky, rozsahy, podmínky, proměnné; každý token má místo, jinak zbytek
     ─► ZAKOTVENÍ (cb5/ground.py): identita jmen, instance z neurčité zmínky, zájmena a nevyslovený
        podmět z aktivace/tématu, přivlastnění, tituly, pojmenování; otevřené položky
     ─► PAMĚŤ: attach s proveniencí a stupněm; definice → naučené vazby
```

Otázka jde touž čtečkou (díra = tázací slovo), zakotví se **bez zápisu** a jde do **logiky**
(`cb5/logic.py`): shoda dotazu s výroky přes uzávěry — každá role dotazu musí mít protějšek
(proto „Bydlí Petr v Brně?“ není ANO jen proto, že Petr někde bydlí) — negace → NE, počty,
rozsahy, modalita → MOŽNÁ, wh‑výčty, definice, veličiny, vztahová jména, pravidla, podmínky.
Když logika nedá verdikt, přijde **propad** „vím: …“ (jen řadí, netvrdí) a při NEVÍM případně
**návrh šablony** (systém se zeptá sám — jen na jednu věc, s evidencí).

## 4 · Anatomie odpovědi

```text
» Kde se narodil Alois Jirásek?
čtu: narodit_se(kde:?, kdo:·Alois Jirásek)        ← jak byla otázka přečtena (díra = ?)
→ Hronov                                           ← verdikt / výplň díry
   - narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)  [s0001]     ← premisa (id výroku)
       zdroj: „Alois Jirásek se narodil roku 1851 v Hronově.“ (dialog, věta 1)  ← citace věty
   ↳ synonymum: učit ~ působit                     ← kroky odvození (jsou‑li)
   [řekls to; kdo:pro-drop z kontextu]             ← stupeň; výchozí volby, na nichž to stojí
```

Verdikty: `ANO` / `NE` / `NEVÍM` / `MOŽNÁ` (text říká jen, že může/chce) / `KONFLIKT`
(pro i proti, oboje s důkazem). U wh‑otázek se místo verdiktu vypíší výplně, každá se svým
důkazem. `NE — předpoklad otázky neplatí` je odpověď na „Proč Petr přišel?“, když víme, že
nepřišel.

Symboly ve výpisu: `∀pes` obecně všichni psi · `∃maso` nějaké maso · `·Petr` konkrétní ·
`⟨member⟩` ∈ · `⟨subset⟩` ⊆ · `X` proměnná · `[…]` vnořená věta · `#40000` počet.

---

## 5 · Ukázky

### 5.1 Fakta, otázky, nevyslovený podmět, návrh synonyma

Druhá věta nemá podmět — doplní se z aktivace (poslední podmět), a odpověď to přizná.
„Kde učil?“ o „učit“ nic neví, ale vidí, že o Jiráskovi má „působit“ s toutéž rolí — nabídne
**jednu** šablonu; `ano` ji naučí a otázku zodpoví znovu. „Bydlí v Brně?“ zůstane NEVÍM
(Brno nikde není), žádná tichá nepravda.

```text
» Alois Jirásek se narodil roku 1851 v Hronově.
✓ zapsáno [s0001] narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)

» Působil jako učitel v Litomyšli.
✓ zapsáno [s0002] působit(kdo: Alois Jirásek, jako: ∃učitel, kde: Litomyšl)
   [kdo:pro-drop z kontextu; kdo: „nevyslovený podmět“ = Alois Jirásek (z aktivace)]

» Kde se narodil Alois Jirásek?
čtu: narodit_se(kde:?, kdo:·Alois Jirásek)
→ Hronov
   - narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)  [s0001]
       zdroj: „Alois Jirásek se narodil roku 1851 v Hronově.“ (dialog, věta 1)
   [řekls to]

» Kdy se narodil?
čtu: narodit_se(kdo:·∅, kdy:?)
→ 1851
   - narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)  [s0001]
       zdroj: „Alois Jirásek se narodil roku 1851 v Hronově.“ (dialog, věta 1)
   [řekls to]

» Kde učil Jirásek?
čtu: učit(kde:?, kdo:·Jirásek)
→ NEVÍM
   chybí: o „učit“ nemám žádný výrok
   vím:
   - působit(kdo: Alois Jirásek, jako: ∃učitel, kde: Litomyšl)  — zdroj: „Působil jako učitel v Litomyšli.“ (dialog, věta 2)
   - narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)  — zdroj: „Alois Jirásek se narodil roku 1851 v Hronově.“ (dialog, věta 1)
   ? o Alois Jirásek nemám „učit“, ale mám „působit“ se stejnými rolemi (kde). Znamená „učit“ totéž co „působit“?
   → šablona: !uč synonymum učit = působit   (odpověz „ano“ = naučit a odpovědět znovu, „ne“ = nenabízet, „jen tady“ = nechat)

» ano
naučeno: učit ~ působit
— znovu: Kde učil Jirásek?
čtu: učit(kde:?, kdo:·Jirásek)
→ Litomyšl
   - působit(kdo: Alois Jirásek, jako: ∃učitel, kde: Litomyšl)  [s0002]
       zdroj: „Působil jako učitel v Litomyšli.“ (dialog, věta 2)
   ↳ synonymum: učit ~ působit
   [řekls to; kdo:pro-drop z kontextu; kdo: „nevyslovený podmět“ = Alois Jirásek (z aktivace)]

» Bydlí Jirásek v Brně?
čtu: bydlet(kdo:·Jirásek, kde:·Brno)
→ NEVÍM
   chybí: o Brno nevím nic
   vím:
   - působit(kdo: Alois Jirásek, jako: ∃učitel, kde: Litomyšl)  — zdroj: „Působil jako učitel v Litomyšli.“ (dialog, věta 2)
   - narodit_se(kdo: Alois Jirásek, kdy: 1851, kde: Hronov)  — zdroj: „Alois Jirásek se narodil roku 1851 v Hronově.“ (dialog, věta 1)

» !program
s0001: narodit_se(kdo:·Alois Jirásek, kdy:·1851, kde:·Hronov) @said @dialog#1
s0002: působit(kdo:·Alois Jirásek, jako:∃učitel, kde:·Litomyšl) @said @dialog#2

```

### 5.2 Třídy: ∀, ∈, ⊆, výjimky

Generický prézens dává ∀; kopula s obecným podmětem je ⊆, s konkrétním ∈. Vlastnost třídy
se přenáší dolů přes ⊆/∈. Výjimka (`!výjimka`) zastaví přenos pro jednu podtřídu — o tučňákovi
pak systém *neví*, netvrdí opak.

```text
» Pes je šelma.
✓ zapsáno [s0001] být(kdo: ∀pes, co: ∃šelma) ⟨subset⟩
   [kdo:∀ generický prézens; kernel:subset (obecný podmět)]

» Šelmy jedí maso.
✓ zapsáno [s0002] jíst(kdo: ∀šelma, co: ∃maso)
   [kdo:∀ generický prézens]

» Rex je pes.
✓ zapsáno [s0003] být(kdo: Rex, co: ∃pes) ⟨member⟩
   [kernel:member (určitý podmět)]

» Jedí psi maso?
čtu: jíst(kdo:∀pes, co:∃maso)
→ ANO
   protože:
   - jíst(kdo: ∀šelma, co: ∃maso)  [s0002]
       zdroj: „Šelmy jedí maso.“ (dialog, věta 2)
   - být(kdo: ∀pes, co: ∃šelma) ⟨subset⟩  [s0001]
       zdroj: „Pes je šelma.“ (dialog, věta 1)
   ↳ pes ⊆ šelma (∀ se přenáší dolů)
   [odvozeno z: řekls to; kdo:∀ generický prézens]

» Je Rex šelma?
čtu: být(kdo:·Rex, co:∃šelma) ⟨member⟩
→ ANO
   protože:
   - být(kdo: Rex, co: ∃pes) ⟨member⟩  [s0003]
       zdroj: „Rex je pes.“ (dialog, věta 3)
   - být(kdo: ∀pes, co: ∃šelma) ⟨subset⟩  [s0001]
       zdroj: „Pes je šelma.“ (dialog, věta 1)
   ↳ Rex ∈ šelma
   [odvozeno z: řekls to]

» Tučňák je pták.
✓ zapsáno [s0004] být(kdo: ∀tučňák, co: ∃pták) ⟨subset⟩
   [kdo:∀ generický prézens; kernel:subset (obecný podmět)]

» Ptáci létají.
✓ zapsáno [s0005] létat(kdo: ∀pták)
   [kdo:∀ generický prézens]

» !výjimka létat pták tučňák
výjimka: létat o pták neplatí pro tučňák

» Létá tučňák?
čtu: létat(kdo:∀tučňák)
→ NEVÍM
   vím:
   - létat(kdo: ∀pták)  — zdroj: „Ptáci létají.“ (dialog, věta 5)
   - být(kdo: ∀tučňák, co: ∃pták) ⟨subset⟩  — zdroj: „Tučňák je pták.“ (dialog, věta 4)

» Létá vrabec?
čtu: létat(kdo:∀vrabec)
→ NEVÍM

» Vrabec je pták.
✓ zapsáno [s0006] být(kdo: ∀vrabec, co: ∃pták) ⟨subset⟩
   [kdo:∀ generický prézens; kernel:subset (obecný podmět)]

» Létá vrabec?
čtu: létat(kdo:∀vrabec)
→ ANO
   protože:
   - létat(kdo: ∀pták)  [s0005]
       zdroj: „Ptáci létají.“ (dialog, věta 5)
   - být(kdo: ∀vrabec, co: ∃pták) ⟨subset⟩  [s0006]
       zdroj: „Vrabec je pták.“ (dialog, věta 6)
   ↳ vrabec ⊆ pták (∀ se přenáší dolů)
   [odvozeno z: řekls to; kdo:∀ generický prézens]

```

### 5.3 Referenty v dialogu: instance, jména, zájmena

„Petr má psa“ založí bezejmennou instanci; „Jmenuje se Rex“ jméno připíše *jí* (bezejmennému
referentu), ne Petrovi. „ho“ nemůže být podmět téže věty. Nevyslovený podmět hlavní věty se
vezme z předcházející vedlejší věty (Jana), se shodou rodu.

```text
» Petr má psa.
✓ zapsáno [s0001] být(kdo: pes, co: ∃pes) ⟨member⟩
   [instance: členství z neurčité zmínky]
✓ zapsáno [s0002] mít(kdo: Petr, co: ∃pes)
   [co: nová instance e0002 ∈ pes (neurčitá zmínka)]

» Jmenuje se Rex.
✓ zapsáno [s0003] jmenovat_se(kdo: Rex, co: Rex)
   [kdo:pro-drop z kontextu; kdo: „nevyslovený podmět“ = pes (z aktivace); jméno „Rex“ připsáno k e0002 (Rex)]

» Petr ho venčí každý den.
✓ zapsáno [s0004] venčit(kdo: Petr, co: Rex, jak dlouho: ∀den)
   [co: „on“ = Rex (z aktivace)]

» Kdo venčí Rexe?
čtu: venčit(kdo:?, co:·Rex)
→ Petr
   - venčit(kdo: Petr, co: Rex, jak dlouho: ∀den)  [s0004]
       zdroj: „Petr ho venčí každý den.“ (dialog, věta 3)
   [řekls to; co: „on“ = Rex (z aktivace)]

» Čí je Rex?
čtu: být(kdo:·Rex, čí:?)
→ Petr
   - mít(kdo: Petr, co: ∃Rex)  [s0002]
       zdroj: „Petr má psa.“ (dialog, věta 1)
   ↳ čí = kdo má
   [řekls to; co: nová instance e0002 ∈ pes (neurčitá zmínka)]

» Než Jana odešla, zamkla dveře.
✓ zapsáno [s0005] být(kdo: dveře, co: ∃dveře) ⟨member⟩
   [instance: členství z neurčité zmínky]
✓ zapsáno [s0006] zamknout(kdo: Jana, kdy: [odejít(kdo: Jana)], co: ∃dveře)
   [kdo: „Jana“ z vedlejší věty (nevyslovený podmět); co: nová instance e0005 ∈ dveře (neurčitá zmínka)]

» Kdo zamkl dveře?
čtu: zamknout(kdo:?, co:∃dveře)
→ Jana
   - zamknout(kdo: Jana, kdy: [odejít(kdo: Jana)], co: ∃dveře)  [s0006]
       zdroj: „Než Jana odešla, zamkla dveře.“ (dialog, věta 4)
   - být(kdo: dveře, co: ∃dveře) ⟨member⟩  [s0005]
       zdroj: „Než Jana odešla, zamkla dveře.“ (dialog, věta 4)
   ↳ dveře ∈ dveře
   [odvozeno z: řekls to; kdo: „Jana“ z vedlejší věty (nevyslovený podmět); co: nová instance e0005 ∈ dveře (neurčitá zmínka)]

```

### 5.4 Vztahová jména: zúžení ⟨…⟩, definice z textu, inverze, dědění tříd

`otec⟨Petr Novák⟩` je třída zúžená vztahem. Definice „Tchán je otec manžela nebo manželky“ se
zapíše jako fakt **a navíc** jako řetěz `otec∘manžel`; otázka ho rozvine s důkazem. Inverze
(syn↔otec/matka podle rodu) je osivo v `defaults.py`, další se učí (`!uč inverze`). „Otec je
rodič“ ⇒ `otec⟨X⟩ ⊆ rodič⟨X⟩`. „Petr má bratra Karla“ váže vztahové jméno k podmětu.

```text
» Petr Novák je manžel Jany Novákové.
✓ zapsáno [s0001] být(kdo: Petr Novák, co: ∃manžel Jana Nováková) ⟨member⟩
   [kernel:member (určitý podmět)]

» Karel Novák je otec Petra Nováka.
✓ zapsáno [s0002] být(kdo: Karel Novák, co: ∃otec Petr Novák) ⟨member⟩
   [kernel:member (určitý podmět)]

» Tchán je otec manžela nebo manželky.
naučeno [s0003]: tchán(X) = otec(manžel(X)) nebo otec(manželka(X))
✓ zapsáno [s0004] být(kdo: ∀tchán, co: ∃otec manžel) ⟨subset⟩
   [kdo:∀ generický prézens; tvar definice vztahového jména (řetěz uložen navíc); kernel:subset (obecný podmět)]

» Kdo je tchán Jany Novákové?
čtu: být(kdo:∀tchán⟨Jana Nováková⟩, co:?)
→ Karel Novák
   - být(kdo: Petr Novák, co: ∃manžel Jana Nováková) ⟨member⟩  [s0001]
       zdroj: „Petr Novák je manžel Jany Novákové.“ (dialog, věta 1)
   - být(kdo: Karel Novák, co: ∃otec Petr Novák) ⟨member⟩  [s0002]
       zdroj: „Karel Novák je otec Petra Nováka.“ (dialog, věta 2)
   ↳ Petr Novák ∈ manžel⟨Jana Nováková⟩
   ↳ Karel Novák ∈ otec⟨Petr Novák⟩
   ↳ tchán = otec∘manžel (naučená definice)
   [odvozeno z: řekls to]

» Otec je rodič.
✓ zapsáno [s0005] být(kdo: ∀otec, co: ∃rodič) ⟨subset⟩
   [kdo:∀ generický prézens; kernel:subset (obecný podmět)]

» Je Karel Novák rodič Petra Nováka?
čtu: být(kdo:·Karel Novák, co:∃rodič⟨Petr Novák⟩) ⟨member⟩
→ ANO
   protože:
   - být(kdo: Karel Novák, co: ∃otec Petr Novák) ⟨member⟩  [s0002]
       zdroj: „Karel Novák je otec Petra Nováka.“ (dialog, věta 2)
   - rel:otec⊆rodič přenáší se na ⟨Petr Novák⟩
   - být(kdo: ∀otec, co: ∃rodič) ⟨subset⟩  [s0005]
       zdroj: „Otec je rodič.“ (dialog, věta 5)
   ↳ Karel Novák ∈ rodič⟨Petr Novák⟩
   [odvozeno z: řekls to]

» Pavla a Jindřich mají syna Matěje.
✓ zapsáno [s0006] být(kdo: Matěj, co: ∃syn Pavla) ⟨member⟩
   [titul „syn“ před jménem = třída]
✓ zapsáno [s0007] být(kdo: Matěj, co: ∃syn Jindřich) ⟨member⟩
   [titul „syn“ před jménem = třída]
✓ zapsáno [s0008] mít(kdo: Pavla + Jindřich, co: Matěj)
   [koordinace:kdo:distribuce; syn ⟨Pavla + Jindřich⟩ (vztahové jméno u „mít“ se váže k podmětu)]

» Kdo je matka Matěje?
čtu: být(kdo:∀matka⟨Matěj⟩, co:?)
→ Pavla
   - být(kdo: Matěj, co: ∃syn Pavla) ⟨member⟩  [s0006]
       zdroj: „Pavla a Jindřich mají syna Matěje.“ (dialog, věta 6)
   ↳ Matěj ∈ syn⟨Pavla⟩ ⇒ Pavla ∈ matka⟨Matěj⟩ (inverze syn↔matka)
   [odvozeno z: řekls to; inverze vztahu (osivo)]

```

### 5.5 Srovnání

Srovnávací slovo je vazba na děj a směr (`starší` = dřívější `narodit_se(kdy)`); osivo je
v tabulce, další se učí větou („Delší je ten, kdo měří víc.“) nebo `!srovnání`.

```text
» Pavla se narodila v roce 1980.
✓ zapsáno [s0001] narodit_se(kdo: Pavla, kdy: 1980)

» Jindřich se narodil v roce 1975.
✓ zapsáno [s0002] narodit_se(kdo: Jindřich, kdy: 1975)

» Je Pavla starší než Jindřich?
čtu: srovnání(kdo:·Pavla, jaký:·starý, než:·Jindřich)
→ NE
   protože:
   - narodit_se(kdo: Pavla, kdy: 1980)  [s0001]
       zdroj: „Pavla se narodila v roce 1980.“ (dialog, věta 1)
   - narodit_se(kdo: Jindřich, kdy: 1975)  [s0002]
       zdroj: „Jindřich se narodil v roce 1975.“ (dialog, věta 2)
   ↳ Pavla: 1980
   ↳ Jindřich: 1975
   ↳ starý: dřívější narodit_se(kdy)
   [odvozeno z: řekls to; srovnání (osivo)]

» Kdo je starší, Pavla nebo Jindřich?
čtu: srovnání(kdo:?, jaký:·starý, z:·Pavla+·Jindřich)
→ Jindřich
   - narodit_se(kdo: Jindřich, kdy: 1975)  [s0002]
       zdroj: „Jindřich se narodil v roce 1975.“ (dialog, věta 2)
   - narodit_se(kdo: Pavla, kdy: 1980)  [s0001]
       zdroj: „Pavla se narodila v roce 1980.“ (dialog, věta 1)
   ↳ Jindřich: 1975
   ↳ Pavla: 1980
   ↳ starý: dřívější narodit_se(kdy)
   [odvozeno z: řekls to; srovnání (osivo)]

```

### 5.6 Veličiny, rozsahy, binární pravidla

Veličina je role s hodnotou a jednotkou (`délka: 10 cm`). Otázka „Vejde se…?“ nemá výrok,
ale systém vidí touž veličinu u obou stran a nabídne **porovnání**; po `ano` odpoví testem
`10 <= 8`. Rozsah „30 000 až 50 000“ dává ANO/NE podle příslušnosti do intervalu.

```text
» Telefon má na délku 10 cm.
✓ zapsáno [s0001] mít(kdo: ∀telefon, délka: 10 cm)
   [kdo:∀ generický prézens; veličina délka: „na+Acc“ + hodnota → role délka]

» Kapsa je na délku 8 cm.
✓ zapsáno [s0002] být(kdo: ∀kapsa, délka: 8 cm)
   [kdo:∀ generický prézens; veličina délka: „na+Acc“ + hodnota → role délka]

» Vejde se telefon do kapsy?
čtu: vejít(co:∀telefon, do+Gen:∃kapsa)
→ NEVÍM
   chybí: o „vejít“ nemám žádný výrok
   vím:
   - být(kdo: ∀kapsa, délka: 8 cm)  — zdroj: „Kapsa je na délku 8 cm.“ (dialog, věta 2)
   - mít(kdo: ∀telefon, délka: 10 cm)  — zdroj: „Telefon má na délku 10 cm.“ (dialog, věta 1)
   ? o telefon i kapsa znám délka; platí „vejít“, když délka(telefon) <= délka(kapsa)? (test uprav: <=, >=, <, >, =)
   → šablona: !uč porovnání vejít délka <=   (odpověz „ano“ = naučit a odpovědět znovu, „ne“ = nenabízet, „jen tady“ = nechat)

» ano
naučeno [s0003]: vejít(X, Y) platí, když délka(X) <= délka(Y)
— znovu: Vejde se telefon do kapsy?
čtu: vejít(co:∀telefon, do+Gen:∃kapsa)
→ NE
   protože:
   - mít(kdo: ∀telefon, délka: 10 cm)  [s0001]
       zdroj: „Telefon má na délku 10 cm.“ (dialog, věta 1)
   - být(kdo: ∀kapsa, délka: 8 cm)  [s0002]
       zdroj: „Kapsa je na délku 8 cm.“ (dialog, věta 2)
   ↳ délka: telefon = 10 cm, kapsa = 8 cm → 10 <= 8: neplatí
   ↳ vejít ⇐ délka <= (naučené pravidlo)
   [odvozeno z: řekls to; binární pravidlo (šablona porovnání)]

» V úlu je 30 000 až 50 000 dělnic.
✓ zapsáno [s0004] být(kdo: ∀30 000–50 000 dělnice, kde: ∃úl)
   [kdo:∀ generický prézens]

» Je v úlu 40 000 dělnic?
čtu: být(kdo:∀dělnice#40000, kde:∃úl)
→ ANO
   protože:
   - být(kdo: ∀30 000–50 000 dělnice, kde: ∃úl)  [s0004]
       zdroj: „V úlu je 30 000 až 50 000 dělnic.“ (dialog, věta 3)
   ↳ počet 40000 je v rozsahu 30000–50000
   [řekls to; kdo:∀ generický prézens]

» Kolik dělnic je v úlu?
čtu: být(kdo:?count:∀dělnice, kde:∃úl)
→ 30 000–50 000
   - být(kdo: ∀30 000–50 000 dělnice, kde: ∃úl)  [s0004]
       zdroj: „V úlu je 30 000 až 50 000 dělnic.“ (dialog, věta 3)
   [řekls to; kdo:∀ generický prézens]

```

### 5.7 Čas: intervaly, překryv, sloučení, relativní čas

Interval životů + otázka „mohli se potkat?“ → nabídka **překryvu** (vrstva nad primitivními
fakty: pravidlo se nabídne, jen když má vstupy). Dvě věty o témže ději (duben + 1975) se
sloučí. „před 2 miliardami let“ je čas relativně k teď.

```text
» Magdalena žila mezi lety 1900 až 2000.
✓ zapsáno [s0001] žít(kdo: Magdalena, kdy: 1900 – 2000)

» Superman žil mezi lety 2001 až 3001.
✓ zapsáno [s0002] žít(kdo: Superman, kdy: 2001 – 3001)

» Mohli se Magdalena a Superman potkat?
čtu: možnost:potkat_se(kdo:·Magdalena+·Superman)
→ NEVÍM
   chybí: o „potkat_se“ nemám žádný výrok
   vím:
   - žít(kdo: Superman, kdy: 2001 – 3001)  — zdroj: „Superman žil mezi lety 2001 až 3001.“ (dialog, věta 2)
   - žít(kdo: Magdalena, kdy: 1900 – 2000)  — zdroj: „Magdalena žila mezi lety 1900 až 2000.“ (dialog, věta 1)
   ? o Magdalena i Superman znám žít(kdy); je „potkat_se“ možné, když se ty časy překrývají?
   → šablona: !uč překryv potkat_se žít   (odpověz „ano“ = naučit a odpovědět znovu, „ne“ = nenabízet, „jen tady“ = nechat)

» ano
naučeno [s0003]: potkat_se(A, B) platí, když se překrývají intervaly žít(kdy) u A i B
— znovu: Mohli se Magdalena a Superman potkat?
čtu: možnost:potkat_se(kdo:·Magdalena+·Superman)
→ NE
   protože:
   - žít(kdo: Magdalena, kdy: 1900 – 2000)  [s0001]
       zdroj: „Magdalena žila mezi lety 1900 až 2000.“ (dialog, věta 1)
   - žít(kdo: Superman, kdy: 2001 – 3001)  [s0002]
       zdroj: „Superman žil mezi lety 2001 až 3001.“ (dialog, věta 2)
   ↳ Magdalena: 1900 – 2000
   ↳ Superman: 2001 – 3001
   ↳ potkat_se ⇐ překryv intervalů žít(kdy) (naučené pravidlo)
   [odvozeno z: řekls to; binární pravidlo (šablona překryv)]

» Jindřich se narodil v dubnu.
✓ zapsáno [s0004] narodit_se(kdo: Jindřich, kdy: duben)

» Jindřich se narodil roku 1975.
✓ zapsáno [s0005] narodit_se(kdo: Jindřich, kdy: 1975)

» Kdy se narodil Jindřich?
čtu: narodit_se(kdy:?, kdo:·Jindřich)
→ 4/1975
   - narodit_se(kdo: Jindřich, kdy: 1975)  [s0005]
       zdroj: „Jindřich se narodil roku 1975.“ (dialog, věta 4)
   - narodit_se(kdo: Jindřich, kdy: duben)  [s0004]
       zdroj: „Jindřich se narodil v dubnu.“ (dialog, věta 3)
   ↳ sloučeno ze dvou vět: 1975 + duben → 4/1975 (týž děj, týž podmět)
   [odvozeno z: řekls to]

» První sinice se objevily před 2 miliardami let.
✓ zapsáno [s0006] objevit_se(kdo: sinice (první), kdy: před 2 miliardami let)
   [kdo:· epizoda]

» Kdy se objevily první sinice?
čtu: objevit_se(kdy:?, kdo:·sinice[první])
→ před 2 miliardami let
   - objevit_se(kdo: sinice (první), kdy: před 2 miliardami let)  [s0006]
       zdroj: „První sinice se objevily před 2 miliardami let.“ (dialog, věta 5)
   [řekls to; kdo:· epizoda]

```

### 5.8 Podmínky a pravidla přímo z věty

„X, pokud Y“: Y se **netvrdí** (⊂ v `!program`), X platí jen když Y plyne z paměti — jinak
odpověď říká, co chybí. „Každý, kdo …“ / „Kdo …, ten …“ / „Pokud někdo …“ dávají výrok
s **proměnnou X**; dotaz ji váže (`X := Petr`), wh‑otázka ji vyčísluje z podmínky. „Každý pes,
který štěká, je hlídač“ = dvě podmínky (X ∈ pes ∧ štěká X) — a „Štěká každý pes?“ je NEVÍM,
protože omezovací vztažná věta nic netvrdí.

```text
» Petr půjde na oslavu, pokud půjde Karel.
✓ zapsáno [s0001] jít(kdo: Petr, na+Acc: ∃oslava, podmínka: [jít(kdo: Karel)])
   [podmínka: pokud]
   ? o0001: Co znamená role „na+Acc“ (na+Acc)? (kde, kdy, kudy, čím, …)

» Půjde Petr na oslavu?
čtu: jít(kdo:·Petr, na+Acc:∃oslava)
→ NEVÍM
   chybí: [s0001] platí jen pod podmínkou: jít(kdo:·Karel) — to nevím
   vím:
   - jít(kdo: Petr, na+Acc: ∃oslava, podmínka: [jít(kdo: Karel)])  — zdroj: „Petr půjde na oslavu, pokud půjde Karel.“ (dialog, věta 1)

» Karel půjde na oslavu.
✓ zapsáno [s0003] jít(kdo: Karel, na+Acc: ∃oslava)
   ? o0002: Co znamená role „na+Acc“ (na+Acc)? (kde, kdy, kudy, čím, …)

» Půjde Petr na oslavu?
čtu: jít(kdo:·Petr, na+Acc:∃oslava)
→ ANO
   protože:
   - jít(kdo: Petr, na+Acc: ∃oslava, podmínka: [jít(kdo: Karel)])  [s0001]
       zdroj: „Petr půjde na oslavu, pokud půjde Karel.“ (dialog, věta 1)
   - jít(kdo: Karel, na+Acc: ∃oslava)  [s0003]
       zdroj: „Karel půjde na oslavu.“ (dialog, věta 2)
   ↳ podmínka splněna: jít(kdo:·Karel)
   [odvozeno z: řekls to; podmínka: pokud]

» Každý, kdo bydlí v Praze, bydlí v Česku.
✓ zapsáno [s0004] bydlet(kdo: X, kde: Česko, podmínka: [bydlet(kdo: X, kde: Praha)])
   [pravidlo z věty: každý, kdo … (podmínka)]

» Petr bydlí v Praze.
✓ zapsáno [s0006] bydlet(kdo: Petr, kde: Praha)

» Bydlí Petr v Česku?
čtu: bydlet(kdo:·Petr, kde:·Česko)
→ ANO
   protože:
   - bydlet(kdo: X, kde: Česko, podmínka: [bydlet(kdo: X, kde: Praha)])  [s0004]
       zdroj: „Každý, kdo bydlí v Praze, bydlí v Česku.“ (dialog, věta 3)
   - bydlet(kdo: Petr, kde: Praha)  [s0006]
       zdroj: „Petr bydlí v Praze.“ (dialog, věta 4)
   ↳ X := Petr
   ↳ podmínka splněna: bydlet(kdo:X, kde:·Praha)
   [odvozeno z: řekls to; pravidlo z věty: každý, kdo … (podmínka)]

» Kdo bydlí v Česku?
čtu: bydlet(kdo:?, kde:·Česko)
→ Petr
   - bydlet(kdo: X, kde: Česko, podmínka: [bydlet(kdo: X, kde: Praha)])  [s0004]
       zdroj: „Každý, kdo bydlí v Praze, bydlí v Česku.“ (dialog, věta 3)
   - bydlet(kdo: Petr, kde: Praha)  [s0006]
       zdroj: „Petr bydlí v Praze.“ (dialog, věta 4)
   ↳ pravidlo z věty [s0004]: X := Petr
   [odvozeno z: řekls to; pravidlo z věty: každý, kdo … (podmínka)]

» Každý pes, který štěká, je hlídač.
✓ zapsáno [s0007] být(kdo: X, co: ∃hlídač, podmínka: [být(kdo: X, co: ∃pes) ⟨member⟩], podmínka: [štěkat(kdo: X)]) ⟨member⟩
   [kernel:subset (obecný podmět); pravidlo z věty: každý pes, který … (podmínka: třída + vztažná věta)]

» Rex je pes.
✓ zapsáno [s0010] být(kdo: Rex, co: ∃pes) ⟨member⟩
   [kernel:member (určitý podmět)]

» Rex štěká.
✓ zapsáno [s0011] štěkat(kdo: Rex)

» Alík je pes.
✓ zapsáno [s0012] být(kdo: Alík, co: ∃pes) ⟨member⟩
   [kernel:member (určitý podmět)]

» Je Rex hlídač?
čtu: být(kdo:·Rex, co:∃hlídač) ⟨member⟩
→ ANO
   protože:
   - být(kdo: X, co: ∃hlídač, podmínka: [být(kdo: X, co: ∃pes) ⟨member⟩], podmínka: [štěkat(kdo: X)]) ⟨member⟩  [s0007]
       zdroj: „Každý pes, který štěká, je hlídač.“ (dialog, věta 5)
   - být(kdo: Rex, co: ∃pes) ⟨member⟩  [s0010]
       zdroj: „Rex je pes.“ (dialog, věta 6)
   - štěkat(kdo: Rex)  [s0011]
       zdroj: „Rex štěká.“ (dialog, věta 7)
   ↳ X := Rex
   ↳ Rex ∈ pes
   ↳ podmínka splněna: být(kdo:X, co:∃pes) ⟨member⟩
   ↳ podmínka splněna: štěkat(kdo:X)
   [odvozeno z: řekls to; kernel:subset (obecný podmět); pravidlo z věty: každý pes, který … (podmínka: třída + vztažná věta)]

» Je Alík hlídač?
čtu: být(kdo:·Alík, co:∃hlídač) ⟨member⟩
→ NEVÍM
   chybí: [s0007] platí jen pod podmínkou: štěkat(kdo:·Alík) — to nevím
   vím:
   - být(kdo: X, co: ∃hlídač, podmínka: [být(kdo: X, co: ∃pes) ⟨member⟩], podmínka: [štěkat(kdo: X)]) ⟨member⟩  — zdroj: „Každý pes, který štěká, je hlídač.“ (dialog, věta 5)
   - být(kdo: Alík, co: ∃pes) ⟨member⟩  — zdroj: „Alík je pes.“ (dialog, věta 8)

» Štěká každý pes?
čtu: štěkat(kdo:∀pes)
→ NEVÍM
   vím:
   - být(kdo: Alík, co: ∃pes) ⟨member⟩  — zdroj: „Alík je pes.“ (dialog, věta 8)
   - být(kdo: Rex, co: ∃pes) ⟨member⟩  — zdroj: „Rex je pes.“ (dialog, věta 6)

» !program
s0001: jít(kdo:·Petr, na+Acc:∃oslava, podmínka:[s0002]) @said @dialog#1
s0002: jít(kdo:·Karel) @said @dialog#1 ⊂(podmínka)
s0003: jít(kdo:·Karel, na+Acc:∃oslava) @said @dialog#2
s0004: bydlet(kdo:X, kde:·Česko, podmínka:[s0005]) @said @dialog#3
s0005: bydlet(kdo:X, kde:·Praha) @said @dialog#3 ⊂(podmínka)
s0006: bydlet(kdo:·Petr, kde:·Praha) @said @dialog#4
s0007: být(kdo:X, co:∃hlídač, podmínka:[s0008], podmínka:[s0009]) ⟨member⟩ @said @dialog#5
s0008: být(kdo:X, co:∃pes) ⟨member⟩ @said @dialog#5 ⊂(podmínka)
s0009: štěkat(kdo:X) @said @dialog#5 ⊂(podmínka)
s0010: být(kdo:·Rex, co:∃pes) ⟨member⟩ @said @dialog#6
s0011: štěkat(kdo:·Rex) @said @dialog#7
s0012: být(kdo:·Alík, co:∃pes) ⟨member⟩ @said @dialog#8

```

### 5.9 Proč, účel, řeč

Příčinná věta = role `proč`, účelová („aby“) = `účel` (netvrdí se, ale na „proč“ odpovídá).
Kladná otázka nad záporným výrokem → NE s vysvětlením. Věta pod slovesem mluvení se tvrdí
s doložkou „podle koho“.

```text
» Petr nepřišel, protože byl nemocný.
✓ zapsáno [s0001] ne-přijít(kdo: Petr, proč: [být(kdo: Petr, jaký: ∃nemocný)])

» Proč Petr nepřišel?
čtu: ¬přijít(proč:?, kdo:·Petr)
→ být(kdo: Petr, jaký: ∃nemocný)
   - ne-přijít(kdo: Petr, proč: [být(kdo: Petr, jaký: ∃nemocný)])  [s0001]
       zdroj: „Petr nepřišel, protože byl nemocný.“ (dialog, věta 1)
   ↳ spojka „protože“
   [řekls to]

» Proč Petr přišel?
čtu: přijít(proč:?, kdo:·Petr)
→ NE — předpoklad otázky neplatí:
   - ne-přijít(kdo: Petr, proč: [být(kdo: Petr, jaký: ∃nemocný)])  [s0001]
       zdroj: „Petr nepřišel, protože byl nemocný.“ (dialog, věta 1)
   ↳ předpoklad otázky neplatí (výrok je záporný)
   [řekls to]

» Petr šel do obchodu, aby koupil chleba.
✓ zapsáno [s0003] jít(kdo: Petr, do+Gen: ∃obchod, účel: [koupit(kdo: Petr, co: ∃chléb)])
✓ zapsáno [s0004] být(kdo: chléb, co: ∃chléb) ⟨member⟩
   [instance: členství z neurčité zmínky]
   ? o0001: Co znamená role „do+Gen“ (do+Gen)? (kde, kdy, kudy, čím, …)

» Proč šel Petr do obchodu?
čtu: jít(proč:?, kdo:·Petr, do+Gen:∃obchod)
→ koupit(kdo: Petr, co: ∃chléb)
   - jít(kdo: Petr, do+Gen: ∃obchod, účel: [koupit(kdo: Petr, co: ∃chléb)])  [s0003]
       zdroj: „Petr šel do obchodu, aby koupil chleba.“ (dialog, věta 2)
   ↳ role „účel“ — ptal ses „proč“
   [řekls to]

» Koupil Petr chleba?
čtu: koupit(kdo:·Petr, co:∃chléb)
→ NEVÍM
   chybí: o „koupit“ nemám žádný výrok
   vím:
   - jít(kdo: Petr, do+Gen: ∃obchod, účel: [koupit(kdo: Petr, co: ∃chléb)])  — zdroj: „Petr šel do obchodu, aby koupil chleba.“ (dialog, věta 2)
   - ne-přijít(kdo: Petr, proč: [být(kdo: Petr, jaký: ∃nemocný)])  — zdroj: „Petr nepřišel, protože byl nemocný.“ (dialog, věta 1)
   - být(kdo: chléb, co: ∃chléb) ⟨member⟩  — zdroj: „Petr šel do obchodu, aby koupil chleba.“ (dialog, věta 2)

» Ježíš kázal, že Bůh je láska.
✓ zapsáno [s0006] kázat(kdo: Ježíš, co: [být(kdo: Bůh, co: ∃láska) ⟨member⟩])

» Je Bůh láska?
čtu: být(kdo:·Bůh, co:∃láska) ⟨member⟩
→ ANO
   protože:
   - být(kdo: Bůh, co: ∃láska) ⟨member⟩  [s0007]
       zdroj: „Ježíš kázal, že Bůh je láska.“ (dialog, věta 3)
   ↳ Bůh ∈ láska
   [řekls to; podle Ježíš (kázat)]

```

### 5.10 Místa: uvnitř a tranzitivita

„X je v Y“ u věcí dává řetěz „přes krabici“; u míst „leží na / je část“ dává jádro `within`,
takže „Žije Petr na Moravě?“ plyne z „žije v Brně“ + „Brno leží na Moravě“.

```text
» Prací prášek je v krabici.
✓ zapsáno [s0001] být(kdo: ∀prášek (prací), kde: ∃krabice)
   [kdo:∀ generický prézens]

» Krabice je v koupelně.
✓ zapsáno [s0002] být(kdo: ∀krabice, kde: ∃koupelna)
   [kdo:∀ generický prézens]

» Kde je prací prášek?
čtu: být(kdo:∀prášek[prací], kde:?)
→ krabice
   - být(kdo: ∀prášek (prací), kde: ∃krabice)  [s0001]
       zdroj: „Prací prášek je v krabici.“ (dialog, věta 1)
   [řekls to; kdo:∀ generický prézens]
→ koupelna
   - být(kdo: ∀prášek (prací), kde: ∃krabice)  [s0001]
       zdroj: „Prací prášek je v krabici.“ (dialog, věta 1)
   - být(kdo: ∀krabice, kde: ∃koupelna)  [s0002]
       zdroj: „Krabice je v koupelně.“ (dialog, věta 2)
   ↳ přes krabice: krabice je v koupelna
   [odvozeno z: řekls to; kdo:∀ generický prézens]

» Petr žije v Brně.
✓ zapsáno [s0003] žít(kdo: Petr, kde: Brno)

» Brno leží na Moravě.
✓ zapsáno [s0004] ležet(kdo: Brno, kde: Morava) ⟨within⟩
   [kernel:within (místo leží v místě)]

» Žije Petr na Moravě?
čtu: žít(kdo:·Petr, kde:·Morava)
→ ANO
   protože:
   - žít(kdo: Petr, kde: Brno)  [s0003]
       zdroj: „Petr žije v Brně.“ (dialog, věta 3)
   - ležet(kdo: Brno, kde: Morava) ⟨within⟩  [s0004]
       zdroj: „Brno leží na Moravě.“ (dialog, věta 4)
   ↳ Brno ⊆ Morava (místo)
   [odvozeno z: řekls to]

```

### 5.11 Opravy a odvolání

„Ne, …“ odvolá poslední výrok o témže a zapíše nový; `!zapomeň sXXXX` odvolá cokoli.
V `!program` odvolané zůstávají s ✗ a důvodem.

```text
» Ronik je pes.
✓ zapsáno [s0001] být(kdo: ∀ronik, co: ∃pes) ⟨subset⟩
   [kdo:∀ generický prézens; kernel:subset (obecný podmět)]

» Ronik bydlí v Petrovicích.
✓ zapsáno [s0002] bydlet(kdo: Ronik, kde: Petrovice)
   [identita: „Ronik“ = Ronik (částečné jméno)]

» Ne, Ronik bydlí v Praze.
odvolávám: s0002
✓ zapsáno [s0003] bydlet(kdo: Ronik, kde: Praha)
   [identita: „Ronik“ = Ronik (částečné jméno)]

» Kde bydlí Ronik?
čtu: bydlet(kde:?, kdo:·Ronik)
→ Praha
   - bydlet(kdo: Ronik, kde: Praha)  [s0003]
       zdroj: „Ne, Ronik bydlí v Praze.“ (dialog, věta 3)
   [řekls to; identita: „Ronik“ = Ronik (částečné jméno)]

» !zapomeň s0001
odvoláno: s0001

» Je Ronik pes?
čtu: být(kdo:·Ronik, co:∃pes) ⟨member⟩
→ NEVÍM
   chybí: o „být“ nemám žádný výrok
   vím:
   - bydlet(kdo: Ronik, kde: Praha)  — zdroj: „Ne, Ronik bydlí v Praze.“ (dialog, věta 3)

» !program
s0001: být(kdo:∀Ronik, co:∃pes) ⟨subset⟩ @said @dialog#1 ✗(zapomenuto dialogem (tah 5))
s0002: bydlet(kdo:·Ronik, kde:·Petrovice) @said @dialog#2 ✗(oprava (tah 3): Ne, Ronik bydlí v Praze.)
s0003: bydlet(kdo:·Ronik, kde:·Praha) @said @dialog#3

```

### 5.12 Šablony, moduly vazeb

`!šablony` vypíše, co jde systému vysvětlit (a stejné okno je ve viewBase). Vazby drží paměť;
`!ulož-vazby` je vypíše jako přehratelný program bez faktů, `!načti-vazby` je pustí do jiné
paměti (touž cestou jako dialog, tj. s výroky a proveniencí). `--vazby soubor` při startu.
Odvolání definičního výroku vypne i vazbu.

```text
» !šablony
Šablony (vyplň a pošli; nebo v prohlížeči okno „Vysvětlit vztah“):
  !uč druh <X> <Y>                                   X je druh Y (X ⊆ Y)   např. !uč druh jezevčík pes
  !uč prvek <X> <Y>                                   X je jeden z Y (X ∈ Y)   např. !uč prvek Hrabal spisovatel
  !uč totožnost <X> <Y>                                   X je totéž co Y (jedno individuum, dvě jména)   např. !uč totožnost Hrabal „Bohumil Hrabal“
  !uč vyloučení <X> <Y>                                   žádné X není Y (třídy se vylučují → NE)   např. !uč vyloučení kopytník šelma
  !uč složený <X> <R1> <R2> <R2b>                       X = R1 ∘ R2 (X někoho je R1 jeho R2; tchán = otec manžela)   např. !uč složený tchán otec manžel manželka
  !uč inverze <A> <B>                                   A a B jsou obrácené vztahy (X je A Y-a ⇔ Y je B X-a)   např. !uč inverze manžel manželka
  !uč srovnání <S> <P> <R> <směr>                        „S“ je ten, kdo má větší/menší/dřívější/pozdější hodnotu role R děje P   např. !uč srovnání delší měřit * víc
  !uč pravidlo <P(role:X)> <=>> <Q(role:X)>              kdo P(role:X), ten Q(role:X) — můstek mezi ději   např. !uč pravidlo jet(kam:X) => být(kde:X)
  !uč role <tvar> <=> <role>                         povrchový tvar role znamená jádrovou roli   např. !uč role přes+Acc = kudy
  !uč synonymum <A> <=> <B>                               slovo A znamená totéž co B (predikáty)   např. !uč synonymum kázat = hlásat
  !uč výjimka <P> <X> <Y>                               pravidlo P o třídě X neplatí pro Y   např. !uč výjimka létat pták tučňák
  !uč hodnota <X> <Q> <N> <j>                           X má Q rovno N jednotek   např. !uč hodnota Vltava délka 430 km
  !uč překryv <Q> <P>                                   Q(A a B) platí, když se překrývají intervaly kdy děje P u obou (potkat_se ⇐ žít)   např. !uč překryv potkat_se žít
  !uč porovnání <Q> <V> <TEST>                            Q(X, Y) platí, když veličina V u X TEST veličina V u Y (vejít_se ⇐ délka <=)   např. !uč porovnání vejít_se délka <=

» !uč překryv potkat_se žít
naučeno [s0001]: potkat_se(A, B) platí, když se překrývají intervaly žít(kdy) u A i B

» !uč složený tchán otec manžel manželka
naučeno [s0002]: tchán(X) = otec(manžel(X)) nebo otec(manželka(X))

» !ulož-vazby /tmp/vazby-ukazka.txt
modul vazeb uložen do /tmp/vazby-ukazka.txt: 2 vazeb

» !zapomeň s0001
odvoláno: s0001

» !program
s0001: binární_pravidlo(jaký:·potkat_se, co:·žít) @said @šablona#0 ✗(zapomenuto dialogem (tah 5))
s0002: definice_vztahu(jaký:·tchán, co:·otec, co:·otec) @said @šablona#0

```

Obsah uloženého modulu:

```text
# conbond5 — modul vazeb (přehratelné příkazy, bez faktů)
!uč složený tchán otec manžel manželka
!uč překryv potkat_se žít
```

---

## 6 · Příkazy

`!program` výpis výroků · `!kdo X` / `!popiš X` vše o uzlu · `!otevřené` backlog ·
`!odpověz o0001 kde` · `!zapomeň s0003` / `!zapomeň Ronik` · `!role v+Loc = kde` ·
`!synonymum kázat = hlásat` · `!srovnání starší = narodit_se kdy dřív` ·
`!pravidlo jet(kam:X) => být(kde:X)` · `!výjimka létat pták tučňák` · `!šablony` ·
`!uč <šablona> …` · `!ulož-vazby f.txt` / `!načti-vazby f.txt` · `!ulož p.json` / `!načti p.json` ·
`!graf g.json`. Odpovědi na návrh: `ano` / `ne` (odmítnutí se pamatuje) / `jen tady`.
Vykřičník lze vynechat.

## 7 · Kde co hledat v kódu

| soubor | co dělá |
|---|---|
| `cb5/oracle.py` | UDPipe, keš rozborů, nahrávka pro testy |
| `cb5/diakritika.py` | obnova háčků z tvarů, které paměť viděla |
| `cb5/chronos.py` | čas: rozpoznání a osa (před / uvnitř / překryv) |
| `cb5/defaults.py` | **všechny tabulky**: role z předložky+pádu, tázací slova, částice, synonyma, inverze vztahů, srovnávací osivo, veličiny, spojky (podmínka / účel / čas / příčina), proměnné |
| `cb5/read.py` | rozbor → predikace (největší modul; každý jev má vlastní metodu s docstringem) |
| `cb5/ground.py` | predikace → uzly a výroky v paměti (identita, zájmena, instance, tituly, proměnné) |
| `cb5/memory.py` | graf, výroky, uzávěry, aktivace, naučené vazby, JSON, modul vazeb |
| `cb5/logic.py` | hodnocení otázek (shoda, jádro, výčty, veličiny, vztahy, pravidla, podmínky) |
| `cb5/sablony.py` | šablony `!uč …` a návrh šablony při NEVÍM |
| `cb5/dialog.py` | `Session`: věty, otázky, opravy, příkazy, žurnál, přehrání |
| `cb5/render.py`, `cb5/recall.py` | text odpovědi; propad „vím: …“ |
| `cb5/bench.py` | měření nad korpusem conBond2 |
| `moduly/` | moduly vazeb (textové programy) |

Testy jsou hermetické (`tests/data/parses.json` = nahrané rozbory): každá ukázka výše má
protějšek v `tests/test_dialog.py`.

## 8 · Co (zatím) neumí

- Homonyma na začátku věty: „Jí Rex maso?“ se přečte jako zájmeno (parser), otázka nevyjde.
- Čas nezakládá platnost („bydlel v Praze do roku 2000“ × „Kde bydlí?“ dá Prahu).
- Rozdíly a procenta („o 40 % větší“), superlativy s měrou.
- Disjunktnost tříd z textu („Je kůň šelma?“ → NE chce vědět, že se řády vylučují).
- Otázka může založit prázdný referent („Kdo je Karel Čapek?“ — v grafu se neukáže, v paměti je).
- Text bez diakritiky se doplní jen z tvarů, které paměť už viděla.

Podrobný seznam otevřených směrů: `HANDOVER.md` § 5.
