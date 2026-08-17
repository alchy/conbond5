"""Paměť: graf uzlů a výroků s proveniencí, stupněm, uzávěry a aktivací.

Proč graf (spec § 3): jedna paměť nese znalost (tvrdé hrany: role,
`member`, `subset`, `within`, `name`, `same_as`), kontext dialogu (aktivace)
i propady (měkké hrany spoluvýskytu). Pravdivost teče jen po tvrdých
hranách; aktivace jen řadí. Uložený **program je seznam výroků** (JSON);
graf je jeho deterministická projekce.

Vstupy: `Statement`y z `ground.py`, tahy dialogu.
Výstupy: uzávěry s důkazem (`subset_star` …), aktivní výroky, `graph()`
pro viewBase, `save/load`.

Zásady, které se tu hlídají:
* nic se nemaže — `revoke` jen zneplatní s důvodem, historie zůstává;
* individua vznikají jen tady (`new_node`, `ensure_*`), nikdy při dotazu;
* id jsou deterministická (pořadí vzniku), žádné hodiny.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal, Sequence

import networkx as nx

from cb5.chronos import TimeSpec, before as time_before, within as time_within

Grade = Literal["said", "read", "derived"]
Quant = Literal["∀", "∃", "·"]

KERNELS = ("member", "subset", "within", "same_as", "before", "name")


@dataclass
class Node:
    """Uzel grafu: entita (anonymní identita se jmény), group (množina podle
    lemmatu, případně zúžená přívlastky), místo, čas, hodnota, dokument, věta."""

    id: str
    kind: str
    lemma: str = ""
    names: list[str] = field(default_factory=list)
    attrs: list[str] = field(default_factory=list)
    base: str | None = None
    time: TimeSpec | None = None
    gender: str | None = None
    number: str | None = None
    doc: str = ""
    text: str = ""
    #: Zúžení group vztahem: „Gen:e0003“ (otec Petra Nováka).
    rel: str | None = None

    def label(self) -> str:
        if self.kind == "time" and self.time is not None:
            return self.time.label
        if self.kind in ("entity", "place") and self.names:
            return self.names[0]
        out = self.lemma or self.text or self.id
        if self.attrs:
            out = f"{self.lemma}[{','.join(self.attrs)}]"
        if self.rel:
            out += f"⟨{self.rel.split(':', 1)[1]}⟩"
        return out

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["time"] = asdict(self.time) if self.time else None
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Node":
        t = d.get("time")
        time = None
        if isinstance(t, dict):
            time = TimeSpec(
                kind=t["kind"], label=t["label"],  # type: ignore[arg-type]
                start=tuple(t["start"]) if t.get("start") else None,  # type: ignore[arg-type]
                end=tuple(t["end"]) if t.get("end") else None,  # type: ignore[arg-type]
            )
        return cls(
            id=str(d["id"]), kind=str(d["kind"]), lemma=str(d.get("lemma", "")),
            names=list(d.get("names", [])), attrs=list(d.get("attrs", [])),  # type: ignore[call-overload]
            base=d.get("base"), time=time, gender=d.get("gender"), number=d.get("number"),  # type: ignore[arg-type]
            doc=str(d.get("doc", "")), text=str(d.get("text", "")), rel=d.get("rel"),
        )


@dataclass
class Role:
    """Role výroku: jméno, výplně (id uzlů; koordinace = víc), kvantifikátor
    s autoritou, povrchový tvar, případně vnořený výrok (id) nebo díra."""

    name: str
    terms: list[str] = field(default_factory=list)
    quant: Quant | None = None
    authority: str = "structural"
    surface: str = ""
    nested: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    #: horní mez rozsahu k počtu („30 000–50 000“): counts = dolní mez
    hi: dict[str, int] = field(default_factory=dict)
    #: původní zápis, když int neunese desetiny („1–4,5“, „3,5“)
    count_text: dict[str, str] = field(default_factory=dict)
    wh: bool = False
    wh_kind: str = ""
    #: proměnná pravidla („Každý, kdo …“ → X): role bez termu, kterou váže dotaz
    var: str = ""


@dataclass
class OpenItem:
    """Otevřená položka (backlog): co systém při čtení nevěděl, ale nezastavilo ho to."""

    id: str
    kind: str
    about: str
    question: str
    statement: str
    options: list[str] = field(default_factory=list)
    answer: str | None = None


@dataclass
class Provenance:
    doc: str = ""
    sent_no: int = 0
    text: str = ""
    turn: int = 0
    model: str = ""


@dataclass
class Statement:
    """Řádek programu = reifikovaný výrok (uzel grafu s hranami rolí)."""

    id: str
    pred: str | None
    kind: str
    neg: bool = False
    modality: str | None = None
    kernel: str | None = None
    roles: list[Role] = field(default_factory=list)
    grade: Grade = "read"
    defaults: list[str] = field(default_factory=list)
    residue: list[tuple[str, str]] = field(default_factory=list)
    open: list[str] = field(default_factory=list)
    prov: Provenance = field(default_factory=Provenance)
    status: str = "active"
    reason: str = ""
    derived_from: str | None = None
    sentence: str = ""
    tense: str | None = None
    mood: str = "assert"

    def role(self, name: str) -> Role | None:
        for r in self.roles:
            if r.name == name:
                return r
        return None

    def term_ids(self) -> list[str]:
        out: list[str] = []
        for r in self.roles:
            out.extend(r.terms)
        return out

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["residue"] = [list(x) for x in self.residue]
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Statement":
        roles = [Role(**r) for r in d.get("roles", [])]  # type: ignore[union-attr]
        prov = Provenance(**d.get("prov", {}))  # type: ignore[arg-type]
        return cls(
            id=str(d["id"]), pred=d.get("pred"), kind=str(d["kind"]), neg=bool(d.get("neg")),  # type: ignore[arg-type]
            modality=d.get("modality"), kernel=d.get("kernel"), roles=roles,  # type: ignore[arg-type]
            grade=d.get("grade", "read"), defaults=list(d.get("defaults", [])),  # type: ignore[arg-type,call-overload]
            residue=[tuple(x) for x in d.get("residue", [])], open=list(d.get("open", [])),  # type: ignore[misc,call-overload]
            prov=prov, status=str(d.get("status", "active")), reason=str(d.get("reason", "")),
            derived_from=d.get("derived_from"), sentence=str(d.get("sentence", "")),  # type: ignore[arg-type]
            tense=d.get("tense"), mood=str(d.get("mood", "assert")),  # type: ignore[arg-type]
        )


@dataclass
class Rule:
    """Můstkové pravidlo z dialogu: dotaz na `dst_pred` se zkusí jako dotaz
    na `src_pred` s přemapovanými rolemi (`{"kde": "kam"}`)."""

    id: str
    src_pred: str
    dst_pred: str
    role_map: dict[str, str]
    reason: str = ""


class Memory:
    """Graf výroků. Viz docstring modulu."""

    PREFIX = {"entity": "e", "group": "g", "place": "p", "time": "t", "value": "v", "document": "d", "sentence": "z"}
    DECAY = 0.6

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.statements: dict[str, Statement] = {}
        self.open_items_: dict[str, OpenItem] = {}
        self.rules: list[Rule] = []
        self.counters: dict[str, int] = defaultdict(int)
        self.activation_: dict[str, float] = defaultdict(float)
        self.soft: dict[tuple[str, str], float] = defaultdict(float)
        self.learned: dict[str, dict[str, Any]] = {"roles": {}, "synonyms": {}, "comparatives": {}}
        self.exceptions: list[tuple[str, str, str]] = []  # (pred, group_id, excluded_id)
        #: verze báze — mění se každým zápisem/odvoláním; klíč keše uzávěrů
        self.version = 0
        self._edge_cache: dict[tuple[int, str], dict[str, list[tuple[str, str]]]] = {}
        # indexy
        self._groups: dict[tuple[str, tuple[str, ...]], str] = {}
        self._times: dict[tuple[object, ...], str] = {}
        self._by_pred: dict[str, list[str]] = defaultdict(list)
        self._by_term: dict[str, list[str]] = defaultdict(list)

    # ---- id ------------------------------------------------------------------

    def _next(self, prefix: str) -> str:
        self.counters[prefix] += 1
        return f"{prefix}{self.counters[prefix]:04d}"

    # ---- uzly ------------------------------------------------------------------

    def new_node(self, kind: str, lemma: str = "", *, names: Sequence[str] = (), attrs: Sequence[str] = (),
                 base: str | None = None, time: TimeSpec | None = None, gender: str | None = None,
                 number: str | None = None, doc: str = "", text: str = "") -> Node:
        node = Node(self._next(self.PREFIX.get(kind, "n")), kind, lemma, list(dict.fromkeys(names)), sorted(set(attrs)),
                    base, time, gender, number, doc, text)
        self.nodes[node.id] = node
        return node

    @staticmethod
    def _name_key(name: str) -> tuple[str, ...]:
        return tuple(w.lower() for w in name.replace("-", " ").split())

    def find_entity(self, name_lemmas: Sequence[str], *, kinds: Sequence[str] = ("entity", "place")) -> list[Node]:
        """Uzly, jejichž jméno se s dotazem překrývá: přesná shoda > dotaz je
        částí jména („Jirásek“ ⊂ „Alois Jirásek“) > jméno je částí dotazu."""
        q = tuple(w.lower() for w in name_lemmas)
        if not q:
            return []
        exact: list[Node] = []
        partial: list[Node] = []
        for n in self.nodes.values():
            if n.kind not in kinds:
                continue
            keys = [self._name_key(x) for x in n.names]
            if q in keys or any(set(q) == set(k) for k in keys):
                exact.append(n)
                continue
            # částečná shoda JEN proti kanonickému (nejdelšímu) jménu — krátké
            # tvary („Jirásek“) v seznamu jmen nesmí scelit „Josefa Jiráska“
            # s „Aloisem Jiráskem“
            canon = max(keys, key=len) if keys else ()
            if canon and (set(q) < set(canon) or (set(canon) < set(q) and len(canon) > 1)):
                partial.append(n)
        return exact or partial

    def ensure_entity(self, name_lemmas: Sequence[str], forms: Sequence[str] = (), *, kind: str = "entity",
                      gender: str | None = None, number: str | None = None, doc: str = "",
                      prefer: str | None = None) -> tuple[Node, bool]:
        """Najdi entitu podle jména, nebo ji založ. Vrací (uzel, nová?).
        Při víc kandidátech vyhrává `prefer` (téma dokumentu), jinak aktivace."""
        # místa i entity se hledají v jednom prostoru jmen: „vulkán Ol Doinyo Lengai“ (entita)
        # a „sopka Ol Doinyo Lengai“ (místo) je totéž jméno → týž uzel
        found = self.find_entity(name_lemmas, kinds=("entity", "place"))
        if not found and forms:
            # lemma je z parseru dvojznačné („Pavla“ = Nom Pavla i Acc Pavel) — zkus přesný CELÝ
            # tvar jména, který už paměť viděla („Pavla“, „Petra Nováka“) — ne jednotlivá slova
            # (přes „Nováková“ by se scelila celá rodina)
            full = " ".join(f for f in forms if f)
            by_form = [n for n in self.nodes.values() if n.kind in ("entity", "place") and full in n.names]
            if len(by_form) >= 1:
                found = by_form
        if len(found) == 1:
            n = found[0]
            full = " ".join(name_lemmas)
            if full not in n.names:
                n.names.append(full)
            for f in forms:
                if f not in n.names:
                    n.names.append(f)
            return n, False
        if not found:
            # dřív přečteno jako TŘÍDA z neznámého slova s velkým písmenem („Ronik je pes.“) →
            # teď je to vlastní jméno: uzel se převede na entitu, výroky zůstávají
            for n in self.nodes.values():
                if n.kind == "group" and n.text == "cap" and not n.attrs and not n.rel and n.lemma == " ".join(name_lemmas).lower():
                    n.kind, n.text = kind, "cap→entity"
                    n.names = list(dict.fromkeys([" ".join(name_lemmas)] + [f for f in forms if f]))
                    n.gender, n.number = n.gender or gender, n.number or number
                    return n, False
        if len(found) > 1:
            # víc kandidátů: téma dokumentu; jinak uzel, o kterém už něco víme; jinak nejaktivnější
            preferred = [n for n in found if n.id == prefer]
            best = preferred[0] if preferred else max(
                found, key=lambda n: (len(self._by_term.get(n.id, [])) > 0, self.activation_.get(n.id, 0.0), -int(n.id[1:])))
            full = " ".join(name_lemmas)
            if full not in best.names:
                best.names.append(full)
            return best, False
        names = [" ".join(name_lemmas)] + [f for f in forms if f]
        return self.new_node(kind, " ".join(name_lemmas), names=names, gender=gender, number=number, doc=doc), True

    def ensure_group(self, lemma: str, attrs: Sequence[str] = (), rel: str | None = None) -> Node:
        """Group podle lemmatu, případně zúžená přívlastky (`mazlíček[domácí]`)
        a/nebo vztahem k uzlu (`otec⟨e0003⟩`); zúžená group má `base` = širší
        (nejdřív bez vztahu, pak bez přívlastků) → `subset` strukturálně."""
        key = (lemma, tuple(sorted(set(attrs))) + ((f"rel={rel}",) if rel else ()))
        if key in self._groups:
            return self.nodes[self._groups[key]]
        base: str | None = None
        if rel:
            base = self.ensure_group(lemma, attrs).id
        elif attrs:
            base = self.ensure_group(lemma).id
        node = self.new_node("group", lemma, attrs=attrs, base=base)
        node.rel = rel
        self._groups[key] = node.id
        return node

    def find_group(self, lemma: str, attrs: Sequence[str] = (), rel: str | None = None) -> Node | None:
        key = (lemma, tuple(sorted(set(attrs))) + ((f"rel={rel}",) if rel else ()))
        return self.nodes.get(self._groups.get(key, ""))

    def ensure_place(self, name_lemmas: Sequence[str], forms: Sequence[str] = ()) -> Node:
        return self.ensure_entity(name_lemmas, forms, kind="place")[0]

    def ensure_time(self, spec: TimeSpec) -> Node:
        key = (spec.kind, spec.label, spec.start, spec.end)
        if key in self._times:
            return self.nodes[self._times[key]]
        node = self.new_node("time", spec.label, time=spec)
        self._times[key] = node.id
        return node

    def ensure_document(self, name: str) -> Node:
        for n in self.nodes.values():
            if n.kind == "document" and n.lemma == name:
                return n
        return self.new_node("document", name, doc=name)

    def new_sentence(self, doc: str, no: int, text: str) -> Node:
        return self.new_node("sentence", f"{doc}#{no}", doc=doc, text=text)

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def label(self, node_id: str) -> str:
        """Popiska uzlu s rozřešeným zúžením: `otec⟨Petr Novák⟩` místo `otec⟨e0003⟩`."""
        n = self.nodes.get(node_id)
        if n is None:
            return node_id
        if n.kind == "entity" and not n.names and n.base:
            return self.label(n.base)
        out = n.label()
        if n.rel and ":" in n.rel:
            surface, target = n.rel.split(":", 1)
            out = out.replace(f"⟨{target}⟩", f"⟨{self.label(target)}⟩")
        return out

    # ---- výroky ---------------------------------------------------------------

    def attach(self, stmt: Statement) -> Statement:
        """Zapiš výrok. Přidělí id, zaindexuje, aktivuje jeho termy."""
        if not stmt.id:
            stmt.id = self._next("s")
        self.statements[stmt.id] = stmt
        self.version += 1
        if stmt.pred:
            self._by_pred[stmt.pred].append(stmt.id)
        for t in stmt.term_ids():
            self._by_term[t].append(stmt.id)
        ids = stmt.term_ids()
        self.activate(ids, 1.0)
        # podmět nese téma dál — o něco silnější aktivace (sliding window)
        subj = stmt.role("kdo")
        if subj:
            self.activate(subj.terms, 0.5)
        self.co_mention(ids)
        return stmt

    def revoke(self, sid: str, reason: str) -> list[str]:
        """Zneplatni výrok (a vše z něj odvozené / do něj vnořené). Vrací id.
        Výrok kind=definice nese naučené pravidlo → i to se vypne (nic se nemaže, jen odvolá)."""
        out: list[str] = []
        st = self.statements.get(sid)
        if st is None or st.status != "active":
            return out
        st.status = "revoked"
        st.reason = reason
        self.version += 1
        out.append(sid)
        if st.kind == "definice":
            self._unlearn(st)
        for other in list(self.statements.values()):
            if other.derived_from == sid and other.status == "active":
                out.extend(self.revoke(other.id, f"odvoláno s {sid}: {reason}"))
        return out

    def _unlearn(self, st: Statement) -> None:
        """Odvolání definičního výroku vypne odpovídající naučenou vazbu v `learned`."""
        jaky = st.role("jaký")
        head = self.nodes[jaky.terms[0]].lemma if jaky and jaky.terms and jaky.terms[0] in self.nodes else None
        if head is None:
            return
        if st.pred == "definice_vztahu":
            defs = self.learned.get("rel_defs", {})
            chains = [r.surface.split("∘") for r in st.roles if r.name == "co" and r.surface and "∘" in r.surface]
            if chains and head in defs:
                defs[head] = [c for c in defs[head] if c not in chains]
                if not defs[head]:
                    defs.pop(head)
            else:
                defs.pop(head, None)
        elif st.pred == "definice":
            self.learned.get("comparatives", {}).pop(head, None)
        elif st.pred == "binární_pravidlo":
            self.learned.get("binary", {}).pop(head, None)
        elif st.pred == "inverze":
            co = st.role("co")
            other = self.nodes[co.terms[0]].lemma if co and co.terms else None
            inv = self.learned.get("inverse", {})
            if other:
                inv.get(head, []) and inv[head].remove(other) if other in inv.get(head, []) else None
                inv.get(other, []) and inv[other].remove(head) if head in inv.get(other, []) else None

    def learned_program(self) -> list[str]:
        """Modul vazeb: naučené vazby jako přehratelné příkazy (`!role`, `!synonymum`,
        `!srovnání`, `!uč složený/inverze/překryv/porovnání`, `!pravidlo`, `!výjimka`).
        Bez faktů — přenositelné mezi paměťmi; načtení jde touž cestou jako dialog,
        takže každá vazba má i v cílové paměti výrok s proveniencí (lze ji odvolat)."""
        out: list[str] = []
        for surface, name in self.learned.get("roles", {}).items():
            out.append(f"!role {surface} = {name}")
        for a, b in self.learned.get("synonyms", {}).items():
            out.append(f"!synonymum {a} = {b}")
        dirs = {"earlier": "dřív", "later": "později", "more": "víc", "less": "míň"}
        for lemma, c in self.learned.get("comparatives", {}).items():
            out.append(f"!srovnání {lemma} = {c['pred']} {c['role']} {dirs.get(c['dir'], c['dir'])}")
        for head, chains in self.learned.get("rel_defs", {}).items():
            by_first: dict[str, list[str]] = {}
            for ch in chains:
                by_first.setdefault(ch[0], []).append(ch[1])
            for r1, seconds in by_first.items():
                for i in range(0, len(seconds), 2):  # šablona bere r2 a volitelně alternativu
                    out.append(f"!uč složený {head} {r1} {' '.join(seconds[i:i + 2])}")
        seen: set[tuple[str, str]] = set()
        for a, bs in self.learned.get("inverse", {}).items():
            for b in bs:
                if (b, a) not in seen:
                    seen.add((a, b))
                    out.append(f"!uč inverze {a} {b}")
        for q, spec in self.learned.get("binary", {}).items():
            if spec["test"] == "překryv":
                out.append(f"!uč překryv {q} {spec['source']}")
            else:
                out.append(f"!uč porovnání {q} {spec['source']} {spec['test']}")
        for r in self.rules:
            src = ",".join(f"{k}:X{i}" for i, k in enumerate(r.role_map))
            dst = ",".join(f"{v}:X{i}" for i, v in enumerate(r.role_map.values()))
            out.append(f"!pravidlo {r.src_pred}({src}) => {r.dst_pred}({dst})")
        for pred, g, x in self.exceptions:
            out.append(f"!výjimka {pred} {self.label(g)} {self.label(x)}")
        return out

    def revoke_utterance(self, sentence_id: str, reason: str) -> list[str]:
        out: list[str] = []
        for st in list(self.statements.values()):
            if st.sentence == sentence_id and st.status == "active" and st.derived_from is None:
                out.extend(self.revoke(st.id, reason))
        return out

    def inspect(self, sid: str) -> Statement:
        return self.statements[sid]

    def active(self) -> Iterator[Statement]:
        for st in self.statements.values():
            if st.status == "active":
                yield st

    def by_pred(self, pred: str) -> list[Statement]:
        return [self.statements[i] for i in self._by_pred.get(pred, []) if self.statements[i].status == "active"]

    def statements_about(self, node_id: str) -> list[Statement]:
        return [self.statements[i] for i in self._by_term.get(node_id, []) if self.statements[i].status == "active"]

    def last_statement(self, *, grade: str | None = None) -> Statement | None:
        for st in reversed(list(self.statements.values())):
            if st.status == "active" and st.derived_from is None and (grade is None or st.grade == grade):
                return st
        return None

    # ---- otevřené položky -----------------------------------------------------

    def add_open(self, kind: str, about: str, question: str, statement: str, options: Sequence[str] = ()) -> OpenItem:
        item = OpenItem(self._next("o"), kind, about, question, statement, list(options))
        self.open_items_[item.id] = item
        st = self.statements.get(statement)
        if st is not None:
            st.open.append(item.id)
        return item

    def open_items(self) -> list[OpenItem]:
        return [o for o in self.open_items_.values() if o.answer is None and self.statements.get(o.statement, Statement("", None, "")).status == "active"]

    # ---- pravidla, výjimky ------------------------------------------------------

    def add_rule(self, src_pred: str, dst_pred: str, role_map: dict[str, str], reason: str = "") -> Rule:
        rule = Rule(self._next("r"), src_pred, dst_pred, dict(role_map), reason)
        self.rules.append(rule)
        return rule

    def add_exception(self, pred: str, group_id: str, excluded_id: str) -> None:
        """`∀`‑výrok o `group_id` neplatí pro `excluded_id` (algebra NOT)."""
        self.exceptions.append((pred, group_id, excluded_id))

    def excluded(self, pred: str, group_id: str, node_id: str) -> bool:
        for p, g, x in self.exceptions:
            if p == pred and g == group_id and (x == node_id or self.subset_star(node_id, x) is not None or self.member_star(node_id, x) is not None):
                return True
        return False

    # ---- uzávěry ---------------------------------------------------------------

    def _kernel_edges(self, kernel: str) -> dict[str, list[tuple[str, str]]]:
        """Tvrdé hrany daného jádra z aktivních nenegovaných výroků: a → (b, sid).
        Kešované podle verze báze (zúžené group přibývají bez výroku, proto
        je v klíči i počet uzlů)."""
        key = (self.version * 100003 + len(self.nodes), kernel)
        hit = self._edge_cache.get(key)
        if hit is not None:
            return hit
        edges: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for st in self.active():
            if st.kernel != kernel or st.neg:
                continue
            a, b = self._kernel_pair(st)
            if a and b:
                for x in a:
                    for y in b:
                        edges[x].append((y, st.id))
        if kernel == "subset":
            rel_groups: dict[tuple[str, tuple[str, ...]], list[Node]] = defaultdict(list)
            for n in self.nodes.values():
                if n.kind == "group" and n.base:
                    edges[n.id].append((n.base, f"restricts:{n.id}"))
                if n.kind == "group" and n.rel:
                    rel_groups[(n.lemma, tuple(n.attrs))].append(n)
            # zúžení vztahem s UŽŠÍM cílem: příbuzný⟨pes[domácí]⟩ ⊆ příbuzný⟨pes⟩ (cíl přes `restricts`)
            for group_nodes in rel_groups.values():
                by_target = {n.rel.split(":", 1)[1]: n for n in group_nodes if n.rel}
                for n in group_nodes:
                    t = self.nodes.get(n.rel.split(":", 1)[1]) if n.rel else None
                    while t is not None and t.base:
                        wider = by_target.get(t.base)
                        if wider is not None:
                            edges[n.id].append((wider.id, f"rel:{n.id}⊆{wider.id}"))
                            break
                        t = self.nodes.get(t.base)
        if len(self._edge_cache) > 64:
            self._edge_cache.clear()
        self._edge_cache[key] = edges
        return edges

    @staticmethod
    def _kernel_pair(st: Statement) -> tuple[list[str], list[str]]:
        subj = st.role("kdo")
        obj = st.role("co") or st.role("kde")
        return (subj.terms if subj else []), (obj.terms if obj else [])

    def _closure(self, kernel: str, a: str, b: str, *, symmetric: bool = False) -> list[str] | None:
        if a == b:
            return []
        edges = self._kernel_edges(kernel)
        if symmetric:
            # nesahat do kešované mapy — postavit vlastní kopii s opačnými hranami
            both: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for x, ys in edges.items():
                both[x].extend(ys)
                for y, sid in ys:
                    both[y].append((x, sid))
            edges = both
        seen = {a}
        frontier: list[tuple[str, list[str]]] = [(a, [])]
        while frontier:
            x, path = frontier.pop(0)
            for y, sid in edges.get(x, []):
                if y == b:
                    return path + [sid]
                if y not in seen:
                    seen.add(y)
                    frontier.append((y, path + [sid]))
        return None

    def same_as_star(self, a: str, b: str) -> list[str] | None:
        return self._closure("same_as", a, b, symmetric=True)

    def subset_star(self, a: str, b: str) -> list[str] | None:
        """`a ⊆ b` přes řetěz `subset` (i zúžení `restricts`) a `same_as`.
        Strukturálně také přes zúžení vztahem: `příbuzný⟨pes[domácí]⟩ ⊆ příbuzný⟨pes⟩`,
        `otec⟨Petr⟩ ⊆ otec⟨člověk⟩` (cíl zúžení je užší / prvek)."""
        direct = self._closure("subset", a, b)
        if direct is not None:
            return direct
        na, nb = self.nodes.get(a), self.nodes.get(b)
        if (na and nb and na.kind == "group" and nb.kind == "group" and na.rel and nb.rel
                and na.lemma == nb.lemma and na.attrs == nb.attrs and na.id != nb.id):
            ta, tb = na.rel.split(":", 1)[1], nb.rel.split(":", 1)[1]
            inner = self.subset_star(ta, tb)
            if inner is None and self.nodes.get(ta, Node("", "")).kind in ("entity", "place"):
                inner = self.member_star(ta, tb)
            if inner is not None:
                return [f"rel:{ta}⊆{tb}"] + inner
        # týž vztažený cíl, jiné vztahové jméno: otec ⊆ rodič ⇒ otec⟨Jana⟩ ⊆ rodič⟨Jana⟩
        if (na and nb and na.kind == "group" and nb.kind == "group" and na.rel and nb.rel and na.rel == nb.rel
                and na.lemma != nb.lemma):
            ba, bb = self.find_group(na.lemma, na.attrs), self.find_group(nb.lemma, nb.attrs)
            if ba is not None and bb is not None:
                base = self._closure("subset", ba.id, bb.id)
                if base is not None:
                    return [f"rel:{na.lemma}⊆{nb.lemma} přenáší se na ⟨{self.label(na.rel.split(':', 1)[1])}⟩"] + base
        # přes ekvivalenci jmen na obou koncích
        for x in self._class(a):
            for y in self._class(b):
                r = self._closure("subset", x, y)
                if r is not None:
                    return (self.same_as_star(a, x) or []) + r + (self.same_as_star(y, b) or [])
        return None

    def member_star(self, e: str, g: str) -> list[str] | None:
        """`e ∈ g`: `member` do nějaké group, která je ⊆ g. Entita, o níž byl
        omylem zapsán `subset` (než se poznalo, že je to jméno), projde přes něj."""
        edges = self._kernel_edges("member")
        best: list[str] | None = None
        ne = self.nodes.get(e)
        if ne is not None and ne.kind == "entity":
            via_subset = self.subset_star(e, g)
            if via_subset:
                best = via_subset
        for x in self._class(e):
            for h, sid in edges.get(x, []):
                sub = self.subset_star(h, g)
                if sub is not None:
                    path = ((self.same_as_star(e, x) or []) + [sid] + sub)
                    if best is None or len(path) < len(best):
                        best = path
        return best

    def within_star(self, a: str, b: str) -> list[str] | None:
        return self._closure("within", a, b)

    def before(self, a: str, b: str) -> bool | None:
        na, nb = self.nodes.get(a), self.nodes.get(b)
        if na and nb and na.time and nb.time:
            return time_before(na.time, nb.time)
        return None

    def time_within(self, a: str, b: str) -> bool | None:
        na, nb = self.nodes.get(a), self.nodes.get(b)
        if na and nb and na.time and nb.time:
            return time_within(na.time, nb.time)
        return None

    def disjoint(self, a: str, b: str) -> str | None:
        """Existuje aktivní `¬subset(x, y)` s a ⊆ x a b ⊆ y (nebo obráceně)? Vrací id."""
        for st in self.active():
            if st.kernel == "subset" and st.neg:
                xs, ys = self._kernel_pair(st)
                for x in xs:
                    for y in ys:
                        if (self.subset_star(a, x) is not None and self.subset_star(b, y) is not None) or (
                            self.subset_star(b, x) is not None and self.subset_star(a, y) is not None
                        ):
                            return st.id
        return None

    def _class(self, node_id: str) -> list[str]:
        out = [node_id]
        edges = self._kernel_edges("same_as")
        changed = True
        while changed:
            changed = False
            for x in list(out):
                for y, _ in edges.get(x, []):
                    if y not in out:
                        out.append(y)
                        changed = True
                for z, ys in edges.items():
                    if any(y == x for y, _ in ys) and z not in out:
                        out.append(z)
                        changed = True
        return out

    def known_members(self, g: str) -> list[tuple[str, list[str]]]:
        """Známé prvky group (přes member + subset řetězy) s důkazem."""
        out: list[tuple[str, list[str]]] = []
        for st in self.active():
            if st.kernel == "member" and not st.neg:
                es, gs = self._kernel_pair(st)
                for e in es:
                    for h in gs:
                        sub = self.subset_star(h, g)
                        if sub is not None and all(e != x for x, _ in out):
                            out.append((e, [st.id] + sub))
        return out

    def known_subsets(self, g: str) -> list[tuple[str, list[str]]]:
        out: list[tuple[str, list[str]]] = []
        for n in self.nodes.values():
            if n.kind == "group" and n.id != g:
                sub = self.subset_star(n.id, g)
                if sub is not None:
                    out.append((n.id, sub))
        return out

    # ---- aktivace, měkké hrany -----------------------------------------------

    def activate(self, node_ids: Sequence[str], energy: float = 1.0) -> None:
        for i in node_ids:
            if i in self.nodes:
                self.activation_[i] += energy

    def tick(self) -> None:
        for k in list(self.activation_):
            self.activation_[k] *= self.DECAY
            if self.activation_[k] < 0.01:
                del self.activation_[k]

    def activation(self, node_id: str) -> float:
        return self.activation_.get(node_id, 0.0)

    def most_active(self, *, kind: str | None = None, gender: str | None = None, number: str | None = None,
                    kinds: Sequence[str] = ()) -> list[Node]:
        out = []
        for i, a in self.activation_.items():
            n = self.nodes.get(i)
            if n is None:
                continue
            if kind and n.kind != kind:
                continue
            if kinds and n.kind not in kinds:
                continue
            if gender and n.gender and gender not in n.gender.split(","):
                continue
            if number and n.number and number != n.number:
                continue
            out.append((a, n))
        out.sort(key=lambda x: (-x[0], x[1].id))
        return [n for _, n in out]

    def co_mention(self, node_ids: Sequence[str]) -> None:
        ids = sorted(set(i for i in node_ids if i in self.nodes))
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                self.soft[(a, b)] += 1.0

    # ---- graf, program, JSON ---------------------------------------------------

    def graph(self) -> nx.MultiDiGraph:
        """Graf pro viewBase: uzly s `kind/label/activation`, hrany s `type`
        a `soft` (měkké jen řadí — v grafu jsou, ale odlišené)."""
        g: nx.MultiDiGraph = nx.MultiDiGraph()
        for n in self.nodes.values():
            if n.kind in ("document", "sentence"):
                continue
            g.add_node(n.id, kind=n.kind, label=n.label(), activation=self.activation(n.id))
        shown = list(self.active()) + [st for st in self.statements.values() if st.status == "embedded"
                                          and st.derived_from in self.statements and self.statements[st.derived_from].status == "active"]
        for st in shown:
            g.add_node(st.id, kind="statement", label=self.render_short(st) + (f" ({st.reason})" if st.status == "embedded" else ""),
                       grade=st.grade, activation=0.0, embedded=st.status == "embedded")
            for r in st.roles:
                for t in r.terms:
                    g.add_edge(st.id, t, type=f"role:{r.name}", soft=False)
                if r.nested:
                    g.add_edge(st.id, r.nested, type=f"role:{r.name}", soft=False)
            if st.kernel and not st.neg:
                a, b = self._kernel_pair(st)
                for x in a:
                    for y in b:
                        g.add_edge(x, y, type=st.kernel, soft=False, statement=st.id)
        for n in self.nodes.values():
            if n.kind == "group" and n.base:
                g.add_edge(n.id, n.base, type="restricts", soft=False)
        for (sa, sb), w in self.soft.items():
            g.add_edge(sa, sb, type="co_mention", soft=True, weight=w)
        # referent jen z otázky (žádný výrok, žádná hrana) v grafu neruší — v paměti zůstává (téma pro další tah)
        for nid in [n for n in list(g.nodes) if g.degree(n) == 0 and g.nodes[n].get("kind") != "statement"]:
            g.remove_node(nid)
        return g

    @staticmethod
    def count_label(role: "Role", t: str) -> str:
        """Počet u termu jako text: „42“, „30 000–50 000“ (mezera po tisících od 10 000)."""
        def fmt(n: int) -> str:
            return f"{n:,}".replace(",", " ") if n >= 10000 else str(n)
        if t in role.count_text:
            return role.count_text[t]
        lo = role.counts[t]
        return fmt(lo) + (f"–{fmt(role.hi[t])}" if t in role.hi else "")

    def render_short(self, st: Statement) -> str:
        head = st.pred or "∅"
        if st.neg:
            head = "¬" + head
        if st.modality:
            head = f"{st.modality}:{head}"
        parts = []
        for r in st.roles:
            if r.nested:
                parts.append(f"{r.name}:[{r.nested}]")
            elif r.wh:
                parts.append(f"{r.name}:?")
            elif r.var:
                parts.append(f"{r.name}:{r.var}")
            else:
                labels = []
                for t in r.terms:
                    lab = self.nodes[t].label() if t in self.nodes else t
                    if t in r.counts:
                        lab += f"#{r.counts[t]}" + (f"–{r.hi[t]}" if t in r.hi else "")
                    labels.append((r.quant or "") + lab)
                parts.append(f"{r.name}:{'+'.join(labels)}")
        k = f" ⟨{st.kernel}⟩" if st.kernel else ""
        return f"{head}({', '.join(parts)}){k}"

    def program(self) -> list[str]:
        out = []
        for st in self.statements.values():
            flag = "" if st.status == "active" else f" ✗({st.reason})"
            out.append(f"{st.id}: {self.render_short(st)} @{st.grade} @{st.prov.doc}#{st.prov.sent_no}{flag}")
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "format": "conbond5-memory/1",
            "counters": dict(self.counters),
            "nodes": [n.to_json() for n in self.nodes.values()],
            "statements": [s.to_json() for s in self.statements.values()],
            "open": [asdict(o) for o in self.open_items_.values()],
            "rules": [asdict(r) for r in self.rules],
            "exceptions": [list(x) for x in self.exceptions],
            "learned": self.learned,
            "soft": [[a, b, w] for (a, b), w in sorted(self.soft.items())],
            "activation": dict(sorted(self.activation_.items())),
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Memory":
        m = cls()
        m.counters = defaultdict(int, d.get("counters", {}))  # type: ignore[arg-type]
        for nd in d.get("nodes", []):  # type: ignore[union-attr]
            n = Node.from_json(nd)
            m.nodes[n.id] = n
            if n.kind == "group":
                m._groups[(n.lemma, tuple(n.attrs) + ((f"rel={n.rel}",) if n.rel else ()))] = n.id
            if n.kind == "time" and n.time:
                m._times[(n.time.kind, n.time.label, n.time.start, n.time.end)] = n.id
        for sd in d.get("statements", []):  # type: ignore[union-attr]
            s = Statement.from_json(sd)
            m.statements[s.id] = s
            if s.pred:
                m._by_pred[s.pred].append(s.id)
            for t in s.term_ids():
                m._by_term[t].append(s.id)
        for od in d.get("open", []):  # type: ignore[union-attr]
            o = OpenItem(**od)
            m.open_items_[o.id] = o
        for rd in d.get("rules", []):  # type: ignore[union-attr]
            m.rules.append(Rule(**rd))
        m.exceptions = [tuple(x) for x in d.get("exceptions", [])]  # type: ignore[misc,union-attr]
        m.learned = d.get("learned", m.learned)  # type: ignore[assignment]
        for a, b, w in d.get("soft", []):  # type: ignore[union-attr]
            m.soft[(a, b)] = w
        m.activation_ = defaultdict(float, d.get("activation", {}))  # type: ignore[arg-type]
        return m

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Memory":
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))
