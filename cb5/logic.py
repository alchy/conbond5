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

from cb5.chronos import MONTHS, TimeSpec, overlap as time_overlap
from cb5.defaults import ADVERB_QUANTITY, COMPARATIVES_SEED, LOCATIVE_SURFACES, PLACE_NOUNS, QUANTITY_BOUNDS, RELATION_CONVERSE, RELATION_GENDER, synonym_class
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
PERSON_FAMILY = ("s_kým", "co", "komu", "kdo")


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
            return Proof(same, [f"{m.label(q)} = {m.label(f)}"])
        qk, fk = self._kind(q), self._kind(f)
        # místa: kde/kam/odkud dotazu obsahuje místo výroku
        if qk == "place" and fk == "place":
            w = m.within_star(f, q)
            if w is not None:
                return Proof(w, [f"{m.label(f)} ⊆ {m.label(q)} (místo)"], grade="derived")
            return None
        if qk == "time" and fk == "time":
            if m.time_within(f, q):
                return Proof([], [f"{m.label(f)} je v {m.label(q)}"])
            return None
        # entita / instance dotazu × group výroku
        if qk in ("entity", "place") and fk == "group":
            if fquant == "∀":
                mem = m.member_star(q, f)
                if mem is not None:
                    return Proof(mem, [f"{m.label(q)} ∈ {m.label(f)} (∀ se přenáší dolů)"], grade="derived")
            return None
        # group dotazu × group výroku
        if qk == "group" and fk == "group":
            if fquant == "∀":
                sub = m.subset_star(q, f)
                if sub is not None:
                    return Proof(sub, [f"{m.label(q)} ⊆ {m.label(f)} (∀ se přenáší dolů)"], grade="derived" if sub else "read")
                return None
            # ∃ / · výrok: dotaz sedí, když je výrok stejně nebo víc konkrétní
            sub = m.subset_star(f, q)
            if sub is not None and qquant != "∀":
                return Proof(sub, [f"{m.label(f)} ⊆ {m.label(q)}"] if sub else [], grade="derived" if sub else "read")
            return None
        # group dotazu × instance výroku („Napsal román?“ × r1 ∈ román)
        if qk == "group" and fk in ("entity", "place"):
            if qquant == "∀":
                return None
            mem = m.member_star(f, q)
            if mem is not None:
                return Proof(mem, [f"{m.label(f)} ∈ {m.label(q)}"], grade="derived")
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

    # ---- vztahová jména: otec⟨Petr⟩, tchán⟨Jana⟩ = otec⟨manžel⟨Jana⟩⟩ ------------------------

    def rel_members(self, lemma: str, target: str, depth: int = 0) -> list[tuple[str, Proof]]:
        """Kdo je `lemma` uzlu `target`: přímé členství v group lemma⟨target⟩, inverze
        (target ∈ manželka⟨Z⟩ ⇒ Z ∈ manžel⟨target⟩) a naučené definice (tchán = otec∘manžel).
        Každý nález nese důkaz; hloubka řetězu omezena (definice se rozvíjejí rekurzivně)."""
        m = self.m
        out: list[tuple[str, Proof]] = []
        seen: set[str] = set()
        if depth > 4:
            return out
        # 1) přímo
        g = m.find_group(lemma, (), f"Gen:{target}")
        if g is not None:
            for e, path in m.known_members(g.id):
                if e not in seen:
                    seen.add(e)
                    out.append((e, Proof(path, [f"{m.label(e)} ∈ {m.label(g.id)}"], [], self._grade_of(path))))
        # 2) inverze: target ∈ R'⟨Z⟩, R' inverzní k lemma ⇒ Z ∈ lemma⟨target⟩ (rod Z podle lemma)
        need = RELATION_GENDER.get(lemma)
        converses = list(RELATION_CONVERSE.get(lemma, ())) + [c for c in m.learned.get("inverse", {}).get(lemma, []) if c not in RELATION_CONVERSE.get(lemma, ())]
        for conv in converses:
            for st in m.statements_about(target):
                if st.kernel != "member" or st.neg or st.status != "active":
                    continue
                kdo, co = st.role("kdo"), st.role("co")
                if not (kdo and target in kdo.terms and co):
                    continue
                for gid in co.terms:
                    gn = m.nodes.get(gid)
                    if gn is None or gn.kind != "group" or gn.lemma != conv or not gn.rel:
                        continue
                    z = gn.rel.split(":", 1)[1]
                    zn = m.nodes.get(z)
                    if zn is None or (need and zn.gender and need not in zn.gender.split(",")):
                        continue
                    if z not in seen:
                        seen.add(z)
                        out.append((z, Proof([st.id], [f"{m.label(target)} ∈ {m.label(gid)} ⇒ {m.label(z)} ∈ {lemma}⟨{m.label(target)}⟩ (inverze {conv}↔{lemma})"], ["inverze vztahu (osivo)"], "derived")))
        # 3) definice: lemma = R1∘R2∘… → R2⟨target⟩ → R1⟨…⟩
        for chain in m.learned.get("rel_defs", {}).get(lemma, []):
            frontier: list[tuple[str, Proof]] = [(target, Proof())]
            for r in reversed(chain):
                nxt: list[tuple[str, Proof]] = []
                for node, pr in frontier:
                    for e, pe in self.rel_members(r, node, depth + 1):
                        nxt.append((e, pr.merged(pe)))
                frontier = nxt
                if not frontier:
                    break
            for e, pr in frontier:
                if e not in seen:
                    seen.add(e)
                    pr.steps.append(f"{lemma} = {'∘'.join(chain)} (naučená definice)")
                    pr.grade = "derived"
                    out.append((e, pr))
        return out

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
                        proofs.append(Proof(w, [f"{m.label(s)} ⊆ {m.label(o)}"], grade=self._grade_of(w)))
                    continue
                if sk in ("entity", "place"):
                    mem = m.member_star(s, o)
                    if mem is not None:
                        proofs.append(Proof(mem, [f"{m.label(s)} ∈ {m.label(o)}"], grade=self._grade_of(mem)))
                        continue
                    on = m.nodes.get(o)
                    if on is not None and on.kind == "group" and on.rel and on.rel.startswith("Gen:"):
                        hit = [pr for e, pr in self.rel_members(on.lemma, on.rel.split(":", 1)[1]) if e == s]
                        if hit:
                            proofs.append(hit[0])
                            continue
                    # disjunktnost: s ∈ H, H ∦ o
                    for st in m.active():
                        st_kdo, st_co = st.role("kdo"), st.role("co")
                        if st.kernel == "member" and not st.neg and st_kdo and s in st_kdo.terms:
                            for h in (st_co.terms if st_co else []):
                                d = m.disjoint(h, o)
                                if d is not None:
                                    counter.append(Proof([st.id, d], [f"{m.label(s)} ∈ {m.label(h)}", f"{m.label(h)} ∦ {m.label(o)}"], grade="derived"))
                elif sk == "group":
                    sub = m.subset_star(s, o)
                    if sub is not None:
                        proofs.append(Proof(sub, [f"{m.label(s)} ⊆ {m.label(o)}"], grade=self._grade_of(sub)))
                        continue
                    d = m.disjoint(s, o)
                    if d is not None:
                        counter.append(Proof([d], [f"{m.label(s)} ∦ {m.label(o)}"], grade="derived"))
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

    def comparative(self, lemma: str) -> tuple[str, str, str] | None:
        """Srovnávací slovo → (predikát, role, směr): naučené z dialogu má přednost před osivem."""
        learned = self.m.learned.get("comparatives", {})
        if lemma in learned:
            d = learned[lemma]
            return (str(d["pred"]), str(d["role"]), str(d["dir"]))
        return COMPARATIVES_SEED.get(lemma)

    def _value(self, node_id: str, pred: str, role: str) -> tuple[object, str] | None:
        """Hodnota role `role` výroku `pred` o uzlu: (id času | číslo, id výroku)."""
        for st in self.m.statements_about(node_id):
            if not st.pred or self.same_pred(st.pred, pred) is None or st.neg:
                continue
            kdo = st.role("kdo")
            if not (kdo and node_id in kdo.terms):
                continue
            named = st.role(role) if role != "*" else None
            roles = [named] if named is not None else list(st.roles)  # role nesedí na jméno → kterákoli s hodnotou
            for r in roles:
                if r is None:
                    continue
                for t in r.terms:
                    if self._kind(t) == "time":
                        return t, st.id
                    if t in r.counts:
                        return r.counts[t], st.id
        return None

    def _birth(self, node_id: str) -> tuple[str, str] | None:
        v = self._value(node_id, "narodit_se", "kdy")
        return (str(v[0]), v[1]) if v and isinstance(v[0], str) else None

    def compare(self, q: Statement) -> Verdict | None:
        """Srovnání věku z narození: „Je Pavla starší než Jindřich?“, „Kdo je starší, A nebo B?“."""
        m = self.m
        adj = q.role("jaký")
        if q.pred != "srovnání" or not adj or not adj.terms:
            return None
        lemma = m.nodes[adj.terms[0]].lemma
        spec = self.comparative(lemma)
        if spec is None:
            known_words = sorted(set(COMPARATIVES_SEED) | set(m.learned.get("comparatives", {})))
            word = (m.nodes[adj.terms[0]].names or [lemma])[0]
            return Verdict("NEVÍM", missing=[f"srovnání „{word}“ neumím — nauč mě větou „{word.capitalize()} je ten, kdo …“ nebo `!srovnání {word} = <predikát> <role> <dřív|později|víc|míň>` (znám: {', '.join(known_words)})"])
        pred, role, direction = spec
        DIR = {"earlier": "dřívější", "later": "pozdější", "more": "větší", "less": "menší"}
        note = f"{lemma}: {DIR[direction]} {pred}({role})"
        src = "naučeno dialogem" if lemma in m.learned.get("comparatives", {}) else "osivo"

        def key(v: object) -> tuple[int, int, int] | float:
            if isinstance(v, str):
                n = m.nodes.get(v)
                return (n.time.start or (0, 0, 0)) if n and n.time else (0, 0, 0)
            return float(v)  # type: ignore[arg-type]

        def show(v: object) -> str:
            return m.label(v) if isinstance(v, str) else str(v)

        kdo, than, cands = q.role("kdo"), q.role("než"), q.role("z")
        if kdo and kdo.wh and cands and cands.terms:
            vals = [(c, self._value(c, pred, role)) for c in cands.terms]
            known = [(c, v) for c, v in vals if v]
            missing = [f"chybí {pred}({role}): {m.label(c)}" for c, v in vals if not v]
            if len(known) < 2:
                return Verdict("NEVÍM", missing=missing or ["málo kandidátů se známou hodnotou"])
            known.sort(key=lambda cv: key(cv[1][0]))
            pick = known[0] if direction in ("earlier", "less") else known[-1]
            steps = [f"{m.label(c)}: {show(v[0])}" for c, v in known] + [note]
            proof = Proof([v[1] for _, v in known], steps, [f"srovnání ({src})"], "derived")
            return Verdict("ANO", [proof], fillers=[(pick[0], proof)], missing=missing)
        if kdo and kdo.terms and than and than.terms:
            a, b = kdo.terms[0], than.terms[0]
            va, vb = self._value(a, pred, role), self._value(b, pred, role)
            missing = [f"chybí {pred}({role}): {m.label(x)}" for x, vx in ((a, va), (b, vb)) if not vx]
            if not va or not vb:
                return Verdict("NEVÍM", missing=missing)
            ka, kb = key(va[0]), key(vb[0])
            if isinstance(va[0], str) and isinstance(vb[0], str):
                before = m.before(va[0], vb[0])
                after = m.before(vb[0], va[0])
                if before is None and after is None:
                    return Verdict("NEVÍM", missing=["hodnoty nejdou srovnat (bez roku)"])
                truth = bool(before) if direction == "earlier" else bool(after)
            else:
                truth = (ka < kb) if direction in ("earlier", "less") else (ka > kb)  # type: ignore[operator]
            proof = Proof([va[1], vb[1]], [f"{m.label(a)}: {show(va[0])}", f"{m.label(b)}: {show(vb[0])}", note], [f"srovnání ({src})"], "derived")
            return Verdict("ANO" if truth else "NE", [proof] if truth else [], [] if truth else [proof])
        return None

    # ---- binární pravidla: Q(A,B) ⇐ TEST(hodnota u A, hodnota u B) ------------------------

    def _participants(self, q: Statement) -> list[str]:
        """Účastníci binárního dotazu: dva termy v `kdo` („Magdalena a Superman“), nebo
        první z kdo/co a druhý z do+Gen/kam/s_kým/než/komu („telefon do kapsy“)."""
        kdo = q.role("kdo")
        if kdo and len(kdo.terms) >= 2:
            return kdo.terms[:2]
        first = next((r.terms[0] for r in q.roles if r.name in ("kdo", "co") and r.terms), None)
        second = next((r.terms[0] for r in q.roles if r.name in ("do+Gen", "kam", "s_kým", "než", "komu", "do", "k+Dat", "na+Acc") and r.terms), None)
        return [x for x in (first, second) if x]

    def _quantity_of(self, node_id: str, qname: str) -> tuple[int, str, str] | None:
        """(hodnota, jednotka‑label, id výroku) veličiny `qname` u uzlu — z role téhož jména,
        nebo z `být(jaký: adj)` + míry; přes ∀‑třídu uzlu, když sám hodnotu nemá."""
        m = self.m
        cands = [node_id]
        n = m.nodes.get(node_id)
        if n is not None and n.kind == "entity":
            for st in m.statements_about(node_id):
                if st.kernel == "member" and not st.neg:
                    co = st.role("co")
                    if co:
                        cands.extend(co.terms)
        for x in cands:
            for st in m.statements_about(x):
                if st.status != "active" or st.neg:
                    continue
                kdo = st.role("kdo")
                if not (kdo and x in kdo.terms):
                    continue
                r = st.role(qname)
                if r is None and st.pred == "být" and st.role("jaký"):
                    jaky = st.role("jaký")
                    if jaky and any(ADVERB_QUANTITY.get(m.nodes[t].lemma) == qname for t in jaky.terms if t in m.nodes):
                        r = next((rr for rr in st.roles if rr.counts), None)
                if r is None:
                    continue
                for t in r.terms:
                    if t in r.counts:
                        return r.counts[t], m.label(t), st.id
        return None

    def _interval_of(self, node_id: str, pred: str) -> tuple[str, str] | None:
        """(id času, id výroku) role `kdy` děje `pred` o uzlu."""
        v = self._value(node_id, pred, "kdy")
        return (str(v[0]), v[1]) if v and isinstance(v[0], str) else None

    def binary_rule(self, q: Statement) -> Verdict | None:
        """Naučené binární pravidlo pro predikát dotazu (šablony `překryv`, `porovnání`)."""
        m = self.m
        rules = m.learned.get("binary", {})
        spec = None
        for pred, r in rules.items():
            if self.same_pred(q.pred, pred) is not None:
                spec = r
                break
        if spec is None:
            return None
        parts = self._participants(q)
        if len(parts) < 2:
            return None
        a, b = parts[0], parts[1]
        if spec["test"] == "překryv":
            ia, ib = self._interval_of(a, spec["source"]), self._interval_of(b, spec["source"])
            missing = [f"chybí {spec['source']}(kdy): {m.label(x)}" for x, i in ((a, ia), (b, ib)) if not i]
            if not ia or not ib:
                return Verdict("NEVÍM", missing=missing)
            na, nb = m.nodes[ia[0]].time, m.nodes[ib[0]].time
            ov = time_overlap(na, nb) if na and nb else None
            if ov is None:
                return Verdict("NEVÍM", missing=["časy nejdou srovnat"])
            proof = Proof([ia[1], ib[1]], [f"{m.label(a)}: {m.label(ia[0])}", f"{m.label(b)}: {m.label(ib[0])}",
                                          f"{q.pred} ⇐ překryv intervalů {spec['source']}(kdy) (naučené pravidlo)"], ["binární pravidlo (šablona překryv)"], "derived")
            return Verdict("ANO" if ov else "NE", [proof] if ov else [], [] if ov else [proof])
        if spec["test"] in ("<=", ">=", "<", ">", "="):
            qnames = [x for x in str(spec["source"]).split(",") if x]
            proofs: list[Proof] = []
            truth = True
            missing = []
            for qn in qnames:
                va, vb = self._quantity_of(a, qn), self._quantity_of(b, qn)
                if not va or not vb:
                    missing.extend(f"chybí {qn}: {m.label(x)}" for x, v in ((a, va), (b, vb)) if not v)
                    continue
                op = spec["test"]
                res = {"<=": va[0] <= vb[0], ">=": va[0] >= vb[0], "<": va[0] < vb[0], ">": va[0] > vb[0], "=": va[0] == vb[0]}[op]
                truth = truth and res
                proofs.append(Proof([va[2], vb[2]], [f"{qn}: {m.label(a)} = {va[0]} {va[1]}, {m.label(b)} = {vb[0]} {vb[1]} → {va[0]} {op} {vb[0]}: {'platí' if res else 'neplatí'}"], ["binární pravidlo (šablona porovnání)"], "derived"))
            if not proofs:
                return Verdict("NEVÍM", missing=missing)
            for pr in proofs:
                pr.steps.append(f"{q.pred} ⇐ {spec['source']} {spec['test']} (naučené pravidlo)")
            return Verdict("ANO" if truth else "NE", proofs if truth else [], [] if truth else proofs, missing=missing)
        return None

    def evaluate(self, q: Statement, *, depth: int = 0) -> Verdict:
        m = self.m
        if depth == 0:
            br = self.binary_rule(q)
            if br is not None:
                return br
        if q.pred == "srovnání":
            direct = self._direct(q)
            if direct is not None:
                return direct
            cv = self.compare(q)
            if cv is not None:
                return cv
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
        # užší shoda (otázka o třídě, výrok o její ∀‑podtřídě): ANO s přiznáním
        if not pos and not neg:
            for f in candidates:
                if f.neg or f.mood == "question":
                    continue
                p = self._match_narrower(q, f)
                if p is not None and "__count_mismatch__" not in p.defaults:
                    if q.modality is None and f.modality in ("možnost", "vůle", "fáze"):
                        p.steps.append(f"výrok je jen {f.modality}")
                        modal.append(p)
                    else:
                        pos.append(p)
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

    def _match_narrower(self, q: Statement, f: Statement) -> Proof | None:
        """Shoda, kde term dotazu je ŠIRŠÍ třída než ∀‑term výroku (kočka × kočka[dospělý]).
        Odpověď pak platí jen o té užší třídě — důkaz to říká."""
        proof = Proof([f.id], [], list(f.defaults), f.grade)
        narrowed_once = False
        for qr in q.roles:
            if qr.wh:
                continue
            fr = f.role(qr.name)
            if fr is None:
                if not qr.terms:
                    continue
                return None
            p = self.match_role(qr, fr, pred=f.pred)
            if p is not None:
                proof = proof.merged(p)
                continue
            ok = False
            for qt in qr.terms:
                for ft in fr.terms:
                    if self._kind(qt) == "group" and self._kind(ft) == "group" and fr.quant == "∀":
                        sub = self.m.subset_star(ft, qt)
                        if sub is not None:
                            proof = proof.merged(Proof(sub, [f"platí o užší třídě {self.m.label(ft)} ⊆ {self.m.label(qt)}"], [], "derived"))
                            ok = narrowed_once = True
            if not ok:
                return None
        return proof if narrowed_once else None

    def _direct(self, q: Statement) -> Verdict | None:
        """Přímý výrok téhož tvaru (řekls „Pavla je mladší než Jindřich“)."""
        pos = [self.match(q, f) for f in self.m.by_pred("srovnání") if not f.neg]
        proofs = [p for p in pos if p is not None]
        return Verdict("ANO", proofs) if proofs else None

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
                    out.append(f"o {m.label(t)} nevím nic")
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
        if q.pred == "srovnání":
            cv = self.compare(q)
            if cv is not None:
                return cv
        # VELIČINA: „Jak rychle může jet automobil po dálnici?“ / „Jak vysoká je Sněžka?“
        if hole.wh_kind == "value":
            v = self.quantity(q, hole)
            if v is not None:
                return v
        # „Co víš o X?“ / „Jaké druhy X znáš?“ / „Jaké znáš spisovatele?“ → co paměť drží
        if q.pred in ("vědět", "znát", "pamatovat_si", "pamatovat"):
            about = q.role("o_čem") or q.role("co") or q.role("jaký")
            targets = [t for r in (about,) if r for t in r.terms]
            if targets:
                t0 = targets[0]
                if self._kind(t0) == "group" and (about is not None and about.wh):
                    # výčet známých prvků / podtříd třídy — otevřený svět: „znám tyhle, jestli všechny, nevím“
                    v = self.describe_verdict(t0, Role("co", wh=True))
                    if v.fillers:
                        for _, pr in v.fillers:
                            pr.steps.append("výčet známého — jestli je to všechno, nevím")
                        return v
                    return Verdict("NEVÍM", missing=[f"o třídě {m.label(t0)} neznám žádný prvek ani podtřídu"])
                items = [(st.id, Proof([st.id], [], list(st.defaults), st.grade)) for st in self.describe(t0) if not st.derived_from]
                if items:
                    return Verdict("ANO", [p for _, p in items], fillers=items)
                return Verdict("NEVÍM", missing=[f"o {m.label(t0)} nevím nic"])
        # „Co dělá X?“ / „Co umí X?“ → děje, kde je X podmětem (i přes ∀ nadtřídu)
        if q.pred in ("dělat", "činit", "umět", "dokázat", "provádět") and hole.name == "co" and q.role("kdo") and q.role("kdo").terms:  # type: ignore[union-attr]
            subj = q.role("kdo")
            acts: list[tuple[str, Proof]] = []
            for f in m.active():
                if f.kind != "verb" or f.pred in (None, "být", "věk", "srovnání", "definice", "dělat") or f.mood == "question" or f.derived_from:
                    continue
                fk = f.role("kdo")
                if not fk or not fk.terms:
                    continue
                matched_role = self.match_role(subj, fk, pred=f.pred)  # type: ignore[arg-type]
                if matched_role is None:
                    continue
                proof = matched_role.merged(Proof([f.id], [], list(f.defaults), f.grade))
                if q.pred in ("umět", "dokázat") and f.modality is None:
                    proof.steps.append("děj, ne schopnost — beru jako doklad")
                acts.append((f.id, proof))
            if acts:
                return Verdict("ANO", [p for _, p in acts], fillers=acts)
        # definice: „Kdo/co je X?“
        if q.pred == "být" and hole.name in ("co", "jaký") and q.role("kdo") and q.role("kdo").terms:  # type: ignore[union-attr]
            v = self.describe_verdict(q.role("kdo").terms[0], hole)  # type: ignore[union-attr]
            if hole.name == "co" and v.fillers:
                # „Co je X?“ → třídy mají přednost; vlastnosti jen když třídy nejsou
                classes = [(t, p) for t, p in v.fillers if self._kind(t) == "group" and any(
                    s in self.m.statements and self.m.statements[s].kernel in ("member", "subset") for s in p.statements)]
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
            same_named = [r for r in f.roles if r.name == hole.name]
            if len(same_named) > 1 and hole.wh_kind == "filler":
                # „Vrtačka je ve sklepě na poličce.“ — dvě role kde: obě jsou odpověď
                merged = Role(hole.name, [t for r in same_named for t in r.terms], same_named[0].quant, same_named[0].authority, same_named[0].surface)
                fr = merged
            if hole.wh_kind == "count" and (fr is None or not fr.counts):
                # „Kolik měří Vltava?“ — počet bez pojmenované role: kterákoli role s číslem;
                # „Kolik zubů má chrup?“ × „chrup se skládá z 30 zubů“ — role s TÝMŽ termem a číslem
                cands_r = [r for r in f.roles if r.counts and (not hole.terms or any(
                    self.match_term(qt, hole.quant, t, r.quant, role=hole.name) is not None for qt in hole.terms for t in r.terms))]
                fr = cands_r[0] if cands_r else fr
            if fr is None or (not fr.terms and not fr.nested):
                # díra bez výplně ve výroku: dotaz na roli, kterou výrok nemá
                if self._near(q, f):
                    near.append(f.id)
                continue
            if hole.wh_kind == "count":
                for t in fr.terms:
                    if t in fr.counts and (not hole.terms or any(self.match_term(qt, hole.quant, t, fr.quant, role=hole.name) is not None for qt in hole.terms)):
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
        family = PLACE_FAMILY if hole.name in PLACE_FAMILY else TIME_FAMILY if hole.name in TIME_FAMILY else PERSON_FAMILY if hole.name in ("s_kým", "komu") else ()
        if not fillers and family and hole.wh_kind == "filler":
            for f, p in matched:
                sibs = list(family) + ([r.name for r in f.roles if r.name in LOCATIVE_SURFACES] if family is PLACE_FAMILY else [])
                for sib in sibs:
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
                        if family is PLACE_FAMILY and not (k == "place" or (k == "group" and m.nodes[t].lemma in PLACE_NOUNS) or sib in LOCATIVE_SURFACES):
                            continue
                        if family is PERSON_FAMILY and (k != "entity" or t in q.term_ids()):
                            continue
                        if t not in seen:
                            seen.add(t)
                            p2 = Proof(list(p.statements), list(p.steps) + [f"role „{sib}“ — ptal ses „{hole.name}“"], list(p.defaults), p.grade)
                            fillers.append((t, p2))
        # užší shoda: otázka o kočce, výrok o dospělé kočce (∀ užší třída) — s přiznáním
        if not fillers and hole.wh_kind in ("filler", "count"):
            for f in m.active():
                if self.same_pred(q.pred, f.pred) is None or f.neg or f.id in {x.id for x, _ in matched}:
                    continue
                narrowed = self._match_narrower(q, f)
                if narrowed is None:
                    continue
                fr = f.role(hole.name)
                if fr is None or not fr.terms:
                    continue
                for t in fr.terms:
                    key = f"count:{fr.counts[t]}" if hole.wh_kind == "count" and t in fr.counts else t
                    if hole.wh_kind == "count" and (t not in fr.counts or (hole.terms and not any(self.match_term(qt, hole.quant, t, fr.quant, role=hole.name) is not None for qt in hole.terms))):
                        continue
                    if key not in seen:
                        seen.add(key)
                        fillers.append((key, narrowed))
        # místo uvnitř výplně: „gymnázium v Broumově“ → nmod:v+Loc(gymnázium, Broumov);
        # „strana Československa“ → zúžení group místem. Běží i tehdy, když sourozenecká
        # role dala jen povrchové místo (radnice) — obojí se nabídne, s přiznáním.
        # dokud mezi výplněmi není skutečné MÍSTO (jen „radnice“, „chalupa“, „bitva“), hledej
        # místo uvnitř výplně: „na radnici v Praze“, „na chalupě na Hrádečku“, „v bitvě u Zborova“
        weak_only = bool(fillers) and not any(self._kind(t) == "place" for t, _ in fillers)
        if (not fillers or weak_only) and hole.name in PLACE_FAMILY and hole.wh_kind == "filler":
            for f, p in matched:
                for r in f.roles:
                    for t in r.terms:
                        tn = m.nodes.get(t)
                        if tn is not None and tn.rel and ":" in tn.rel:
                            target = tn.rel.split(":", 1)[1]
                            if self._kind(target) == "place" and target not in seen:
                                seen.add(target)
                                fillers.append((target, Proof(list(p.statements), list(p.steps) + [f"místo uvnitř: {m.label(t)}"], list(p.defaults), weakest(p.grade, "derived"))))
                        for st in m.statements_about(t):
                            if st.kind != "nmod" or st.status != "active":
                                continue
                            kdo, co = st.role("kdo"), st.role("co")
                            if not (kdo and t in kdo.terms and co):
                                continue
                            for pl in co.terms:
                                if self._kind(pl) == "place" and pl not in seen:
                                    seen.add(pl)
                                    p2 = Proof(list(p.statements) + [st.id], list(p.steps) + [f"místo uvnitř: {m.label(t)} — {st.pred}"], list(p.defaults), weakest(p.grade, "derived"))
                                    fillers.append((pl, p2))
        # sloučení částečných časů TÉHOŽ děje: „v dubnu“ + „roku 1975“ → duben 1975 (přiznaně)
        if hole.name in TIME_FAMILY and hole.wh_kind == "filler" and len(fillers) >= 2:
            years = [(t, p) for t, p in fillers if not t.startswith("count:") and m.nodes[t].time and m.nodes[t].time.kind == "year"]  # type: ignore[union-attr]
            partial = [(t, p) for t, p in fillers if not t.startswith("count:") and m.nodes[t].time and (
                (m.nodes[t].time.kind == "name" and m.nodes[t].time.label in MONTHS) or (m.nodes[t].time.kind == "point" and (m.nodes[t].time.start or (0,))[0] == 0))]  # type: ignore[union-attr]
            if len(years) == 1 and len(partial) == 1:
                (ty, py), (tp, pp) = years[0], partial[0]
                yspec = m.nodes[ty].time
                pspec = m.nodes[tp].time
                assert yspec is not None and pspec is not None and yspec.start is not None
                yr = yspec.start[0]
                if pspec.kind == "name":
                    mo = MONTHS[pspec.label]
                    merged_spec = TimeSpec("point", f"{mo}/{yr}", (yr, mo, 0), (yr, mo, 0))
                else:
                    ms, ds = (pspec.start or (0, 0, 0))[1], (pspec.start or (0, 0, 0))[2]
                    merged_spec = TimeSpec("point", f"{ds}. {ms}. {yr}" if ds else f"{ms}/{yr}", (yr, ms, ds), (yr, ms, ds))
                node = m.ensure_time(merged_spec)
                proof = py.merged(pp)
                proof.steps.append(f"sloučeno ze dvou vět: {m.label(ty)} + {m.label(tp)} → {merged_spec.label} (týž děj, týž podmět)")
                proof.grade = "derived"
                fillers = [(node.id, proof)] + [f for f in fillers if f[0] not in (ty, tp)]
                seen.add(node.id)
        # tranzitivita umístění: prášek v krabici, krabice v koupelně → i koupelna (přiznaně, přes krabici)
        if hole.name == "kde" and hole.wh_kind == "filler" and fillers:
            frontier = [(t, p) for t, p in fillers if not t.startswith("count:")]
            hops = 0
            while frontier and hops < 3:
                nxt: list[tuple[str, Proof]] = []
                for t, p in frontier:
                    for st in m.statements_about(t):
                        if st.status != "active" or st.neg or st.pred != "být":
                            continue
                        kdo, kde = st.role("kdo"), st.role("kde")
                        if not (kdo and t in kdo.terms and kde):
                            continue
                        for z in kde.terms:
                            if z not in seen:
                                seen.add(z)
                                p2 = Proof(list(p.statements) + [st.id], list(p.steps) + [f"přes {m.label(t)}: {m.label(t)} je v {m.label(z)}"], list(p.defaults), "derived")
                                fillers.append((z, p2))
                                nxt.append((z, p2))
                frontier = nxt
                hops += 1
        # místo u jména podmětu: „Vulkán Ol Doinyo Lengai v Tanzanii je…“ → nmod:v+Loc(entita, Tanzanie)
        if not fillers and hole.name in PLACE_FAMILY and hole.wh_kind == "filler" and q.role("kdo"):
            for x in q.role("kdo").terms:  # type: ignore[union-attr]
                if self._kind(x) not in ("entity", "place"):
                    continue
                for st in m.statements_about(x):
                    surface = (st.pred or "").split(":", 1)[1] if (st.pred or "").startswith("nmod:") else ""
                    if st.kind != "nmod" or st.status != "active" or surface not in LOCATIVE_SURFACES:
                        continue
                    kdo, co = st.role("kdo"), st.role("co")
                    if not (kdo and x in kdo.terms and co):
                        continue
                    for pl in co.terms:
                        if self._kind(pl) == "place" and pl not in seen:
                            seen.add(pl)
                            fillers.append((pl, Proof([st.id], [f"místo u jména: {m.label(x)} {surface} {m.label(pl)} — ptal ses „{hole.name}“"], list(st.defaults), weakest(st.grade, "derived"))))
        if fillers:
            # u místa napřed skutečná místa, pak povrchové role; jinak podle stupně a délky důkazu
            def rank(x: tuple[str, Proof]) -> tuple[int, int, int]:
                is_place = 0 if (hole.name in PLACE_FAMILY and self._kind(x[0]) == "place") else 1
                return (is_place, -GRADE_RANK[x[1].grade], len(x[1].statements))
            fillers.sort(key=rank)
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers, near=near)
        return Verdict("NEVÍM", missing=self._missing(q, near), near=near)

    def quantity(self, q: Statement, hole: Role) -> Verdict | None:
        """Díra na veličinu Q (rychlost, výška…). Zdroje v pořadí:
        1) výrok o podmětu s rolí Q nebo s mírou u přídavného jména (Sněžka je vysoká 1603 m);
        2) výrok téhož predikátu s číselnou rolí (Sněžka měří 1603 m);
        3) MŮSTEK (výchozí, přiznaný): veličina ukotvená na místě/věci z otázky —
           „maximální rychlost na dálnici je 130 km/h“ platí pro „jet po dálnici“ → nejvýše 130 km/h."""
        m = self.m
        Q = hole.name
        fillers: list[tuple[str, Proof]] = []
        seen: set[str] = set()
        subj = q.role("kdo")
        subj_terms = subj.terms if subj else []
        # 1) + 2): výroky o podmětu
        for x in subj_terms:
            for st in m.statements_about(x):
                if st.status != "active" or st.neg:
                    continue
                kdo = st.role("kdo")
                if not (kdo and any(self.match_term(x, subj.quant if subj else None, t, kdo.quant, role="kdo") is not None for t in kdo.terms)):
                    continue
                r = st.role(Q)
                if r is None and st.pred == "být" and st.role("jaký"):
                    jaky = st.role("jaký")
                    if jaky and any(ADVERB_QUANTITY.get(m.nodes[t].lemma) == Q for t in jaky.terms if t in m.nodes):
                        r = next((rr for rr in st.roles if rr.counts), None)
                if r is None and st.pred and self.same_pred(st.pred, q.pred) is not None:
                    r = next((rr for rr in st.roles if rr.counts), None)
                if r is None and st.pred in ("měřit", "vážit", "dosahovat") and Q in ("výška", "délka", "hmotnost", "vzdálenost", "hloubka"):
                    r = next((rr for rr in st.roles if rr.counts), None)
                if r is None:
                    continue
                for t in r.terms:
                    if t in r.counts:
                        key = f"count:{r.counts[t]} {m.label(t)}"
                        if key not in seen:
                            seen.add(key)
                            fillers.append((key, Proof([st.id], [f"{Q} z výroku o {m.label(x)}"], list(st.defaults), st.grade)))
        if fillers:
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers)
        # 3) můstek přes ukotvenou veličinu: group Q[attrs] ⟶ nmod/rel ⟶ X, kde X je term z otázky
        anchors = [t for r in q.roles if not r.wh for t in r.terms]
        for st in m.active():
            if st.pred != "být" or st.neg:
                continue
            kdo, co = st.role("kdo"), st.role("co")
            if not (kdo and co and kdo.terms):
                continue
            g = m.nodes.get(kdo.terms[0])
            if g is None or g.kind != "group" or g.lemma != Q:
                continue
            values = [(t, co.counts[t]) for t in co.terms if t in co.counts]
            if not values:
                continue
            # ukotvení: nmod výrok (kdo=g, co=X) nebo rel g⟨X⟩ pro X z otázky (i přes ⊆)
            anchor: str | None = None
            link: str | None = None
            for x in anchors:
                if g.rel and g.rel.split(":", 1)[1] == x:
                    anchor, link = x, "rel"
                for nm in m.statements_about(g.id):
                    if nm.kind == "nmod" and nm.status == "active":
                        k2, c2 = nm.role("kdo"), nm.role("co")
                        if k2 and g.id in k2.terms and c2 and any(t == x or m.subset_star(x, t) is not None for t in c2.terms):
                            anchor, link = x, nm.id
                if anchor:
                    break
            if anchor is None:
                continue
            bound = next((QUANTITY_BOUNDS[a] for a in g.attrs if a in QUANTITY_BOUNDS), "")
            for t, c in values:
                key = f"count:{bound + ' ' if bound else ''}{c} {m.label(t)}"
                if key not in seen:
                    seen.add(key)
                    sids = [st.id] + ([link] if link and link != "rel" else [])
                    fillers.append((key, Proof(sids, [f"{m.label(g.id)} ukotvená na {m.label(anchor)} platí pro {q.pred}({m.label(anchor)}) — výchozí můstek: omezení místa/věci omezuje děj na ní"], ["můstek: veličina místa → děj"], "derived")))
        if fillers:
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers)
        return None

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
        node = m.nodes.get(node_id)
        below: list[tuple[str, Proof]] = []
        if node is not None and node.kind == "group" and hole.name == "co":
            # „Kdo je otec Petra Nováka?“ / „Co je nejbližší příbuzný psa?“ → známé prvky a podtřídy;
            # ale „Co je silnice?“ chce napřed, čím silnice JE (nadtřídy) — podřazené až jako přiznané
            for e, path in m.known_members(node_id):
                if e not in seen:
                    seen.add(e)
                    below.append((e, Proof(path, [f"{m.label(e)} ∈ {m.label(node_id)}"], [], self._grade_of(path))))
            for g, path in m.known_subsets(node_id):
                if g not in seen and not path[0].startswith("restricts:"):
                    seen.add(g)
                    below.append((g, Proof(path, [f"{m.label(g)} ⊆ {m.label(node_id)} (podřazená třída, ne definice)"], [], self._grade_of(path))))
            if node.rel and not below and node.rel.startswith("Gen:"):
                # „Kdo je tchán Jany Novákové?“ — nic přímého → inverze a naučené definice
                for e, pr in self.rel_members(node.lemma, node.rel.split(":", 1)[1]):
                    if e not in seen:
                        seen.add(e)
                        below.append((e, pr))
            # nic o X samém: co platí o UŽŠÍCH třídách X („příbuzný domácího psa je vlk“ pro „příbuzný psa“)
            narrow: list[tuple[str, Proof]] = []
            for g, path in m.known_subsets(node_id):
                for st in m.statements_about(g):
                    kdo, co = st.role("kdo"), st.role("co")
                    if st.status != "active" or st.neg or not (kdo and g in kdo.terms and co) or st.pred != "být":
                        continue
                    if not (st.kernel in ("member", "subset") or st.role("jaký")):
                        continue
                    for t in co.terms:
                        if t not in seen and t != node_id and st.id not in path:
                            seen.add(t)
                            narrow.append((t, Proof([st.id] + [x for x in path if not x.startswith(("restricts:", "rel:"))],
                                                    [f"platí o užší třídě {m.label(g)} ⊆ {m.label(node_id)}"], list(st.defaults), "derived")))
            if node.rel and (narrow or below):
                chosen = narrow or below
                return Verdict("ANO", [p for _, p in chosen], fillers=chosen)
            fillers.extend(narrow)
            if fillers:
                return Verdict("ANO", [p for _, p in fillers], fillers=fillers)
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
            if hole.name == "jaký" and s.pred == "být" and s.role("co"):
                # „Jaká je maximální rychlost?“ → hodnota (130 km/h)
                co = s.role("co")
                for t in (co.terms if co else []):
                    if t in co.counts and t not in seen:  # type: ignore[union-attr]
                        seen.add(t)
                        fillers.append((f"count:{co.counts[t]} {m.label(t)}", Proof([s.id], [], list(s.defaults), s.grade)))  # type: ignore[union-attr]
        if not fillers and below:
            fillers = below
        if fillers:
            return Verdict("ANO", [p for _, p in fillers], fillers=fillers)
        near = [s.id for s in self.describe(node_id)]
        return Verdict("NEVÍM", near=near, missing=[] if near else [f"o {m.label(node_id)} nevím nic"])


def evaluate(memory: Memory, q: Statement) -> Verdict:
    return Evaluator(memory).evaluate(q)


def enumerate_(memory: Memory, q: Statement) -> Verdict:
    return Evaluator(memory).enumerate(q)


def describe(memory: Memory, node_id: str) -> list[Statement]:
    return Evaluator(memory).describe(node_id)
