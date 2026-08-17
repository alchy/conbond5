"""Render: z verdiktu a důkazu čeština — verdikt, důvod, zdroj, doložka stupně.

Proč šablony jako data (spec § 9): výstup smí říct jen to, co stojí ve
struktuře, kterou systém opravdu použil. Chybějící šablona je chyba, ne
tichý fallback. Vzhled je záměrně „strukturovaný“ (role: výplň), protože
pravdivý výpis je víc než hezká věta bez krytí (poučení conbond4 § 8).
"""

from __future__ import annotations

from typing import Sequence

from cb5.logic import Proof, Verdict
from cb5.memory import Memory, Statement

ROLE_LABELS: dict[str, str] = {
    "kdo": "kdo", "co": "co", "komu": "komu", "čím": "čím", "kde": "kde", "kam": "kam", "odkud": "odkud",
    "kudy": "kudy", "kdy": "kdy", "od_kdy": "od kdy", "do_kdy": "do kdy", "jak": "jak", "jaký": "jaký",
    "s_kým": "s kým", "o_čem": "o čem", "pro_koho": "pro koho", "jako": "jako", "jak_dlouho": "jak dlouho",
    "pořadí": "pořadí", "téma": "téma",
}

GRADE_LABELS = {"said": "řekls to", "read": "přečteno z textu", "derived": "odvozeno"}

TEMPLATES = {
    "ANO": "→ ANO",
    "NE": "→ NE",
    "NEVÍM": "→ NEVÍM",
    "KONFLIKT": "→ KONFLIKT — mám důkaz pro obojí",
    "MOŽNÁ": "→ MOŽNÁ — text říká jen, že může",
    "source": "zdroj: „{text}“ ({doc}, věta {no})",
    "because": "protože:",
    "known": "vím:",
    "missing": "chybí:",
    "grade": "[{grade}{defaults}]",
    "wh_empty": "→ NEVÍM",
}


def role_label(name: str) -> str:
    return ROLE_LABELS.get(name, name)


def describe_node(m: Memory, node_id: str) -> str:
    """Čitelné jméno uzlu: entita jménem, instance jako „auto (modré)“,
    group lemmatem s přívlastky, čas popiskou."""
    n = m.nodes.get(node_id)
    if n is None:
        return node_id
    if n.kind == "entity" and not n.names and n.base:
        base = m.nodes[n.base]
        attrs = list(n.attrs)
        for st in m.statements_about(node_id):
            kdo, jaky = st.role("kdo"), st.role("jaký")
            if st.pred == "být" and kdo and node_id in kdo.terms and jaky and not st.neg:
                attrs.extend(m.nodes[t].lemma for t in jaky.terms if t in m.nodes)
        return base.lemma + (f" ({', '.join(dict.fromkeys(attrs))})" if attrs else "")
    if n.kind == "group":
        out = n.lemma + (f" ({', '.join(n.attrs)})" if n.attrs else "")
        if n.rel and ":" in n.rel:
            out += " " + describe_node(m, n.rel.split(":", 1)[1])  # „otec Petr Novák“, „péče majitel“
        return out
    return n.label()


def render_statement(m: Memory, st: Statement, *, with_source: bool = False) -> str:
    head = st.pred or "∅"
    if st.neg:
        head = "ne-" + head
    if st.modality:
        head = f"{st.modality}: {head}"
    parts: list[str] = []
    for r in st.roles:
        if r.nested and r.nested in m.statements:
            parts.append(f"{role_label(r.name)}: [{render_statement(m, m.statements[r.nested])}]")
            continue
        if r.var:
            parts.append(f"{role_label(r.name)}: {r.var}")  # proměnná pravidla („každý, kdo …“)
            continue
        labels = []
        for t in r.terms:
            lab = describe_node(m, t)
            if t in r.counts:
                lab = f"{Memory.count_label(r, t)} {lab}"
            labels.append(((r.quant or "") if r.quant in ("∀", "∃") else "") + lab)
        if labels:
            parts.append(f"{role_label(r.name)}: {' + '.join(labels)}")
    kernel = f" ⟨{st.kernel}⟩" if st.kernel else ""
    out = f"{head}({', '.join(parts)}){kernel}"
    if with_source and st.prov.text:
        out += "  — " + TEMPLATES["source"].format(text=st.prov.text, doc=st.prov.doc, no=st.prov.sent_no)
    return out


