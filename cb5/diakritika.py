"""Obnova diakritiky před rozborem — z toho, co už systém četl.

Proč: UDPipe je natrénovaný na správné češtině; „Pes ji maso.“ bez háčků
dá `ji`/`maso` jako `dep` a z „bydli“ lemma *bydnout*. Když je věta celá
bez diakritiky, zkusíme ji doplnit **z keše rozborů** (tvary, které
parser už viděl s háčky) — je to výchozí volba, hlásí se v odpovědi
(„doplnil jsem diakritiku: bydli → bydlí“) a nikdy se neaplikuje na větu,
která už nějaký háček má.

Slovník: složený tvar (bez diakritiky, malými písmeny) → nejčastější
původní tvar. Staví se z JSON keše rozborů (`data/cache/parses.json`,
`tests/data/parses.json`) a ukládá do `data/cache/diakritika.json`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable

_WORD = re.compile(r"[A-Za-zÀ-ž]+")
_DIACRITICS = "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"


def fold(word: str) -> str:
    """„bydlí“ → „bydli“ (NFKD bez kombinačních znaků, malá písmena)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", word) if not unicodedata.combining(ch)).lower()


def has_diacritics(text: str) -> bool:
    return any(ch in _DIACRITICS for ch in text)


class Restorer:
    """Slovník složený tvar → tvar s diakritikou; `restore(text)`."""

    def __init__(self, table: dict[str, str] | None = None) -> None:
        self.table: dict[str, str] = dict(table or {})

    @classmethod
    def from_parses(cls, paths: Iterable[Path], *, save_to: Path | None = None) -> "Restorer":
        counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for path in paths:
            if not Path(path).exists():
                continue
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for key, entry in data.items():
                parses = entry.get("parts", [entry]) if isinstance(entry, dict) else []
                for parse in parses:
                    for tok in parse.get("tokens", []):
                        form = str(tok.get("form", ""))
                        if not _WORD.fullmatch(form):
                            continue
                        f = fold(form)
                        if f != form.lower():
                            counts[f][form.lower()] += 1.0
                        else:
                            counts[f][form.lower()] += 0.5  # tvar bez háčků existuje také — počítá se slaběji
        table = {f: max(c.items(), key=lambda kv: kv[1])[0] for f, c in counts.items() if c}
        r = cls(table)
        if save_to is not None:
            save_to.parent.mkdir(parents=True, exist_ok=True)
            save_to.write_text(json.dumps(table, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return r

    @classmethod
    def load_or_build(cls, cache: Path, sources: Iterable[Path]) -> "Restorer":
        if cache.exists():
            return cls(json.loads(cache.read_text(encoding="utf-8")))
        return cls.from_parses(sources, save_to=cache)

    def restore(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Doplní diakritiku slovům věty bez háčků. Vrací (text, změny).
        Věta s aspoň jedním háčkem se nemění (nemá smysl hádat)."""
        if has_diacritics(text) or not self.table:
            return text, []
        changes: list[tuple[str, str]] = []

        def fix(m: re.Match[str]) -> str:
            w = m.group(0)
            best = self.table.get(w.lower())
            if best is None or best == w.lower():
                return w
            out = best.capitalize() if w[:1].isupper() and not w.isupper() else (best.upper() if w.isupper() else best)
            if out != w:
                changes.append((w, out))
            return out

        return _WORD.sub(fix, text), changes
