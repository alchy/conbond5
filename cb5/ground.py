"""Zakotvení: čtení → uzly a výroky v paměti.

Proč zvláštní vrstva (spec § 3.2 conbond4, tady § 5–6): čtení jmenuje
věci slovy, paměť je drží jako uzly. Mezi tím stojí rozhodnutí o identitě
(„Jirásek“ = „Alois Jirásek“?), o zájmenech a nevysloveném podmětu
(aktivace = sliding window), o instanci z neurčité zmínky („Filip má
auto“ zakládá anonymní auto ∈ auto) a o přivlastnění („Filipovo auto“).
Každé takové rozhodnutí je **výchozí volba s autoritou** a zapíše se do
`Statement.defaults`; co se rozhodnout nedá, je otevřená položka.

Vstup: `Reading`, `Memory`, provenience, stupeň, téma dokumentu.
Výstup: `Grounded` — zapsané výroky (u otázky nezapsané, jen zakotvené).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cb5.memory import Memory, Node, OpenItem, Provenance, Role, Statement
from cb5.read import Predication, Reading, TermSpec


@dataclass
class Grounded:
    statements: list[Statement] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    open: list[OpenItem] = field(default_factory=list)
    #: hlavní výrok (u otázky nezapsaný)
    main: Statement | None = None
    sentence: str = ""


class Grounder:
    """Jedno zakotvení jedné věty (drží paměť, provenienci a poznámky)."""

    def __init__(self, memory: Memory, prov: Provenance, grade: str, *, topic: str | None, write: bool) -> None:
        self.m = memory
        self.prov = prov
        self.grade = grade
        self.topic = topic
        self.write = write
        self.out = Grounded()
        self._defaults: list[str] = []
        self._pending_open: list[tuple[str, str, str, list[str]]] = []  # (kind, about, question, options)

    # ---- termy ---------------------------------------------------------------

    def resolve_term(self, t: TermSpec, *, role: str, subject_specific: bool, pred: str | None) -> str | None:
        """Term → id uzlu (nebo `None`, když se rozřešit nedá).

        Zaznamená výchozí volby do `self._defaults` a otevřené položky do
        `self._pending_open`.
        """
        if t.kind == "wh":
            return None
        if t.kind == "entity":
            node, new = self.m.ensure_entity(t.name_lemmas or (t.lemma,), t.forms, gender=t.gender, number=t.number, doc=self.prov.doc, prefer=self.topic)
            if new:
                self.out.nodes.append(node)
                self.out.notes.append(f"{node.label()} → {node.id} (založen)")
            else:
                self.out.notes.append(f"{' '.join(t.forms)} → {node.id} ({node.label()}; týž uzel)")
                if " ".join(t.name_lemmas) != node.lemma:
                    self._defaults.append(f"identita: „{' '.join(t.name_lemmas)}“ = {node.label()} (částečné jméno)")
            self._title(t, node)
            return node.id
        if t.kind == "place":
            node = self.m.ensure_place(t.name_lemmas or (t.lemma,), t.forms)
            if node.gender is None:
                node.gender, node.number = t.gender, t.number
            self._title(t, node)
            return node.id
        if t.kind == "time":
            if t.time is None:
                return self.m.ensure_group(t.lemma).id
            return self.m.ensure_time(t.time).id
        if t.kind == "pron":
            return self._resolve_pron(t, role)
        if t.kind == "value":
            return self.m.ensure_group(t.lemma).id
        # group (případně zúžená vztahem: „otec Petra Nováka“)
        rel: str | None = None
        if t.rel is not None:
            rel_id = self.resolve_term(t.rel[1], role=role, subject_specific=False, pred=pred)
            if rel_id is not None:
                rel = f"{t.rel[0]}:{rel_id}"
        group = self.m.ensure_group(t.lemma, t.attrs, rel)
        if t.possessor is not None:
            owned = self._resolve_possessed(t, group, role)
            if owned is not None:
                return owned
        if t.quant == "·" and t.quant_authority == "determiner":
            # „ten pes“ — určitý popis: naposled aktivní prvek té group, jinak nový
            for cand in self.m.most_active(kind="entity"):
                if self.m.member_star(cand.id, group.id) is not None:
                    self._defaults.append(f"{role}: „{t.lemma}“ = {cand.label()} (určitý popis z aktivace)")
                    return cand.id
        if (t.quant == "∃" and role == "co" and subject_specific and self.write
                and pred not in ("být",) and t.count is None):
            # neurčitá zmínka u konkrétního podmětu → nová instance („Filip má auto“ → a1 ∈ auto)
            inst = self.m.new_node("entity", t.lemma, names=[], attrs=t.attrs, doc=self.prov.doc, gender=t.gender, number=t.number)
            inst.base = group.id
            self.out.nodes.append(inst)
            self._defaults.append(f"{role}: nová instance {inst.id} ∈ {group.label()} (neurčitá zmínka)")
            self._member(inst.id, group.id)
            return inst.id
        return group.id

    def _title(self, t: TermSpec, node: Node) -> None:
        """„řeka Vltava“ → Vltava ∈ řeka (titul = třída), jen při zápisu a jen jednou."""
        if not t.note.startswith("titul:") or not self.write:
            return
        group = self.m.ensure_group(t.note.split(":", 1)[1], t.attrs)
        if self.m.member_star(node.id, group.id) is not None:
            return
        st = Statement("", "být", "copula", kernel="member", grade=self.grade, prov=self.prov, sentence=self.out.sentence,  # type: ignore[arg-type]
                       roles=[Role("kdo", [node.id], "·", "structural"), Role("co", [group.id], "∃", "structural")],
                       defaults=[f"titul „{group.lemma}“ před jménem = třída"])
        self.m.attach(st)
        self.out.statements.append(st)

    def _member(self, elem: str, group: str) -> None:
        st = Statement("", "být", "copula", kernel="member", grade=self.grade, prov=self.prov, sentence=self.out.sentence,  # type: ignore[arg-type]
                       roles=[Role("kdo", [elem], "·", "structural"), Role("co", [group], "∃", "structural")],
                       defaults=["instance: členství z neurčité zmínky"])
        self.m.attach(st)
        self.out.statements.append(st)

    def _resolve_pron(self, t: TermSpec, role: str) -> str | None:
        """Zájmeno / nevyslovený podmět → nejaktivnější uzel se shodou rodu a
        čísla; jinak téma dokumentu; jinak otevřená položka."""
        if t.lemma in ("se", "sebe", "si"):
            return None
        # entity mají přednost před místy (podmět „oženil se“ není město); místo až
        # když žádná entita v kontextu není
        cands = self.m.most_active(kinds=("entity",), gender=t.gender, number=t.number) or self.m.most_active(kinds=("place",), gender=t.gender, number=t.number)
        if t.person in ("1", "2"):
            cands = []
        if cands:
            node = cands[0]
            # téma dokumentu má přednost, dokud není jiný kandidát VÝRAZNĚ čerstvější
            # (encyklopedický text: vedlejší osoby se zmíní jednou, téma se vrací)
            topic = self.m.nodes.get(self.topic) if self.topic else None
            if topic is not None and topic in cands and topic is not node:
                if self.m.activation(topic.id) * 3.0 >= self.m.activation(node.id):
                    node = topic
            self._defaults.append(f"{role}: „{t.lemma if t.lemma != '∅' else 'nevyslovený podmět'}“ = {node.label()} (z aktivace)")
            return node.id
        if self.topic and self.topic in self.m.nodes and t.person not in ("1", "2"):
            node = self.m.nodes[self.topic]
            self._defaults.append(f"{role}: „{t.lemma if t.lemma != '∅' else 'nevyslovený podmět'}“ = {node.label()} (téma dokumentu)")
            return node.id
        self._pending_open.append(("reference", t.lemma, f"Na koho odkazuje „{t.lemma if t.lemma != '∅' else 'nevyslovený podmět'}“ v roli {role}?", []))
        return None

    def _resolve_possessed(self, t: TermSpec, group: Node, role: str) -> str | None:
        """„Filipovo auto“ / „jeho auto“ → auto, které Filip má (výrok `mít`),
        jinak nová instance s `mít`."""
        kind, word = t.possessor  # type: ignore[misc]
        owner: Node | None = None
        if kind == "adj":
            stem = word
            for suf in ("ův", "ova", "ovo", "in", "ina", "ino"):
                if word.endswith(suf):
                    stem = word[: -len(suf)]
                    break
            cands = [n for n in self.m.nodes.values() if n.kind == "entity" and any(w.lower().startswith(stem.lower()) for name in n.names for w in name.split()) and len(stem) >= 3]
            if len(cands) == 1:
                owner = cands[0]
            elif cands:
                owner = max(cands, key=lambda n: self.m.activation(n.id))
        else:
            cands = self.m.most_active(kinds=("entity",))
            owner = cands[0] if cands else (self.m.nodes.get(self.topic) if self.topic else None)
        if owner is None:
            self._pending_open.append(("reference", word, f"Čí je „{t.lemma}“ („{word}“)?", []))
            return None
        self._defaults.append(f"{role}: „{word} {t.lemma}“ → vlastník {owner.label()}")
        # existující vlastnictví?
        for st in self.m.statements_about(owner.id):
            if st.pred in ("mít", "vlastnit") and not st.neg:
                kdo, co = st.role("kdo"), st.role("co")
                if kdo and owner.id in kdo.terms and co:
                    for x in co.terms:
                        if self.m.member_star(x, group.id) is not None:
                            return x
        if not self.write:
            return None
        inst = self.m.new_node("entity", t.lemma, attrs=t.attrs, doc=self.prov.doc, gender=t.gender, number=t.number)
        inst.base = group.id
        self.out.nodes.append(inst)
        self._member(inst.id, group.id)
        st = Statement("", "mít", "verb", grade=self.grade, prov=self.prov, sentence=self.out.sentence,  # type: ignore[arg-type]
                       roles=[Role("kdo", [owner.id], "·", "structural"), Role("co", [inst.id], "·", "structural")],
                       defaults=[f"vlastnictví z přivlastnění „{word}“"])
        self.m.attach(st)
        self.out.statements.append(st)
        return inst.id

    # ---- predikace -----------------------------------------------------------

    def ground_predication(self, p: Predication, *, parent: str | None = None, residue: list[tuple[str, str]] | None = None) -> Statement:
        self._defaults = list(p.defaults)
        self._pending_open = []
        subj = p.role("kdo")
        subject_specific = bool(subj and subj.terms and subj.terms[0].kind in ("entity", "pron") and subj.terms[0].quant == "·")
        st = Statement("", p.pred, p.kind, neg=p.neg, modality=p.modality, kernel=p.kernel, grade=self.grade,  # type: ignore[arg-type]
                       prov=self.prov, sentence=self.out.sentence, tense=p.tense, mood=p.mood, derived_from=parent,
                       residue=list(residue or []))
        nested_specs: list[tuple[Role, Predication]] = []
        for rf in p.roles:
            role = Role(rf.name, [], None, rf.authority, rf.surface, wh=rf.wh, wh_kind=rf.wh_kind)
            if rf.nested is not None:
                nested_specs.append((role, rf.nested))
            for t in rf.terms:
                nid = self.resolve_term(t, role=rf.name, subject_specific=subject_specific, pred=p.pred)
                if nid is None:
                    continue
                role.terms.append(nid)
                if t.count is not None:
                    role.counts[nid] = t.count
                if role.quant is None:
                    role.quant = t.quant
                if t.quant_authority.startswith("default") and t.quant_authority not in ("default:předmět",):
                    pass  # už je v p.defaults z čtení
            if rf.authority == "surface" and not rf.wh and p.kind not in ("nmod", "appos"):
                self._pending_open.append(("role_name", rf.surface, f"Co znamená role „{rf.name}“ ({rf.surface})? (kde, kdy, kudy, čím, …)", ["kde", "kdy", "kam", "odkud", "kudy", "čím", "s_kým", "komu"]))
            st.roles.append(role)
        st.defaults = list(dict.fromkeys(self._defaults))
        pending = list(self._pending_open)
        if self.write:
            self.m.attach(st)
            self.out.statements.append(st)
            for kind, about, question, options in pending:
                item = self.m.add_open(kind, about, question, st.id, options)
                self.out.open.append(item)
            if st.residue:
                item = self.m.add_open("residue", ", ".join(f"„{f}“" for f, _ in st.residue),
                                       "Do čtení se nedostalo: " + ", ".join(f"„{f}“ ({path})" for f, path in st.residue) + " — jakou roli to hraje?", st.id)
                self.out.open.append(item)
        for role, nested in nested_specs:
            child = self.ground_predication(nested, parent=st.id if self.write else None)
            role.nested = child.id or None
            if not self.write:
                role.nested = None
                self.out.statements.append(child)
        return st

    def ground(self, reading: Reading) -> Grounded:
        if self.write:
            sent = self.m.new_sentence(self.prov.doc, self.prov.sent_no, self.prov.text)
            self.out.sentence = sent.id
        main = self.ground_predication(reading.main, residue=reading.residue)
        self.out.main = main
        for sec in reading.main.secondary:
            self.ground_predication(sec)
        return self.out


def ground(reading: Reading, memory: Memory, prov: Provenance, grade: str = "read", *,
           topic: str | None = None, write: bool = True) -> Grounded:
    """Zakotvi čtení do paměti. `write=False` jen rozřeší termy (otázka
    bázi nemění, I‑12) — vrací hlavní výrok bez id."""
    return Grounder(memory, prov, grade, topic=topic, write=write).ground(reading)
