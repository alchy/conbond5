"""Výchozí volby čtení jako DATA (spec § 2/3, § 5).

Proč zvláštní modul: tohle je přesně to, co conbond4 odmítal rozhodnout bez
člověka („v+Loc není v osivu, aby se systém zeptal“). conbond5 rozhoduje
sám, ale **každou volbu označí** (`authority="default"`) a dialog ji může
přepsat (`!role v+Loc = kde`) nebo odvolat. Nic z toho není zadrátované
v kódu čtení — čtení tabulky jen čte.

Konvence: klíče rolí jsou česká slova (`kde`, `kam`, `kdy`, `kdo`, `co`,
`komu`, `čím`, `s_kým`, `jak`), protože je pak render i otázka „kde“ čte
stejně; povrchové jméno role je `předložka+Pád` (`v+Loc`) nebo holý pád.
"""

from __future__ import annotations

#: (předložka, Pád) → jméno role podle druhu výplně: `place` / `time` / `*`.
#: Chybí-li klíč, role si nechá povrchové jméno a vznikne otevřená položka.
ROLE_BY_CASE: dict[tuple[str, str], dict[str, str]] = {
    ("v", "Loc"): {"place": "kde", "time": "kdy", "duration": "kdy", "*": "kde"},
    ("v", "Acc"): {"time": "kdy", "*": "v+Acc"},
    ("na", "Loc"): {"place": "kde", "time": "kdy", "*": "kde"},
    ("na", "Acc"): {"place": "kam", "*": "na+Acc"},
    ("do", "Gen"): {"place": "kam", "time": "do_kdy", "*": "do+Gen"},
    ("z", "Gen"): {"place": "odkud", "time": "od_kdy", "*": "z+Gen"},
    ("od", "Gen"): {"place": "odkud", "time": "od_kdy", "*": "od+Gen"},
    ("k", "Dat"): {"place": "kam", "*": "k+Dat"},
    ("u", "Gen"): {"place": "kde", "*": "u+Gen"},
    ("s", "Ins"): {"*": "s_kým"},
    ("o", "Loc"): {"*": "o_čem"},
    ("o", "Acc"): {"*": "o+Acc"},
    ("po", "Loc"): {"place": "kudy", "time": "po_kdy", "*": "po+Loc"},
    ("před", "Ins"): {"place": "kde", "time": "před_kdy", "*": "před+Ins"},
    ("za", "Gen"): {"time": "kdy", "*": "za+Gen"},
    ("za", "Ins"): {"place": "kde", "*": "za+Ins"},
    ("během", "Gen"): {"time": "kdy", "duration": "kdy", "*": "během+Gen"},
    ("po", "Acc"): {"duration": "jak_dlouho", "time": "jak_dlouho", "*": "po+Acc"},
    ("za", "Acc"): {"time": "kdy", "duration": "jak_dlouho", "*": "za+Acc"},
    ("mezi", "Ins"): {"place": "kde", "time": "kdy", "*": "mezi+Ins"},
    ("přes", "Acc"): {"place": "kudy", "*": "přes+Acc"},
    ("kolem", "Gen"): {"time": "kdy", "place": "kde", "*": "kolem+Gen"},
    ("okolo", "Gen"): {"time": "kdy", "place": "kde", "*": "okolo+Gen"},
    ("při", "Loc"): {"time": "kdy", "*": "při+Loc"},
    ("nad", "Ins"): {"place": "kde", "*": "nad+Ins"},
    ("pod", "Ins"): {"place": "kde", "*": "pod+Ins"},
    ("vedle", "Gen"): {"place": "kde", "*": "vedle+Gen"},
    ("uvnitř", "Gen"): {"place": "kde", "*": "uvnitř+Gen"},
    ("blízko", "Gen"): {"place": "kde", "*": "blízko+Gen"},
    ("pro", "Acc"): {"*": "pro_koho"},
    ("bez", "Gen"): {"*": "bez+Gen"},
    ("podle", "Gen"): {"*": "podle+Gen"},
    ("proti", "Dat"): {"*": "proti+Dat"},
    ("díky", "Dat"): {"*": "proč"},
    ("kvůli", "Dat"): {"*": "proč"},
    ("jako", ""): {"*": "jako"},
    ("", "Ins"): {"*": "čím"},
    ("", "Dat"): {"*": "komu"},
    ("", "Gen"): {"time": "kdy", "duration": "jak_dlouho", "*": "čeho"},
    ("", "Acc"): {"time": "kdy", "duration": "jak_dlouho", "*": "obl:Acc"},
    ("", "Loc"): {"place": "kde", "time": "kdy", "*": "obl:Loc"},
    ("", "Nom"): {"*": "obl:Nom"},
}

