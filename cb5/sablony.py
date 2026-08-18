"""Šablony pro vysvětlení pojmu / vztahu — vyplňuje člověk, nabízí systém.

Proč: volným dialogem se nové vztahy vysvětlit spolehlivě nedají (parser
rozbije každou definiční větu jinak a stroj by musel hádat, co je definice
a co fakt). Šablona = **jedna operace jádra s pojmenovanými sloty**:
člověk ji vybere a vyplní (`!uč druh jezevčík pes`, okno ve viewBase),
parser do toho nemluví, systém ukáže, jak to přečetl, a zapíše to
s proveniencí „šablona“. Jádro tím nezíská žádnou novou sémantiku — jen se
dozví, které slovo/tvar spouští kterou z jeho operací.

Druhá polovina: **při NEVÍM systém sám pozná, který vztah chybí**, a nabídne
předvyplněnou šablonu (jednu, tu nejbližší). Člověk odpoví `ano` (zapíše se
a otázka se zodpoví znovu), `ne` (odmítnutí se pamatuje, znovu se nenabídne)
nebo `jen tady` (nic se neučí). To je proaktivita § 12‑5 zadání conbond4
bez pasti conbond4 — ptá se jen tam, kde se člověk ptal první.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cb5 import defaults as D
from cb5.memory import Memory, Provenance, Role, Statement

if TYPE_CHECKING:  # pragma: no cover
    from cb5.dialog import Session
    from cb5.logic import Verdict


@dataclass
class Sablona:
    name: str
    popis: str
    sloty: list[tuple[str, str]]  # (jméno slotu, popis)
    priklad: str
    #: kolik slotů je povinných (zbytek volitelný)
    povinne: int = 0


@dataclass
class Navrh:
    """Návrh šablony při NEVÍM: jméno + předvyplněné sloty + zdůvodnění + původní otázka."""

    sablona: str
    args: list[str]
    proc: str
    otazka: str
    key: str = ""

    def __post_init__(self) -> None:
        self.key = self.key or f"{self.sablona}:" + " ".join(self.args)

    def prikaz(self) -> str:
        return f"!uč {self.sablona} " + " ".join(self.args)


SABLONY: dict[str, Sablona] = {
    "druh": Sablona("druh", "X je druh Y (X ⊆ Y)", [("X", "užší třída"), ("Y", "širší třída")], "!uč druh jezevčík pes", 2),
    "prvek": Sablona("prvek", "X je jeden z Y (X ∈ Y)", [("X", "jméno"), ("Y", "třída")], "!uč prvek Hrabal spisovatel", 2),
    "totožnost": Sablona("totožnost", "X je totéž co Y (jedno individuum, dvě jména)", [("X", "jméno"), ("Y", "jméno")], "!uč totožnost Hrabal „Bohumil Hrabal“", 2),
    "vyloučení": Sablona("vyloučení", "žádné X není Y (třídy se vylučují → NE)", [("X", "třída"), ("Y", "třída")], "!uč vyloučení kopytník šelma", 2),
    "složený": Sablona("složený", "X = R1 ∘ R2 (X někoho je R1 jeho R2; tchán = otec manžela)", [("X", "vztahové jméno"), ("R1", "vnější vztah"), ("R2", "vnitřní vztah"), ("R2b", "alternativa vnitřního (volitelně)")], "!uč složený tchán otec manžel manželka", 3),
    "inverze": Sablona("inverze", "A a B jsou obrácené vztahy (X je A Y-a ⇔ Y je B X-a)", [("A", "vztah"), ("B", "obrácený vztah")], "!uč inverze manžel manželka", 2),
    "srovnání": Sablona("srovnání", "„S“ je ten, kdo má větší/menší/dřívější/pozdější hodnotu role R děje P", [("S", "srovnávací slovo"), ("P", "predikát (děj)"), ("R", "role s hodnotou (kdy, co, * = kterákoli)"), ("směr", "víc | míň | dřív | později")], "!uč srovnání delší měřit * víc", 4),
    "pravidlo": Sablona("pravidlo", "kdo P(role:X), ten Q(role:X) — můstek mezi ději", [("P(role:X)", "zdrojový děj s rolí"), ("=>", "šipka"), ("Q(role:X)", "cílový děj s rolí")], "!uč pravidlo jet(kam:X) => být(kde:X)", 3),
    "role": Sablona("role", "povrchový tvar role znamená jádrovou roli", [("tvar", "předložka+Pád, např. přes+Acc"), ("=", ""), ("role", "kde | kdy | kam | odkud | kudy | čím | s_kým | komu")], "!uč role přes+Acc = kudy", 3),
    "synonymum": Sablona("synonymum", "slovo A znamená totéž co B (predikáty)", [("A", "sloveso"), ("=", ""), ("B", "sloveso")], "!uč synonymum kázat = hlásat", 3),
    "výjimka": Sablona("výjimka", "pravidlo P o třídě X neplatí pro Y", [("P", "predikát"), ("X", "třída"), ("Y", "výjimka")], "!uč výjimka létat pták tučňák", 3),
    "hodnota": Sablona("hodnota", "X má Q rovno N jednotek", [("X", "věc"), ("Q", "veličina"), ("N", "číslo"), ("j", "jednotka (volitelně)")], "!uč hodnota Vltava délka 430 km", 3),
    "překryv": Sablona("překryv", "Q(A a B) platí, když se překrývají intervaly kdy děje P u obou (potkat_se ⇐ žít)", [("Q", "dotazovaný děj"), ("P", "děj s rolí kdy u obou")], "!uč překryv potkat_se žít", 2),
    "porovnání": Sablona("porovnání", "Q(X, Y) platí, když veličina V u X TEST veličina V u Y (vejít_se ⇐ délka <=)", [("Q", "dotazovaný děj"), ("V", "veličina (víc: délka,šířka)"), ("TEST", "<= | >= | < | > | =")], "!uč porovnání vejít_se délka <=", 3),
}


def seznam() -> str:
    lines = ["Šablony (vyplň a pošli; nebo v prohlížeči okno „Vysvětlit vztah“):"]
    for s in SABLONY.values():
        sl = " ".join(f"<{k}>" for k, _ in s.sloty)
        lines.append(f"  !uč {s.name} {sl:40}  {s.popis}   např. {s.priklad}")
    return "\n".join(lines)


def _split_args(text: str) -> list[str]:
    """Argumenty šablony: mezerami, uvozovky „…“/"…" drží celek."""
    out: list[str] = []
    for m in re.finditer(r'„([^“]*)“|"([^"]*)"|(\S+)', text):
        out.append(next(g for g in m.groups() if g is not None))
    return out


def apply(session: "Session", name: str, args: list[str]) -> str:
    """Použij šablonu na paměť sezení. Vrací text pro člověka."""
    m = session.memory
    s = SABLONY.get(name)
    if s is None:
        return f"neznámá šablona „{name}“\n" + seznam()
    if len(args) < s.povinne:
        return f"šablona {name} chce {s.povinne} slotů: {' '.join(f'<{k}>' for k, _ in s.sloty)} — např. {s.priklad}"
    prov = Provenance("šablona", 0, f"!uč {name} " + " ".join(args), session.turn_no, "")

    def group(lemma: str) -> str:
        return m.ensure_group(lemma).id

    def entity(name_: str) -> str:
        return m.ensure_entity(name_.split(), [name_])[0].id

    def stmt(pred: str, kind: str, roles: list[Role], kernel: str | None = None, neg: bool = False, note: str = "") -> Statement:
        st = Statement("", pred, kind, neg=neg, kernel=kernel, roles=roles, grade="said", prov=prov, defaults=[f"šablona {name}" + (f": {note}" if note else "")])
        m.attach(st)
        return st

    if name == "druh":
        st = stmt("být", "copula", [Role("kdo", [group(args[0])], "∀", "said"), Role("co", [group(args[1])], "∃", "said")], "subset")
        return f"zapsáno [{st.id}]: {args[0]} ⊆ {args[1]}"
    if name == "prvek":
        st = stmt("být", "copula", [Role("kdo", [entity(args[0])], "·", "said"), Role("co", [group(args[1])], "∃", "said")], "member")
        return f"zapsáno [{st.id}]: {args[0]} ∈ {args[1]}"
    if name == "totožnost":
        st = stmt("být", "copula", [Role("kdo", [entity(args[0])], "·", "said"), Role("co", [entity(args[1])], "·", "said")], "same_as")
        return f"zapsáno [{st.id}]: {args[0]} = {args[1]}"
    if name == "vyloučení":
        st = stmt("být", "copula", [Role("kdo", [group(args[0])], "∀", "said"), Role("co", [group(args[1])], "∃", "said")], "subset", neg=True)
        return f"zapsáno [{st.id}]: žádný {args[0]} není {args[1]} ({args[0]} ∦ {args[1]})"
    if name == "složený":
        head, r1, r2 = args[0], args[1], args[2]
        chains = [[r1, r2]] + ([[r1, args[3]]] if len(args) > 3 else [])
        defs = m.learned.setdefault("rel_defs", {}).setdefault(head, [])
        for ch in chains:
            if ch not in defs:
                defs.append(ch)
        st = stmt("definice_vztahu", "definice", [Role("jaký", [group(head)], "·", "said")] + [Role("co", [group(c[0])], "·", "said", surface="∘".join(c)) for c in chains], note=" | ".join("∘".join(c) for c in chains))
        return f"naučeno [{st.id}]: {head}(X) = " + " nebo ".join(f"{c[0]}({c[1]}(X))" for c in chains)
    if name == "inverze":
        a, b = args[0], args[1]
        inv = m.learned.setdefault("inverse", {})
        inv.setdefault(a, [])
        inv.setdefault(b, [])
        if b not in inv[a]:
            inv[a].append(b)
        if a not in inv[b]:
            inv[b].append(a)
        st = stmt("inverze", "definice", [Role("jaký", [group(a)], "·", "said"), Role("co", [group(b)], "·", "said")])
        return f"naučeno [{st.id}]: {a} ↔ {b}"
    if name == "srovnání":
        word, pred, role, dword = args[0], args[1], args[2], args[3]
        direction = D.DIRECTION_ADVERBS.get(dword) or {"earlier": "earlier", "later": "later", "more": "more", "less": "less"}.get(dword)
        if direction is None:
            return f"neznám směr „{dword}“ (víc | míň | dřív | později)"
        return session._learn_comparative(session._adj_lemma(word), pred, role, direction, prov.text)
    if name == "pravidlo":
        return session.command("!pravidlo " + " ".join(args))
    if name == "role":
        return session.command("!role " + " ".join(args))
    if name == "synonymum":
        return session.command("!synonymum " + " ".join(args))
    if name == "výjimka":
        return session.command("!výjimka " + " ".join(args))
    if name == "hodnota":
        x, q, n = args[0], args[1], args[2]
        unit = args[3] if len(args) > 3 else "číslo"
        raw = n.replace(",", ".").replace(" ", "")
        try:
            value = int(float(raw))
        except ValueError:
            return f"„{n}“ není číslo"
        subj = entity(x) if x[:1].isupper() else group(x)
        u = m.ensure_group(unit)
        u.text = u.text or "value"
        st = stmt("být", "copula", [Role("kdo", [subj], "·" if x[:1].isupper() else "∀", "said"), Role(q, [u.id], "∃", "said", counts={u.id: value})])
        return f"zapsáno [{st.id}]: {x} má {q} {value} {unit}"
    if name == "překryv":
        q_, p_ = args[0], args[1]
        m.learned.setdefault("binary", {})[q_] = {"test": "překryv", "source": p_}
        st = stmt("binární_pravidlo", "definice", [Role("jaký", [group(q_)], "·", "said"), Role("co", [group(p_)], "·", "said", surface="překryv")], note=f"{q_} ⇐ překryv {p_}(kdy)")
        return f"naučeno [{st.id}]: {q_}(A, B) platí, když se překrývají intervaly {p_}(kdy) u A i B"
    if name == "porovnání":
        q_, v_, test = args[0], args[1], args[2]
        if test not in ("<=", ">=", "<", ">", "="):
            return f"neznám test „{test}“ (<= | >= | < | > | =)"
        m.learned.setdefault("binary", {})[q_] = {"test": test, "source": v_}
        st = stmt("binární_pravidlo", "definice", [Role("jaký", [group(q_)], "·", "said"), Role("co", [group(v_.split(",")[0])], "·", "said", surface=test)], note=f"{q_} ⇐ {v_} {test}")
        return f"naučeno [{st.id}]: {q_}(X, Y) platí, když {v_}(X) {test} {v_}(Y)"
    return f"šablona {name} zatím nemá provedení"


# --------------------------------------------------------------------------
# návrh šablony při NEVÍM
# --------------------------------------------------------------------------

def navrhni(memory: Memory, q: Statement, verdict: "Verdict", question: str) -> Navrh | None:
    """Z otázky, verdiktu NEVÍM a toho, co je v paměti blízko, odhadne JEDNU
    chybějící vazbu a vrátí předvyplněnou šablonu (nebo None)."""
    m = memory
    refused = set(memory.learned.get("refused", {}).keys())

    def ok(n: Navrh) -> Navrh | None:
        return None if n.key in refused else n

    miss = " ".join(verdict.missing)
    # 0) binární dotaz bez pravidla: oba účastníci mají intervaly téhož děje → překryv;
    #    oba mají touž veličinu → porovnání
    from cb5.logic import Evaluator
    ev = Evaluator(m)
    parts = ev._participants(q)
    if len(parts) == 2 and q.pred and q.pred not in m.learned.get("binary", {}):
        a, b = parts
        preds_a = {st.pred for st in m.statements_about(a) if st.pred and st.role("kdy") and st.role("kdy").terms}  # type: ignore[union-attr]
        preds_b = {st.pred for st in m.statements_about(b) if st.pred and st.role("kdy") and st.role("kdy").terms}  # type: ignore[union-attr]
        both = sorted(preds_a & preds_b)
        if both and q.modality:
            p_ = both[0]
            return ok(Navrh("překryv", [q.pred, p_], f"o {m.label(a)} i {m.label(b)} znám {p_}(kdy); je „{q.pred}“ možné, když se ty časy překrývají?", question))
        qn_a = {r.name for st in m.statements_about(a) for r in st.roles if r.counts and r.name in D.ADVERB_QUANTITY.values()}
        qn_b = {r.name for st in m.statements_about(b) for r in st.roles if r.counts and r.name in D.ADVERB_QUANTITY.values()}
        common = sorted(qn_a & qn_b)
        if common:
            return ok(Navrh("porovnání", [q.pred, ",".join(common), "<="], f"o {m.label(a)} i {m.label(b)} znám {', '.join(common)}; platí „{q.pred}“, když {common[0]}({m.label(a)}) <= {common[0]}({m.label(b)})? (test uprav: <=, >=, <, >, =)", question))
    kdo = q.role("kdo")
    # 0b) neznámý/nedoložený predikát: podmět má výroky s JINÝM predikátem, který má stejné role
    #     jako otázka → nabídni synonymum (jen když se role skutečně kryjí)
    if kdo and kdo.terms and q.pred and not verdict.near and q.pred not in ("být", "dělat", "umět", "vědět", "znát"):
        wanted = {r.name for r in q.roles if r.name != "kdo"}
        # termy otázky mimo podmět (Brno v „Bydlí Jirásek v Brně?“) musí kandidát znát — jinak by
        # synonymum nic nezodpovědělo a návrh by byl šum
        other_terms = {t for r in q.roles if r.name != "kdo" and not r.wh for t in r.terms}
        cands: dict[str, tuple[int, str]] = {}  # pred → (počet, poslední id výroku)
        for x in kdo.terms:
            for st in m.statements_about(x):
                if st.kind != "verb" or not st.pred or st.status != "active" or st.derived_from or st.pred == q.pred:
                    continue
                if st.pred in ("být", "mít", "věk", "srovnání", "definice"):
                    continue
                have = {r.name for r in st.roles if r.name != "kdo"}
                if wanted and wanted <= have and other_terms <= set(st.term_ids()):
                    cnt, _ = cands.get(st.pred, (0, ""))
                    cands[st.pred] = (cnt + 1, st.id)
        if cands:
            # víc dokladů vítězí; při shodě naposled řečené (nejbližší v rozhovoru)
            best = max(cands, key=lambda k: cands[k])
            return ok(Navrh("synonymum", [q.pred, "=", best], f"o {m.label(kdo.terms[0])} nemám „{q.pred}“, ale mám „{best}“ se stejnými rolemi ({', '.join(sorted(wanted)) or 'bez rolí'}). Znamená „{q.pred}“ totéž co „{best}“?", question))
    # 1) neznámé srovnávací slovo
    mt = re.search(r"srovnání „([^“]+)“ neumím", miss)
    if mt:
        word = mt.group(1)
        # kandidát predikát: děj, kde mají obě strany číslo/čas
        preds = [st.pred for st in m.active() if st.pred and any(r.counts or any(m.nodes.get(t, None) and m.nodes[t].kind == "time" for t in r.terms) for r in st.roles)]
        pred = max(set(preds), key=preds.count) if preds else "měřit"
        return ok(Navrh("srovnání", [word, pred, "*", "víc"], f"neznám slovo „{word}“; o věcech mám číselné hodnoty u děje „{pred}“ — je „{word}“ ten, kdo má víc/míň (dřív/později)?", question))
    # 2) vztahové jméno bez prvků a bez definice
    if kdo and kdo.terms and q.pred == "být":
        n = m.nodes.get(kdo.terms[0])
        if n is not None and n.kind == "group" and n.rel and n.lemma not in m.learned.get("rel_defs", {}):
            known = sorted({g.lemma for g in m.nodes.values() if g.kind == "group" and g.rel and g.lemma != n.lemma})[:8]
            return ok(Navrh("složený", [n.lemma, "<R1>", "<R2>"], f"neznám, jak se „{n.lemma}“ skládá z jiných vztahů; znám vztahová jména: {', '.join(known) or '—'} — doplň R1 a R2 (X = R1 jeho R2)", question))
    # 3) blízký výrok s týmž podmětem, ale jinou rolí/predikátem → můstek
    q_place = next((r for r in q.roles if r.name in ("kde", "kdy") and r.terms and not r.wh), None)
    if q_place and kdo and kdo.terms:
        around = [st for x in kdo.terms for st in m.statements_about(x)]
        for f in around:
            if f.pred == q.pred or f.kind != "verb" or f.status != "active" or f.derived_from:
                continue
            for fr in f.roles:
                if fr.name != q_place.name and fr.name in ("kam", "odkud", "kudy", "kde", "do_kdy", "od_kdy") and any(
                    t == qt or m.within_star(t, qt) is not None for t in fr.terms for qt in q_place.terms):
                    return ok(Navrh("pravidlo", [f"{f.pred}({fr.name}:X)", "=>", f"{q.pred}({q_place.name}:X)"],
                                    f"vím: {m.render_short(f)}; ptáš se na {q.pred}({q_place.name}). Plyne z „{f.pred}({fr.name})“ i „{q.pred}({q_place.name})“?", question))
    # 4) „Je X Y?“ s NEVÍM: X ∈ Z známé, o Y nic → vyloučení
    if q.kernel in ("member", "subset") and q.role("co") and q.role("co").terms:  # type: ignore[union-attr]
        y = q.role("co").terms[0]  # type: ignore[union-attr]
        for x in (kdo.terms if kdo else []):
            for st in m.statements_about(x):
                if st.kernel in ("member", "subset") and not st.neg and st.status == "active":
                    co = st.role("co")
                    if co and co.terms and co.terms[0] != y and m.nodes.get(co.terms[0], None) and m.nodes[co.terms[0]].kind == "group":
                        z = co.terms[0]
                        return ok(Navrh("vyloučení", [m.nodes[z].lemma, m.label(y)], f"vím: {m.label(x)} ∈ {m.label(z)}; o {m.label(y)} nic. Vylučují se {m.label(z)} a {m.label(y)}?", question))
    return None
