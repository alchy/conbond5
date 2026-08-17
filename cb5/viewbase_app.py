"""Konverzace nad živým grafem ve viewBase (volitelný adaptér).

    pip install -e /Users/j/Projects/viewBase/python      # viewbase (lokálně)
    python -m cb5.viewbase_app [--pamet p.json] [--port 8080]

Proč: paměť conbond5 JE graf (spec § 3) a člověk má vidět, čím systém
myslí. Adaptér drží mimo jádro: po každém tahu se rozdíl paměti promítne
do plátna (`ensure_node`/`ensure_edge`), aktivace se ukáže jako
`highlight`, a konzole v prohlížeči (`TerminalWindow`) je tentýž dialog
jako `python -m cb5 chat`. Klik na uzel otevře detail s výroky.

Typy uzlů: entita, group (i zúžená), místo, čas, výrok. Tvrdé hrany jsou
role a jádrové relace; měkké (spoluvýskyt) se kreslí tence a jinou barvou,
aby bylo vidět, co nese pravdivost a co jen aktivaci (I‑8).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.oracle import live_or_recorded
from cb5.render import describe_node, render_statement

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "data" / "cache" / "parses.json"

TYPES = {
    "entity": dict(shape="sphere", color="#28d7fe", size=1.4),
    "group": dict(shape="box", color="#7bd389", size=1.2),
    "place": dict(shape="octahedron", color="#ffb347", size=1.3),
    "time": dict(shape="box", color="#c9c9c9", size=0.9),
    "value": dict(shape="box", color="#c9c9c9", size=0.8),
    "statement": dict(shape="sphere", color="#ff2a6d", size=0.7),
    "statement_said": dict(shape="sphere", color="#ff5fa2", size=0.8),
}


def build(session: Session, *, title: str = "conbond5", autosave: Path | None = None) -> object:
    """Plátno + konzole nad sezením. `autosave` = po každém tahu uložit paměť
    (`p.json`) a připsat tah do žurnálu (`p.jsonl`) — aby šel rozhovor
    sledovat zvenčí a přehrát."""
    import json

    import viewbase as vb  # type: ignore[import-not-found]

    canvas = vb.Canvas(title=title, theme="cyber", highlight_neighbors=1)
    for name, style in TYPES.items():
        canvas.define_type(name, **style)
    canvas.define_type("soft", color="#333333", size=0.1)

    synced_nodes: set[str] = set()
    synced_edges: set[tuple[str, str, str]] = set()

    def sync() -> None:
        m = session.memory
        g = m.graph()
        with canvas.batch():
            for nid, data in g.nodes(data=True):
                kind = data.get("kind", "group")
                t = kind
                if kind == "statement" and data.get("grade") == "said":
                    t = "statement_said"
                if t not in TYPES:
                    t = "group"
                label = data.get("label", nid)
                if kind == "statement":
                    label = m.render_short(m.statements[nid]) if nid in m.statements else label
                if kind == "statement":
                    info = render_statement(m, m.statements[nid], with_source=True) if nid in m.statements else ""
                else:
                    info = " | ".join(render_statement(m, s) for s in m.statements_about(nid)[:6])
                canvas.ensure_node(str(nid), type=t, label="{name}", name=label, kind=kind, vyroky=info)
                synced_nodes.add(str(nid))
            for a, b, data in g.edges(data=True):
                key = (str(a), str(b), str(data.get("type")))
                if key in synced_edges or a == b:
                    continue
                synced_edges.add(key)
                canvas.ensure_edge(str(a), str(b), type=str(data.get("type")), soft=bool(data.get("soft")))
            # odvolané výroky zmizí z plátna
            for sid, st in m.statements.items():
                if st.status != "active" and canvas.has_node(sid):
                    canvas.remove_node(sid)
        # aktivace = kontext
        for n in m.most_active()[:3]:
            if canvas.has_node(n.id):
                canvas.highlight(n.id, 1)

    konzole = vb.TerminalWindow("dialog", title="conbond5 — dialog", prompt="» ", width=640)

    def on_input(event: object) -> None:
        line = getattr(event, "line", "").strip()
        if not line:
            return
        canvas.terminal_write("dialog", f"» {line}")
        try:
            answer = session.say(line)
            for out in answer.text.splitlines():
                canvas.terminal_write("dialog", out)
        except Exception as exc:  # noqa: BLE001 — konzole nesmí spadnout
            canvas.terminal_write("dialog", f"✗ chyba: {exc}")
            sync()
            return
        sync()
        if autosave is not None:
            session.memory.save(autosave)
            turn = session.journal[-1]
            with autosave.with_suffix(".jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"no": turn.no, "kind": turn.kind, "text": turn.text, "doc": turn.doc, "answer": answer.text}, ensure_ascii=False) + "\n")

    canvas.detail_window(rows=[("uzel", "name"), ("druh", "kind"), ("výroky", "vyroky")], width_chars=60)

    @canvas.on_click
    def _clicked(event: object) -> None:
        nid = getattr(event, "node_id", None)
        m = session.memory
        if nid and nid in m.nodes:
            canvas.terminal_write("dialog", f"[{nid}] {describe_node(m, nid)}")
            for st in m.statements_about(nid)[:5]:
                canvas.terminal_write("dialog", "   " + render_statement(m, st, with_source=True))
        elif nid and nid in m.statements:
            canvas.terminal_write("dialog", f"[{nid}] {render_statement(m, m.statements[nid], with_source=True)}")

    canvas.open_terminal(konzole, on_input=on_input)
    canvas.terminal_write("dialog", "conbond5: piš věty (zapíšu), otázky (odpovím), !nápověda pro příkazy.")
    sync()
    return canvas


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pamet", help="JSON paměti (načte se, na konci uloží)")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    try:
        import viewbase as vb  # type: ignore[import-not-found]
    except ImportError:
        print("viewbase není nainstalované: pip install -e /Users/j/Projects/viewBase/python", file=sys.stderr)
        return 2
    memory = Memory.load(Path(args.pamet)) if args.pamet and Path(args.pamet).exists() else Memory()
    session = Session(memory, live_or_recorded(CACHE))
    canvas = build(session, autosave=Path(args.pamet) if args.pamet else None)
    try:
        vb.serve(canvas, port=args.port, open_browser=True)
    finally:
        if args.pamet:
            session.memory.save(Path(args.pamet))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
