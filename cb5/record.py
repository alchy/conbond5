"""Pořízení nahraných rozborů pro testy.

    python -m cb5.record tests/data/sentences.txt tests/data/parses.json

Jedna věta na řádek; prázdné řádky a řádky začínající `#` se přeskočí.
Rozbory už nahrané se nepřepisují (jsou to zlatá data — kdyby model driftl,
má to být vidět jako rozdíl při vědomém obnovení, ne tichá záměna).
"""

from __future__ import annotations

import sys
from pathlib import Path

from cb5.oracle import CachedOracle, UDPipeOracle


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    sentences = Path(argv[0]).read_text(encoding="utf-8").splitlines()
    oracle = CachedOracle(UDPipeOracle(), Path(argv[1]))
    new = 0
    for line in sentences:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        before = oracle.dirty
        oracle.parse(text)
        new += oracle.dirty - before if oracle.dirty >= before else 1
    oracle.flush()
    print(f"nahráno {new} nových rozborů do {argv[1]} ({oracle.provenance})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