def _grade_note(m: Memory, proof: Proof) -> str:
    grades = {m.statements[s].grade for s in proof.statements if s in m.statements}
    label = GRADE_LABELS[proof.grade]
    if proof.grade == "derived" and grades:
        label += " z: " + ", ".join(GRADE_LABELS[g] for g in sorted(grades))
    defaults = [d for d in proof.defaults if not d.startswith("__")]
    # doložka „podle koho“ se ukáže vždy, i když důkaz šel jádrem (∈/⊆) a výchozí volby výroku nenesl
    for sid in proof.statements:
        st = m.statements.get(sid)
        for d in (st.defaults if st else []):
            if d.startswith("podle ") and d not in defaults:
                defaults.append(d)
    return TEMPLATES["grade"].format(grade=label, defaults=("; " + "; ".join(defaults)) if defaults else "")


def _proof_lines(m: Memory, proof: Proof, indent: str = "   ") -> list[str]:
    lines: list[str] = []
    for sid in proof.statements:
        st = m.statements.get(sid)
        if st is None:
            if sid.startswith("restricts:"):
                continue
            lines.append(f"{indent}- {sid}")
            continue
        lines.append(f"{indent}- {render_statement(m, st)}  [{sid}]")
        if st.prov.text:
            lines.append(f"{indent}    " + TEMPLATES["source"].format(text=st.prov.text, doc=st.prov.doc, no=st.prov.sent_no))
    for step in proof.steps:
        if step:
            lines.append(f"{indent}↳ {step}")
    lines.append(f"{indent}{_grade_note(m, proof)}")
    return lines


def render_answer(m: Memory, verdict: Verdict, *, wh: bool, recalled: Sequence[Statement] = ()) -> str:
    lines: list[str] = []
    if wh:
        if verdict.fillers:
            # výplně se stejným důkazem se sloučí do jednoho řádku
            groups: list[tuple[tuple[str, ...], list[str], Proof]] = []
            for t, proof in verdict.fillers:
                if t.startswith("count:"):
                    label = t.split(":", 1)[1]
                elif t in m.statements:
                    label = render_statement(m, m.statements[t])  # „Co dělá X?“ → celý děj
                else:
                    label = describe_node(m, t)
                key = tuple(proof.statements)
                for k, labels, _ in groups:
                    if k == key:
                        labels.append(label)
                        break
                else:
                    groups.append((key, [label], proof))
            for _, labels, proof in groups:
                lines.append("→ " + "; ".join(labels))
                lines.extend(_proof_lines(m, proof))
        else:
            lines.append(TEMPLATES["wh_empty"])
    else:
        lines.append(TEMPLATES[verdict.value])
        for proof in verdict.proofs:
            lines.append("   " + TEMPLATES["because"])
            lines.extend(_proof_lines(m, proof, "   "))
        if verdict.counter:
            lines.append("   proti tomu:" if verdict.value == "KONFLIKT" else "   " + TEMPLATES["because"])
            for proof in verdict.counter:
                lines.extend(_proof_lines(m, proof, "   "))
    if verdict.value == "NEVÍM" or (wh and not verdict.fillers):
        for miss in verdict.missing:
            lines.append(f"   {TEMPLATES['missing']} {miss}")
        near = [m.statements[s] for s in verdict.near if s in m.statements]
        shown: list[Statement] = []
        for st in list(near) + list(recalled):
            if st not in shown:
                shown.append(st)
        if shown:
            lines.append("   " + TEMPLATES["known"])
            for st in shown[:5]:
                lines.append(f"   - {render_statement(m, st, with_source=True)}")
    return "\n".join(lines)
