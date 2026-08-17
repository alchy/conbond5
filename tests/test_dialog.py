"""Dialog: vkládání, otázky, opravy, backlog, příkazy, propad, render, replay."""

from pathlib import Path

import pytest

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.oracle import RecordedOracle
from cb5.recall import recall

DATA = Path(__file__).parent / "data" / "parses.json"


@pytest.fixture()
def s() -> Session:
    return Session(Memory(), RecordedOracle(DATA))


def test_ingest_then_ask_with_source(s: Session) -> None:
    reps = s.ingest("Alois Jirásek se narodil ve východočeském Hronově u Náchoda.\nCelý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.", "alois_jirásek")
    assert len(reps) == 2 and all(r["statements"] for r in reps)
    a = s.say("Kde se narodil Alois Jirásek?")
    assert a.verdict is not None and a.verdict.value == "ANO"
    assert "Hronov" in a.text and "zdroj: „Alois Jirásek se narodil" in a.text and "alois_jirásek, věta 1" in a.text
    b = s.say("Kde pracoval Alois Jirásek?")
    assert "Litomyšl" in b.text and "Praha" in b.text and "nevyslovený podmět" in b.text


def test_unknown_stays_unknown_and_correction(s: Session) -> None:
    s.say("Petr bydlí v Praze.")
    a = s.say("Bydlí Petr v Brně?")
    assert a.verdict is not None and a.verdict.value == "NEVÍM" and "vím:" in a.text and "Praha" in a.text
    c = s.say("Ne, Petr bydlí v Brně.")
    assert c.revoked == ["s0001"] and c.statements
    assert "Brno" in s.say("Kde bydlí Petr?").text
    assert s.memory.statements["s0001"].status == "revoked"


def test_denial_revokes_last(s: Session) -> None:
    s.say("Pes štěká.")
    a = s.say("To není pravda.")
    assert a.revoked == ["s0001"]
    assert s.say("Štěká pes?").verdict.value == "NEVÍM"  # type: ignore[union-attr]


def test_conflict_is_reported_and_exception_narrows(s: Session) -> None:
    s.say("Ptáci létají.")
    s.say("Tučňák je pták.")
    assert s.say("Létá tučňák?").verdict.value == "ANO"  # type: ignore[union-attr]
    a = s.say("Tučňák nelétá.")
    assert a.conflict is not None and "odporuje" in a.text
    assert s.say("Létá tučňák?").verdict.value == "KONFLIKT"  # type: ignore[union-attr]
    assert "výjimka" in s.say("!výjimka létat pták tučňák").text
    assert s.say("Létá tučňák?").verdict.value == "NE"  # type: ignore[union-attr]
    s.say("Vrabec je pták.")
    assert s.say("Létá vrabec?").verdict.value == "ANO"  # type: ignore[union-attr]


def test_role_learning_closes_open_item(s: Session) -> None:
    a = s.say("Vesmír se rozšířil do dnešní podoby.")
    assert any(o.kind == "role_name" and o.about == "do+Gen" for o in a.open)
    assert "o0001" in s.say("!otevřené").text
    r = s.say("!role do+Gen = kam")
    assert "přejmenováno v 1" in r.text
    assert s.say("!otevřené").text == "žádné otevřené položky"
    st = s.memory.statements["s0001"]
    assert st.role("kam") is not None


def test_rule_command_bridges(s: Session) -> None:
    s.say("Petr jel v pondělí do Prahy.")
    s.say("Praha je v Česku.")
    assert s.say("Byl Petr v pondělí v Česku?").verdict.value == "NEVÍM"  # type: ignore[union-attr]
    assert "pravidlo r0001" in s.say("!pravidlo jet(kam:X) => být(kde:X)").text
    a = s.say("Byl Petr v pondělí v Česku?")
    assert a.verdict.value == "ANO" and "pravidlo r0001" in a.text  # type: ignore[union-attr]


def test_synonym_command(s: Session) -> None:
    s.say("Hrabal napsal Postřižiny.")
    s.say("!synonymum napsat = stvořit")
    from cb5.defaults import synonym_class
    assert synonym_class("stvořit", s.memory.learned["synonyms"]) == synonym_class("napsat")
    assert synonym_class("stvořit") != synonym_class("napsat")  # bez paměti nic
    assert s.say("Kdo stvořil Postřižiny?").verdict.value == "ANO"  # type: ignore[union-attr]


def test_quantifier_fix(s: Session) -> None:
    s.say("Ptáci létají.")
    a = s.say("Ne každý pták.")
    assert "∀ → ∃" in s.memory.statements["s0001"].defaults[-1]
    s.say("Tučňák je pták.")
    assert s.say("Létá tučňák?").verdict.value == "NEVÍM"  # type: ignore[union-attr]


def test_recall_returns_related(s: Session) -> None:
    s.say("Alois Jirásek se narodil ve východočeském Hronově u Náchoda.")
    s.say("Jirásek zemřel v Praze.")
    jir = s.memory.find_entity(["Jirásek"])[0]
    got = recall(s.memory, [jir.id], 2)
    assert len(got) == 2 and {g.pred for g in got} == {"narodit_se", "zemřít"}


