"""Logika: hodnocení výroků nad pamětí — ANO / NE / NEVÍM s důkazem.

Proč právě takhle (spec § 6): dotaz je zakotvený výrok s dírami; odpověď
je **shoda dotazu s výroky paměti**, kde každá role dotazu musí mít
protějšek ve výroku (výrok smí mít role navíc, dotaz ne — to je oprava
chyby „Bydlí Petr v Brně? → ANO“ z conbond4) a termy se porovnávají přes
uzávěry: `same_as*`, distribuce `∀` dolů přes `member*`/`subset*`, místa
přes `within*`, čas přes obsažení intervalů. `NE` vzniká jen z výroku
s opačnou polaritou, z disjunktnosti nebo z jiného počtu; jinak `NEVÍM`
s tím, co je blízko a co chybí.

Každý verdikt nese `Proof`: id výroků, kroky (uzávěry, pravidla,
synonyma) a výchozí volby, na kterých stojí — a stupeň = nejslabší
premisa. Modalita je příznak: prostý výrok odpovídá i na „může“;
modální výrok na prostou otázku dává `MOŽNÁ`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from cb5.defaults import PLACE_NOUNS, synonym_class
from cb5.memory import Memory, Role, Statement

Grade = Literal["said", "read", "derived"]
GRADE_RANK = {"said": 3, "read": 2, "derived": 1}


@dataclass
class Proof:
    """Důkaz: výroky, kroky, výchozí volby, stupeň = nejslabší premisa.
    Prázdný důkaz (žádná premisa) má stupeň `said`, aby slučováním nic
    neoslabil."""

    statements: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    defaults: list[str] = field(default_factory=list)
    grade: Grade = "said"

    def merged(self, other: "Proof") -> "Proof":
        return Proof(
            self.statements + [s for s in other.statements if s not in self.statements],
            self.steps + other.steps,
            self.defaults + [d for d in other.defaults if d not in self.defaults],
            weakest(self.grade, other.grade),
        )


@dataclass
class Verdict:
    value: Literal["ANO", "NE", "NEVÍM", "KONFLIKT", "MOŽNÁ"]
    proofs: list[Proof] = field(default_factory=list)
    counter: list[Proof] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    near: list[str] = field(default_factory=list)
    #: wh: (id uzlu nebo `count:N`, důkaz)
    fillers: list[tuple[str, Proof]] = field(default_factory=list)


def weakest(a: str, b: str) -> Grade:
    return a if GRADE_RANK[a] <= GRADE_RANK[b] else b  # type: ignore[return-value]


def _same_pred(a: str | None, b: str | None, learned: dict[str, str] | None = None) -> str | None:
    """Shoda predikátu: přesná, nebo přes třídu synonym (vrací popis kroku)."""
    if a is None or b is None:
        return None
    if a == b:
        return ""
    if synonym_class(a, learned) == synonym_class(b, learned):
        return f"synonymum: {a} ~ {b}"
    # zvratné „se/si“ jako slabá shoda („uprchnout_se“ z otázky × „uprchnout“)
    sa, sb = a.split("_se")[0].split("_si")[0], b.split("_se")[0].split("_si")[0]
    if sa == sb or synonym_class(sa, learned) == synonym_class(sb, learned):
        return f"zvratné se: {a} ~ {b}"
    return None


PLACE_FAMILY = ("kde", "kam", "odkud", "kudy")
TIME_FAMILY = ("kdy", "od_kdy", "do_kdy", "po_kdy", "před_kdy", "jak_dlouho")


class Evaluator:
    def __init__(self, memory: Memory) -> None:
        self.m = memory
        self.syn = memory.learned.get("synonyms", {})

    def same_pred(self, a: str | None, b: str | None) -> str | None:
        return _same_pred(a, b, self.syn)

    # ---- termy ---------------------------------------------------------------

    def _kind(self, node_id: str) -> str:
        n = self.m.nodes.get(node_id)
        return n.kind if n else "?"

    def _is_instance(self, node_id: str) -> bool:
        n = self.m.nodes.get(node_id)
        return bool(n and n.kind == "entity" and n.base)

    def match_term(self, q: str, qquant: str | None, f: str, fquant: str | None, *, role: str) -> Proof | None:
        """Sedí term dotazu `q` na term výroku `f`? Vrací kroky nebo `None`."""
        m = self.m
        if q == f:
            return Proof()
        same = m.same_as_star(q, f)
        if same is not None:
            return Proof(same, [f"{m.node(q).label()} = {m.node(f).label()}"])
        qk, fk = self._kind(q), self._kind(f)
        # místa: kde/kam/odkud dotazu obsahuje místo výroku
        if qk == "place" and fk == "place":
            w = m.within_star(f, q)
            if w is not None:
                return Proof(w, [f"{m.node(f).label()} ⊆ {m.node(q).label()} (místo)"], grade="derived")
            return None
        if qk == "time" and fk == "time":
            if m.time_within(f, q):
                return Proof([], [f"{m.node(f).label()} je v {m.node(q).label()}"])
            return None
        # entita / instance dotazu × group výroku
        if qk in ("entity", "place") and fk == "group":
            if fquant == "∀":
                mem = m.member_star(q, f)
                if mem is not None:
                    return Proof(mem, [f"{m.node(q).label()} ∈ {m.node(f).label()} (∀ se přenáší dolů)"], grade="derived")
            return None
        # group dotazu × group výroku
        if qk == "group" and fk == "group":
            if fquant == "∀":
                sub = m.subset_star(q, f)
                if sub is not None:
                    return Proof(sub, [f"{m.node(q).label()} ⊆ {m.node(f).label()} (∀ se přenáší dolů)"], grade="derived" if sub else "read")
                return None
            # ∃ / · výrok: dotaz sedí, když je výrok stejně nebo víc konkrétní
            sub = m.subset_star(f, q)
            if sub is not None and qquant != "∀":
                return Proof(sub, [f"{m.node(f).label()} ⊆ {m.node(q).label()}"] if sub else [], grade="derived" if sub else "read")
            return None
        # group dotazu × instance výroku („Napsal román?“ × r1 ∈ román)
        if qk == "group" and fk in ("entity", "place"):
            if qquant == "∀":
                return None
            mem = m.member_star(f, q)
            if mem is not None:
                return Proof(mem, [f"{m.node(f).label()} ∈ {m.node(q).label()}"], grade="derived")
            return None
        return None

    def match_role(self, qr: Role, fr: Role, *, pred: str | None) -> Proof | None:
        if qr.wh:
            return Proof()
        if not qr.terms:
            return Proof()  # role bez termu (nerozřešené zájmeno) nic neomezuje — přiznat v defaults
        proof = Proof()
        for qt in qr.terms:
            best: Proof | None = None
            for ft in fr.terms:
                if pred and fr.quant == "∀" and self.m.excluded(pred, ft, qt):
                    continue
                p = self.match_term(qt, qr.quant, ft, fr.quant, role=qr.name)
                if p is not None and (best is None or len(p.statements) < len(best.statements)):
                    best = p
            if best is None:
                return None
            proof = proof.merged(best)
            # počty: přesná tvrzení
            if qt in qr.counts:
                fc = None
                for ft in fr.terms:
                    if ft in fr.counts and self.match_term(qt, qr.quant, ft, fr.quant, role=qr.name) is not None:
                        fc = fr.counts[ft]
                if fc is None:
                    return None
                if fc != qr.counts[qt]:
                    proof.steps.append(f"počet {fc} ≠ {qr.counts[qt]}")
                    proof.defaults.append("__count_mismatch__")
        return proof

    def match(self, q: Statement, f: Statement, *, depth: int = 0) -> Proof | None:
        """Shoda dotazu `q` s výrokem `f` (bez ohledu na polaritu — tu řeší volající)."""
        step = self.same_pred(q.pred, f.pred)
        if step is None:
            return None
        if f.mood == "question":
            return None
        proof = Proof([f.id], [step] if step else [], list(f.defaults), f.grade)
        # modalita
        if q.modality is None and f.modality in ("možnost", "vůle", "fáze"):
            proof.steps.append(f"výrok je jen {f.modality}")
            proof.defaults.append("__modal__")
        for qr in q.roles:
            if qr.wh:
                continue
            fr = f.role(qr.name)
            if fr is None:
                # nested v dotazu × nested ve výroku se neporovnává (mez v1)
                if qr.nested is not None or not qr.terms:
                    continue
                return None
            p = self.match_role(qr, fr, pred=f.pred)
            if p is None:
                return None
            proof = proof.merged(p)
        return proof

    # ---- jádrové dotazy (kopula) ---------------------------------------------

    def kernel_verdict(self, q: Statement) -> Verdict | None:
        m = self.m
        subj, obj = q.role("kdo"), (q.role("co") or q.role("kde"))
        if not subj or not obj or not subj.terms or not obj.terms or obj.wh:
            return None
        proofs: list[Proof] = []
        counter: list[Proof] = []
        for s in subj.terms:
            for o in obj.terms:
                sk = self._kind(s)
                if q.kernel == "within" or (q.kernel is None and self._kind(o) == "place" and q.role("kde") is not None):
                    w = m.within_star(s, o)
                    if w is not None:
                        proofs.append(Proof(w, [f"{m.node(s).label()} ⊆ {m.node(o).label()}"], grade=self._grade_of(w)))
                    continue
                if sk in ("entity", "place"):
                    mem = m.member_star(s, o)
                    if mem is not None:
                        proofs.append(Proof(mem, [f"{m.node(s).label()} ∈ {m.node(o).label()}"], grade=self._grade_of(mem)))
                        continue
                    # disjunktnost: s ∈ H, H ∦ o
                    for st in m.active():
                        st_kdo, st_co = st.role("kdo"), st.role("co")
                        if st.kernel == "member" and not st.neg and st_kdo and s in st_kdo.terms:
                            for h in (st_co.terms if st_co else []):
                                d = m.disjoint(h, o)
                                if d is not None:
                                    counter.append(Proof([st.id, d], [f"{m.node(s).label()} ∈ {m.node(h).label()}", f"{m.node(h).label()} ∦ {m.node(o).label()}"], grade="derived"))
                elif sk == "group":
                    sub = m.subset_star(s, o)
                    if sub is not None:
                        proofs.append(Proof(sub, [f"{m.node(s).label()} ⊆ {m.node(o).label()}"], grade=self._grade_of(sub)))
                        continue
                    d = m.disjoint(s, o)
                    if d is not None:
                        counter.append(Proof([d], [f"{m.node(s).label()} ∦ {m.node(o).label()}"], grade="derived"))
        if proofs and counter:
            return Verdict("KONFLIKT", proofs, counter)
        if proofs:
            return Verdict("ANO", proofs)
        if counter:
            return Verdict("NE", [], counter)
        return None

    def _grade_of(self, sids: list[str]) -> Grade:
        g: Grade = "said"
        for s in sids:
            st = self.m.statements.get(s)
            if st is not None:
                g = weakest(g, st.grade)
        return g if len(sids) <= 1 else weakest(g, "derived")

    # ---- ano/ne --------------------------------------------------------------

    def evaluate(self, q: Statement, *, depth: int = 0) -> Verdict:
        m = self.m
        pos: list[Proof] = []
        neg: list[Proof] = []
        modal: list[Proof] = []
        near: list[str] = []
        if q.kernel in ("member", "subset", "within", "same_as") or (q.pred == "být" and q.role("kde")):
            kv = self.kernel_verdict(q)
            if kv is not None and kv.value in ("ANO", "NE", "KONFLIKT"):
                # doplň ještě přímé výroky (např. `být` s dalšími rolemi)
                if kv.value == "ANO":
                    return kv
                neg.extend(kv.counter)
                pos.extend(kv.proofs)
        candidates = [f for f in m.active() if self.same_pred(q.pred, f.pred) is not None]
        for f in candidates:
            p = self.match(q, f, depth=depth)
            if p is None:
                if self._near(q, f):
                    near.append(f.id)
                continue
            if "__count_mismatch__" in p.defaults:
                p.defaults.remove("__count_mismatch__")
                neg.append(p)
                continue
            if "__modal__" in p.defaults:
                p.defaults.remove("__modal__")
                modal.append(p)
                continue
            (neg if f.neg else pos).append(p)
        # pravidla (můstky)
        if depth == 0:
            for rule in m.rules:
                if self.same_pred(rule.dst_pred, q.pred) is None:
                    continue
                inv = {v: k for k, v in rule.role_map.items()}
                q2 = Statement("", rule.src_pred, q.kind, roles=[Role(inv.get(r.name, r.name), list(r.terms), r.quant, r.authority, r.surface, wh=r.wh, wh_kind=r.wh_kind, counts=dict(r.counts)) for r in q.roles], mood="question")
                v2 = self.evaluate(q2, depth=1)
                for p in v2.proofs:
                    p.steps.append(f"pravidlo {rule.id}: {rule.src_pred}→{rule.dst_pred}")
                    p.grade = weakest(p.grade, "derived")
                    pos.append(p)
                for p in v2.counter:
                    neg.append(p)
        if pos and neg:
            return Verdict("KONFLIKT", pos, neg, near=near)
        if pos:
            return Verdict("ANO", pos, near=near)
        if neg:
            return Verdict("NE", [], neg, near=near)
        if modal:
            return Verdict("MOŽNÁ", modal, near=near)
        return Verdict("NEVÍM", missing=self._missing(q, near), near=near)

    def _near(self, q: Statement, f: Statement) -> bool:
        """Blízký výrok: týž predikát a aspoň jeden term dotazu sedí."""
        for qr in q.roles:
            fr = f.role(qr.name)
            if fr is None or qr.wh:
                continue
            for qt in qr.terms:
                for ft in fr.terms:
                    if self.match_term(qt, qr.quant, ft, fr.quant, role=qr.name) is not None:
                        return True
        return False

    def _missing(self, q: Statement, near: list[str]) -> list[str]:
        m = self.m
        out: list[str] = []
        for r in q.roles:
            for t in r.terms:
                if not m.statements_about(t) and self._kind(t) in ("entity", "place"):
                    out.append(f"o {m.node(t).label()} nevím nic")
        if not near and not out and q.pred:
            preds = {s.pred for s in m.active() if s.pred}
            if not any(self.same_pred(q.pred, p) is not None for p in preds):
                out.append(f"o „{q.pred}“ nemám žádný výrok")
        return out

    # ---- wh --------------------------------------------------------------------

    def enumerate(self, q: Statement) -> Verdict:
        m = self.m
        hole = next((r for r in q.roles if r.wh), None)
        if hole is None:
            return self.evaluate(q)
        # definice: „Kdo/co je X?“
        if q.pred == "být" and hole.name in ("co", "jaký") and q.role("kdo") and q.role("kdo").terms:  # type: ignore[union-attr]
            v = self.describe_verdict(q.role("kdo").terms[0], hole)  # type: ignore[union-attr]
            if hole.name == "co" and v.fillers:
                # „Co je X?“ → třídy mají přednost; vlastnosti jen když třídy nejsou
                classes = [(t, p) for t, p in v.fillers if self._kind(t) == "group" and any(
                    self.m.statements[s].kernel in ("member", "subset") for s in p.statements)]
                if classes:
                    v.fillers = classes
                    v.proofs = [p for _, p in classes]
            return v
        fillers: list[tuple[str, Proof]] = []
        seen: set[str] = set()
        near: list[str] = []
        matched: list[tuple[Statement, Proof]] = []
        for f in m.active():
            if self.same_pred(q.pred, f.pred) is None or f.neg:
                continue
            p = self.match(q, f)
            if p is None:
                if self._near(q, f):
                    near.append(f.id)
                continue
            matched.append((f, p))
            fr = f.role(hole.name)
            if fr is None or (not fr.terms and not fr.nested):
                # díra bez výplně ve výroku: dotaz na roli, kterou výrok nemá
                if self._near(q, f):
                    near.append(f.id)
                continue
            if hole.wh_kind == "count":
                for t in fr.terms:
                    if t in fr.counts:
                        key = f"count:{fr.counts[t]}"
                        if key not in seen:
                            seen.add(key)
                            fillers.append((key, p))
                continue
            for t in fr.terms:
                if t not in seen:
                    seen.add(t)
                    fillers.append((t, p))
            if fr.nested and fr.nested not in seen:
                seen.add(fr.nested)
                fillers.append((fr.nested, p))
        # pravidla
        for rule in m.rules:
            if self.same_pred(rule.dst_pred, q.pred) is None:
                continue
            inv = {v: k for k, v in rule.role_map.items()}
            q2 = Statement("", rule.src_pred, q.kind, roles=[Role(inv.get(r.name, r.name), list(r.terms), r.quant, r.authority, r.surface, wh=r.wh, wh_kind=r.wh_kind) for r in q.roles], mood="question")
            v2 = self.enumerate(q2) if q2.pred != q.pred else Verdict("NEVÍM")
            for t, p in v2.fillers:
                if t not in seen:
                    seen.add(t)
                    p.steps.append(f"pravidlo {rule.id}: {rule.src_pred}→{rule.dst_pred}")
                    fillers.append((t, p))
        # rodina rolí: „kde“ bez `kde` → sourozenci (kam/odkud/kudy) s přiznáním; totéž čas
        family = PLACE_FAMILY if hole.name in PLACE_FAMILY else TIME_FAMILY if hole.name in TIME_FAMILY else ()
        if not fillers and family and hole.wh_kind == "filler":
            for f, p in matched:
                for sib in family:
                    if sib == hole.name:
                        continue
                    fr = f.role(sib)
                    if fr is None:
                        continue
                    for t in fr.terms:
                        # jen výplně správného druhu: čas pro čas, místo pro místo
                        k = self._kind(t)
                        if family is TIME_FAMILY and k != "time":
                            continue
                        if family is PLACE_FAMILY and not (k == "place" or (k == "group" and m.nodes[t].lemma in PLACE_NOUNS)):
                            continue
                        if t not in seen:
                            seen.add(t)
                            p2 = Proof(list(p.statements), list(p.steps) + [f"role „{sib}“ — ptal ses „{hole.name}“"], list(p.defaults), p.grade)
                            fillers.append((t, p2))
        # místo uvnitř výplně: „gymnázium v Broumově“ → nmod:v+Loc(gymnázium, Broumov)
        if not fillers and hole.name in PLACE_FAMILY and hole.wh_kind == "filler":
            for f, p in matched:
                for r in f.roles:
                    for t in r.terms:
                        for st in m.statements_about(t):
                            if st.kind != "nmod" or st.status != "active":
                                continue
                            kdo, co = st.role("kdo"), st.role("co")
                            if not (kdo and t in kdo.terms and co):
                                continue
                            for pl in co.terms:
                                if self._kind(pl) == "place" and pl not in seen:
                                    seen.add(pl)
                                    p2 = Proof(list(p.statements) + [st.id], list(p.steps) + [f"místo uvnitř: {m.node(t).label()} — {st.pred}"], list(p.defaults), weakest(p.grade, "derived"))
                                    fillers.append((pl, p2))
        if fillers:
            fillers.sort(key=lambda x: (-GRADE_RANK[x[1].grade], len(x[1].statements)))
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers, near=near)
        return Verdict("NEVÍM", missing=self._missing(q, near), near=near)

    def describe(self, node_id: str) -> list[Statement]:
        """Okolí uzlu: členství/podmnožiny, `být`, výroky s uzlem v podmětu, ostatní."""
        m = self.m
        about = m.statements_about(node_id)
        def rank(s: Statement) -> tuple[int, int]:
            kdo = s.role("kdo")
            is_subj = bool(kdo and node_id in kdo.terms)
            if s.kernel in ("member", "subset") and is_subj:
                return (0, -GRADE_RANK[s.grade])
            if s.pred == "být" and is_subj:
                return (1, -GRADE_RANK[s.grade])
            if is_subj:
                return (2, -GRADE_RANK[s.grade])
            return (3, -GRADE_RANK[s.grade])
        return sorted(about, key=rank)

    def describe_verdict(self, node_id: str, hole: Role) -> Verdict:
        m = self.m
        fillers: list[tuple[str, Proof]] = []
        seen: set[str] = set()
        for s in self.describe(node_id):
            kdo = s.role("kdo")
            if not (kdo and node_id in kdo.terms) or s.neg:
                continue
            if hole.name != "jaký" and (s.kernel in ("member", "subset") or (s.pred == "být" and s.role("co"))):
                co = s.role("co")
                for t in (co.terms if co else []):
                    if t not in seen:
                        seen.add(t)
                        fillers.append((t, Proof([s.id], [], list(s.defaults), s.grade)))
            if s.pred == "být" and s.role("jaký") and hole.name in ("jaký", "co"):
                for t in s.role("jaký").terms:  # type: ignore[union-attr]
                    if t not in seen:
                        seen.add(t)
                        fillers.append((t, Proof([s.id], [], list(s.defaults), s.grade)))
        if fillers:
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers)
        near = [s.id for s in self.describe(node_id)]
        return Verdict("NEVÍM", near=near, missing=[] if near else [f"o {m.node(node_id).label()} nevím nic"])


def evaluate(memory: Memory, q: Statement) -> Verdict:
    return Evaluator(memory).evaluate(q)


def enumerate_(memory: Memory, q: Statement) -> Verdict:
    return Evaluator(memory).enumerate(q)


def describe(memory: Memory, node_id: str) -> list[Statement]:
    return Evaluator(memory).describe(node_id)
