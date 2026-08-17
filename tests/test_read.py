"""Čtení: predikace, role, negace, modalita, kopula, fragment, závorka, zbytek.

Každý test navíc drží pojistku „nic se neztrácí“: každý token má právě
jedno místo v `placement()`.
"""

from pathlib import Path

import pytest

from cb5.oracle import RecordedOracle
from cb5.read import Predication, Reading, read

DATA = Path(__file__).parent / "data" / "parses.json"
SENTENCES = Path(__file__).parent / "data" / "sentences.txt"


@pytest.fixture(scope="module")
def oracle() -> RecordedOracle:
    return RecordedOracle(DATA)


def R(oracle: RecordedOracle, text: str) -> Reading:
    r = read(oracle.parse(text))
    placed = r.placement()
    missing = [t.form for t in r.parse.tokens if t.index not in placed]
    assert not missing, f"tokeny bez místa: {missing}"
    return r


def terms(p: Predication, role: str) -> list[str]:
    r = p.role(role)
    assert r is not None, f"role {role} chybí v {p}"
    return [t.label() for t in r.terms]


def test_simple_verb_with_place(oracle: RecordedOracle) -> None:
    r = R(oracle, "Petr bydlí v Praze.")
    m = r.main
    assert m.pred == "bydlet" and m.kind == "verb" and not m.neg and m.mood == "assert"
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].kind == "entity" and kdo.terms[0].quant == "·"
    kde = m.role("kde")
    assert kde and kde.surface == "v+Loc" and kde.authority == "default" and kde.terms[0].kind == "place"
    assert r.residue == []


def test_reflexive_and_nmod_secondary(oracle: RecordedOracle) -> None:
    r = R(oracle, "Alois Jirásek se narodil ve východočeském Hronově u Náchoda.")
    m = r.main
    assert m.pred == "narodit_se"
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].name_lemmas == ("Alois", "Jirásek") and kdo.terms[0].name_tokens == (1, 2)
    kde = m.role("kde")
    assert kde and kde.terms[0].lemma == "Hronov" and kde.terms[0].attrs == ("východočeský",)
    assert r.residue == []
    assert any(s.kind == "nmod" and s.pred == "nmod:u+Gen" for s in m.secondary)


def test_negation_and_generic_quantifier(oracle: RecordedOracle) -> None:
    m = R(oracle, "Tučňák nelétá.").main
    assert m.pred == "létat" and m.neg
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].quant == "∀" and kdo.terms[0].quant_authority.startswith("default")
    assert any("generický" in d for d in m.defaults)


def test_modality_advcl_and_negated_aux(oracle: RecordedOracle) -> None:
    r = R(oracle, "Chov domácích zvířat může mít negativní dopad na jejich zdraví, pokud nejsou splněny určité požadavky.")
    m = r.main
    assert m.pred == "mít" and m.modality == "možnost"
    assert [t.lemma for t in m.role("kdo").terms] == ["chov"] and m.role("kdo").terms[0].rel is not None  # type: ignore[union-attr]
    co = m.role("co")
    assert co and co.terms[0].lemma == "dopad" and co.terms[0].attrs == ("negativní",)
    adv = m.role("podmínka")  # „pokud …“ = podmínka (věta pod ní se netvrdí)
    assert adv and adv.nested is not None and adv.nested.pred == "splněný" and adv.nested.neg and adv.nested.embedded == "podmínka"
    assert terms(adv.nested, "co") == ["požadavek"]
    assert r.residue == []
    kinds = {s.pred for s in m.secondary}
    assert "nmod:na+Acc" in kinds  # genitiv „domácích zvířat“ je teď zúžení třídy chov⟨zvíře⟩, ne výrok vedle věty


def test_time_name_and_direction(oracle: RecordedOracle) -> None:
    m = R(oracle, "Petr jel v pondělí do Prahy.").main
    kdy = m.role("kdy")
    assert kdy and kdy.terms[0].kind == "time" and kdy.terms[0].time is not None and kdy.terms[0].time.label == "pondělí"
    assert terms(m, "kam") == ["Praha"]


def test_count(oracle: RecordedOracle) -> None:
    m = R(oracle, "Dospělý pes má 42 zubů.").main
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].lemma == "pes" and kdo.terms[0].attrs == ("dospělý",) and kdo.terms[0].quant == "∀"
    co = m.role("co")
    assert co and co.terms[0].lemma == "zub" and co.terms[0].count == 42 and co.terms[0].quant == "∃"


def test_prodrop_and_coordinated_places(oracle: RecordedOracle) -> None:
    r = R(oracle, "Celý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.")
    m = r.main
    assert m.pred == "pracovat"
    kdo = m.role("kdo")
    assert kdo and kdo.authority == "prodrop" and kdo.terms[0].kind == "pron" and kdo.terms[0].gender == "Masc"
    assert set(terms(m, "kde")) == {"gymnázium", "Litomyšl", "Praha"}
    assert [t.lemma for t in m.role("jako").terms] == ["učitel"]  # type: ignore[union-attr]
    assert m.role("jak_dlouho") is not None
    assert r.residue == []


def test_questions_have_holes(oracle: RecordedOracle) -> None:
    m = R(oracle, "Kde se narodil Alois Jirásek?").main
    assert m.mood == "question"
    kde = m.role("kde")
    assert kde and kde.wh and kde.wh_kind == "filler" and kde.terms == []
    m2 = R(oracle, "Kolik zubů má dospělý pes?").main
    co = m2.role("co")
    assert co and co.wh and co.wh_kind == "count" and co.terms[0].lemma == "zub"
    m3 = R(oracle, "Kdy se narodil Isaac Newton?").main
    assert m3.role("kdy") is not None and m3.role("kdy").wh  # type: ignore[union-attr]


