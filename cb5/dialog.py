"""Dialog: tahy nad pamětí — vkládání textu, tvrzení, otázky, opravy, backlog.

Proč (spec § 8): dialog je jediné místo, které mění paměť, a dělá to
třemi cestami — `ingest` (dokument, stupeň `read`), `say` (tvrzení
`said` / otázka bez zápisu / oprava = odvolání + zápis) a příkazy `!…`
(doučení rolí, synonym, pravidel, výjimek; backlog). Žurnál tahů +
deterministické čtení ⇒ `replay` dá týž program.

Sliding window: každá věta aktivuje své uzly, po každé větě `tick()`
(vyhasnutí); nevyslovený podmět a zájmena se doplňují z aktivace, jinak
z tématu dokumentu (první entita v podmětu).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import networkx as nx

from cb5.ground import Grounded, ground
from cb5.logic import Verdict, enumerate_, evaluate
from cb5.memory import Memory, Node, OpenItem, Provenance, Statement
from cb5.oracle import OracleError, Parse, SegmentationError
from cb5.read import Reading, read
from cb5.recall import recall
from cb5.render import describe_node, render_answer, render_statement


@dataclass
class Turn:
    no: int
    kind: str  # ingest | say | command | resolve
    text: str
    doc: str = ""


@dataclass
class Answer:
    text: str
    verdict: Verdict | None = None
    statements: list[str] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)
    open: list[OpenItem] = field(default_factory=list)
    conflict: Verdict | None = None
    reading: str = ""


class Session:
    """Jedno sezení nad jednou pamětí a jedním orákulem."""

    def __init__(self, memory: Memory | None = None, oracle: object = None) -> None:
        self.memory = memory or Memory()
        self.oracle = oracle
        self.journal: list[Turn] = []
        self.turn_no = 0
        self.topics: dict[str, str] = {}
        self._sent_no: dict[str, int] = {}
        self._last_said: list[str] = []
        self._restore_learned()

    # ---- pomocníci -------------------------------------------------------------

    def _restore_learned(self) -> None:
        self.memory.learned.setdefault("roles", {})
        self.memory.learned.setdefault("synonyms", {})

    def _read(self, parse: Parse, mood: str | None = None) -> Reading:
        return read(parse, mood, learned_roles=self.memory.learned.get("roles", {}))

    def _turn(self, kind: str, text: str, doc: str = "") -> Turn:
        self.turn_no += 1
        t = Turn(self.turn_no, kind, text, doc)
        self.journal.append(t)
        return t

    def _prov(self, doc: str, text: str) -> Provenance:
        self._sent_no[doc] = self._sent_no.get(doc, 0) + 1
        model = getattr(self.oracle, "provenance", "")
        return Provenance(doc, self._sent_no[doc], text, self.turn_no, model)

    def _parses(self, text: str) -> list[Parse]:
        assert self.oracle is not None, "sezení bez orákula neumí číst text"
        try:
            return list(self.oracle.segment(text))  # type: ignore[attr-defined]
        except AttributeError:
            return [self.oracle.parse(text)]  # type: ignore[attr-defined]

    def _update_topic(self, doc: str, g: Grounded) -> None:
        if doc in self.topics or g.main is None:
            return
        kdo = g.main.role("kdo")
        if kdo:
            for t in kdo.terms:
                n = self.memory.nodes.get(t)
                if n and n.kind == "entity" and n.names:
                    self.topics[doc] = t
                    return

    # ---- vkládání textu ----------------------------------------------------------

    def ingest(self, text: str, doc: str = "dialog") -> list[dict[str, object]]:
        """Dokument → věty → čtení → zápis (`read`). Vrací zprávu za větu."""
        self._turn("ingest", text, doc)
        self.memory.ensure_document(doc)
        reports: list[dict[str, object]] = []
        for line in text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            raw = raw.strip("= ").strip() or raw
            try:
                parses = self._parses(raw)
            except (OracleError, SegmentationError) as exc:
                reports.append({"text": raw, "error": str(exc)})
                continue
            for parse in parses:
                reports.append(self._ingest_sentence(parse, doc))
        return reports

    def _ingest_sentence(self, parse: Parse, doc: str) -> dict[str, object]:
        reading = self._read(parse, "assert")
        prov = self._prov(doc, parse.text)
        g = ground(reading, self.memory, prov, "read", topic=self.topics.get(doc))
        self._update_topic(doc, g)
        self.memory.tick()
        # téma dokumentu drží slabou stálou aktivaci — dokument JE o něm
        if doc in self.topics:
            self.memory.activate([self.topics[doc]], 0.3)
        return {
            "text": parse.text,
            "reading": str(reading.main),
            "statements": [s.id for s in g.statements],
            "residue": list(reading.residue),
            "open": [o.id for o in g.open],
            "defaults": list(g.main.defaults) if g.main else [],
        }

    # ---- tah dialogu -----------------------------------------------------------

    #: Příkazy jdou i bez „!“, když věta začíná příkazovým slovem.
    COMMAND_WORDS = frozenset({"zapomeň", "zapomen", "odvolej", "popiš", "popis", "otevřené", "otevrene", "backlog",
                               "nápověda", "napoveda", "program", "ulož", "uloz", "načti", "nacti", "graf", "pravidlo",
                               "synonymum", "výjimka", "vyjimka", "odpověz", "odpovez", "role"})

    def say(self, text: str, doc: str = "dialog") -> Answer:
        text = text.strip()
        first = text.split(None, 1)[0].lower().rstrip(".!:") if text else ""
        if first in self.COMMAND_WORDS and not text.startswith("!"):
            text = "!" + text
        if text.startswith("!"):
            self._turn("command", text)
            return Answer(self.command(text))
        self._turn("say", text, doc)
        try:
            parses = self._parses(text)
        except (OracleError, SegmentationError) as exc:
            return Answer(f"✗ nepřečteno: {exc}")
        answers: list[Answer] = []
        for parse in parses:
            answers.append(self._say_one(parse, doc))
        if len(answers) == 1:
            return answers[0]
        return Answer("\n".join(a.text for a in answers), statements=[s for a in answers for s in a.statements],
                      revoked=[r for a in answers for r in a.revoked], verdict=answers[-1].verdict)

    def _say_one(self, parse: Parse, doc: str) -> Answer:
        reading = self._read(parse)
        if reading.main.mood == "question":
            return self._answer(reading, doc)
        return self._assert(reading, doc)

    def _answer(self, reading: Reading, doc: str) -> Answer:
        m = self.memory
        prov = Provenance(doc, 0, reading.parse.text, self.turn_no, getattr(self.oracle, "provenance", ""))
        g = ground(reading, m, prov, "said", topic=self.topics.get(doc), write=False)
        q = g.main
        assert q is not None
        wh = any(r.wh for r in q.roles)
        verdict = enumerate_(m, q) if wh else evaluate(m, q)
        recalled: list[Statement] = []
        if verdict.value == "NEVÍM":
            recalled = recall(m, q.term_ids(), 3, pred=q.pred, exclude=verdict.near)
        # otázka aktivuje kontext (ne bázi)
        m.activate(q.term_ids(), 0.5)
        m.tick()
        text = f"čtu: {reading.main}\n" + render_answer(m, verdict, wh=wh, recalled=recalled)
        return Answer(text, verdict, reading=str(reading.main))

    def _assert(self, reading: Reading, doc: str) -> Answer:
        m = self.memory
        main = reading.main
        revoked: list[str] = []
        lines: list[str] = []
        # oprava: „To není pravda.“ / „Ne.“ / „Ne, …“
        is_denial = main.kind == "copula" and main.neg and any(
            t.lemma == "pravda" for r in main.roles for t in r.terms) or reading.parse.text.strip(".! ").lower() in ("ne", "to ne", "špatně")
        if is_denial or main.correction:
            for sid in self._last_said:
                revoked.extend(m.revoke(sid, f"oprava (tah {self.turn_no}): {reading.parse.text}"))
            if revoked:
                lines.append("odvolávám: " + ", ".join(revoked))
            if is_denial:
                self._last_said = []
                return Answer("\n".join(lines) or "nemám co odvolat", revoked=revoked)
        # „Ne každý pták.“ — oprava kvantifikátoru poslední věty
        if main.kind == "fragment" and reading.parse.text.lower().startswith("ne ") and main.role("téma"):
            return self._fix_quantifier(reading, doc)
        # konflikt: ptej se paměti PŘED zápisem
        prov = self._prov(doc, reading.parse.text)
        conflict: Verdict | None = None
        if main.kind in ("verb", "copula"):
            probe = ground(reading, m, prov, "said", topic=self.topics.get(doc), write=False).main
            if probe is not None:
                probe.mood = "question"
                probe_neg = probe.neg
                probe.neg = False
                v = evaluate(m, probe)
                if (v.value == "NE" and not probe_neg) or (v.value == "ANO" and probe_neg) or v.value == "KONFLIKT":
                    conflict = v
        g = ground(reading, m, prov, "said", topic=self.topics.get(doc))
        self._update_topic(doc, g)
        m.tick()
        self._last_said = [s.id for s in g.statements if s.derived_from is None]
        for s in g.statements:
            if s.derived_from is None:
                lines.append(f"✓ zapsáno [{s.id}] {render_statement(m, s)}")
                if s.defaults:
                    lines.append("   [" + "; ".join(s.defaults) + "]")
        if reading.residue:
            lines.append("   zbytek: " + ", ".join(f"„{f}“ ({p})" for f, p in reading.residue))
        for o in g.open:
            lines.append(f"   ? {o.id}: {o.question}")
        if conflict is not None:
            lines.append("⚠ to si odporuje s tím, co už vím:")
            for p in (conflict.counter or conflict.proofs):
                for sid in p.statements:
                    if sid in m.statements:
                        lines.append(f"   - {render_statement(m, m.statements[sid], with_source=True)}  [{sid}]")
                for step in p.steps:
                    if step:
                        lines.append(f"   ↳ {step}")
            lines.append("   (nechávám obojí; otázky na to budou hlásit KONFLIKT — oprav `!zapomeň s…`, nebo zúž `!výjimka <predikát> <skupina> <výjimka>`)")
        return Answer("\n".join(lines), statements=[s.id for s in g.statements], revoked=revoked, open=g.open, conflict=conflict, reading=str(main))

    def _fix_quantifier(self, reading: Reading, doc: str) -> Answer:
        m = self.memory
        term = reading.main.role("téma").terms[0]  # type: ignore[union-attr]
        group = m.find_group(term.lemma, term.attrs) or m.find_group(term.lemma)
        if group is None or not self._last_said:
            return Answer("nevím, kterou větu opravit")
        changed = []
        for sid in self._last_said:
            st = m.statements.get(sid)
            if st is None:
                continue
            for r in st.roles:
                if group.id in r.terms and r.quant == "∀":
                    r.quant = "∃"
                    st.defaults.append(f"kvantifikátor {r.name}: ∀ → ∃ (oprava dialogem, tah {self.turn_no})")
                    changed.append(sid)
        if not changed:
            return Answer("v poslední větě není ∀ nad touhle skupinou")
        return Answer("opraveno: " + ", ".join(f"{sid} → {render_statement(m, m.statements[sid])}" for sid in changed), statements=changed)

    # ---- backlog -----------------------------------------------------------------

    def open(self) -> list[OpenItem]:
        return self.memory.open_items()

    def resolve(self, item_id: str, value: str) -> str:
        """Odpověď na otevřenou položku: přejmenuje roli / doplní odkaz."""
        self._turn("resolve", f"{item_id} {value}")
        m = self.memory
        item = m.open_items_.get(item_id)
        if item is None:
            return f"neznámá položka {item_id}"
        st = m.statements.get(item.statement)
        if st is None:
            return f"výrok {item.statement} neexistuje"
        if item.kind == "role_name":
            for r in st.roles:
                if r.surface == item.about and r.name == item.about:
                    r.name = value
                    r.authority = "said"
            st.defaults.append(f"role {item.about} → {value} (odpověď na {item_id})")
            item.answer = value
            return f"{st.id}: {render_statement(m, st)}"
        if item.kind == "reference":
            cands = m.find_entity(value.split())
            if not cands:
                node, _ = m.ensure_entity(value.split(), [value])
            else:
                node = cands[0]
            for r in st.roles:
                if not r.terms and r.name == (item.question.split("v roli ")[-1].rstrip("?") if "v roli " in item.question else r.name):
                    r.terms.append(node.id)
                    m._by_term[node.id].append(st.id)
                    break
            else:
                kdo = st.role("kdo")
                if kdo is not None and not kdo.terms:
                    kdo.terms.append(node.id)
                    m._by_term[node.id].append(st.id)
            st.defaults.append(f"odkaz „{item.about}“ = {node.label()} (odpověď na {item_id})")
            item.answer = value
            return f"{st.id}: {render_statement(m, st)}"
        item.answer = value
        st.defaults.append(f"{item.kind}: {value} (odpověď na {item_id})")
        return f"{item_id}: zaznamenáno"

    # ---- příkazy -------------------------------------------------------------------

    def command(self, line: str) -> str:
        m = self.memory
        parts = line[1:].strip().split(None, 1)
        if not parts:
            return self._help()
        cmd, arg = parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")
        if cmd in ("zapomeň", "zapomen", "revoke", "odvolej"):
            arg = arg.rstrip(".!")
            if arg in m.statements:
                revoked = m.revoke(arg, f"zapomenuto dialogem (tah {self.turn_no})")
                return "odvoláno: " + (", ".join(revoked) or "nic")
            targets: list[Node] = list(m.find_entity(arg.split()))
            grp = m.find_group(arg.lower())
            if not targets and grp is not None:
                targets = [grp]
            if not targets:
                return f"neznám výrok ani jméno „{arg}“ (užití: !zapomeň s0003 nebo !zapomeň Ronik)"
            revoked = []
            for node in targets:
                for st in m.statements_about(node.id):
                    if st.derived_from is None:
                        revoked.extend(m.revoke(st.id, f"zapomenuto dialogem: {arg} (tah {self.turn_no})"))
            return f"odvoláno o „{arg}“: " + (", ".join(revoked) or "nic")
        if cmd == "role":
            mt = re.match(r"^(\S+)\s*=\s*(\S+)$", arg)
            if not mt:
                return "užití: !role v+Loc = kde"
            surface, name = mt.group(1), mt.group(2)
            m.learned.setdefault("roles", {})[surface] = name
            n = 0
            for st in m.active():
                for r in st.roles:
                    if r.surface == surface and r.name == surface:
                        r.name, r.authority = name, "learned"
                        st.defaults.append(f"role {surface} → {name} (naučeno, tah {self.turn_no})")
                        n += 1
            for o in m.open_items():
                if o.kind == "role_name" and o.about == surface:
                    o.answer = name
            return f"naučeno: {surface} = {name}; přejmenováno v {n} výrocích"
        if cmd in ("synonymum", "synonym"):
            mt = re.match(r"^(\S+)\s*=\s*(\S+)$", arg)
            if not mt:
                return "užití: !synonymum kázat = hlásat"
            a, b = mt.group(1), mt.group(2)
            m.learned.setdefault("synonyms", {})[a] = b
            return f"naučeno: {a} ~ {b}"
        if cmd == "pravidlo":
            mt = re.match(r"^(\S+?)\((.*?)\)\s*=>\s*(\S+?)\((.*?)\)$", arg)
            if not mt:
                return "užití: !pravidlo jet(kam:X) => být(kde:X)"
            src, sroles, dst, droles = mt.groups()
            def parse_roles(s: str) -> dict[str, str]:
                out: dict[str, str] = {}
                for piece in s.split(","):
                    if ":" in piece:
                        r, v = piece.split(":", 1)
                        out[v.strip()] = r.strip()
                return out
            sv, dv = parse_roles(sroles), parse_roles(droles)
            role_map = {sv[v]: dv[v] for v in sv if v in dv}
            rule = m.add_rule(src, dst, role_map, f"dialog tah {self.turn_no}")
            return f"pravidlo {rule.id}: {src}({', '.join(f'{k}' for k in role_map)}) ⇒ {dst}({', '.join(role_map.values())})"
        if cmd in ("výjimka", "vyjimka"):
            ws = arg.split()
            if len(ws) != 3:
                return "užití: !výjimka létat pták tučňák"
            pred, g1, g2 = ws
            a, b = m.find_group(g1), m.find_group(g2)
            if a is None or b is None:
                ents = m.find_entity([g2])
                if a is None or not ents:
                    return f"neznám skupinu {g1 if a is None else g2}"
                b = ents[0]
            m.add_exception(pred, a.id, b.id)
            return f"výjimka: {pred} o {a.label()} neplatí pro {b.label()}"
        if cmd in ("otevřené", "otevrene", "backlog"):
            items = m.open_items()
            if not items:
                return "žádné otevřené položky"
            return "\n".join(f"{o.id} [{o.kind}] ({o.statement}): {o.question}" for o in items)
        if cmd in ("odpověz", "odpovez"):
            ws = arg.split(None, 1)
            if len(ws) != 2:
                return "užití: !odpověz o0001 kde"
            return self.resolve(ws[0], ws[1])
        if cmd == "program":
            return "\n".join(m.program()) or "(prázdná paměť)"
        if cmd in ("ulož", "uloz", "save"):
            m.save(Path(arg))
            return f"uloženo do {arg}"
        if cmd in ("načti", "nacti", "load"):
            self.memory = Memory.load(Path(arg))
            self._restore_learned()
            return f"načteno z {arg}: {len(list(self.memory.active()))} výroků"
        if cmd == "graf":
            g = m.graph()
            data = nx.node_link_data(g, edges="links")
            Path(arg).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return f"graf uložen do {arg}: {g.number_of_nodes()} uzlů, {g.number_of_edges()} hran"
        if cmd in ("kdo", "co", "popiš", "popis"):
            found = m.find_entity(arg.split())
            grp = m.find_group(arg)
            target: Node | None = found[0] if found else grp
            if target is None:
                return f"neznám {arg}"
            lines = [f"{target.id} {describe_node(m, target.id)}:"]
            for st in m.statements_about(target.id):
                lines.append("  " + render_statement(m, st, with_source=True))
            return "\n".join(lines)
        if cmd in ("nápověda", "napoveda", "help", "?"):
            return self._help()
        return f"neznámý příkaz {cmd}\n" + self._help()

    @staticmethod
    def _help() -> str:
        return (
            "příkazy: !zapomeň s0001 · !role v+Loc = kde · !synonymum kázat = hlásat · "
            "!pravidlo jet(kam:X) => být(kde:X) · !výjimka létat pták tučňák · !otevřené · "
            "!odpověz o0001 kde · !program · !popiš Jirásek · !ulož p.json · !načti p.json · !graf g.json"
        )

    # ---- žurnál ---------------------------------------------------------------------

    def journal_json(self) -> list[dict[str, object]]:
        return [{"no": t.no, "kind": t.kind, "text": t.text, "doc": t.doc} for t in self.journal]

    @classmethod
    def replay(cls, journal: Sequence[dict[str, object]] | Sequence[Turn], oracle: object) -> "Session":
        """Přehraj žurnál nad čerstvou pamětí — deterministicky týž program."""
        s = cls(Memory(), oracle)
        for t in journal:
            kind = t.kind if isinstance(t, Turn) else str(t["kind"])
            text = t.text if isinstance(t, Turn) else str(t["text"])
            doc = t.doc if isinstance(t, Turn) else str(t.get("doc", ""))
            if kind == "ingest":
                s.ingest(text, doc or "dialog")
            elif kind == "say":
                s.say(text, doc or "dialog")
            elif kind == "command":
                s.say(text)
            elif kind == "resolve":
                item, value = text.split(None, 1)
                s.resolve(item, value)
        return s
