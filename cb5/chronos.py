"""Chronos — čas jako data: rozpoznání z tokenů, uspořádání, obsažení.

Proč zvláštní modul: čas je jediná veličina, kterou korpus nese na každé
druhé větě (letopočty, data, „v letech …“), a otázky „kdy“ tvoří 58 %
zlaté sady conBond2. Zároveň nechceme temporální logiku — jen **body a
intervaly na jedné ose** s primitivními predikáty `before` a `within`
(spec § 6, § 11). Specialista dodává primitiva, algebra zůstává jedna.

Rozpoznává se výhradně z tokenů rozboru (lemma, UPOS, tvar), nikdy
regexem nad textem věty — jinak by tu vznikl druhý parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from cb5.oracle import Token

Date = tuple[int, int, int]  # (rok, měsíc, den); 0 = neurčeno

MONTHS: dict[str, int] = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4, "květen": 5, "červen": 6,
    "červenec": 7, "srpen": 8, "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}
WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")
SEASONS = ("jaro", "léto", "podzim", "zima")
RELATIVE_DAYS = ("dnes", "včera", "zítra", "předevčírem", "pozítří", "letos", "loni", "vloni")
#: Substantiva, jejichž výplň v roli `v+Loc` apod. znamená ČAS, ne místo.
TIME_NOUNS = frozenset(
    {"rok", "léta", "století", "tisíciletí", "den", "měsíc", "týden", "hodina", "minuta",
     "doba", "období", "věk", "éra", "epocha", "dekáda", "desetiletí", "sezóna", "noc",
     "ráno", "večer", "poledne", "půlnoc", "začátek", "konec", "polovina", "závěr", "průběh",
     "dětství", "mládí", "stáří", "život", "válka", "středověk", "starověk", "novověk"}
    | set(MONTHS) | set(WEEKDAYS) | set(SEASONS)
)

Kind = Literal["point", "year", "interval", "name", "century"]


@dataclass(frozen=True, slots=True)
class TimeSpec:
    """Bod nebo interval na časové ose.

    `start`/`end` jsou (rok, měsíc, den) s nulou za neurčené části; u bodu
    je `end == start`. `kind=name` je pojmenovaný čas bez ukotvení
    (pondělí, včera) — porovnává se jen na rovnost jména.
    """

    kind: Kind
    label: str
    start: Date | None = None
    end: Date | None = None

    @property
    def year(self) -> int | None:
        return self.start[0] if self.start and self.start[0] else None

    def __str__(self) -> str:
        return self.label


def _year(token: Token) -> int | None:
    """Čtyřmístné (nebo tří‑) číslo bez tečky = letopočet."""
    form = token.form.strip()
    if token.upos != "NUM" or not form.isdigit():
        return None
    value = int(form)
    return value if 100 <= value <= 2999 else None


def _day(token: Token) -> int | None:
    """`23.` (řadová číslovka s tečkou) = den v měsíci."""
    form = token.form.strip()
    if token.upos == "NUM" and form.endswith(".") and form[:-1].isdigit():
        value = int(form[:-1])
        return value if 1 <= value <= 31 else None
    return None


def _fmt(d: Date) -> str:
    y, m, day = d
    if m and day:
        return f"{day}. {m}. {y}"
    if m:
        return f"{m}/{y}"
    return str(y)


def time_from_tokens(tokens: Sequence[Token]) -> TimeSpec | None:
    """Z posloupnosti tokenů (obvykle podstrom `obl` nebo obsah závorky)
    udělá `TimeSpec`, nebo `None`, když v ní čas není.

    Umí: `23. srpna 1851`, `srpen 1851`, `roku 1851`, `v roce 1851`, `1851`,
    `1851–1930` (interval), `v letech 1910–1920` / `1910 a 1920`, `ve 20.
    století`, `v pondělí`, `včera`. Vrací první rozpoznaný čas zleva.
    """
    toks = [t for t in tokens if t.upos != "PUNCT" or t.form in ("–", "-", "—")]
    lemmas = [t.lemma for t in toks]
    # pojmenované časy
    for t in toks:
        if t.lemma in WEEKDAYS or t.lemma in SEASONS or t.lemma in RELATIVE_DAYS:
            return TimeSpec("name", t.lemma)
    # století: „20. století“
    for i, t in enumerate(toks):
        if t.lemma == "století":
            for j in range(max(0, i - 2), i):
                raw = toks[j].form.rstrip(".")
                # řadová číslovka bývá i ADJ (`20.`) — rozhoduje tvar, ne UPOS
                d = int(raw) if raw.isdigit() else None
                if d and d <= 21:
                    return TimeSpec("century", f"{d}. století", ((d - 1) * 100 + 1, 0, 0), (d * 100, 0, 0))
    # posbírej data zleva: den? měsíc? rok
    dates: list[Date] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        day = _day(t)
        month = MONTHS.get(t.lemma)
        year = _year(t)
        if day is not None and i + 1 < len(toks) and MONTHS.get(toks[i + 1].lemma):
            month = MONTHS[toks[i + 1].lemma]
            y = _year(toks[i + 2]) if i + 2 < len(toks) else None
            dates.append((y or 0, month, day))
            i += 3 if y else 2
            continue
        if month is not None:
            y = _year(toks[i + 1]) if i + 1 < len(toks) else None
            if y:
                dates.append((y, month, 0))
                i += 2
                continue
        if year is not None:
            dates.append((year, 0, 0))
        i += 1
    if not dates:
        return None
    if len(dates) >= 2 and any(l in ("–", "-", "—", "a", "až", "nebo") for l in lemmas):
        a, b = dates[0], dates[1]
        joiner = "nebo" if "nebo" in lemmas else "–"
        return TimeSpec("interval", f"{_fmt(a)} {joiner} {_fmt(b)}", a, b)
    d = dates[0]
    if d[1] and d[2]:
        return TimeSpec("point", _fmt(d), d, d)
    if d[1]:
        return TimeSpec("point", _fmt(d), d, d)
    if d[0] == 0:
        return None
    return TimeSpec("year", str(d[0]), d, d)


def is_time_noun(lemma: str) -> bool:
    return lemma in TIME_NOUNS


def year_of(t: TimeSpec | None) -> int | None:
    return t.year if t else None


def _key(d: Date) -> tuple[int, int, int]:
    return (d[0], d[1] or 1, d[2] or 1)


def before(a: TimeSpec, b: TimeSpec) -> bool | None:
    """`a` celé před `b`? `None`, když nejsou srovnatelné (jména, chybí rok)."""
    if a.kind == "name" or b.kind == "name" or not a.end or not b.start:
        if a.kind == "name" and b.kind == "name" and a.label in WEEKDAYS and b.label in WEEKDAYS:
            return WEEKDAYS.index(a.label) < WEEKDAYS.index(b.label)
        return None
    if a.end[0] == 0 or b.start[0] == 0:
        return None
    return _key(a.end) < _key(b.start)


def within(a: TimeSpec, b: TimeSpec) -> bool | None:
    """Leží `a` uvnitř `b`? Rok v roce, den v roce, bod v intervalu.
    Jména jen na rovnost. `None` = nesrovnatelné."""
    if a.kind == "name" or b.kind == "name":
        return a.label == b.label if a.kind == "name" and b.kind == "name" else None
    if not (a.start and a.end and b.start and b.end):
        return None
    if a.start[0] == 0 or b.start[0] == 0:
        return None
    lo, hi = _key(b.start), (b.end[0], b.end[1] or 12, b.end[2] or 31)
    return lo <= _key(a.start) and (a.end[0], a.end[1] or 12, a.end[2] or 31) <= hi


def same(a: TimeSpec, b: TimeSpec) -> bool:
    return a.kind == b.kind and a.start == b.start and a.end == b.end and (a.kind != "name" or a.label == b.label)