def test_yes_no_question_keeps_all_roles(oracle: RecordedOracle) -> None:
    m = R(oracle, "Bydlí Petr v Brně?").main
    assert m.mood == "question" and terms(m, "kdo") == ["Petr"] and terms(m, "kde") == ["Brno"]


def test_case_ambiguity_subject(oracle: RecordedOracle) -> None:
    m = R(oracle, "Obsahuje citron vitamín C?").main
    assert terms(m, "kdo") == ["citron"] and terms(m, "co") == ["vitamín C"]
    assert any("dvojznačnost" in d for d in m.defaults)


# ---- kopula, fragment, závorka ----------------------------------------------


def test_copula_subset(oracle: RecordedOracle) -> None:
    m = R(oracle, "Jezevčík je pes.").main
    assert m.kind == "copula" and m.pred == "být" and m.kernel == "subset"
    assert terms(m, "kdo") == ["jezevčík"] and terms(m, "co") == ["pes"]
    assert m.role("kdo").terms[0].quant == "∀"  # type: ignore[union-attr]


def test_copula_question_with_nmod_wobble(oracle: RecordedOracle) -> None:
    m = R(oracle, "Je jezevčík pes?").main
    assert m.mood == "question" and m.kernel == "subset"
    assert terms(m, "kdo") == ["jezevčík"] and terms(m, "co") == ["pes"]


def test_copula_determiners(oracle: RecordedOracle) -> None:
    m = R(oracle, "Každý spisovatel je člověk.").main
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].quant == "∀" and kdo.terms[0].quant_authority == "determiner"
    n = R(oracle, "Žádný stroj není člověk.").main
    assert n.neg and n.kernel == "subset" and n.role("kdo").terms[0].quant == "∀"  # type: ignore[union-attr]


def test_copula_within_and_member(oracle: RecordedOracle) -> None:
    m = R(oracle, "Praha je v Česku.").main
    assert m.kernel == "within" and terms(m, "kde") == ["Česko"]
    h = R(oracle, "Hrabal je spisovatel.").main
    assert h.kernel == "member" and terms(h, "kdo") == ["Hrabal"]


def test_bio_parenthesis(oracle: RecordedOracle) -> None:
    r = R(oracle, "Alois Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha) byl český prozaik, dramatik, středoškolský učitel, a politik.")
    m = r.main
    assert m.kernel == "member"
    assert terms(m, "co") == ["prozaik", "dramatik", "učitel", "politik"]
    assert m.role("co").terms[0].attrs == ("český",)  # type: ignore[union-attr]
    preds = {s.pred: s for s in m.secondary}
    assert set(preds) == {"narodit_se", "zemřít"}
    n = preds["narodit_se"]
    assert terms(n, "kdo") == ["Alois Jirásek"] and terms(n, "kde") == ["Hronov"]
    assert n.role("kdy").terms[0].time.start == (1851, 8, 23)  # type: ignore[union-attr]
    z = preds["zemřít"]
    assert terms(z, "kde") == ["Praha"] and z.role("kdy").terms[0].time.start == (1930, 3, 12)  # type: ignore[union-attr]
    assert "životopisná závorka" in n.defaults
    assert r.residue == []


def test_bio_parenthesis_dates_only(oracle: RecordedOracle) -> None:
    r = R(oracle, "Isaac Newton (4. ledna 1643 – 31. března 1727) byl anglický fyzik, matematik, astronom, alchymista a teolog.")
    preds = {s.pred: s for s in r.main.secondary}
    assert preds["narodit_se"].role("kdy").terms[0].time.year == 1643  # type: ignore[union-attr]
    assert preds["zemřít"].role("kdy").terms[0].time.year == 1727  # type: ignore[union-attr]
    assert terms(r.main, "co") == ["fyzik", "matematik", "astronom", "alchymista", "teolog"]
    assert r.residue == []


def test_definition_question(oracle: RecordedOracle) -> None:
    m = R(oracle, "Kdo je Isaac Newton?").main
    assert m.kind == "copula" and m.mood == "question"
    assert terms(m, "kdo") == ["Isaac Newton"]
    co = m.role("co")
    assert co and co.wh


def test_fragment_with_participle(oracle: RecordedOracle) -> None:
    r = R(oracle, "Úrazy způsobené pády.")
    assert r.main.kind == "fragment" and r.main.pred is None
    assert terms(r.main, "téma") == ["úraz"]
    sec = r.main.secondary[0]
    assert sec.pred == "způsobený" and terms(sec, "co") == ["úraz"] and terms(sec, "čím") == ["pád"]


def test_coordinated_predicates_share_subject(oracle: RecordedOracle) -> None:
    r = R(oracle, "Petr přišel a sedl si.")
    assert r.main.pred == "přijít" and terms(r.main, "kdo") == ["Petr"]
    assert r.main.secondary and r.main.secondary[0].pred.startswith("sednout") and terms(r.main.secondary[0], "kdo") == ["Petr"]


def test_possessive_and_correction_marker(oracle: RecordedOracle) -> None:
    m = R(oracle, "Filipovo auto je modré.").main
    kdo = m.role("kdo")
    assert kdo and kdo.terms[0].possessor == ("adj", "Filipův") and kdo.terms[0].quant == "·"
    assert terms(m, "jaký") == ["modrý"]
    n = R(oracle, "Ne, Petr bydlí v Brně.").main
    assert n.correction and not n.neg


def test_every_recorded_sentence_reads_and_places_all_tokens(oracle: RecordedOracle) -> None:
    lines = [l.strip() for l in SENTENCES.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    for text in lines:
        R(oracle, text)
