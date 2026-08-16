"""Logika: shoda dotazu s výroky přes uzávěry, NE z opačné polarity, NEVÍM s tím, co chybí."""

from pathlib import Path

import pytest

from cb5.ground import ground
from cb5.logic import enumerate_, evaluate
from cb5.memory import Memory, Provenance
from cb5.oracle import RecordedOracle
from cb5.read import read

DATA = Path(__file__).parent / "data" / "parses.json"


@pytest.fixture(scope="module")
def oracle() -> RecordedOracle:
    return RecordedOracle(DATA)


class Box:
    def __init__(self, oracle: RecordedOracle) -> None:
        self.o = oracle
        self.m = Memory()
        self.n = 0

    def say(self, *texts: str) -> None:
        for t in texts:
            self.n += 1
            ground(read(self.o.parse(t)), self.m, Provenance("t", self.n, t, self.n, "test"), "said")
            self.m.tick()

    def ask(self, text: str):
        self.n += 1
        g = ground(read(self.o.parse(text)), self.m, Provenance("t", self.n, text, self.n, "test"), write=False)
        q = g.main
        assert q is not None
        if any(r.wh for r in q.roles):
            return enumerate_(self.m, q)
        return evaluate(self.m, q)

    def labels(self, verdict) -> list[str]:
        out = []
        for t, _ in verdict.fillers:
            out.append(t if t.startswith("count:") else self.m.node(t).label())
        return out


def test_direct_and_extra_role_in_question(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Petr bydlí v Praze.")
    assert b.ask("Bydlí Petr v Praze?").value == "ANO"
    v = b.ask("Bydlí Petr v Brně?")
    assert v.value == "NEVÍM" and v.near  # ví o Praze, o Brně nic


def test_forall_distributes_down_via_subset_and_member(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Pes štěká.", "Jezevčík je pes.")
    v = b.ask("Štěká jezevčík?")
    assert v.value == "ANO"
    assert any("⊆" in step for step in v.proofs[0].steps)
    assert v.proofs[0].grade == "derived"
    assert any("generický" in d for d in v.proofs[0].defaults)


def test_no_subset_means_unknown_with_near(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Pes štěká.")
    v = b.ask("Štěká jezevčík?")
    assert v.value == "NEVÍM"


def test_negation_gives_no(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Tučňák nelétá.")
    assert b.ask("Létá tučňák?").value == "NE"


def test_syllogism_and_disjoint(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Každý spisovatel je člověk.", "Žádný stroj není člověk.", "Hrabal je spisovatel.", "Hrabal napsal Postřižiny.")
    assert b.ask("Je Hrabal člověk?").value == "ANO"
    v = b.ask("Je Hrabal stroj?")
    assert v.value == "NE" and v.counter
    w = b.ask("Napsal Postřižiny spisovatel?")
    assert w.value == "ANO"
    kdo = b.ask("Kdo napsal Postřižiny?")
    assert b.labels(kdo) == ["Hrabal"]


def test_dialog_b_what_does_not_follow(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Citron je ovoce.", "Ovoce obsahuje vitamíny.", "Vitamín C je vitamín.")
    assert b.ask("Obsahuje citron vitamín C?").value == "NEVÍM"
    assert b.ask("Obsahuje citron nějaký vitamín?").value == "ANO"
    assert b.labels(b.ask("Co obsahuje ovoce?")) == ["vitamín"]


def test_places_and_within(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Praha je v Česku.", "Petr jel v pondělí do Prahy.")
    assert b.ask("Je Praha v Česku?").value == "ANO"
    assert b.labels(b.ask("Kam jel Petr v pondělí?")) == ["Praha"]


def test_wh_where_when_count(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Alois Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha) byl český prozaik, dramatik, středoškolský učitel, a politik.",
          "Celý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.",
          "Dospělý pes má 42 zubů.")
    assert b.labels(b.ask("Kde se narodil Alois Jirásek?")) == ["Hronov"]
    assert b.labels(b.ask("Kdy zemřel Alois Jirásek?")) == ["12. 3. 1930"]
    assert set(b.labels(b.ask("Kde pracoval Alois Jirásek?"))) == {"gymnázium", "Litomyšl", "Praha"}
    assert b.labels(b.ask("Kolik zubů má dospělý pes?")) == ["count:42"]
    assert b.ask("Má dospělý pes 42 zubů?").value == "ANO"
    kdo = b.ask("Kdo je Alois Jirásek?")
    assert set(b.labels(kdo)) >= {"prozaik[český]", "dramatik", "politik"}


def test_modality(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Chov domácích zvířat může mít negativní dopad na jejich zdraví, pokud nejsou splněny určité požadavky.")
    # prostý dotaz na modální výrok → MOŽNÁ
    v = b.ask("Má chov negativní dopad?")
    assert v.value in ("MOŽNÁ", "NEVÍM")


def test_synonym_match(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Petr bydlí v Praze.")
    v = b.ask("Kde žije Petr?")
    assert b.labels(v) == ["Praha"] and any("synonymum" in s for s in v.proofs[0].steps)


def test_rule_bridges(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Petr jel v pondělí do Prahy.", "Praha je v Česku.")
    assert b.ask("Byl Petr v pondělí v Česku?").value == "NEVÍM"
    b.m.add_rule("jet", "být", {"kam": "kde"}, "kdo někam jel, tam byl")
    v = b.ask("Byl Petr v pondělí v Česku?")
    assert v.value == "ANO" and any("pravidlo" in s for s in v.proofs[0].steps)


def test_exception_narrows_forall(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Ptáci létají.", "Tučňák je pták.", "Vrabec je pták.")
    assert b.ask("Létá tučňák?").value == "ANO"
    b.say("Tučňák nelétá.")
    assert b.ask("Létá tučňák?").value == "KONFLIKT"
    ptak = b.m.find_group("pták"); tucnak = b.m.find_group("tučňák")
    assert ptak and tucnak
    b.m.add_exception("létat", ptak.id, tucnak.id)
    assert b.ask("Létá tučňák?").value == "NE"
    assert b.ask("Létá vrabec?").value == "ANO"


def test_instance_matches_group_question(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Hrabal napsal román.")
    assert b.ask("Napsal Hrabal román?").value == "ANO"
    assert b.labels(b.ask("Co napsal Hrabal?")) == ["román"]


def test_time_containment_in_question(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Alois Jirásek (23. srpna 1851 Hronov – 12. března 1930 Praha) byl český prozaik, dramatik, středoškolský učitel, a politik.")
    assert b.ask("Narodil se Jirásek v roce 1851?").value == "ANO"
    b.say("Petr bydlí v Praze.")
    assert b.ask("Bydlel Petr v Praze v roce 1990?").value == "NEVÍM"


def test_modal_question_on_modal_fact(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Chov domácích zvířat může mít negativní dopad na jejich zdraví, pokud nejsou splněny určité požadavky.")
    assert b.ask("Může chov mít negativní dopad?").value == "ANO"
    assert b.ask("Má chov negativní dopad?").value == "MOŽNÁ"


def test_definition_of_group_and_property(oracle: RecordedOracle) -> None:
    b = Box(oracle)
    b.say("Jezevčík je pes.", "Filip má auto.", "Filipovo auto je modré.")
    assert b.labels(b.ask("Co je jezevčík?")) == ["pes"]
    assert b.labels(b.ask("Jaké je Filipovo auto?")) == ["modrý"]
    co = b.ask("Co má Filip?")
    assert b.m.node(co.fillers[0][0]).lemma == "auto"
