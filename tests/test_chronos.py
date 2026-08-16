"""Chronos: rozpoznání času z tokenů, uspořádání, obsažení."""

from pathlib import Path

import pytest

from cb5.chronos import TimeSpec, before, is_time_noun, time_from_tokens, within, year_of
from cb5.oracle import RecordedOracle, Token

DATA = Path(__file__).parent / "data" / "parses.json"


def T(form: str, lemma: str | None = None, upos: str = "NUM") -> Token:
    return Token(1, form, lemma or form, upos, 0, "dep")


def test_full_date() -> None:
    t = time_from_tokens([T("23."), T("srpna", "srpen", "NOUN"), T("1851")])
    assert t == TimeSpec("point", "23. 8. 1851", (1851, 8, 23), (1851, 8, 23))


def test_roku_and_v_roce() -> None:
    assert time_from_tokens([T("roku", "rok", "NOUN"), T("1851")]).year == 1851
    t = time_from_tokens([T("v", "v", "ADP"), T("roce", "rok", "NOUN"), T("1851")])
    assert t is not None and t.kind == "year" and t.label == "1851"


def test_bare_year_and_month_year() -> None:
    assert time_from_tokens([T("1851")]).kind == "year"
    t = time_from_tokens([T("v", "v", "ADP"), T("srpnu", "srpen", "NOUN"), T("1851")])
    assert t is not None and t.start == (1851, 8, 0)


def test_interval_and_alternative() -> None:
    t = time_from_tokens([T("1851"), T("–", "–", "PUNCT"), T("1930")])
    assert t is not None and t.kind == "interval" and t.start == (1851, 0, 0) and t.end == (1930, 0, 0)
    t2 = time_from_tokens([T("v", "v", "ADP"), T("letech", "léta", "NOUN"), T("1910"), T("nebo", "nebo", "CCONJ"), T("1920")])
    assert t2 is not None and "nebo" in t2.label


def test_named_and_century() -> None:
    assert time_from_tokens([T("v", "v", "ADP"), T("pondělí", "pondělí", "NOUN")]) == TimeSpec("name", "pondělí")
    c = time_from_tokens([T("ve", "v", "ADP"), T("20.", "20.", "ADJ"), T("století", "století", "NOUN")])
    assert c is not None and c.kind == "century" and c.start == (1901, 0, 0)


def test_no_time() -> None:
    assert time_from_tokens([T("Praze", "Praha", "PROPN")]) is None
    assert time_from_tokens([T("42")]) is None  # číslo bez letopočtu není čas


def test_before_within() -> None:
    a = time_from_tokens([T("23."), T("srpna", "srpen", "NOUN"), T("1851")])
    b = time_from_tokens([T("1930")])
    y = time_from_tokens([T("1851")])
    assert a and b and y
    assert before(a, b) is True and before(b, a) is False
    assert within(a, y) is True and within(y, a) is False
    assert before(TimeSpec("name", "pondělí"), TimeSpec("name", "úterý")) is True
    assert before(TimeSpec("name", "včera"), y) is None
    assert year_of(a) == 1851


def test_time_nouns() -> None:
    assert is_time_noun("rok") and is_time_noun("pondělí") and not is_time_noun("Praha")


def test_from_real_parse() -> None:
    parse = RecordedOracle(DATA).parse("Petr jel v pondělí do Prahy.")
    pondeli = next(t for t in parse.tokens if t.lemma == "pondělí")
    assert time_from_tokens(parse.subtree(pondeli.index)) == TimeSpec("name", "pondělí")
