"""Orákulum: nahrané rozbory, JSON round-trip, keš netáhne službu podruhé."""

from pathlib import Path

import pytest

from cb5.oracle import (
    CachedOracle,
    OracleError,
    Parse,
    RecordedOracle,
    Token,
    parse_from_json,
    parse_to_json,
    render_forms,
)

DATA = Path(__file__).parent / "data" / "parses.json"


@pytest.fixture(scope="session")
def oracle() -> RecordedOracle:
    return RecordedOracle(DATA)


def test_recorded_parse_has_root_and_provenance(oracle: RecordedOracle) -> None:
    parse = oracle.parse("Petr bydlí v Praze.")
    assert parse.root().lemma == "bydlet"
    assert parse.provenance.startswith("udpipe2")
    assert [t.form for t in parse.tokens] == ["Petr", "bydlí", "v", "Praze", "."]


def test_missing_sentence_explains_how_to_record(oracle: RecordedOracle) -> None:
    with pytest.raises(KeyError, match="cb5.record"):
        oracle.parse("Tahle věta v nahrávce není.")


def test_json_round_trip(oracle: RecordedOracle) -> None:
    parse = oracle.parse("Petr bydlí v Praze.")
    again = parse_from_json(parse_to_json(parse))
    assert again == parse


def test_children_subtree_path(oracle: RecordedOracle) -> None:
    parse = oracle.parse("Alois Jirásek se narodil ve východočeském Hronově u Náchoda.")
    root = parse.root()
    kids = [t.deprel for t in parse.children(root.index)]
    assert "nsubj" in kids and "obl" in kids
    hronov = next(t for t in parse.tokens if t.lemma == "Hronov")
    assert {t.form for t in parse.subtree(hronov.index)} == {"ve", "východočeském", "Hronově", "u", "Náchoda"}
    nachod = next(t for t in parse.tokens if t.lemma == "Náchod")
    assert parse.path(nachod.index) == "obl>nmod"


def test_cached_oracle_calls_inner_once(tmp_path: Path) -> None:
    calls: list[str] = []

    class Fake:
        provenance = "udpipe2 model=test tokenizer=x"

        def parse(self, text: str) -> Parse:
            calls.append(text)
            return Parse(text=text, tokens=(Token(1, "Ahoj", "ahoj", "INTJ", 0, "root"),), provenance=self.provenance)

    cache = CachedOracle(Fake(), tmp_path / "c.json")  # type: ignore[arg-type]
    cache.parse("Ahoj")
    cache.parse("Ahoj")
    cache.flush()
    assert calls == ["Ahoj"]
    reloaded = RecordedOracle(tmp_path / "c.json")
    assert reloaded.parse("Ahoj").root().lemma == "ahoj"


def test_render_forms_no_space_before_punct() -> None:
    toks = (Token(1, "Pes", "pes", "NOUN", 2, "nsubj"), Token(2, "štěká", "štěkat", "VERB", 0, "root"), Token(3, ".", ".", "PUNCT", 2, "punct"))
    assert render_forms(toks) == "Pes štěká."


def test_parse_without_root_is_error() -> None:
    p = Parse("x", (Token(1, "x", "x", "X", 5, "dep"),), "p")
    with pytest.raises(OracleError):
        p.root()
