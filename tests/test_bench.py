"""Bench: porovnání očekávané odpovědi s výplněmi (jména, tvary, letopočty, počty)."""

from cb5.bench import answer_matches
from cb5.chronos import TimeSpec
from cb5.memory import Memory


def test_answer_matches_forms_years_counts() -> None:
    m = Memory()
    hronov = m.ensure_place(["Hronov"], ["Hronově"])
    t = m.ensure_time(TimeSpec("point", "23. 8. 1851", (1851, 8, 23), (1851, 8, 23)))
    ok, _ = answer_matches(m, ["Hronově"], [hronov.id], "")
    assert ok
    ok, _ = answer_matches(m, ["roce 1851"], [t.id], "")
    assert ok
    ok, _ = answer_matches(m, ["42"], ["count:42"], "")
    assert ok
    ok, text_ok = answer_matches(m, ["Praze"], [hronov.id], "vím: bydlet(kde: Praha)")
    assert not ok and not text_ok  # „Praze“ není v textu doslova; text_hit je přísný
    ok, text_ok = answer_matches(m, ["1930"], [], "zemřít(kdy: 12. 3. 1930)")
    assert not ok and text_ok