def test_program_save_load_and_graph(s: Session, tmp_path: Path) -> None:
    s.say("Jezevčík je pes.")
    assert "s0001" in s.say("!program").text
    assert "uloženo" in s.say(f"!ulož {tmp_path / 'm.json'}").text
    s2 = Session(Memory.load(tmp_path / "m.json"), RecordedOracle(DATA))
    assert s2.say("Je jezevčík pes?").verdict.value == "ANO"  # type: ignore[union-attr]
    assert "uzlů" in s.say(f"!graf {tmp_path / 'g.json'}").text


def test_replay_gives_same_program(s: Session) -> None:
    s.ingest("Alois Jirásek se narodil ve východočeském Hronově u Náchoda.\nCelý život pracoval jako učitel dějepisu na gymnáziu, nejprve v Litomyšli a poté v Praze.", "alois_jirásek")
    s.say("Petr bydlí v Praze.")
    s.say("Ne, Petr bydlí v Brně.")
    s.say("Kde bydlí Petr?")
    s.say("!role do+Gen = kam")
    again = Session.replay(s.journal_json(), RecordedOracle(DATA))
    assert again.memory.program() == s.memory.program()
    assert again.memory.to_json()["statements"] == s.memory.to_json()["statements"]


def test_unknown_name_read_as_class_then_as_name(s: Session) -> None:
    """„Ronik je pes.“ čte parser jako třídu (ronik), „Je Ronik pes?“ jako jméno — musí se potkat."""
    s.say("Ronik je pes.")
    a = s.say("Je Ronik pes?")
    assert a.verdict is not None and a.verdict.value == "ANO"
    s.say("Ronik bydlí v Petrovicích.")
    assert "Petrovice" in s.say("Kde bydlí Ronik?").text
    r = s.say("zapomeň Ronik")  # příkaz i bez „!“
    assert "odvoláno" in r.text
    assert s.say("Kde bydlí Ronik?").verdict.value == "NEVÍM"  # type: ignore[union-attr]


def test_age_pattern(s: Session) -> None:
    s.say("Ronikovi je 17 let.")
    a = s.say("Kolik je Ronikovi let?")
    assert a.verdict is not None and a.verdict.fillers and a.verdict.fillers[0][0] == "count:17"


def test_diacritics_restored_and_noise_refused() -> None:
    from cb5.diakritika import Restorer, fold
    assert fold("bydlí") == "bydli"
    r = Restorer({"ji": "jí", "bydli": "bydlí", "pes": "pes"})
    s = Session(Memory(), RecordedOracle(DATA), restorer=r)
    a = s.say("Pes ji maso.")
    assert "doplnil jsem diakritiku: ji → jí" in a.text and a.statements
    assert s.memory.statements[a.statements[0]].pred == "jíst"
    assert any("diakritika doplněna" in d for d in s.memory.statements[a.statements[0]].defaults)
    # šum bez predikátu se nezapíše a řekne to
    b = Session(Memory(), RecordedOracle(DATA))
    n = b.say("Pes ji maso.")
    assert n.text.startswith("✗ nerozumím") and not n.statements and not list(b.memory.active())


def test_coordinated_subject_case_ambiguity_and_comparison(s: Session) -> None:
    s.say("Pavla se narodila v roce 1978.")
    s.say("Jindřich se narodil v roce 1975.")
    s.say("Pavla a Jindřich mají syna Matěje.")
    a = s.say("Koho má Pavla?")  # „Pavla“ čte parser jako Acc od Pavel — musí se najít podle tvaru
    assert a.verdict is not None and [s.memory.label(t) for t, _ in a.verdict.fillers] == ["Matěj"]
    assert s.say("Má Pavla syna?").verdict.value == "ANO"  # type: ignore[union-attr]
    kdo = s.say("Kdo má syna?")
    assert {s.memory.label(t) for t, _ in kdo.verdict.fillers} == {"Pavla", "Jindřich"}  # type: ignore[union-attr]
    assert s.say("Je Pavla starší než Jindřich?").verdict.value == "NE"  # type: ignore[union-attr]
    w = s.say("Kdo je starší, Pavla nebo Jindřich?")
    assert w.verdict is not None and s.memory.label(w.verdict.fillers[0][0]) == "Jindřich"
    assert s.say("Je Pavla mladší než Matěj?").verdict.value == "NEVÍM"  # type: ignore[union-attr]


def test_comparative_defined_in_dialog(s: Session) -> None:
    """Srovnávací slovo se definuje větou nebo příkazem — jádro jen porovnává hodnotu role."""
    s.say("Vltava měří 430 kilometrů.")
    s.say("Labe měří 1094 kilometrů.")
    a = s.say("Je Vltava delší než Labe?")
    assert a.verdict is not None and a.verdict.value == "NEVÍM" and "nauč mě" in a.text
    d = s.say("Delší je ten, kdo měří víc.")
    assert d.text.startswith("naučeno") and s.memory.learned["comparatives"]["dlouhý"]["dir"] == "more"
    assert s.say("Je Vltava delší než Labe?").verdict.value == "NE"  # type: ignore[union-attr]
    w = s.say("Kdo je delší, Vltava nebo Labe?")
    assert w.verdict is not None and s.memory.label(w.verdict.fillers[0][0]) == "Labe"
    assert "naučeno" in s.say("!srovnání kratší = měřit co míň").text
    assert s.say("Je Vltava kratší než Labe?").verdict.value == "ANO"  # type: ignore[union-attr]
    # přehrání žurnálu zopakuje i definice
    again = Session.replay(s.journal_json(), RecordedOracle(DATA))
    assert again.memory.learned["comparatives"].keys() == s.memory.learned["comparatives"].keys()
