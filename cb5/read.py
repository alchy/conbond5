"""Čtení: rozbor jedné věty → predikace, ve které **nic se neztrácí**.

Proč takhle: conbond4 měl 22 pater kaskády, která si předávala kandidáty
a každé mohlo čtení zastavit otázkou. conbond5 čte **tabulkově**: kořen
rozhodne druh predikace (sloveso / kopula / fragment), každý závislý člen
se podle deprelu zařadí do role, atributu, vnořené predikace, částice —
a co nikam nepatří, skončí ve **zbytku** s cestou deprelů. Výsledek je
vždy: čtení existuje, a je vidět, co v něm chybí.

Výchozí volby (jméno role z předložky + pádu, kvantifikátor z tvaru,
kopula → member/subset/within) se berou z `defaults.py` a **každá se
zapíše** do `Predication.defaults`, aby ji paměť a odpověď mohly citovat.

Vstup: `Parse` (viz `oracle.py`), volitelně `mood`.
Výstup: `Reading` = hlavní predikace + vedlejší predikace + zbytek +
`placement()` (index tokenu → kam se dostal). Test „každý token má právě
jedno místo“ je pojistka proti tichému zahazování.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

from cb5 import defaults as D
from cb5.chronos import MONTHS, TimeSpec, is_time_noun, time_from_tokens

MONTH_LEMMAS = frozenset(MONTHS)
from cb5.oracle import Parse, Token

Quant = Literal["∀", "∃", "·"]
Kind = Literal["entity", "group", "place", "time", "value", "pron", "wh", "var"]


def _name_lemma(tok: Token) -> str:
    """Lemma vlastního jména s velkým písmenem podle tvaru („Alík“ má v UDPipe lemma „alík“)."""
    if tok.upos == "PROPN" and tok.form[:1].isupper() and tok.lemma[:1].islower():
        return tok.lemma[:1].upper() + tok.lemma[1:]
    return tok.lemma

#: Deprely, které nesou strukturu, ne obsah — pohltí je jejich hlava.
STRUCTURAL = frozenset(
    {"aux", "aux:pass", "cop", "cc", "cc:preconj", "mark", "case", "det", "det:numgov",
     "det:nummod", "expl:pv", "expl:pass", "expl", "fixed", "flat", "flat:name",
     "flat:foreign", "compound", "goeswith", "reparandum", "punct", "clf", "dep:aux"}
)


@dataclass
class TermSpec:
    """Jeden term v roli: co věta jmenuje, ještě před zakotvením do paměti.

    `kind` říká, jaký uzel má vzniknout (entita, group, místo, čas, hodnota,
    zájmeno k rozřešení, tázací díra); `attrs` jsou pohlcené přívlastky
    (`amod`), `count` číslovka, `time` rozpoznaný čas; `quant` + autorita
    kvantifikátoru; `tokens` = všechny tokeny, které term spotřeboval.
    """

    head: int
    lemma: str
    forms: tuple[str, ...]
    upos: str
    kind: Kind
    attrs: tuple[str, ...] = ()
    count: int | None = None
    #: horní mez rozsahu („30 000–50 000 dělnic“, „12–14 mm“): count = dolní mez
    count_hi: int | None = None
    #: původní zápis čísla/rozsahu, když ho int neunese („1–4,5“, „3,5“)
    count_text: str = ""
    #: jméno veličiny, když term vznikl z „velikosti 12–14 mm“ (hodnota s jednotkou pod substantivem veličiny)
    quantity: str = ""
    time: TimeSpec | None = None
    gender: str | None = None
    number: str | None = None
    person: str | None = None
    quant: Quant | None = None
    quant_authority: str = ""
    tokens: tuple[int, ...] = ()
    name_tokens: tuple[int, ...] = ()
    #: Lemmata tokenů jména (klíč identity entity: „Alois Jirásek“).
    name_lemmas: tuple[str, ...] = ()
    #: Přivlastnění: `("pron", "jeho")` nebo `("adj", "Filipův")` — rozřeší se v paměti.
    possessor: tuple[str, str] | None = None
    #: Zúžení group vztažnou / participiální větou apod. jen jako poznámka pro render.
    note: str = ""
    #: Zúžení třídy genitivem vlastního jména: „otec Petra Nováka“ → ("Gen", term Petr Novák).
    rel: "tuple[str, TermSpec] | None" = None
    #: Alternativy zúžení z koordinace: „otec manžela NEBO manželky“ → (term manželka,).
    rel_alts: "tuple[TermSpec, ...]" = ()

    def label(self) -> str:
        if self.kind in ("entity", "place") and self.name_lemmas:
            return " ".join(self.name_lemmas)
        if self.kind == "time" and self.time is not None:
            return self.time.label
        out = self.lemma
        if self.count is not None:
            out += f"#{self.count}"
        if self.possessor:
            out += f"⟨{self.possessor[1]}⟩"
        if self.rel is not None:
            out += f"⟨{self.rel[1].label()}⟩"
        return out


@dataclass
class RoleFill:
    """Role predikace: jméno (`kdo`, `kde`, `v+Loc`…), termy (koordinace =
    víc termů), autorita jména (`structural` / `default` / `learned` /
    `surface`), případně vnořená predikace nebo tázací díra."""

    name: str
    surface: str
    terms: list[TermSpec] = field(default_factory=list)
    authority: str = "structural"
    nested: "Predication | None" = None
    wh: bool = False
    wh_kind: str = ""

    def __str__(self) -> str:
        if self.nested is not None:
            return f"{self.name}:[{self.nested}]"
        if self.wh and not self.terms:
            return f"{self.name}:?"
        prefix = f"{self.name}:?{self.wh_kind}:" if self.wh else f"{self.name}:"
        return prefix + "+".join(
            (t.quant or "") + t.label() + ("".join(f"[{a}]" for a in t.attrs)) for t in self.terms
        )


@dataclass
class Predication:
    """Jedna predikace: predikát + role + polarita + modalita (+ jádrová
    relace u kopuly). `secondary` jsou další predikace téže věty (vztažná
    věta, přívlastek jako vztah, souřadný přísudek, životopisná závorka)."""

    pred: str | None
    kind: Literal["verb", "copula", "fragment", "nmod", "appos"]
    neg: bool = False
    modality: str | None = None
    kernel: str | None = None
    roles: list[RoleFill] = field(default_factory=list)
    mood: Literal["assert", "question"] = "assert"
    head: int = 0
    tokens: tuple[int, ...] = ()
    defaults: list[str] = field(default_factory=list)
    secondary: list["Predication"] = field(default_factory=list)
    tense: str | None = None
    #: „Ne, …“ na začátku: věta opravuje předchozí tvrzení (dialog).
    correction: bool = False
    #: U kopuly jméno role predikátového nominálu (`co` / `jaký` / `kde`…).
    pred_role_name: str = ""
    #: Vnořená věta, která NETVRDÍ svůj obsah („pokud prší“): „podmínka“ / „účel“ / „vedlejší“; "" = tvrdí.
    embedded: str = ""
    #: Věta má tvar definice vztahového jména („Tchán je otec manžela“) — zapíše se jako fakt
    #: A NAVÍC se z ní vezme definiční řetěz (tvar sám nerozhodne, jestli je to definice).
    definition: bool = False

    def role(self, name: str) -> RoleFill | None:
        for r in self.roles:
            if r.name == name:
                return r
        return None

    def __str__(self) -> str:
        head = self.pred or "∅"
        if self.neg:
            head = "¬" + head
        if self.modality:
            head = f"{self.modality}:{head}"
        body = ", ".join(str(r) for r in self.roles)
        k = f" ⟨{self.kernel}⟩" if self.kernel else ""
        return f"{head}({body}){k}"


@dataclass
class Reading:
    """Výsledek čtení jedné věty."""

    parse: Parse
    main: Predication
    residue: list[tuple[str, str]] = field(default_factory=list)
    _placement: dict[int, str] = field(default_factory=dict)

    def placement(self) -> dict[int, str]:
        return dict(self._placement)

    def all_predications(self) -> list[Predication]:
        out: list[Predication] = []

        def walk(p: Predication) -> None:
            out.append(p)
            for r in p.roles:
                if r.nested is not None:
                    walk(r.nested)
            for s in p.secondary:
                walk(s)

        walk(self.main)
        return out


# ==========================================================================
# Čtečka
# ==========================================================================


class _Reader:
    """Stavová čtečka jedné věty (drží rozbor a mapu umístění tokenů)."""

    def __init__(self, parse: Parse, mood: str | None, learned_roles: Mapping[str, str] | None = None) -> None:
        self.p = parse
        self._cond_depth = 0  # >0 = čteme větu pod podmínkovou spojkou („pokud někdo …“ → někdo je proměnná)
        self.learned_roles: Mapping[str, str] = learned_roles or {}
        self.place: dict[int, str] = {}
        self.residue: list[tuple[str, str]] = []
        self.mood: str = mood or ("question" if parse.text.rstrip().endswith("?") or self._has_wh() else "assert")

    # ---- pomocníci -------------------------------------------------------

    def _has_wh(self) -> bool:
        first = next((t for t in self.p.tokens if t.upos != "PUNCT"), None)
        return bool(first and "Int" in (first.feat("PronType") or "") and self.p.text.rstrip().endswith("?"))

    def kids(self, i: int, *deprels: str) -> list[Token]:
        """Děti podle ZÁKLADNÍHO deprelu (`obl` bere i `obl:arg`)."""
        return [t for t in self.p.children(i) if not deprels or t.base_deprel in deprels or t.deprel in deprels]

    def mark(self, indices: int | list[int] | tuple[int, ...], where: str) -> None:
        if isinstance(indices, int):
            indices = [indices]
        for i in indices:
            self.place.setdefault(i, where)

    def case_of(self, i: int) -> str:
        """Předložka členu (lemma `case`; víceslovná přes `fixed` se spojí)."""
        for c in self.p.children(i):
            if c.base_deprel == "case":
                parts = [c.lemma] + [f.lemma for f in self.p.children(c.index) if f.base_deprel == "fixed"]
                return " ".join(parts)
        return ""

    def is_neg(self, t: Token) -> bool:
        return t.feat("Polarity") == "Neg" and t.upos in ("VERB", "AUX", "ADJ")

    # ---- vstup -------------------------------------------------------------

    def read(self) -> Reading:
        root = self.p.root()
        cop = self.kids(root.index, "cop")
        if cop:
            main = self._copula(root, cop[0])
        elif root.upos in ("VERB",) or (root.upos == "AUX" and root.lemma == "být"):
            if root.upos == "AUX":
                main = self._aux_root(root)
            else:
                main = self._verb(root)
        else:
            main = self._fragment(root)
        main.mood = self.mood  # type: ignore[assignment]
        self._sweep()
        return Reading(parse=self.p, main=main, residue=self.residue, _placement=self.place)

    def _sweep(self) -> None:
        """Každý token dostane místo: co není umístěné, je částice
        (strukturní deprel) nebo zbytek s cestou deprelů."""
        for t in self.p.tokens:
            if t.index in self.place:
                continue
            if t.upos == "PUNCT" or t.base_deprel == "punct":
                self.place[t.index] = "punct"
            elif t.deprel in STRUCTURAL or t.base_deprel in STRUCTURAL:
                self.place[t.index] = "particle"
            elif t.lemma in D.PARTICLES and t.upos in ("ADV", "PART", "CCONJ", "SCONJ", "INTJ"):
                self.place[t.index] = "particle"
            else:
                self.place[t.index] = "residue"
                self.residue.append((t.form, self.p.path(t.index)))

    # ---- predikace slovesa -------------------------------------------------

    def _verb(self, head: Token, *, shared_subject: RoleFill | None = None) -> Predication:
        pred_head = head
        modality: str | None = None
        heads = [head]
        # modální / fázové sloveso + infinitiv → predikát je infinitiv
        if head.lemma in D.MODAL_VERBS:
            inf = [t for t in self.kids(head.index, "xcomp") if t.upos == "VERB" and t.feat("VerbForm") == "Inf"]
            if inf:
                modality = D.MODAL_VERBS[head.lemma]
                pred_head = inf[0]
                heads = [head, inf[0]]
                self.mark(head.index, "pred")
            else:
                # „může být fatální“ — xcomp se sponou: kopula s modalitou
                copx = [t for t in self.kids(head.index, "xcomp") if self.kids(t.index, "cop")]
                if copx:
                    self.mark(head.index, "pred")
                    subj = [t for t in self.kids(head.index, "nsubj")]
                    p = self._copula(copx[0], self.kids(copx[0].index, "cop")[0])
                    p.modality = D.MODAL_VERBS[head.lemma]
                    if subj and p.role("kdo") is not None and p.role("kdo").authority == "prodrop":  # type: ignore[union-attr]
                        p.roles.remove(p.role("kdo"))  # type: ignore[arg-type]
                    if subj and p.role("kdo") is None:
                        self._add_role(p, "kdo", subj[0].deprel, subj[0])
                        p.roles.insert(0, p.roles.pop())
                        self._quantify(p)
                        pr = p.role(p.pred_role_name)
                        if pr is not None:
                            p.kernel = self._copula_kernel(p, pr)
                    for a in self.kids(head.index, "aux"):
                        self.mark(a.index, "particle")
                    for t in self.p.children(head.index):
                        if t.base_deprel in ("obl", "advmod", "advcl") and t.index not in self.place:
                            self._roles_of_single(t, p)
                    return p
        pred = self._lemma_with_refl(pred_head)
        p = Predication(pred=pred, kind="verb", modality=modality, head=pred_head.index)
        p.tense = pred_head.feat("Tense") or head.feat("Tense")
        self.mark(pred_head.index, "pred")
        neg = self.is_neg(head) or self.is_neg(pred_head)
        for h in heads:
            for a in self.kids(h.index, "aux"):
                if self.is_neg(a):
                    neg = True
                self.mark(a.index, "particle")
            for adv in self.kids(h.index, "advmod"):
                if adv.lemma == "ne" or (adv.upos == "PART" and adv.feat("Polarity") == "Neg"):
                    if adv.index == 1 and len(self.p.tokens) > 1 and self.p.token(2).form == ",":
                        p.correction = True  # „Ne, …“ = oprava předchozího, ne zápor věty
                    else:
                        neg = True
                    self.mark(adv.index, "particle")
        p.neg = neg
        passive = any(t.deprel == "nsubj:pass" for h in heads for t in self.p.children(h.index)) or any(
            a.deprel == "aux:pass" for h in heads for a in self.p.children(h.index)
        )
        for h in heads:
            self._roles_of(h, p, passive=passive)
        if shared_subject is not None and p.role("kdo") is None:
            p.roles.insert(0, RoleFill("kdo", shared_subject.surface, list(shared_subject.terms), "shared"))
        self._subject_from_ambiguity(p)
        self._prodrop(p, heads)
        self._quantify(p)
        self._membership_verb(p)
        self._quantity_roles(p)
        if p.pred in D.LOCATIVE_VERBS and not p.neg and p.modality is None and p.role("kde") is not None:
            # „Brno leží na Moravě.“ = Brno uvnitř Moravy (jádro within) — jen místo v místě
            s0 = p.role("kdo")
            if s0 and s0.terms and s0.terms[0].kind == "place" and all(t.kind == "place" for t in p.role("kde").terms):  # type: ignore[union-attr]
                p.kernel = "within"
                p.defaults.append("kernel:within (místo leží v místě)")
        # souřadné přísudky: druhá predikace se sdíleným podmětem
        for h in heads:
            for c in self.kids(h.index, "conj"):
                if c.upos == "VERB" or self.kids(c.index, "cop"):
                    self.mark(c.index, "secondary")
                    shared = p.role("kdo")
                    if self.kids(c.index, "cop"):
                        sec = self._copula(c, self.kids(c.index, "cop")[0], shared_subject=shared)
                    else:
                        sec = self._verb(c, shared_subject=shared)
                    p.secondary.append(sec)
                    self.mark(c.index, "secondary")
        return p

    def _quantity_roles(self, p: Predication) -> None:
        """„Telefon má na délku 10 cm.“ / „Kapsa je na délku 8 cm.“: role s jménem veličiny
        (na+Acc: délka) + role s hodnotou (co: 10 cm) → jedna role `délka: 10 cm`."""
        for r in p.roles:
            if len(r.terms) == 1 and r.terms[0].quantity and not r.wh and r.name not in ("kdo",):
                p.defaults.append(f"veličina {r.terms[0].quantity}: „{r.surface}“ + hodnota → role {r.terms[0].quantity}")
                r.name, r.authority = r.terms[0].quantity, "default"
        qnames = set(D.ADVERB_QUANTITY.values())
        qrole = next((r for r in p.roles if r.name not in ("kdo", "co", "jaký", "kde", "kdy", "kam") and r.terms and len(r.terms) == 1
                      and r.terms[0].kind == "group" and r.terms[0].lemma in qnames and r.terms[0].count is None and not r.wh), None)
        vrole = next((r for r in p.roles if r is not qrole and r.terms and any(t.count is not None for t in r.terms) and not r.wh), None)
        if qrole is None or vrole is None:
            return
        qname = qrole.terms[0].lemma
        p.roles.remove(qrole)
        vrole.name, vrole.authority = qname, "default"
        p.defaults.append(f"veličina {qname}: „{qrole.surface}“ + hodnota → role {qname}")

    def _membership_verb(self, p: Predication) -> None:
        """„Pes patří mezi šelmy“ / „patří do skupiny“ / „náleží k“ → jádrová
        relace subset (obecný podmět) nebo member (určitý), role `co`."""
        if p.pred not in ("patřit", "náležet", "řadit_se", "spadat"):
            return
        target = next((r for r in p.roles if r.surface in ("mezi+Acc", "do+Gen", "k+Dat", "pod+Acc") and r.terms), None)
        subj = p.role("kdo")
        if target is None or subj is None or not subj.terms:
            return
        target.name, target.authority = "co", "default"
        st = subj.terms[0]
        p.kernel = "member" if (st.kind in ("entity", "pron", "place", "var") or st.quant == "·") else "subset"
        p.defaults.append(f"kernel:{p.kernel} (patřit {target.surface})")

    def _lemma_with_refl(self, t: Token) -> str:
        lemma = t.lemma
        for c in self.p.children(t.index):
            if c.deprel in ("expl:pv", "expl") and c.form.lower() in ("se", "si"):
                lemma = f"{lemma}_{c.form.lower()}"  # UDPipe má pro „si“ lemma „se“ — rozhoduje tvar
                self.mark(c.index, "particle")
        return lemma

    def _roles_of(self, h: Token, p: Predication, *, passive: bool) -> None:
        for t in self.p.children(h.index):
            d, base = t.deprel, t.base_deprel
            if t.index in self.place and self.place[t.index] in ("pred", "secondary"):
                continue
            if base in ("nsubj", "csubj"):
                name = "co" if d.endswith(":pass") else "kdo"
                if base == "csubj":
                    p.roles.append(RoleFill(name, "csubj", nested=self._verb_or_cop(t), authority="structural"))
                    self.mark(t.index, "nested")
                else:
                    self._add_role(p, name, d, t)
            elif base == "obj":
                self._add_role(p, "co", d, t)
            elif base == "iobj":
                self._add_role(p, "komu", d, t)
            elif base == "obl":
                if d == "obl:agent":
                    self._add_role(p, "kdo", d, t)
                else:
                    name, surface, authority = self._obl_role(t, arg=(d == "obl:arg"))
                    self._add_role(p, name, surface, t, authority=authority)
            elif base == "advmod":
                self._advmod(t, p)
            elif base == "xcomp":
                if t.upos == "VERB":
                    p.roles.append(RoleFill("co", "xcomp", nested=self._verb(t), authority="structural"))
                    self.mark(t.index, "nested")
                else:
                    self._add_role(p, "co", "xcomp", t)
            elif base == "ccomp":
                p.roles.append(RoleFill("co", "ccomp", nested=self._verb_or_cop(t), authority="structural"))
                self.mark(t.index, "nested")
            elif base == "advcl":
                self._advcl(t, p)
            elif base == "conj":
                if t.upos in ("VERB",) or self.kids(t.index, "cop"):
                    continue  # souřadný přísudek řeší volající
                # souřadný člen pod slovesem: ADV, nebo nominál s pádem → další okolnost
                self._conj_under_verb(t, p)
            elif base == "parataxis":
                if t.upos == "VERB" or self.kids(t.index, "cop"):
                    sec = self._verb_or_cop(t)
                    p.secondary.append(sec)
                    self.mark(t.index, "secondary")
                # jinak nechat sweepu (zbytek)
            elif base == "vocative":
                self._add_role(p, "oslovení", d, t)
            elif base == "obl:tmod" or base == "nmod":
                name, surface, authority = self._obl_role(t, arg=False)
                self._add_role(p, name, surface, t, authority=authority)
            # ostatní (dep, orphan, discourse, list…) → sweep → zbytek

    def _verb_or_cop(self, t: Token) -> Predication:
        cop = self.kids(t.index, "cop")
        if cop:
            return self._copula(t, cop[0])
        if t.upos in ("VERB", "AUX"):
            return self._verb(t)
        # participium / adjektivum jako predikát vedlejší věty („nejsou splněny požadavky“)
        return self._participle(t)

    def _participle(self, t: Token) -> Predication:
        """ADJ‑participium jako přísudek („splněny“, „způsobené“, „provedená“)."""
        p = Predication(pred=t.lemma, kind="verb", head=t.index)
        self.mark(t.index, "pred")
        neg = self.is_neg(t)
        for a in self.kids(t.index, "aux"):
            neg = neg or self.is_neg(a)
            self.mark(a.index, "particle")
        p.neg = neg
        p.tense = next((a.feat("Tense") for a in self.kids(t.index, "aux") if a.feat("Tense")), None)
        self._roles_of(t, p, passive=True)
        self._quantify(p)
        return p

    def _add_role(
        self, p: Predication, name: str, surface: str, t: Token, *, authority: str = "structural"
    ) -> None:
        if not any(ch.isalnum() for ch in t.form):
            return  # „>“, „–“ apod. nejsou termy — skončí ve zbytku (sweep)
        wh = self._wh_of(t)
        role = RoleFill(name, surface, authority=authority)
        if wh is not None:
            role.name, role.wh_kind = wh
            role.wh = True
            if name == "kdo" and t.lemma in ("kdo", "co") and (t.feat("Case") in (None, "Nom")):
                role.name = "kdo"  # tázací PODMĚT zůstává podmět („Co je v lednici?“ → kdo:?)
            if self.case_of(t.index) or any(c.base_deprel == "mark" for c in self.p.children(t.index)):
                # „Jako co“, „S kým“, „V čem“ — díra má jméno podle předložky
                mark = next((c.lemma for c in self.p.children(t.index) if c.base_deprel == "mark"), "")
                if mark == "jako":
                    role.name = "jako"
                    for c in self.p.children(t.index):
                        self.mark(c.index, "particle")
                elif self.case_of(t.index):
                    rname, rsurface, _ = self._obl_role(t, arg=False)
                    role.name, role.surface = rname, rsurface
            self.mark(t.index, f"role:{role.name}")
            self._mark_structure(t.index, f"role:{role.name}")
            if role.wh_kind in ("count", "attr") and t.lemma not in D.WH:
                # „kolik zubů“ / „jaké druhy“: díra je počet / vlastnost, term ZŮSTÁVÁ
                # („kolik“ / „jaký“ samo term není)
                role.terms = [self._term(t)]
                role.name = name
            p.roles.append(role)
            return
        role.terms = self._term_group(t)
        if len(role.terms) > 1:
            p.defaults.append(f"koordinace:{name}:distribuce")
        p.roles.append(role)

    def _wh_of(self, t: Token) -> tuple[str, str] | None:
        """Je token tázací díra? Vrací (jméno role, druh)."""
        if self.mood != "question":
            return None
        if t.lemma in D.WH and (
            "Int" in (t.feat("PronType") or "") or t.upos in ("PRON", "DET", "ADV") and not self.p.children(t.index) or D.WH[t.lemma][1] == "count"
        ):
            if t.lemma in ("kdo", "co") and t.upos == "PRON":
                # pád rozhoduje roli: koho/co → co, komu → komu, čím → čím, koho (Gen) → čeho
                by_case = {"Acc": "co", "Dat": "komu", "Ins": "čím", "Gen": "čeho", "Loc": "o_čem"}
                case = t.feat("Case") or "Nom"
                if case in by_case and not self.case_of(t.index):
                    return (by_case[case], "filler")
            return D.WH[t.lemma]
        for c in self.p.children(t.index):
            if c.base_deprel == "det" and c.lemma in D.WH and (
                "Int" in (c.feat("PronType") or "") or D.WH[c.lemma][1] == "count"
            ):
                return D.WH[c.lemma]
        return None

    def _mark_structure(self, i: int, where: str) -> None:
        for c in self.p.children(i):
            if c.deprel in STRUCTURAL or c.base_deprel in STRUCTURAL:
                self.mark(c.index, "particle")

    # ---- okolnosti ---------------------------------------------------------

    def _filler_kind(self, t: Token) -> str:
        """`place` / `time` / `duration` / `*` — druh výplně pro tabulku rolí.
        `duration` = časové substantivum bez ukotveného data („čtrnáct let“)."""
        # pro rozpoznání času jen hlava + přímé číslovky/předložky — celý podstrom by
        # z „v parlamentních volbách v roce 1920“ udělal čas („volba“)
        sub = [x for x in self.p.subtree(t.index) if x.index == t.index or (x.head == t.index and x.base_deprel in ("nummod", "case", "flat"))]
        if is_time_noun(t.lemma):
            sub = [x for x in self.p.subtree(t.index) if x.index == t.index or x.lemma in MONTH_LEMMAS or x.upos in ("NUM", "PUNCT") or is_time_noun(x.lemma)]
        full = self.p.subtree(t.index)
        ago = self.case_of(t.index) == "před" and time_from_tokens(full) is None and any(is_time_noun(x.lemma) and x.index != t.index for x in full)
        if ago:
            return "ago"  # „před 2 miliardami let“, „před třemi lety“ = bod v čase (relativně k teď)
        if is_time_noun(t.lemma) or (t.upos in ("NUM", "ADJ") and time_from_tokens(sub) is not None and not t.feat("NameType")):
            spec = time_from_tokens(sub)
            if is_time_noun(t.lemma) and spec is None:
                return "duration"  # „celý život“, „čtrnáct let“ — bez ukotveného data
            return "time"
        if t.feat("NameType") == "Geo" or t.lemma in D.PLACE_NOUNS:
            return "place"
        if t.upos == "PROPN" and self.case_of(t.index) in D.PLACE_PREPS and t.feat("NameType") in (None, "Geo"):
            # PROPN bez NameType po místní předložce — místo je nejlepší sázka, ale je to výchozí
            return "place?"
        return "*"

    def _obl_role(self, t: Token, *, arg: bool) -> tuple[str, str, str]:
        prep = self.case_of(t.index)
        case = t.feat("Case") or ""
        surface = f"{prep}+{case}" if prep else (case or t.deprel)
        if surface in self.learned_roles:
            return self.learned_roles[surface], surface, "learned"
        table = D.ROLE_BY_CASE.get((prep, case)) or D.ROLE_BY_CASE.get((prep, "")) or {}
        kind = self._filler_kind(t)
        if not arg:
            if kind in ("place", "place?") and "place" in table:
                return table["place"], surface, "default"
            if kind == "time" and "time" in table:
                return table["time"], surface, "default"
            if kind == "duration" and "duration" in table:
                return table["duration"], surface, "default"
            if kind == "ago" or (kind == "duration" and prep == "před"):
                return "kdy", surface, "default"  # „před 2 miliardami let“ = kdy (relativně k teď)
            if kind == "duration" and "time" in table:
                return table["time"], surface, "default"
            if kind == "time" and not prep and "time" not in table:
                return "kdy", surface, "default"  # holý pád s časovým údajem („mezil lety 1900 až 2000“) = kdy
        if "*" in table:
            name = table["*"]
            return name, surface, ("default" if name != surface else "surface")
        return surface, surface, "surface"

    def _advmod(self, t: Token, p: Predication) -> None:
        if t.lemma == "ne" or self.place.get(t.index) == "particle":
            return
        jak = next((c for c in self.p.children(t.index) if c.base_deprel == "advmod" and c.lemma == "jak" and "Int" in (c.feat("PronType") or "")), None)
        if jak is not None and self.mood == "question" and t.lemma in D.ADVERB_QUANTITY:
            # „Jak rychle …?“ → díra na VELIČINU (rychlost) — hodnota s jednotkou
            qname = D.ADVERB_QUANTITY[t.lemma]
            p.roles.append(RoleFill(qname, "jak+advmod", wh=True, wh_kind="value"))
            self.mark(t.index, f"role:{qname}")
            self.mark(jak.index, "particle")
            return
        wh = self._wh_of(t)
        if wh is not None:
            name, kind = wh
            if name == "jak" and p.pred in D.NAMING_VERBS:
                name = "co"  # „Jak se jmenuje pes?“ = díra na jméno
            p.roles.append(RoleFill(name, "advmod", wh=True, wh_kind=kind))
            self.mark(t.index, f"role:{name}")
            return
        if "Rel" in (t.feat("PronType") or "") and t.lemma in D.WH:
            # vztažné příslovce („kde se scházeli“) — místo vyplní hlava vztažné věty
            name, _ = D.WH[t.lemma]
            p.roles.append(RoleFill(name, "advmod", authority="relative"))
            self.mark(t.index, f"role:{name}")
            return
        if t.lemma in D.PARTICLES:
            self.mark(t.index, "particle")
            return
        from cb5.chronos import RELATIVE_DAYS

        if t.lemma in RELATIVE_DAYS or t.lemma in D.SEQUENCE_ADVERBS:
            name = "kdy" if t.lemma in RELATIVE_DAYS else "pořadí"
            term = TermSpec(t.index, t.lemma, (t.form,), t.upos, "time", time=TimeSpec("name", t.lemma), quant="·", quant_authority="structural", tokens=(t.index,))
            role = p.role(name)
            if role is None:
                role = RoleFill(name, "advmod")
                p.roles.append(role)
            role.terms.append(term)
            self.mark(t.index, f"role:{name}")
            for c in self.kids(t.index, "conj"):
                self._conj_under_verb(c, p)
            return
        # ostatní příslovce = způsob
        role = p.role("jak")
        if role is None:
            role = RoleFill("jak", "advmod")
            p.roles.append(role)
        role.terms.append(TermSpec(t.index, t.lemma, (t.form,), t.upos, "group", quant="·", quant_authority="structural", tokens=(t.index,)))
        self.mark(t.index, "role:jak")
        for c in self.kids(t.index, "conj"):
            self._conj_under_verb(c, p)

    def _advcl(self, t: Token, p: Predication) -> None:
        marks = [c for c in self.p.children(t.index) if c.base_deprel == "mark"]
        marker = marks[0].lemma if marks else ""
        for m in marks:
            self.mark(m.index, "particle")
        if t.deprel == "advcl:pred" or (marker == "jako" and t.upos in ("NOUN", "PROPN", "ADJ") and not self.kids(t.index, "cop")):
            # „pracoval jako učitel“ — doplněk, ne věta
            self._add_role(p, "jako", "advcl:pred", t, authority="structural")
            return
        name = f"advcl:{marker}" if marker else "advcl"
        surface0 = name
        tense = t.feat("Tense") or next((a.feat("Tense") for a in self.kids(t.index, "aux", "cop") if a.feat("Tense")), None)
        conditional = marker in D.CONDITIONAL_MARKERS and (marker != "když" or tense in (None, "Pres", "Fut"))
        self._cond_depth += 1 if conditional else 0
        try:
            nested = self._verb_or_cop(t)
        finally:
            self._cond_depth -= 1 if conditional else 0
        authority = "surface"
        if conditional:
            # „X, pokud Y“ / „Když Y, X“: X platí jen za podmínky Y — Y se netvrdí
            name, authority = "podmínka", "default"
            nested.embedded = "podmínka"
            p.defaults.append(f"podmínka: {marker}")
            for c in self.p.children(p.head):
                if c.base_deprel == "advmod" and c.lemma in ("pak", "tak", "potom") and c.index not in self.place:
                    self.mark(c.index, "particle")
        elif marker in D.NON_ASSERTED_MARKERS:
            nested.embedded = D.NON_ASSERTED_MARKERS[marker]
            if nested.embedded == "účel":
                name, authority = "účel", "default"  # „aby koupil chleba“ — účel (netvrdí se, ale odpovídá na „proč“)
        elif marker in D.CAUSAL_MARKERS:
            name, authority = "proč", "default"  # „protože byl nemocný“ = důvod (odpověď na „proč“)
        if marker in D.TEMPORAL_MARKERS and not conditional and name.startswith("advcl"):
            name, authority = "kdy", "default"  # „když přišel domů“, „než odešla“ = časové určení větou
        p.roles.append(RoleFill(name, surface0, nested=nested, authority=authority))
        self.mark(t.index, "nested")

    def _gapping(self, t: Token, p: Predication) -> bool:
        """Elipsa přísudku: „Dospělý pes má 42 zubů, štěně 28 mléčných zubů.“ — `conj` člen
        v nominativu s `orphan` dětmi = druhá predikace s TÝMŽ přísudkem: mít(kdo: štěně, co: 28 zubů)."""
        orphans = [c for c in self.p.children(t.index) if c.base_deprel == "orphan"]
        if not orphans or t.upos not in ("NOUN", "PROPN", "PRON") or p.pred is None:
            return False
        sec = Predication(pred=p.pred, kind="verb", head=t.index, tense=p.tense, modality=p.modality, neg=p.neg)
        sec.defaults.append("elipsa přísudku (orphan): přísudek doplněn z hlavní věty")
        self.mark(t.index, f"role:kdo")
        subj_first = t.feat("Case") in (None, "Nom")
        if subj_first:
            sec.roles.append(RoleFill("kdo", "conj", self._term_group(t), "default"))
        for o in orphans:
            if o.upos in ("NOUN", "PROPN", "PRON", "NUM", "ADJ"):
                name, surface, authority = ("co", "orphan", "default") if not self.case_of(o.index) else self._obl_role(o, arg=False)
                if not subj_first and sec.role("kdo") is None and o.feat("Case") in (None, "Nom"):
                    name = "kdo"
                self._add_role(sec, name, surface, o, authority=authority)
            elif o.upos == "ADV":
                self._advmod(o, sec)
        self._quantify(sec)
        p.secondary.append(sec)
        return True

    def _conj_under_verb(self, t: Token, p: Predication) -> None:
        """Souřadný člen zavěšený pod sloveso/příslovce: `nejprve v Litomyšli a poté v Praze`."""
        for c in self.p.children(t.index):
            if c.base_deprel == "cc":
                self.mark(c.index, "particle")
        if self._gapping(t, p):
            return
        if t.upos == "VERB" or self.kids(t.index, "cop") or (t.upos == "ADJ" and self.kids(t.index, "aux", "nsubj")):
            p.secondary.append(self._verb_or_cop(t) if t.upos != "ADJ" or self.kids(t.index, "cop") else self._participle(t))
            self.mark(t.index, "secondary")
            return
        if t.upos == "ADV":
            self._advmod(t, p)
            return
        if t.upos in ("NOUN", "PROPN", "PRON", "NUM", "ADJ", "DET"):
            name, surface, authority = self._obl_role(t, arg=False)
            role = p.role(name)
            term = self._term(t)
            if role is None:
                p.roles.append(RoleFill(name, surface, [term], authority))
            else:
                role.terms.append(term)
            for c in self.kids(t.index, "conj"):
                self._conj_under_verb(c, p)
            return
        if t.upos == "VERB" or self.kids(t.index, "cop"):
            p.secondary.append(self._verb_or_cop(t))
            self.mark(t.index, "secondary")

    # ---- podmět nevyslovený, kvantifikace ---------------------------------

    def _subject_from_ambiguity(self, p: Predication) -> None:
        """Nom = Acc: parser dal dva `obj` a žádný podmět („Obsahuje citron
        vitamín C?“). Podmět je ten, který se shoduje s přísudkem v čísle;
        při shodě obou první v pořadí věty. Výchozí volba, označená."""
        if p.role("kdo") is not None:
            return
        objs = [r for r in p.roles if r.name == "co" and r.surface == "obj" and r.terms and not r.wh]
        if len(objs) < 2:
            return
        head = self.p.token(p.head)
        number = head.feat("Number") or next((a.feat("Number") for a in self.kids(head.index, "aux") if a.feat("Number")), None)
        agreeing = [r for r in objs if r.terms[0].number == number] if number else objs
        chosen = min(agreeing or objs, key=lambda r: r.terms[0].head)
        chosen.name = "kdo"
        chosen.authority = "default"
        p.defaults.append("kdo:podmět z pádové dvojznačnosti (shoda čísla, pořadí)")
        for r in objs:
            for t in r.terms:
                t.quant = None
                t.quant_authority = ""

    def _prodrop(self, p: Predication, heads: list[Token]) -> None:
        if p.role("kdo") is not None or p.role("co") and any(r.surface == "nsubj:pass" for r in p.roles):
            return
        if any(r.surface == "nsubj:pass" for r in p.roles):
            return
        h = heads[0]
        finite = h.feat("VerbForm") in ("Fin", "Part") or any(a.feat("VerbForm") == "Fin" for a in self.kids(h.index, "aux"))
        if not finite:
            return
        for r in p.roles:
            # „Pokud někdo bydlí v Brně, bydlí na Moravě.“: nevyslovený podmět = proměnná podmínky
            if r.name == "podmínka" and r.nested is not None:
                vk = r.nested.role("kdo")
                if vk is not None and vk.terms and vk.terms[0].kind == "var":
                    p.roles.insert(0, RoleFill("kdo", "podmínka", [vk.terms[0]], "default"))
                    p.defaults.append("kdo: proměnná z podmínky")
                    return
        for r in p.roles:
            # „Než Jana odešla, zamkla dveře.“: nevyslovený podmět = JMÉNO v podmětu PŘEDCHÁZEJÍCÍ vedlejší věty
            # téže věty (shoda rodu, je‑li znám); vedlejší věta za hlavní („…, jelikož jeho matka onemocněla“) ne
            if r.nested is not None and r.name not in ("co", "kdo") and r.nested.head < h.index:
                nk = r.nested.role("kdo")
                if nk is not None and nk.terms and nk.terms[0].kind == "entity" and nk.authority != "prodrop":
                    t0 = nk.terms[0]
                    hg = h.feat("Gender") or ""
                    if hg and t0.gender and t0.gender not in hg.split(","):  # „zamkla“ = Fem,Neut
                        continue
                    p.roles.insert(0, RoleFill("kdo", "advcl", [t0], "default"))
                    p.defaults.append(f"kdo: „{t0.forms[0] if t0.forms else t0.lemma}“ z vedlejší věty (nevyslovený podmět)")
                    return
        person = h.feat("Person") or next((a.feat("Person") for a in self.kids(h.index, "aux") if a.feat("Person")), None)
        gender = h.feat("Gender")
        number = h.feat("Number") or next((a.feat("Number") for a in self.kids(h.index, "aux") if a.feat("Number")), None)
        # neosobní: 3. os. sg. neutrum bez podmětu („prší“, „jedná se“) → nedosazovat
        if person == "3" and gender == "Neut" and number == "Sing" and p.pred and p.pred.endswith("_se"):
            return
        if person in ("3", None) and number in ("Sing", None) and p.pred in D.IMPERSONAL_VERBS and gender in ("Neut", None):
            p.defaults.append("neosobní sloveso — bez podmětu")
            return
        if p.kind == "copula" and person in ("3", None) and number in ("Sing", None) and not any(r.name in ("co", "jaký", "čí", "kolik") for r in p.roles) \
                and any(r.name == "jak" for r in p.roles):
            p.defaults.append("neosobní „je + příslovce“ — bez podmětu")  # „je mokro“, „je hezky“
            return
        term = TermSpec(0, "∅", (), "PRON", "pron", gender=gender, number=number, person=person, quant="·", quant_authority="prodrop")
        p.roles.insert(0, RoleFill("kdo", "prodrop", [term], "prodrop"))
        p.defaults.append("kdo:pro-drop z kontextu")

    def _quantify(self, p: Predication) -> None:
        """Kvantifikátor role podle tvaru — a autorita každé volby."""
        generic = (p.tense == "Pres") or (p.kind == "copula" and p.tense in (None, "Pres"))
        for r in p.roles:
            for t in r.terms:
                if t.quant is not None:
                    continue
                if t.kind in ("entity", "place", "time", "value", "pron", "var"):
                    t.quant, t.quant_authority = "·", "structural"
                elif t.kind == "wh":
                    continue
                elif r.name == "kdo" or (r.name == "co" and r.surface == "nsubj:pass"):
                    if generic:
                        t.quant, t.quant_authority = "∀", "default:generický prézens"
                        p.defaults.append(f"{r.name}:∀ generický prézens")
                    else:
                        t.quant, t.quant_authority = "·", "default:epizoda"
                        p.defaults.append(f"{r.name}:· epizoda")
                else:
                    t.quant, t.quant_authority = "∃", "default:předmět"

    # ---- termy -------------------------------------------------------------

    def _term_group(self, t: Token) -> list[TermSpec]:
        """Term + jeho souřadné členy (`conj`) jako víc termů jedné role."""
        terms = [self._term(t)]
        for c in self.kids(t.index, "conj"):
            if c.upos in ("VERB",) or self.kids(c.index, "cop"):
                continue
            for cc in self.kids(c.index, "cc"):
                self.mark(cc.index, "particle")
            terms.extend(self._term_group(c))
        return terms

    def _term(self, t: Token) -> TermSpec:
        where = "term"
        consumed: list[int] = [t.index]
        self.mark(t.index, where)
        self._mark_structure(t.index, where)
        forms = [t.form]
        name_tokens = [t.index]
        name_lemmas = [_name_lemma(t)]
        attrs: list[str] = []
        count: int | None = None
        count_hi: int | None = None
        count_text = ""
        quantity_name = ""
        possessor: tuple[str, str] | None = None
        quant: Quant | None = None
        qauth = ""
        kind: Kind
        # víceslovné jméno
        titled: list[int] = []  # obecné jméno + vlastní jméno („řeka Vltava“, „prezident Bill Clinton“)
        rel: tuple[str, TermSpec] | None = None
        rel_alts: list[TermSpec] = []
        for f in self.p.children(t.index):
            if f.base_deprel == "flat" or f.deprel == "compound" or (
                f.base_deprel == "nmod" and t.upos == "NOUN" and not self.case_of(f.index)
                and not [c for c in self.p.children(f.index) if c.base_deprel not in ("flat", "punct")]
                and (f.feat("NameType") != "Geo" or t.lemma in D.PLACE_NOUNS)
                and f.feat("Case") in (None, "Nom", t.feat("Case"))
                and (f.upos in ("PROPN", "X", "SYM", "NUM") or f.feat("Abbr") == "Yes" or (len(f.form) <= 2 and not f.feat("Case")))
            ):
                # víceslovné jméno; i „vitamín C“, „skupina B“ (holé nmod bez pádu a bez dětí)
                if t.upos == "NOUN" and f.upos in ("PROPN", "X") and f.feat("Abbr") != "Yes":
                    titled.append(f.index)
                forms.append(f.form)
                name_tokens.append(f.index)
                name_lemmas.append(_name_lemma(f))
                consumed.append(f.index)
                for g in self.p.children(f.index):
                    if g.base_deprel == "flat":  # „Deep Blue“, „Ol Doinyo Lengai“ — flat pod nmod jménem
                        forms.append(g.form)
                        name_tokens.append(g.index)
                        name_lemmas.append(_name_lemma(g))
                        consumed.append(g.index)
                        self.mark(g.index, where)
                self.mark(f.index, where)
                for g in self.p.subtree(f.index):
                    self.mark(g.index, where)
                    if g.index != f.index:
                        consumed.append(g.index)
        # determinátory, číslovky, přívlastky
        for c in self.p.children(t.index):
            d = c.base_deprel
            if d == "det":
                q = D.DETERMINER_QUANT.get(c.lemma)
                if q:
                    quant, qauth = ("∀" if q == "∀neg" else q), "determiner"  # type: ignore[assignment]
                    if q == "∀neg":
                        attrs.append("¬")  # značka pro predikaci
                elif c.lemma in D.POSSESSIVE or c.feat("Poss") == "Yes":
                    possessor = ("pron", c.lemma)
                elif "Int" in (c.feat("PronType") or ""):
                    pass  # díra řešená v _add_role
                self.mark(c.index, "particle")
                consumed.append(c.index)
            elif d == "nummod":
                n = D.number_of(c.form, c.lemma)
                if n is not None:
                    count = n
                    unit_kids = [u for u in self.p.children(c.index) if u.base_deprel in ("nmod", "flat", "compound") and not self.case_of(u.index)
                                 and u.upos in ("NOUN", "SYM", "X") and (u.feat("Abbr") == "Yes" or len(u.form) <= 3 or u.lemma in ("metr", "kilometr", "gram", "kilogram", "litr", "sekunda", "hodina", "stupeň"))]
                    if unit_kids and t.lemma in D.QUANTITY_NOUNS:
                        # „velikosti 12–14 mm“: hodnota s jednotkou pod substantivem veličiny → term je HODNOTA, role = veličina
                        unit_name = "".join(u.form for u in unit_kids)
                        for u in unit_kids:
                            for x in self.p.subtree(u.index):
                                self.mark(x.index, where)
                                consumed.append(x.index)
                        quantity_name = t.lemma
                        name_lemmas = [unit_name]
                    for g in self.p.children(c.index):
                        if g.base_deprel in ("conj", "nmod") and g.upos == "NUM" and D.number_of(g.form, g.lemma) is not None:
                            joiners = {x.form for x in self.p.children(g.index) if x.base_deprel in ("cc", "punct")}
                            if joiners & {"×", "x", "krát"}:
                                count = n * (D.number_of(g.form, g.lemma) or 1)  # „8×8 polí“ = 64
                            elif joiners & {"–", "-", "—", "až"}:
                                count_hi = D.number_of(g.form, g.lemma)  # „30 000–50 000 dělnic“ = rozsah
                                if "," in c.form or "," in g.form or "." in g.form.strip("."):
                                    count_text = f"{c.form}–{g.form}"  # desetinná mez: int ji neunese
                            else:
                                continue
                            for x in self.p.subtree(g.index):
                                self.mark(x.index, where)
                                consumed.append(x.index)
                self.mark(c.index, where)
                consumed.append(c.index)
            elif d == "amod":
                if c.feat("Poss") == "Yes" and c.upos == "ADJ":
                    possessor = ("adj", c.lemma)
                elif self.kids(c.index, "obl", "obj", "nsubj", "advmod", "nmod", "advcl", "xcomp", "iobj") and c.feat("VerbForm") == "Part":
                    # participium s vlastními členy = vedlejší predikace o hlavě
                    self._pending_secondary.append((t, c))
                    continue
                else:
                    attrs.append(("ne" if self.is_neg(c) and not c.lemma.startswith("ne") else "") + c.lemma)
                self.mark(c.index, where)
                consumed.append(c.index)
                for g in self.p.subtree(c.index):
                    if g.index != c.index and (g.base_deprel in ("advmod", "conj", "cc") or g.deprel in STRUCTURAL):
                        self.mark(g.index, "particle")
                        consumed.append(g.index)
                for cc in self.kids(c.index, "conj"):
                    if cc.upos == "ADJ":
                        attrs.append(cc.lemma)
                        self.mark(cc.index, where)
                        consumed.append(cc.index)
            elif d in ("nmod", "appos", "acl", "parataxis", "obl", "advcl"):
                if c.index in consumed:
                    continue
                if d == "advcl" and self.kids(t.index, "cop"):
                    continue  # věta pod jmenným přísudkem („je mokro, když prší“) patří kopule, ne termu
                if (d == "nmod" and t.upos in ("NOUN", "ADJ") and c.upos in ("PROPN", "NOUN") and c.feat("Case") == "Gen"
                        and not self.case_of(c.index) and rel is None):
                    # „otec Petra Nováka“, „příbuzný psa“, „péče majitele“ — holý genitiv ZUŽUJE
                    # třídu (péče⟨majitel⟩ ⊆ péče); paměť z toho dělá zúženou group
                    rel = ("Gen", self._term(c))
                    consumed.append(c.index)
                    for cc in self.kids(c.index, "conj"):
                        if cc.upos == "NOUN" and not self.case_of(cc.index):
                            rel_alts.append(self._term(cc))  # „otec manžela nebo manželky“ — alternativa zúžení
                            for x in self.kids(cc.index, "cc"):
                                self.mark(x.index, "particle")
                            consumed.append(cc.index)
                        else:
                            self._pending_secondary.append((t, cc))  # „péče a pozornosti“ — druhý člen jako výrok vedle
                    continue
                self._pending_secondary.append((t, c))
            elif d == "advmod" and c.lemma in D.PARTICLES:
                self.mark(c.index, "particle")
        # druh
        time = None
        if "Int" in (t.feat("PronType") or ""):
            kind = "wh"
        elif t.upos == "PROPN" or (t.upos == "X" and t.form[:1].isupper()):
            # cizí jména („Deep Blue“, „Ol Doinyo Lengai“) chodí z parseru jako X — jsou to jména
            kind = "place" if (t.feat("NameType") == "Geo" or self._filler_kind(t) == "place?") else "entity"
            quant, qauth = quant or "·", qauth or "structural"
        elif (t.upos == "NOUN" and t.form[:1].isupper() and t.index > 1 and not is_time_noun(t.lemma) and not titled
              and self.case_of(t.index) in D.PLACE_PREPS and t.feat("Case") in ("Loc", "Gen", "Acc", "Ins")):
            # „v Hrádečku“, „u Náchoda“ — velké písmeno po místní předložce uprostřed věty = místo,
            # i když parser slovo nezná (lemma malými písmeny)
            kind = "place"
            quant, qauth = quant or "·", qauth or "structural"
            name_lemmas = [t.lemma[:1].upper() + t.lemma[1:]]
        elif t.upos == "NOUN" and t.form[:1].isupper() and t.lemma == t.form.lower() and t.index > 1 and not is_time_noun(t.lemma) and not titled:
            # velké písmeno uprostřed věty a lemma = tvar: parser slovo nezná → je to jméno
            kind = "entity"
            quant, qauth = quant or "·", qauth or "structural"
            name_lemmas = [t.form]
        elif t.upos == "NOUN" and titled:
            # „řeka Vltava“, „sopka Ol Doinyo Lengai“: entita pojmenovaná vlastním jménem,
            # obecné jméno je její třída (paměť přidá member) — jméno bez titulu
            kind = "entity"
            quant, qauth = quant or "·", qauth or "structural"
            name_tokens = [i for i in name_tokens if i != t.index]
            name_lemmas = [_name_lemma(self.p.token(i)) for i in name_tokens]
            forms = [self.p.token(i).form for i in name_tokens]
            geo = any(self.p.token(i).feat("NameType") == "Geo" for i in name_tokens)
            if geo or t.lemma in D.PLACE_NOUNS:
                kind = "place"
        elif t.upos in ("PRON", "DET") and (t.lemma in D.VAR_PRONOUNS or (t.lemma == "ten" and any(
                c.base_deprel == "acl" for c in self.p.children(t.index)))) and (
                t.lemma not in D.EXISTENTIAL_PRONOUNS or self._cond_depth > 0):
            # „Každý, kdo …“ / „ten, kdo …“ / „pokud někdo …“: proměnná pravidla, ne odkaz
            kind = "var"
            quant, qauth = "·", "structural"
        elif t.upos in ("PRON", "DET") and t.lemma in D.EXISTENTIAL_PRONOUNS:
            # „Někdo zaklepal.“ mimo podmínku: neurčitý činitel — role bez výplně (nic o něm nevíme)
            kind = "group"
            quant, qauth = "∃", "structural"
        elif t.upos == "PRON" or (t.upos == "DET" and not self.p.children(t.index)):
            kind = "pron"
            quant, qauth = "·", "structural"
        elif self.case_of(t.index) == "před" and t.upos in ("NUM", "NOUN") and time_from_tokens(self.p.subtree(t.index)) is None and any(
                is_time_noun(x.lemma) and x.index != t.index for x in self.p.subtree(t.index)):
            # „před 2 miliardami let“ — relativní čas; popiska = celý tvar
            kind = "time"
            body = [x for x in self.p.subtree(t.index) if x.upos not in ("ADP", "PUNCT")]
            time = TimeSpec("name", " ".join(x.form for x in sorted(body, key=lambda x: x.index)))
            for x in body:
                self.mark(x.index, where)
                consumed.append(x.index)
            count = None
        elif t.upos == "NUM":
            kind = "value"
            time = time_from_tokens([t])
            # jednotka: „130 km/h“ = NUM s holým nmod řetězem (km → h)
            unit_tokens = [c for c in self.p.subtree(t.index) if c.index != t.index and c.base_deprel in ("nmod", "punct", "flat", "compound") and not self.case_of(c.index) and c.upos in ("NOUN", "SYM", "PUNCT", "X", "PROPN")]
            # interpunkce jen UVNITŘ jednotky („km/h“), ne tečka za větou
            while unit_tokens and unit_tokens[-1].upos == "PUNCT":
                unit_tokens.pop()
            unit = "".join(c.form for c in unit_tokens) if unit_tokens else ""
            if time and not unit:
                kind = "time"
            else:
                count = D.number_of(t.form, t.lemma)
                if count is not None and ("," in t.form or "." in t.form.strip(".")):
                    count_text = t.form  # „3,5 km“ — desetinné číslo zůstane v popisce
                if unit:
                    time = None
                    for c in unit_tokens:
                        self.mark(c.index, where)
                        consumed.append(c.index)
                    name_lemmas = [unit]
        else:
            # jen hlava + PŘÍMÉ číslovky/předložky/flat — ne celý podstrom (kořen
            # věty má pod sebou všechno, včetně letopočtů cizích členů)
            sub = [x for x in self.p.subtree(t.index) if x.index == t.index or (x.head == t.index and x.base_deprel in ("nummod", "case", "flat"))]
            if is_time_noun(t.lemma):
                # „dne 12. srpna 1879“, „v sobotu 21. prosince“, „mezi lety 1900 až 2000“: datum
                # visí pod časovým substantivem hlouběji — u časového slova je celý podstrom jeho
                sub = [x for x in self.p.subtree(t.index) if (x.index == t.index or x.lemma in MONTH_LEMMAS or x.upos in ("NUM", "PUNCT") or is_time_noun(x.lemma)
                                                             or x.lemma in ("až", "a", "nebo", "–", "-", "—"))]
            # čas jen u ČASOVÉHO substantiva („roku 1851“, „v letech …“); „244 kostí“
            # a „430 kilometrů“ nejsou letopočty
            time = time_from_tokens(sub) if is_time_noun(t.lemma) else None
            if is_time_noun(t.lemma) or time is not None:
                kind = "time"
                count = None  # letopočet není počet
                if time is None:
                    # „před 2 miliardami let“, „v dětství“: pojmenovaný čas s celým tvarem jako popiskou
                    body = [x for x in sub if x.upos not in ("ADP", "PUNCT")]
                    # „na počátku hry“, „na konci války“: genitivní doplnění patří k popisce času
                    for g in self.p.children(t.index):
                        if g.base_deprel == "nmod" and g.feat("Case") == "Gen" and g.upos in ("NOUN", "PROPN") and g not in body:
                            body.append(g)
                            for x in self.p.subtree(g.index):
                                self.mark(x.index, where)
                                consumed.append(x.index)
                    head_lemma = is_time_noun(t.lemma) and not any(x.upos == "NUM" for x in body)  # „konec války“, ale „2 miliardami let“
                    label = " ".join(x.lemma if head_lemma and x.index == t.index else x.form for x in sorted(body, key=lambda x: x.index)) if len(body) > 1 else t.lemma
                    if len(body) > 1 and self.case_of(t.index) == "před":
                        label = "před " + label  # relativní čas: „před 2 miliardami let“
                    time = TimeSpec("name", label if len(body) > 1 else t.lemma)
                for x in sub:
                    self.mark(x.index, where)
            elif t.lemma in D.PLACE_NOUNS and False:
                kind = "place"
            else:
                kind = "group"
        if quantity_name:
            kind, quant, qauth = "value", "·", "structural"
        spec = TermSpec(
            head=t.index, lemma=" ".join(name_lemmas) if kind in ("group", "value") else t.lemma, forms=tuple(forms), upos=t.upos, kind=kind,
            attrs=tuple(a for a in attrs if a != "¬"), count=count, count_hi=count_hi, count_text=count_text, time=time, quantity=quantity_name,
            gender=t.feat("Gender"), number=t.feat("Number"), person=t.feat("Person"),
            quant=quant, quant_authority=qauth, tokens=tuple(sorted(set(consumed))),
            name_tokens=tuple(name_tokens), name_lemmas=tuple(name_lemmas), possessor=possessor, rel=rel,
            rel_alts=tuple(rel_alts),
        )
        if kind in ("entity", "place") and t.upos == "NOUN" and titled:
            spec.note = f"titul:{t.lemma}"
        elif kind == "group" and t.form[:1].isupper() and t.lemma == t.form.lower() and t.index == 1 and not attrs:
            spec.note = "možná jméno"  # věta začíná neznámým slovem s velkým písmenem
        if possessor is not None and spec.quant is None:
            spec.quant, spec.quant_authority = "·", "default:přivlastnění"
        if "¬" in attrs:
            spec.note = "žádný"
        return spec

    _pending_secondary: list[tuple[Token, Token]]

    # ---- kopula ------------------------------------------------------------

    def _age(self, root: Token, cop: Token) -> Predication | None:
        """„Ronikovi je 17 let.“ / „Kolik je Petrovi let?“ → věk(kdo: X, co: N rok).
        Tvar: kořen v dativu (komu), `nsubj` = léta/rok s číslovkou nebo s „kolik“."""
        if root.feat("Case") != "Dat":
            return None
        years = [c for c in self.p.children(root.index) if c.base_deprel == "nsubj" and c.lemma in ("léta", "rok")]
        if not years:
            return None
        y = years[0]
        p = Predication(pred="věk", kind="verb", head=root.index)
        p.tense = cop.feat("Tense")
        self.mark(cop.index, "pred")
        self.mark(root.index, "role:kdo")
        p.defaults.append("věk: dativ + být + N let")
        who = self._term(root)
        p.roles.append(RoleFill("kdo", "Dat", [who], "default"))
        wh = self._wh_of(y)
        if wh is not None:
            role = RoleFill("co", "nsubj", wh=True, wh_kind="count")
            role.terms = [self._term(y)]
            for t in role.terms:
                t.count, t.kind, t.time = None, "group", None  # tentýž uzel jako u tvrzení (léta = group)
            self.mark(y.index, "role:co")
            self._mark_structure(y.index, "role:co")
            p.roles.append(role)
        else:
            term = self._term(y)
            term.kind = "group"
            term.time = None
            term.quant, term.quant_authority = "∃", "structural"
            for c in self.p.children(y.index):
                raw = c.form.replace(" ", "").rstrip(".")
                if c.base_deprel == "nummod" and raw.isdigit():
                    term.count = int(raw)  # u času se počet maže — tady je to VĚK
            p.roles.append(RoleFill("co", "nsubj", [term], "structural"))
        for child in self.p.children(root.index):
            if child.base_deprel in ("obl", "advmod", "advcl"):
                self._roles_of_single(child, p)
        return p

    def _comparison(self, root: Token, cop: Token) -> Predication | None:
        """„Pavla je starší než Jindřich.“ / „Kdo je starší, Pavla nebo Jindřich?“ →
        srovnání(kdo, jaký: starý, než: X | z: kandidáti). Vyhodnocení dělá logika
        (věk z narození); tady jen tvar."""
        if root.upos != "ADJ" or root.feat("Degree") != "Cmp":
            return None
        than = [c for c in self.p.children(root.index) if c.base_deprel in ("advcl", "obl", "nmod")
                and any(m.lemma == "než" for m in self.p.children(c.index) if m.base_deprel in ("mark", "case"))]
        # kandidáti „Pavla nebo Jindřich“ visí jako appos, nebo jako conj pod přídavným jménem
        cands = [c for c in self.p.children(root.index) if c.base_deprel == "appos" or (c.base_deprel == "conj" and c.upos in ("PROPN", "NOUN"))]
        subj = [c for c in self.p.children(root.index) if c.base_deprel == "nsubj"]
        if not than and not cands:
            return None
        p = Predication(pred="srovnání", kind="verb", head=root.index)
        p.tense = cop.feat("Tense")
        self.mark(cop.index, "pred")
        self.mark(root.index, "pred")
        p.defaults.append("srovnání: komparativ + než")
        if subj:
            self._add_role(p, "kdo", subj[0].deprel, subj[0])
        adj = TermSpec(root.index, root.lemma, (root.form,), "ADJ", "group", quant="·", quant_authority="structural", tokens=(root.index,))
        p.roles.append(RoleFill("jaký", "cop", [adj], "structural"))
        for c in than:
            for m in self.p.children(c.index):
                if m.base_deprel in ("mark", "case"):
                    self.mark(m.index, "particle")
            self._add_role(p, "než", "než", c, authority="structural")
        for c in cands:
            self._add_role(p, "z", "appos", c, authority="structural")
        self._quantify(p)
        return p

    def _definition(self, root: Token, cop: Token) -> Predication | None:
        """„Starší je ten, kdo se narodil dřív.“ / „Kdo se narodil dřív, je starší.“ →
        definice(jaký: starý, predikát: narodit_se, směr: earlier). Dialog z toho
        udělá naučené srovnávací slovo; jádro nic nového neumí — jen se dozví,
        KTERÉ slovo spouští KTERÉ porovnání."""
        if root.upos != "ADJ" or root.feat("Degree") != "Cmp":
            return None
        clause: Token | None = None
        for c in self.p.children(root.index):
            if c.base_deprel == "csubj" and c.upos == "VERB":
                clause = c
            elif c.base_deprel == "nsubj" and c.lemma == "ten":
                clause = next((r for r in self.p.children(c.index) if r.base_deprel == "acl" and r.upos == "VERB"), None)
                if clause is not None:
                    self.mark(c.index, "particle")
        if clause is None:
            return None
        adv = next((a for a in self.p.children(clause.index) if a.upos == "ADV" and a.lemma in D.DIRECTION_ADVERBS), None)
        if adv is None:
            return None
        p = Predication(pred="definice", kind="verb", head=root.index)
        for i in (cop.index, root.index, clause.index, adv.index):
            self.mark(i, "pred")
        for c in self.p.children(clause.index):
            if c.base_deprel in ("nsubj", "expl", "mark") or c.deprel in STRUCTURAL:
                self.mark(c.index, "particle")
        pred = self._lemma_with_refl(clause)
        p.roles.append(RoleFill("jaký", "cop", [TermSpec(root.index, root.lemma, (root.form,), "ADJ", "group", quant="·", quant_authority="structural", tokens=(root.index,))], "structural"))
        p.roles.append(RoleFill("predikát", "acl", [TermSpec(clause.index, pred, (clause.form,), "VERB", "group", quant="·", quant_authority="structural", tokens=(clause.index,))], "structural"))
        p.roles.append(RoleFill("směr", "advmod", [TermSpec(adv.index, D.DIRECTION_ADVERBS[adv.lemma], (adv.form,), "ADV", "group", quant="·", quant_authority="structural", tokens=(adv.index,))], "structural"))
        p.defaults.append("definice srovnávacího slova")
        return p

    def _copula(self, root: Token, cop: Token | None, *, shared_subject: RoleFill | None = None) -> Predication:
        if cop is not None:
            age = self._age(root, cop)
            if age is not None:
                return age
            dfn = self._definition(root, cop)
            if dfn is not None:
                return dfn
            cmp_ = self._comparison(root, cop)
            if cmp_ is not None:
                return cmp_
        p = Predication(pred="být", kind="copula", head=root.index)
        p.tense = cop.feat("Tense") if cop else None
        if cop is not None:
            self.mark(cop.index, "pred")
        p.neg = (self.is_neg(cop) if cop else False) or self.is_neg(root)
        for a in self.kids(root.index, "aux"):
            p.neg = p.neg or self.is_neg(a)
            self.mark(a.index, "particle")
        for adv in self.kids(root.index, "advmod"):
            if adv.lemma == "ne":
                p.neg = True
                self.mark(adv.index, "particle")
        subj = [t for t in self.p.children(root.index) if t.base_deprel in ("nsubj", "csubj")]
        # predikátový nominál = kořen sám
        wh = self._wh_of(root)
        prep = self.case_of(root.index)
        pred_role: RoleFill
        jak = next((c for c in self.p.children(root.index) if c.base_deprel == "advmod" and c.lemma == "jak" and "Int" in (c.feat("PronType") or "")), None)
        if jak is not None and root.upos == "ADJ" and root.lemma in D.ADVERB_QUANTITY and self.mood == "question":
            # „Jak vysoká je Sněžka?“ → díra na veličinu výška
            wh = None
            qname = D.ADVERB_QUANTITY[root.lemma]
            pred_role = RoleFill(qname, "cop", wh=True, wh_kind="value")
            self.mark(root.index, f"role:{qname}")
            self.mark(jak.index, "particle")
        elif root.upos == "ADJ" and root.lemma in D.ADVERB_QUANTITY and any(
                c.base_deprel in ("obl", "nmod", "obj") and any(g.base_deprel == "nummod" for g in self.p.children(c.index)) for c in self.p.children(root.index)):
            # „Sněžka je vysoká 1603 metrů.“ → role výška: 1603 metr (veličina z přídavného jména)
            qname = D.ADVERB_QUANTITY[root.lemma]
            measure = next(c for c in self.p.children(root.index) if c.base_deprel in ("obl", "nmod", "obj") and any(g.base_deprel == "nummod" for g in self.p.children(c.index)))
            self.mark(root.index, f"role:{qname}")
            pred_role = RoleFill(qname, "cop+měr", self._term_group(measure), "structural")
            p.defaults.append(f"veličina {qname} z „{root.lemma}“ + míra")
        elif wh is not None:
            name, kind = wh
            # „Kdo/Co je X?“ = definice (díra „co“); „Kde/Kdy je X?“ = díra té role
            hole = "jaký" if kind == "attr" else ("co" if name in ("kdo", "co", "čím") else name)  # „Čím je X?“ = definice
            pred_role = RoleFill(hole, "cop", wh=True, wh_kind=kind)
            self.mark(root.index, f"role:{pred_role.name}")
            self._mark_structure(root.index, f"role:{pred_role.name}")
        elif root.upos == "ADJ":
            pred_role = RoleFill("jaký", "cop", self._term_group(root), "structural")
        elif root.upos == "ADV":
            pred_role = RoleFill("jak", "cop", self._term_group(root), "structural")
        elif prep:
            name, surface, authority = self._obl_role(root, arg=False)
            pred_role = RoleFill(name, surface, self._term_group(root), authority)
        else:
            pred_role = RoleFill("co", "cop", self._term_group(root), "structural")
        # podmět
        if subj and self._wh_of(subj[0]) is not None and root.upos in ("NOUN", "PROPN", "ADJ") and wh is None and not prep \
                and root.upos != "ADJ":  # „Kdo/Co je hnědý?“ = kdo:?, jaký: hnědý (výčet nositelů vlastnosti), ne definice
            # („Co je v lednici?“ má předložkový kořen → NEprohazovat: kdo:? , kde: lednice)
            # „Co je jezevčík?“ — tázací podmět, nominál v kořeni: ptá se na definici kořene
            s = subj[0]
            name, kind = self._wh_of(s) or ("co", "filler")
            self.mark(s.index, f"role:{name}")
            subject_role = RoleFill("kdo", "cop-swap", pred_role.terms, "structural")
            pred_role = RoleFill("jaký" if kind == "attr" else "co", "cop", wh=True, wh_kind=kind)
            p.roles.append(subject_role)
            p.defaults.append("kopula: tázací podmět, definice kořene")
        elif subj:
            s = subj[0]
            if s.base_deprel == "csubj":
                p.roles.append(RoleFill("kdo", "csubj", nested=self._verb_or_cop(s)))
                self.mark(s.index, "nested")
            else:
                self._add_role(p, "co" if s.deprel.endswith(":pass") else "kdo", s.deprel, s)
        elif shared_subject is not None:
            p.roles.append(RoleFill("kdo", shared_subject.surface, list(shared_subject.terms), "shared"))
        p.roles.append(pred_role)
        p.pred_role_name = pred_role.name
        # okolnosti u kopuly (byl v Praze učitelem…)
        for t in self.p.children(root.index):
            if self.place.get(t.index) == "term":
                continue  # už pohlceno (míra u veličiny)
            if t.base_deprel in ("obl", "advmod", "advcl", "xcomp", "ccomp", "obj", "iobj", "conj", "parataxis"):
                if t.base_deprel == "conj" and t.upos not in ("VERB",) and not self.kids(t.index, "cop"):
                    continue  # nominální koordinace už je v _term_group kořene
                if t.base_deprel == "advmod" and t.lemma == "ne":
                    continue
                if t.base_deprel == "conj":
                    p.secondary.append(self._verb_or_cop(t) if t.upos == "VERB" else self._copula(t, self.kids(t.index, "cop")[0], shared_subject=p.role("kdo")))
                    self.mark(t.index, "secondary")
                    continue
                self._roles_of_single(t, p)
        if p.role("kdo") is None and shared_subject is None:
            self._prodrop(p, [cop or root])
        self._quantify(p)
        p.kernel = self._copula_kernel(p, pred_role)
        self._quantity_roles(p)
        return p

    def _roles_of_single(self, t: Token, p: Predication) -> None:
        """Jedna okolnost pod kopulou — stejná tabulka jako u slovesa."""
        fake = Predication(pred=None, kind="verb")
        # využij _roles_of nad "virtuální hlavou": zpracujeme jen tento token
        d, base = t.deprel, t.base_deprel
        if base == "obl":
            name, surface, authority = self._obl_role(t, arg=(d == "obl:arg"))
            self._add_role(p, name, surface, t, authority=authority)
        elif base == "advmod":
            self._advmod(t, p)
        elif base == "advcl":
            self._advcl(t, p)
        elif base in ("xcomp", "ccomp"):
            p.roles.append(RoleFill("co", base, nested=self._verb_or_cop(t)))
            self.mark(t.index, "nested")
        elif base in ("obj", "iobj"):
            self._add_role(p, "co" if base == "obj" else "komu", d, t)
        elif base == "parataxis" and (t.upos == "VERB" or self.kids(t.index, "cop")):
            p.secondary.append(self._verb_or_cop(t))
            self.mark(t.index, "secondary")
        del fake

    def _copula_kernel(self, p: Predication, pred_role: RoleFill) -> str | None:
        subj = p.role("kdo")
        if subj is None or not subj.terms or pred_role.wh:
            return None
        s = subj.terms[0]
        if (s.kind == "group" and s.rel is None and not s.attrs and pred_role.name == "co" and pred_role.terms
                and any(t.rel is not None and t.rel[1].kind == "group" for t in pred_role.terms)):
            # „Tchán je otec manžela nebo manželky.“ — třída složená z vztahových jmen. Týž tvar
            # má i „Foton je částice světla“, proto: fakt (subset) A definiční řetěz navíc.
            p.definition = True
            p.defaults.append("tvar definice vztahového jména (řetěz uložen navíc)")
        if (s.kind == "group" and s.quant in ("∀", "∃") and pred_role.name == "co" and pred_role.terms
                and all(t.kind == "entity" for t in pred_role.terms)):
            # „Druh automobilu je Ford, Škoda, Mazda.“ / „Automobil může být Ford…“ — třída = výčet
            # jmen: jména jsou PRVKY třídy, ne naopak. Role se prohodí, jádro member.
            subj.terms, pred_role.terms = pred_role.terms, subj.terms
            subj.authority = "default"
            for t in subj.terms:
                t.quant, t.quant_authority = "·", "structural"
            for t in pred_role.terms:
                t.quant = "∃"
            p.defaults.append("kernel:member (výčet jmen = prvky třídy; role prohozeny)")
            return "member"
        if pred_role.name == "kde" and s.kind == "place":
            p.defaults.append("kernel:within (místo v místě)")
            return "within"
        if pred_role.name != "co" or not pred_role.terms:
            return None
        o = pred_role.terms[0]
        if o.lemma in ("část", "součást") and o.rel is not None and o.rel[1].kind == "place" and s.kind == "place":
            # „Morava je část Česka.“ → Morava uvnitř Česka: role co se přepíše na kde ⟨cíl⟩
            pred_role.name, pred_role.authority = "kde", "default"
            pred_role.terms = [o.rel[1]]
            p.defaults.append("kernel:within („část X“ = uvnitř X)")
            return "within"
        if o.kind in ("time", "value"):
            return None  # „rychlost je 130 km/h“ není členství ani podmnožina
        if s.kind in ("entity", "pron", "var") or (s.kind == "group" and s.quant == "·"):
            if o.kind == "entity":
                p.defaults.append("kernel:same_as (dvě jména)")
                return "same_as"
            p.defaults.append("kernel:member (určitý podmět)")
            return "member"
        if s.kind == "group" and s.quant in ("∀", "∃"):
            p.defaults.append("kernel:subset (obecný podmět)")
            return "subset"
        return None

    def _aux_root(self, root: Token) -> Predication:
        """Kořen je AUX `být` bez `cop` — otázka „Je jezevčík pes?“, „Byl Petr v Česku?“."""
        subj = [t for t in self.p.children(root.index) if t.base_deprel == "nsubj"]
        # predikátový nominál zavěšený jako nmod(Nom) pod podmět, nebo obj/xcomp pod kořen
        nominal: Token | None = None
        if subj:
            for c in self.p.children(subj[0].index):
                if c.base_deprel in ("nmod", "appos") and c.feat("Case") == "Nom" and not self.case_of(c.index):
                    nominal = c
                    break
        if nominal is None:
            for c in self.p.children(root.index):
                if c.base_deprel in ("obj", "xcomp", "nmod") and c.upos in ("NOUN", "PROPN", "ADJ"):
                    nominal = c
                    break
        p = Predication(pred="být", kind="copula", head=root.index)
        p.tense = root.feat("Tense")
        self.mark(root.index, "pred")
        p.neg = self.is_neg(root)
        if subj:
            self._add_role(p, "kdo", subj[0].deprel, subj[0])
        pred_role: RoleFill | None = None
        if nominal is not None:
            pred_role = RoleFill("jaký" if nominal.upos == "ADJ" else "co", "cop", self._term_group(nominal), "structural")
            p.roles.append(pred_role)
        for t in self.p.children(root.index):
            if t.base_deprel in ("obl", "advmod", "advcl", "ccomp", "conj", "parataxis"):
                self._roles_of_single(t, p)
        if p.role("kdo") is None:
            self._prodrop(p, [root])
        self._quantify(p)
        if pred_role is not None:
            p.kernel = self._copula_kernel(p, pred_role)
        elif p.role("kde") is not None:
            s = p.role("kdo")
            if s and s.terms and s.terms[0].kind == "place":
                p.kernel = "within"
        return p

    # ---- fragment ----------------------------------------------------------

    def _fragment(self, root: Token) -> Predication:
        p = Predication(pred=None, kind="fragment", head=root.index)
        if root.upos in ("NOUN", "PROPN", "ADJ", "NUM", "PRON", "DET", "ADV", "SYM", "X"):
            self._add_role(p, "téma", "root", root)
        else:
            self.mark(root.index, "residue")
            self.residue.append((root.form, "root"))
        self._quantify(p)
        return p


# ==========================================================================
# vedlejší predikace z podstromů termů (nmod, acl, appos, závorka)
# ==========================================================================


class Reader(_Reader):
    """Čtečka s druhým průchodem: vedlejší predikace z přívlastků a jmen."""

    def __init__(self, parse: Parse, mood: str | None, learned_roles: Mapping[str, str] | None = None) -> None:
        super().__init__(parse, mood, learned_roles)
        self._pending_secondary = []
        self._bio_done: set[int] = set()

    def read(self) -> Reading:
        root = self.p.root()
        main = self._clause(root)
        if main is None:
            # nadpis + věta („Obezita: Domácí mazlíčci jsou…“): kořen je nominál,
            # věta visí pod ním jako appos/parataxis/conj/dep — ta je hlavní
            clause = next(
                (c for c in self.p.children(root.index)
                 if c.base_deprel in ("appos", "parataxis", "conj", "dep", "acl")
                 and (c.upos == "VERB" or self.kids(c.index, "cop") or (c.upos == "AUX" and c.lemma == "být")
                      or (c.upos == "ADJ" and (self.kids(c.index, "aux", "nsubj", "csubj"))))),
                None,
            )
            if clause is not None:
                self._pending_secondary = [(h, d) for (h, d) in self._pending_secondary if d.index != clause.index]
                main = self._clause(clause) or self._fragment(clause)
                heading = self._fragment(root)
                heading.defaults.append("nadpis před větou")
                main.secondary.insert(0, heading)
            else:
                main = self._fragment(root)
        main.mood = self.mood  # type: ignore[assignment]
        self._free_relative(main)
        var_heads = {t.head for r in main.roles for t in r.terms if t.kind == "var"}
        # druhý průchod: přívlastky jako vztahy vedle věty, závorky, vztažné věty
        seen: set[tuple[int, int]] = set()
        while self._pending_secondary:
            head, dep = self._pending_secondary.pop(0)
            if (head.index, dep.index) in seen or self.place.get(dep.index) == "term":
                continue  # člen už pohltil term (jednotka, zúžení) — není to výrok vedle věty
            seen.add((head.index, dep.index))
            if head.index in var_heads and dep.base_deprel == "acl":
                # „Každý, kdo bydlí v Praze, …“: vztažná věta o proměnné = PODMÍNKA pravidla, ne výrok vedle
                cond = self._acl(head, dep)
                cond.embedded = "podmínka"
                main.roles.append(RoleFill("podmínka", "acl", nested=cond, authority="default"))
                main.defaults.append("pravidlo z věty: každý, kdo … (podmínka)")
                continue
            generic = self._generic_relative(main, head, dep)
            if generic is not None:
                # „Každý pes, který štěká, je hlídač.“: omezovací vztažná věta u obecného podmětu =
                # pravidlo: X ∈ pes ∧ štěkat(X) ⇒ hlídač(X) — ne tvrzení „pes štěká“
                role, term = generic
                var = TermSpec(head.index, "X", (head.form,), head.upos, "var", quant="·", quant_authority="structural", tokens=(head.index,))
                role.terms[role.terms.index(term)] = var
                cls = Predication(pred="být", kind="copula", kernel="member", head=head.index)
                cls.roles.append(RoleFill("kdo", "var", [var], "structural"))
                cls.roles.append(RoleFill("co", "acl", [TermSpec(head.index, term.lemma, term.forms, head.upos, "group", attrs=term.attrs, quant="∃", quant_authority="structural", tokens=(head.index,), name_lemmas=term.name_lemmas, rel=term.rel)], "structural"))
                cls.embedded = "podmínka"
                cond = self._acl(head, dep, head_term=var)
                cond.embedded = "podmínka"
                main.roles.append(RoleFill("podmínka", "acl", nested=cls, authority="default"))
                main.roles.append(RoleFill("podmínka", "acl", nested=cond, authority="default"))
                main.defaults.append(f"pravidlo z věty: každý {term.lemma}, který … (podmínka: třída + vztažná věta)")
                if main.kernel == "subset":
                    main.kernel = "member"  # podmět je teď proměnná (prvek), ne třída
                var_heads.add(head.index)
                continue
            for sec in self._secondary_from(head, dep, main):
                main.secondary.append(sec)
        self._sweep()
        return Reading(parse=self.p, main=main, residue=self.residue, _placement=self.place)

    def _generic_relative(self, main: Predication, head: Token, dep: Token) -> tuple[RoleFill, TermSpec] | None:
        """Omezovací vztažná věta u OBECNÉHO (∀) podmětu hlavní věty: vrací (role, term), jinak None."""
        if dep.base_deprel != "acl":
            return None
        relative = dep.deprel == "acl:relcl" or any("Rel" in (c.feat("PronType") or "") for c in self.p.subtree(dep.index) if c.upos in ("PRON", "DET"))
        if not relative:
            return None
        for r in main.roles:
            if r.name != "kdo":
                continue
            for t in r.terms:
                if t.head == head.index and t.kind == "group" and t.quant == "∀":
                    return r, t
        return None

    def _free_relative(self, main: Predication) -> None:
        """„Kdo jede po dálnici, (ten) jede rychle.“: podmětová věta se vztažným kdo/co →
        podmět hlavní věty je PROMĚNNÁ a věta je podmínka pravidla."""
        for r in list(main.roles):
            if r.nested is None or r.name not in ("kdo", "co") or r.terms:
                continue
            for nr in r.nested.roles:
                for i, t in enumerate(nr.terms):
                    tok = self.p.token(t.head) if t.head else None
                    if tok is not None and tok.upos == "PRON" and tok.lemma in ("kdo", "co") and (
                            "Rel" in (tok.feat("PronType") or "") or "Int" in (tok.feat("PronType") or "")):
                        var = TermSpec(t.head, tok.lemma, (tok.form,), "PRON", "var", quant="·", quant_authority="structural", tokens=(t.head,))
                        nr.terms[i] = var
                        r.terms.append(var)
                        cond = r.nested
                        r.nested = None
                        cond.embedded = "podmínka"
                        main.roles.append(RoleFill("podmínka", "csubj", nested=cond, authority="default"))
                        main.defaults.append("pravidlo z věty: kdo …, ten … (podmínka)")
                        return

    def _clause(self, root: Token) -> Predication | None:
        """Je token hlavou věty (klauze)? Vrátí predikaci, jinak `None`."""
        cop = self.kids(root.index, "cop")
        if cop:
            return self._copula(root, cop[0])
        if root.upos == "VERB":
            return self._verb(root)
        if root.upos == "AUX" and root.lemma == "být":
            return self._aux_root(root)
        if root.upos == "ADJ" and (self.kids(root.index, "aux", "nsubj", "csubj") or root.feat("VerbForm") == "Part" and self.kids(root.index, "obl", "obj")):
            p = self._participle(root)
            self._subject_from_ambiguity(p)
            return p
        if root.upos in ("NOUN", "PROPN", "ADV", "NUM", "PRON", "DET") and self.kids(root.index, "nsubj", "csubj"):
            # spona vypadla (parser), ale podmět je: čti jako kopulu bez spony
            return self._copula(root, None)
        return None

    def _head_term(self, head: Token) -> TermSpec:
        """Term hlavy pro vedlejší predikaci — bez opětovného pohlcení dětí."""
        flats = [f for f in self.p.children(head.index) if f.base_deprel == "flat"]
        forms = [head.form] + [f.form for f in flats]
        lemmas = tuple([_name_lemma(head)] + [_name_lemma(f) for f in flats])
        kind: Kind = "entity" if head.upos in ("PROPN",) or (head.upos == "X" and head.form[:1].isupper()) else "group"
        if head.upos == "PROPN" and head.feat("NameType") == "Geo":
            kind = "place"
        if head.upos in ("PRON", "DET") and (head.lemma in D.VAR_PRONOUNS or head.lemma == "ten"):
            kind = "var"
        # titul + jméno („vulkán Ol Doinyo Lengai“): hlava vedlejšího výroku je ta ENTITA, ne třída
        if head.upos == "NOUN":
            named = [f for f in self.p.children(head.index) if f.base_deprel == "nmod" and f.upos in ("PROPN", "X") and not self.case_of(f.index)
                     and not [c for c in self.p.children(f.index) if c.base_deprel not in ("flat", "punct")] and f.feat("Abbr") != "Yes"
                     and (f.feat("NameType") != "Geo" or head.lemma in D.PLACE_NOUNS)]
            if named:
                nm = named[0]
                name_toks = [nm] + [g for g in self.p.children(nm.index) if g.base_deprel == "flat"]
                forms = [x.form for x in name_toks]
                lemmas = tuple(x.lemma for x in name_toks)
                kind = "place" if (nm.feat("NameType") == "Geo" or head.lemma in D.PLACE_NOUNS) else "entity"
        if is_time_noun(head.lemma):
            kind = "time"
        attrs = tuple(c.lemma for c in self.p.children(head.index) if c.base_deprel == "amod" and c.feat("Poss") != "Yes" and not (c.feat("VerbForm") == "Part" and self.kids(c.index, "obl", "obj", "nsubj", "advmod", "nmod")))
        # totéž zúžení genitivem jako v `_term`, aby hlava vedlejšího výroku byl TÝŽ uzel
        rel: tuple[str, TermSpec] | None = None
        for c in self.p.children(head.index):
            if (c.base_deprel == "nmod" and head.upos in ("NOUN", "ADJ") and c.upos in ("PROPN", "NOUN") and c.feat("Case") == "Gen"
                    and not self.case_of(c.index)):
                rel = ("Gen", self._head_term(c))
                break
        return TermSpec(head.index, head.lemma, tuple(forms), head.upos, kind, attrs=attrs, rel=rel, quant="·", quant_authority="structural", tokens=(head.index,), name_tokens=(head.index,) + tuple(f.index for f in flats), name_lemmas=lemmas, gender=head.feat("Gender"), number=head.feat("Number"))

    def _secondary_from(self, head: Token, dep: Token, main: Predication) -> list[Predication]:
        d = dep.base_deprel
        out: list[Predication] = []
        if d == "parataxis":
            if head.upos == "PROPN":
                return self._bio_parenthesis(head)
            if dep.upos == "VERB" or self.kids(dep.index, "cop"):
                out.append(self._verb_or_cop(dep))
                self.mark(dep.index, "secondary")
            return out
        if d in ("nmod", "conj"):
            # `conj` sem přijde jen jako sourozenec genitivního zúžení („péče a pozornosti“)
            # životopisná závorka: `Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha)`
            if head.upos == "PROPN" and d == "nmod":
                bio = self._bio_parenthesis(head)
                if bio:
                    return bio
            for cc in self.kids(dep.index, "cc"):
                self.mark(cc.index, "particle")
            prep = self.case_of(dep.index)
            case = dep.feat("Case") or ""
            surface = f"nmod:{prep}+{case}" if prep else f"nmod:{case}"
            p = Predication(pred=surface, kind="nmod", head=dep.index)
            p.roles.append(RoleFill("kdo", "head", [self._head_term(head)], "structural"))
            p.roles.append(RoleFill("co", surface, self._term_group(dep), "surface"))
            p.tense = None
            self._quantify(p)
            out.append(p)
        elif d == "appos":
            if head.upos == "PROPN" and self._bio_parenthesis(head):
                return self._bio_parenthesis(head)
            clause = self._clause(dep)
            if clause is not None:
                self.mark(dep.index, "secondary")
                return [clause]
            p = Predication(pred="být", kind="appos", head=dep.index)
            p.roles.append(RoleFill("kdo", "head", [self._head_term(head)], "structural"))
            p.roles.append(RoleFill("co", "appos", self._term_group(dep), "structural"))
            self._quantify(p)
            hk, dk = p.roles[0].terms[0].kind, (p.roles[1].terms[0].kind if p.roles[1].terms else "")
            if hk == "group" and dk == "entity" and dep.upos in ("PROPN", "X"):
                # „Pes domácí (Canis familiaris)“ — jméno TŘÍDY (alias), ne prvek ani totožnost
                p.kernel = "name"
                p.defaults.append("appos: jméno třídy")
            else:
                p.kernel = self._copula_kernel(p, p.roles[1])
            p.defaults.append("appos jako být")
            out.append(p)
        elif d in ("acl", "amod", "advcl"):
            out.append(self._acl(head, dep))
        elif d == "obl":
            prep = self.case_of(dep.index)
            case = dep.feat("Case") or ""
            surface = f"nmod:{prep}+{case}" if prep else f"nmod:{case}"
            p = Predication(pred=surface, kind="nmod", head=dep.index)
            p.roles.append(RoleFill("kdo", "head", [self._head_term(head)], "structural"))
            p.roles.append(RoleFill("co", surface, self._term_group(dep), "surface"))
            self._quantify(p)
            out.append(p)
        return out

    def _acl(self, head: Token, dep: Token, head_term: TermSpec | None = None) -> Predication:
        """Vztažná / participiální věta o hlavě: hlava vyplní roli, kterou
        drží vztažné zájmeno (`který`), u participia patiens (`co`)."""
        for m in self.p.children(dep.index):
            if m.base_deprel == "mark":
                self.mark(m.index, "particle")
        if dep.upos == "VERB" or self.kids(dep.index, "cop"):
            p = self._verb_or_cop(dep)
        else:
            p = self._participle(dep)
        head_term = head_term or self._head_term(head)
        # najdi vztažné zájmeno mezi rolemi
        placed = False
        for r in p.roles:
            if r.authority == "relative" and not r.terms:
                r.terms.append(head_term)
                placed = True
            for i, t in enumerate(list(r.terms)):
                tok = self.p.token(t.head) if t.head else None
                if tok is not None and "Rel" in (tok.feat("PronType") or "") and tok.lemma in ("který", "jenž", "co", "kdo", "kde", "kdy", "jaký"):
                    r.terms[i] = head_term
                    placed = True
        if not placed:
            if p.kind == "verb" and dep.upos == "ADJ":
                # participium: hlava je patiens (způsobené pády → co:úraz)
                role = p.role("co")
                if role is None:
                    p.roles.insert(0, RoleFill("co", "acl", [head_term], "structural"))
                elif not role.terms:
                    role.terms.append(head_term)
                else:
                    p.roles.insert(0, RoleFill("kdo", "acl", [head_term], "structural"))
            else:
                subj = p.role("kdo")
                if subj is None or (subj.terms and subj.terms[0].kind == "pron" and subj.authority == "prodrop"):
                    if subj is not None:
                        p.roles.remove(subj)
                    p.roles.insert(0, RoleFill("kdo", "acl", [head_term], "structural"))
                else:
                    p.roles.append(RoleFill("o_kom", "acl", [head_term], "structural"))
        p.defaults.append("acl: predikace o hlavě")
        self.mark(dep.index, "secondary")
        return p

    def _bio_parenthesis(self, name_head: Token) -> list[Predication]:
        """`X (datum místo – datum místo) …` → narodit_se / zemřít o X.
        Vrací se jen jednou na jméno (závorka má víc členů, každý ji spustí)."""
        if name_head.index in self._bio_done:
            return []
        # tokeny mezi „(“ a „)“ hned za jménem
        idxs = [t.index for t in self.p.tokens]
        last_name = max([name_head.index] + [f.index for f in self.p.children(name_head.index) if f.base_deprel == "flat"])
        if last_name + 1 > len(idxs) or self.p.token(last_name + 1).form != "(":
            return []
        inside: list[Token] = []
        i = last_name + 2
        while i <= len(idxs) and self.p.token(i).form != ")":
            inside.append(self.p.token(i))
            i += 1
        if not inside or i > len(idxs):
            return []
        # rozděl pomlčkou
        parts: list[list[Token]] = [[]]
        for t in inside:
            if t.form in ("–", "-", "—"):
                parts.append([])
            else:
                parts[-1].append(t)
        preds: list[Predication] = []
        subject = self._head_term(name_head)
        for label, part in zip(("narodit_se", "zemřít"), parts):
            time = time_from_tokens(part)
            places = [t for t in part if t.upos == "PROPN" and (t.feat("NameType") == "Geo" or t.upos == "PROPN")]
            if time is None and not places:
                continue
            p = Predication(pred=label, kind="verb", head=part[0].index if part else name_head.index)
            p.roles.append(RoleFill("kdo", "bio", [subject], "structural"))
            if time is not None:
                p.roles.append(RoleFill("kdy", "bio", [TermSpec(part[0].index, time.label, tuple(t.form for t in part if t.upos in ("NUM", "NOUN")), "NUM", "time", time=time, quant="·", quant_authority="structural")], "default"))
            if places:
                pl = places[0]
                p.roles.append(RoleFill("kde", "bio", [TermSpec(pl.index, pl.lemma, (pl.form,), "PROPN", "place", quant="·", quant_authority="structural", tokens=(pl.index,), name_tokens=(pl.index,))], "default"))
            p.defaults.append("životopisná závorka")
            p.tense = "Past"
            preds.append(p)
        if preds:
            self._bio_done.add(name_head.index)
            for t in inside:
                self.mark(t.index, "secondary")
            self.mark(last_name + 1, "punct")
            self.mark(i, "punct")
        return preds


def read(parse: Parse, mood: str | None = None, *, learned_roles: Mapping[str, str] | None = None) -> Reading:
    """Přečti jednu větu. `mood` = `assert` / `question`; když se nezadá,
    rozhodne otazník. `learned_roles` = přepisy povrchových rolí naučené
    dialogem (drží je paměť, ne modul)."""
    return Reader(parse, mood, learned_roles).read()
