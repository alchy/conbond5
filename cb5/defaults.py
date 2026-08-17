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
    ("díky", "Dat"): {"*": "díky+Dat"},
    ("kvůli", "Dat"): {"*": "kvůli+Dat"},
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
    "proč": ("advcl:protože", "filler"), "čí": ("čí", "filler"), "jak": ("jak", "filler"),
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
ADVERB_QUANTITY: dict[str, str] = {
    "rychle": "rychlost", "rychlý": "rychlost", "dlouho": "doba", "dlouhý": "délka", "daleko": "vzdálenost",
    "vysoko": "výška", "vysoký": "výška", "hluboko": "hloubka", "hluboký": "hloubka", "těžký": "hmotnost",
    "široký": "šířka", "starý": "věk", "často": "četnost", "teplý": "teplota", "silný": "síla",
}

#: Přívlastek veličiny → mez v odpovědi („maximální rychlost“ → „nejvýše“).
QUANTITY_BOUNDS: dict[str, str] = {
    "maximální": "nejvýše", "nejvyšší": "nejvýše", "nejvýše": "nejvýše", "horní": "nejvýše", "povolený": "nejvýše",
    "minimální": "nejméně", "nejnižší": "nejméně", "dolní": "nejméně", "průměrný": "průměrně", "obvyklý": "obvykle",
}