#: Naučené přepisy povrchových jmen rolí (dialog `!role přes+Acc = kudy`)
#: drží PAMĚŤ (`Memory.learned["roles"]`) a čtení je dostane parametrem —
#: žádný globální stav, dvě paměti se nesmějí ovlivnit.

#: Determinátor → kvantifikátor. `∀neg` = „žádný“: ∀ + negace predikace.
DETERMINER_QUANT: dict[str, str] = {
    "každý": "∀", "všechen": "∀", "všechno": "∀", "veškerý": "∀", "kterýkoli": "∀",
    "žádný": "∀neg", "nikdo": "∀neg", "nic": "∀neg",
    "ten": "·", "tento": "·", "tenhle": "·", "onen": "·", "tamten": "·",
    "nějaký": "∃", "některý": "∃", "jeden": "∃", "jistý": "∃", "leckterý": "∃",
    "mnohý": "∃", "několik": "∃", "málokterý": "∃",
}

#: Přivlastňovací determinátory a zájmena — odkaz na aktivní uzel.
POSSESSIVE = frozenset({"jeho", "její", "jejich", "můj", "tvůj", "náš", "váš", "svůj"})

#: Částice a příslovce bez role: neztrácejí se (jsou „particle“), ale
#: nemění strukturu. `ne` se čte jako negace, ne částice.
PARTICLES = frozenset(
    {"také", "též", "taky", "i", "jen", "pouze", "už", "již", "ještě", "asi", "prý",
     "však", "ale", "tedy", "totiž", "například", "zejména", "hlavně", "především",
     "přece", "snad", "přitom", "vůbec", "právě", "zase", "opět", "spíše", "spíš",
     "dokonce", "možná", "vlastně", "prostě", "ovšem", "sice", "zřejmě", "patrně",
     "pravděpodobně", "často", "obvykle", "většinou", "zpravidla", "někdy", "vždy",
     "nikdy", "stále", "pořád", "dále", "dál", "tak", "také", "ano", "ne", "nikoli", "nikoliv"}
)

#: Příslovce pořadí a času, která NEjsou částice: nesou roli.
SEQUENCE_ADVERBS = frozenset(
    {"nejprve", "nejdřív", "nejdříve", "poté", "pak", "potom", "později", "nakonec",
     "tehdy", "kdysi", "dříve", "dřív", "následně", "posléze", "mezitím", "současně",
     "zároveň", "brzy", "záhy", "hned", "ihned", "okamžitě", "nedávno", "dosud", "doposud"}
)

#: Modální slovesa: lemma → druh modality (příznak výroku, ne operátor).
#: neosobní slovesa (bez podmětu; pro‑drop se nedosazuje): počasí a stavy
IMPERSONAL_VERBS: frozenset[str] = frozenset({
    "pršet", "sněžit", "mrznout", "mrholit", "hřmít", "blýskat_se", "svítat", "stmívat_se", "šeřit_se",
    "fouknout", "lít", "chumelit", "jednat_se", "stát_se", "dařit_se", "zdát_se", "podařit_se", "hodit_se",
})

#: příčinné spojky: věta pod nimi platí a je odpovědí na „proč“
CAUSAL_MARKERS: frozenset[str] = frozenset({"protože", "jelikož", "neboť", "poněvadž", "kvůli", "díky"})

