"""CLI: konverzace nad pamětí z terminálu.

    python -m cb5 chat [--pamet p.json] [--zurnal rozhovor.jsonl] [--vazby moduly/x.txt]   # REPL: věty, otázky, !příkazy
    python -m cb5 ingest soubor.txt --dok jmeno [--pamet p.json]
    python -m cb5 ask "Kde se narodil Alois Jirásek?" --pamet p.json
    python -m cb5 replay rozhovor.jsonl [--pamet p.json]             # přehraj žurnál do čerstvé paměti

Žurnál je JSON Lines: jeden řádek na tah `{no, kind, text, doc, answer}` —
vstup i celá odpověď systému. Přehrání bere jen vstupy (deterministické
čtení ⇒ týž program), odpovědi slouží člověku jako přepis rozhovoru.

Orákulum je živá služba UDPipe (`127.0.0.1:42200`) s keší
`data/cache/parses.json`; bez služby se čte jen z keše.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.diakritika import Restorer
from cb5.oracle import live_or_recorded

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "data" / "cache" / "parses.json"


def _restorer() -> Restorer:
    return Restorer.load_or_build(HERE / "data" / "cache" / "diakritika.json", [CACHE, HERE / "tests" / "data" / "parses.json"])


def _session(pamet: str | None) -> Session:
    memory = Memory.load(Path(pamet)) if pamet and Path(pamet).exists() else Memory()
    return Session(memory, live_or_recorded(CACHE), restorer=_restorer())


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    chat = sub.add_parser("chat")
    chat.add_argument("--pamet", help="JSON paměti (načte se a při konci uloží)")
    chat.add_argument("--zurnal", help="JSONL žurnál rozhovoru: po každém tahu se připíše vstup i odpověď")
    chat.add_argument("--vazby", action="append", default=[], help="modul vazeb k načtení při startu (lze víckrát), např. moduly/cas_a_veliciny.txt")
    rep = sub.add_parser("replay")
    rep.add_argument("zurnal")
    rep.add_argument("--pamet", help="kam uložit paměť po přehrání")
    ing = sub.add_parser("ingest")
    ing.add_argument("soubor")
    ing.add_argument("--dok", required=True)
    ing.add_argument("--pamet", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("otazka")
    ask.add_argument("--pamet", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        s = _session(args.pamet)
        text = Path(args.soubor).read_text(encoding="utf-8")
        reports = s.ingest(text, args.dok)
        written = sum(1 for r in reports if r.get("statements"))
        print(f"vět: {len(reports)}, zapsáno: {written}, výroků: {len(list(s.memory.active()))}, otevřených: {len(s.memory.open_items())}")
        s.memory.save(Path(args.pamet))
        return 0
    if args.cmd == "ask":
        s = _session(args.pamet)
        print(s.say(args.otazka).text)
        return 0
    if args.cmd == "replay":
        turns = [json.loads(l) for l in Path(args.zurnal).read_text(encoding="utf-8").splitlines() if l.strip()]
        s = Session.replay(turns, live_or_recorded(CACHE))  # replay bez obnovy: žurnál už nese opravené věty
        print(f"přehráno {len(turns)} tahů: {len(list(s.memory.active()))} výroků")
        for line in s.memory.program()[-10:]:
            print("  " + line)
        if args.pamet:
            s.memory.save(Path(args.pamet))
        return 0
    s = _session(args.pamet)
    for modul in args.vazby:
        print(s.load_program(Path(modul)))
    zurnal = Path(args.zurnal) if args.zurnal else None
    print("conbond5 — piš věty (zapíšu), otázky (odpovím), !nápověda pro příkazy, prázdný řádek končí.")
    while True:
        try:
            line = input("» ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        try:
            answer = s.say(line)
            print(answer.text)
        except Exception as exc:  # noqa: BLE001 — REPL nesmí spadnout
            print(f"✗ chyba: {exc}")
            continue
        if zurnal is not None:
            turn = s.journal[-1]
            record = {"no": turn.no, "kind": turn.kind, "text": turn.text, "doc": turn.doc, "answer": answer.text}
            with zurnal.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    if args.pamet:
        s.memory.save(Path(args.pamet))
        print(f"paměť uložena do {args.pamet}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
