"""CLI: konverzace nad pamětí z terminálu.

    python -m cb5 chat [--pamet p.json]            # REPL: věty, otázky, !příkazy
    python -m cb5 ingest soubor.txt --dok jmeno [--pamet p.json]
    python -m cb5 ask "Kde se narodil Alois Jirásek?" --pamet p.json

Orákulum je živá služba UDPipe (`127.0.0.1:42200`) s keší
`data/cache/parses.json`; bez služby se čte jen z keše.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.oracle import live_or_recorded

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "data" / "cache" / "parses.json"


def _session(pamet: str | None) -> Session:
    memory = Memory.load(Path(pamet)) if pamet and Path(pamet).exists() else Memory()
    return Session(memory, live_or_recorded(CACHE))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    chat = sub.add_parser("chat")
    chat.add_argument("--pamet", help="JSON paměti (načte se a při konci uloží)")
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
    s = _session(args.pamet)
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
            print(s.say(line).text)
        except Exception as exc:  # noqa: BLE001 — REPL nesmí spadnout
            print(f"✗ chyba: {exc}")
    if args.pamet:
        s.memory.save(Path(args.pamet))
        print(f"paměť uložena do {args.pamet}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