#: spojky vedlejších vět, které NETVRDÍ obsah věty: podmínka („pokud prší“ netvrdí, že prší),
#: účel, „než/dokud/aniž“. Věta pod nimi se uloží jako vložený výrok (status `embedded`),
#: který se hodnotí jen skrze rodičovský výrok. „když“ je podmínka jen v přítomném/budoucím čase
#: (jinak časová věta, která platí).
#: zájmena, která ve větě NEODKAZUJÍ, ale zastupují proměnnou pravidla: „Každý, kdo …“,
#: „Kdo …, ten …“, „Pokud někdo …“. Term z nich je proměnná (X); shoda s dotazem ji váže.
VAR_PRONOUNS: frozenset[str] = frozenset({"každý", "někdo", "něco", "kdokoli", "kdokoliv", "cokoli", "cokoliv", "všechen", "všichni", "nikdo"})
#: „někdo/něco“ je proměnná jen v podmínce („pokud někdo …“); v holé větě je to neurčitý činitel (∃)
EXISTENTIAL_PRONOUNS: frozenset[str] = frozenset({"někdo", "něco", "kdosi", "cosi"})

#: slovesa mluvení/myšlení: věta pod nimi („Ježíš kázal, že Bůh je láska“) se zapíše jako výrok
#: s doložkou „podle Ježíš (kázat)“ — odpověď ji vždy vypíše (stupeň zůstává, zdroj je vidět)
SPEECH_VERBS: frozenset[str] = frozenset({
    "říct", "říkat", "tvrdit", "prohlásit", "prohlašovat", "kázat", "hlásat", "myslet", "myslet_si", "věřit",
    "domnívat_se", "psát", "napsat", "uvádět", "uvést", "dodat", "odpovědět", "vědět", "zjistit", "slyšet",
    "doufat", "soudit", "předpokládat", "tvrdívat", "vyprávět", "oznámit", "sdělit", "namítat", "namítnout",
})

CONDITIONAL_MARKERS: frozenset[str] = frozenset({"pokud", "jestliže", "jestli", "li", "kdyby", "když", "-li"})
NON_ASSERTED_MARKERS: dict[str, str] = {
    "pokud": "podmínka", "jestliže": "podmínka", "jestli": "podmínka", "li": "podmínka", "-li": "podmínka", "kdyby": "podmínka",
    "aby": "účel", "než": "vedlejší", "dokud": "vedlejší", "aniž": "vedlejší",
}

MODAL_VERBS: dict[str, str] = {
    "moci": "možnost", "smět": "možnost", "lze": "možnost", "dokázat": "možnost",
    "umět": "možnost", "muset": "nutnost", "mít": "povinnost", "chtít": "vůle",
    "hodlat": "vůle", "začít": "fáze", "začínat": "fáze", "přestat": "fáze",
    "pokračovat": "fáze", "snažit_se": "vůle", "pokusit_se": "vůle",
}

#: Tázací slovo → (jméno role, druh díry). Druh: `filler` (chce výplň),
#: `count` (chce počet), `attr` (chce vlastnost).
WH: dict[str, tuple[str, str]] = {
    "kde": ("kde", "filler"), "kam": ("kam", "filler"), "odkud": ("odkud", "filler"),
    "kudy": ("kudy", "filler"), "kdy": ("kdy", "filler"), "odkdy": ("od_kdy", "filler"),
    "dokdy": ("do_kdy", "filler"), "kdo": ("kdo", "filler"), "co": ("co", "filler"),
    "koho": ("co", "filler"), "komu": ("komu", "filler"), "čím": ("čím", "filler"),
    "kolik": ("count", "count"), "jaký": ("jaký", "attr"), "který": ("který", "attr"),
    "proč": ("proč", "filler"), "čí": ("čí", "filler"), "jak": ("jak", "filler"),
    "jak_dlouho": ("jak_dlouho", "filler"),
}

