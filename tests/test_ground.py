"""Zakotvení: identita, koreference aktivací, instance z neurčité zmínky, otevřené položky."""

from pathlib import Path

import pytest

from cb5.ground import ground
from cb5.memory import Memory, Provenance
from cb5.oracle import RecordedOracle
from cb5.read import read

DATA = Path(__file__).parent / "data" / "parses.json"


@pytest.fixture(scope="module")
def oracle() -> RecordedOracle:
    return RecordedOracle(DATA)


def put(m: Memory, oracle: RecordedOracle, text: str, no: int = 1, *, topic: str | None = None, grade: str = "read"):
    g = ground(read(oracle.parse(text)), m, Provenance("t", no, text, no, "test"), grade, topic=topic)
    m.tick()
    return g


def test_simple_statement_written(oracle: RecordedOracle) -> None:
    m = Memory()
    g = put(m, oracle, "Petr bydlí v Praze.")
    st = g.main
    assert st is not None and st.id == "s0001" and st.pred == "bydlet" and st.grade == "read"
    kdo, kde = st.role("kdo"), st.role("kde")
    assert kdo and m.node(kdo.terms[0]).kind == "entity" and m.node(kdo.terms[0]).names[0] == "Petr"
    assert kde and m.node(kde.terms[0]).kind == "place" and kde.authority == "default"
    assert st.sentence.startswith("z") and m.node(st.sentence).text == "Petr bydlí v Praze."


def test_partial_name_merges_into_same_entity(oracle: RecordedOracle) -> None:
    m = Memory()
    g1 = put(m, oracle, "Alois Jirásek se narodil ve východočeském Hronově u Náchoda.", 1)
    g2 = put(m, oracle, "Jirásek zemřel v Praze.", 2)
    e1 = g1.main.role("kdo").terms[0]  # type: ignore[union-attr]
    e2 = g2.main.role("kdo").terms[0]  # type: ignore[union-attr]
    assert e1 == e2
    assert any("částečné jméno" in d for d in g2.main.defaults)  # type: ignore[union-attr]


def test_prodrop_resolves_by_activation(oracle: RecordedOracle) -> None:
    m = Memory()
    g1 = put(m, oracle, "Alois Jirásek se narodil ve východočeském Hronově u Náchoda.", 1)
    g2 = put(m, oracle, "Celý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.", 2)
    jir = g1.main.role("kdo").terms[0]  # type: ignore[union-attr]
    kdo = g2.main.role("kdo")  # type: ignore[union-attr]
    assert kdo and kdo.terms == [jir]
    assert any("nevyslovený podmět" in d and "aktivace" in d for d in g2.main.defaults)  # type: ignore[union-attr]
    kde = g2.main.role("kde")  # type: ignore[union-attr]
    assert kde and {m.node(x).label() for x in kde.terms} == {"gymnázium", "Litomyšl", "Praha"}


def test_pronoun_and_topic_fallback(oracle: RecordedOracle) -> None:
    m = Memory()
    put(m, oracle, "Alois Jirásek se narodil ve východočeském Hronově u Náchoda.", 1)
    g = put(m, oracle, "On se oženil.", 2)
    assert m.node(g.main.role("kdo").terms[0]).names[0] == "Alois Jirásek"  # type: ignore[union-attr]
    m2 = Memory()
    topic = m2.ensure_entity(["Božena", "Němcová"], gender="Fem", number="Sing")[0]
    g3 = put(m2, oracle, "Oženil se v roce 1879.", 1, topic=topic.id)
    assert g3.main.role("kdo").terms == [topic.id]  # type: ignore[union-attr]
    assert any("téma dokumentu" in d for d in g3.main.defaults)  # type: ignore[union-attr]
    m3 = Memory()
    g4 = put(m3, oracle, "Oženil se v roce 1879.", 1)
    assert g4.main.role("kdo").terms == []  # type: ignore[union-attr]
    assert any(o.kind == "reference" for o in g4.open)


def test_surface_role_opens_item(oracle: RecordedOracle) -> None:
    m = Memory()
    g = put(m, oracle, "Vesmír se rozšířil do dnešní podoby.")
    assert any(o.kind == "role_name" and o.about == "do+Gen" for o in g.open)
    assert m.open_items()


def test_indefinite_object_instantiates(oracle: RecordedOracle) -> None:
    m = Memory()
    g = put(m, oracle, "Filip má auto.")
    co = g.main.role("co")  # type: ignore[union-attr]
    inst = m.node(co.terms[0])
    assert inst.kind == "entity" and inst.lemma == "auto"
    auto = m.find_group("auto")
    assert auto and m.member_star(inst.id, auto.id) is not None
    g2 = put(m, oracle, "Filipovo auto je modré.", 2)
    assert g2.main.role("kdo").terms == [inst.id]  # type: ignore[union-attr]
    assert any("vlastník Filip" in d for d in g2.main.defaults)  # type: ignore[union-attr]


def test_generic_subject_does_not_instantiate(oracle: RecordedOracle) -> None:
    m = Memory()
    g = put(m, oracle, "Ovoce obsahuje vitamíny.")
    co = g.main.role("co")  # type: ignore[union-attr]
    assert m.node(co.terms[0]).kind == "group"


def test_question_does_not_write(oracle: RecordedOracle) -> None:
    m = Memory()
    put(m, oracle, "Petr bydlí v Praze.")
    before = len(m.statements)
    g = ground(read(oracle.parse("Bydlí Petr v Brně?")), m, Provenance("t", 2, "?", 2, "test"), write=False)
    assert len(m.statements) == before and g.main is not None and g.main.id == ""
    assert g.main.role("kde") is not None


def test_bio_and_copula_written(oracle: RecordedOracle) -> None:
    m = Memory()
    g = put(m, oracle, "Alois Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha) byl český prozaik, dramatik, středoškolský učitel, a politik.")
    preds = sorted(s.pred for s in g.statements)  # type: ignore[type-var]
    assert preds == ["být", "narodit_se", "zemřít"]
    byt = next(s for s in g.statements if s.pred == "být")
    assert byt.kernel == "member" and len(byt.role("co").terms) == 4  # type: ignore[union-attr]
    jir = byt.role("kdo").terms[0]  # type: ignore[union-attr]
    proz = m.find_group("prozaik", ("český",))
    assert proz and m.member_star(jir, proz.id) == [byt.id]
    assert m.member_star(jir, m.find_group("prozaik").id) is not None  # type: ignore[union-attr]