#: Obecná jména míst — výplň v `v+Loc` apod. je pak MÍSTO i bez NameType=Geo.
PLACE_NOUNS = frozenset(
    {"město", "vesnice", "ves", "obec", "země", "stát", "říše", "království", "kraj",
     "oblast", "region", "provincie", "okres", "čtvrť", "ulice", "náměstí", "řeka",
     "hora", "pohoří", "ostrov", "moře", "oceán", "jezero", "rybník", "les", "pole", "louka",
     "údolí", "sopka", "vulkán", "kopec", "vrch", "poloostrov", "záliv", "pobřeží", "břeh", "pramen",
     "škola", "gymnázium", "univerzita", "fakulta", "akademie", "ústav", "institut",
     "kavárna", "hospoda", "dům", "byt", "vila", "zámek", "hrad", "klášter", "kostel",
     "divadlo", "nemocnice", "továrna", "závod", "podnik", "kancelář", "redakce",
     "dálnice", "silnice", "cesta", "most", "nádraží", "letiště", "přístav", "vězení",
     "tábor", "fronta", "kontinent", "světadíl", "svět", "vesmír", "domov", "exil",
     "emigrace", "zahraničí", "venkov", "centrum", "střed", "okraj", "sever", "jih",
     "východ", "západ", "Evropa", "Amerika", "Asie", "Afrika"}
)

#: Povrchové role s místní předložkou — na „kde“ odpovídají s přiznáním.
LOCATIVE_SURFACES = frozenset({"u+Gen", "v+Loc", "na+Loc", "před+Ins", "za+Ins", "mezi+Ins", "nad+Ins", "pod+Ins", "vedle+Gen", "kolem+Gen", "okolo+Gen", "poblíž+Gen", "blízko+Gen", "uvnitř+Gen", "při+Loc"})

#: Předložky, po nichž je PROPN skoro jistě místo (i bez NameType).
PLACE_PREPS = frozenset({"v", "do", "z", "u", "na", "k", "od", "přes", "po", "za", "mezi", "nad", "pod", "vedle", "před", "kolem", "okolo"})

#: Zájmena, která odkazují (osobní), a jejich rod/číslo pro shodu.
PERSONAL_PRONOUNS = frozenset({"on", "ona", "ono", "oni", "ony", "já", "ty", "my", "vy", "sebe"})

#: Třídy synonym predikátů — OSIVO. Shoda dotazu s výrokem bere i synonymum
#: a důkaz to přizná (`[synonymum: kázat ~ hlásat]`). Dialog přidává
#: `!synonymum kázat = hlásat`. Klíč je reprezentant, hodnota členové.
SYNONYMS: dict[str, frozenset[str]] = {
    "říci": frozenset({"říci", "říkat", "tvrdit", "hlásat", "kázat", "prohlásit", "prohlašovat",
                        "uvést", "uvádět", "pravit", "sdělit", "sdělovat", "oznámit", "oznamovat",
                        "konstatovat", "vyhlásit", "vyhlašovat", "učit", "vyučovat", "poučit"}),
    "pracovat": frozenset({"pracovat", "působit", "sloužit", "zaměstnat_se", "dělat", "vykonávat"}),
    "narodit_se": frozenset({"narodit_se", "přijít_na_svět"}),
    "zemřít": frozenset({"zemřít", "umřít", "skonat", "zahynout", "padnout", "zesnout"}),
    "bydlet": frozenset({"bydlet", "žít", "sídlit", "pobývat", "přebývat", "usadit_se", "usídlit_se"}),
    "napsat": frozenset({"napsat", "sepsat", "psát", "vydat", "vydávat", "publikovat", "uveřejnit",
                         "sepisovat", "zveřejnit"}),
    "studovat": frozenset({"studovat", "vystudovat", "absolvovat", "navštěvovat", "chodit"}),
    "založit": frozenset({"založit", "zakládat", "ustavit", "zřídit", "vytvořit", "vybudovat"}),
    "stát_se": frozenset({"stát_se", "stávat_se"}),
    "získat": frozenset({"získat", "získávat", "obdržet", "dostat", "dostávat", "vyhrát"}),
    "odejít": frozenset({"odejít", "odjet", "odcestovat", "emigrovat", "odstěhovat_se", "opustit"}),
    "vrátit_se": frozenset({"vrátit_se", "vracet_se", "navrátit_se"}),
    "obsahovat": frozenset({"obsahovat", "zahrnovat", "mít", "skládat_se", "sestávat", "sestávat_se", "čítat"}),
    "jet": frozenset({"jet", "jezdit", "cestovat", "odjet", "přijet", "dojet"}),
    "létat": frozenset({"létat", "letět"}),
    "vyžadovat": frozenset({"vyžadovat", "potřebovat", "vyžádat_si"}),
    "oženit_se": frozenset({"oženit_se", "vdát_se", "vzít_si", "uzavřít_sňatek"}),
    "zúčastnit_se": frozenset({"zúčastnit_se", "účastnit_se", "podílet_se"}),
    "začít": frozenset({"začít", "začínat", "zahájit", "započít"}),
}


def synonym_class(pred: str, learned: dict[str, str] | None = None) -> str:
    """Reprezentant třídy synonym (nebo predikát sám, když třídu nemá).

    `learned` jsou dvojice `a → b` naučené dialogem (drží je paměť);
    slučují třídy obou stran, takže reprezentant je ten seedový."""
    def seed_rep(x: str) -> str:
        for rep, members in SYNONYMS.items():
            if x == rep or x in members:
                return rep
        return x
    rep = seed_rep(pred)
    if not learned:
        return rep
    # union-find nad naučenými dvojicemi
    parent: dict[str, str] = {}
    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in learned.items():
        ra, rb = find(seed_rep(a)), find(seed_rep(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return find(rep)


#: Srovnávací slova — OSIVO (výchozí, přepisuje dialog `!srovnání` nebo definiční
#: věta „Starší je ten, kdo se narodil dřív.“): lemma → (predikát, role, směr).
#: Směr: `earlier`/`later` na časové ose, `more`/`less` na číslech (počty).
COMPARATIVES_SEED: dict[str, tuple[str, str, str]] = {
    "starý": ("narodit_se", "kdy", "earlier"),
    "mladý": ("narodit_se", "kdy", "later"),
}

#: Příslovce směru v definiční větě: „dřív“, „později“, „víc“, „míň“.
DIRECTION_ADVERBS: dict[str, str] = {
    "dříve": "earlier", "dřív": "earlier", "brzy": "earlier", "brzo": "earlier",
    "pozdě": "later", "později": "later",
    "více": "more", "víc": "more", "hodně": "more", "mnoho": "more", "déle": "more", "dlouho": "more",
    "méně": "less", "míň": "less", "málo": "less", "kratší": "less",
}


#: Inverze vztahových jmen — OSIVO: X ∈ R⟨Y⟩ ⇒ Y ∈ R'⟨X⟩ pro některé R' (podle rodu Y).
#: „Jana ∈ manželka⟨Petr⟩“ ⇒ „Petr ∈ manžel⟨Jana⟩“; „Karel ∈ otec⟨Petr⟩“ ⇒ „Petr ∈ syn/dcera⟨Karel⟩“.
RELATION_CONVERSE: dict[str, tuple[str, ...]] = {
    "manžel": ("manželka",), "manželka": ("manžel",),
    "otec": ("syn", "dcera"), "matka": ("syn", "dcera"),
    "syn": ("otec", "matka"), "dcera": ("otec", "matka"),
    "bratr": ("bratr", "sestra"), "sestra": ("bratr", "sestra"),
    "sourozenec": ("sourozenec",), "rodič": ("dítě",), "dítě": ("rodič",),
}

#: Rod, který vztahové jméno vyžaduje od SVÉHO nositele (X ∈ otec⟨…⟩ ⇒ X je muž).
RELATION_GENDER: dict[str, str] = {
    "otec": "Masc", "manžel": "Masc", "bratr": "Masc", "syn": "Masc", "děd": "Masc", "dědeček": "Masc",
    "strýc": "Masc", "tchán": "Masc", "zeť": "Masc", "vnuk": "Masc", "synovec": "Masc", "pravnuk": "Masc",
    "matka": "Fem", "manželka": "Fem", "sestra": "Fem", "dcera": "Fem", "bába": "Fem", "babička": "Fem",
    "teta": "Fem", "tchyně": "Fem", "snacha": "Fem", "vnučka": "Fem", "neteř": "Fem", "prababička": "Fem",
}


#: „Jak rychle?“ → veličina „rychlost“ (příslovce/přídavné jméno → jméno veličiny). Data, doplnitelná.
#: číslovky slovem → číslo (počty „šestnáct kamenů“, „dvě dcery“); víceslovné se sčítají/násobí v čtečce
NUMERALS: dict[str, int] = {
    "nula": 0, "jeden": 1, "jedna": 1, "jedno": 1, "dva": 2, "dvě": 2, "oba": 2, "obě": 2, "tři": 3, "čtyři": 4, "pět": 5,
    "šest": 6, "sedm": 7, "osm": 8, "devět": 9, "deset": 10, "jedenáct": 11, "dvanáct": 12, "třináct": 13,
    "čtrnáct": 14, "patnáct": 15, "šestnáct": 16, "sedmnáct": 17, "osmnáct": 18, "devatenáct": 19, "dvacet": 20,
    "třicet": 30, "čtyřicet": 40, "padesát": 50, "šedesát": 60, "sedmdesát": 70, "osmdesát": 80, "devadesát": 90,
    "sto": 100, "dvěstě": 200, "tisíc": 1000, "milion": 1_000_000, "miliarda": 1_000_000_000,
}


def number_of(form: str, lemma: str) -> int | None:
    """Číslo z tvaru („16“, „30 000“, „3,5“→3) nebo z číslovky slovem („šestnáct“); jinak None."""
    raw = form.replace(",", ".").replace(" ", "").replace("\u00a0", "").rstrip(".")
    if raw.replace(".", "", 1).isdigit():
        try:
            return int(float(raw))
        except ValueError:
            return None
    return NUMERALS.get(lemma.lower())


ADVERB_QUANTITY: dict[str, str] = {
    "rychle": "rychlost", "rychlý": "rychlost", "dlouho": "doba", "dlouhý": "délka", "daleko": "vzdálenost",
    "vysoko": "výška", "vysoký": "výška", "hluboko": "hloubka", "hluboký": "hloubka", "těžký": "hmotnost",
    "široký": "šířka", "starý": "věk", "často": "četnost", "teplý": "teplota", "silný": "síla",
}

#: slovesa umístění: dotaz „být(kde)“ („Co je v úlu?“, „Kde je Praha?“) sedí i na ně (přiznaně)
LOCATIVE_VERBS: frozenset[str] = frozenset({"nacházet_se", "ležet", "rozkládat_se", "vyskytovat_se", "stát", "nalézat_se", "být_umístěn"})

#: substantiva veličin: „do velikosti 12–14 mm“, „o hmotnosti 100 mg“ → role <veličina>: hodnota s jednotkou
QUANTITY_NOUNS: frozenset[str] = frozenset(set(ADVERB_QUANTITY.values()) | {
    "velikost", "plocha", "objem", "výkon", "spotřeba", "kapacita", "tloušťka", "průměr", "obvod", "nadmořská výška",
    "rozloha", "hustota", "tlak", "napětí", "frekvence", "cena", "výška", "hmotnost", "teplota", "rychlost", "délka",
})

#: veličiny, které se ptají stejným slovem: „Jak silný je příkrov?“ = tloušťka; velikost ~ rozměr
QUANTITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "síla": ("tloušťka",), "tloušťka": ("síla",), "velikost": ("rozměr", "délka", "výška"), "rozměr": ("velikost",),
    "hmotnost": ("váha",), "váha": ("hmotnost",), "vzdálenost": ("délka",),
}

#: Přívlastek veličiny → mez v odpovědi („maximální rychlost“ → „nejvýše“).
QUANTITY_BOUNDS: dict[str, str] = {
    "maximální": "nejvýše", "nejvyšší": "nejvýše", "nejvýše": "nejvýše", "horní": "nejvýše", "povolený": "nejvýše",
    "minimální": "nejméně", "nejnižší": "nejméně", "dolní": "nejméně", "průměrný": "průměrně", "obvyklý": "obvykle",
}
