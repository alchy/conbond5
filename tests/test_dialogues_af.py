"""Dialogy A–F ze zadání conbond4 (§ 6.12) + adversariální sada.

Kde conbond4 „nezapsal“, conbond5 zapíše a odpověď nese stupeň; nikde
tichá nepravda. Meze v1 jsou tu zapsané jako testy toho, co systém řekne
(NEVÍM + co ví), ne jako díra.
"""

from pathlib import Path

import pytest

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.oracle import RecordedOracle

DATA = Path(__file__).parent / "data" / "parses.json"


@pytest.fixture()
def s() -> Session:
    return Session(Memory(), RecordedOracle(DATA))


def v(s: Session, text: str) -> str:
    a = s.say(text)
    assert a.verdict is not None, a.text
    return a.verdict.value


def test_dialog_a_bridge_over_subset(s: Session) -> None:
    s.say("Auto je dopravní prostředek.")
    s.say("Dopravní prostředek slouží k přesunu nákladů nebo osob.")
    s.say("Dopravní prostředek jezdí po dálnici.")
    s.say("Dálnice má omezenou rychlost na 130 km/h.")
    a = s.say("Jezdí auto po dálnici?")
    assert a.verdict.value == "ANO" and "auto ⊆ prostředek" in a.text  # type: ignore[union-attr]
    # mez v1: veličiny a modální otázka nad nimi — poctivé NEVÍM s tím, co ví
    b = s.say("Jak rychle může jezdit auto po dálnici?")
    assert b.verdict.value == "NEVÍM" and "dálnice" in b.text.lower()  # type: ignore[union-attr]
    # disjunkce v datech nedává konjunktivní odpověď: „nákladů nebo osob“ je koordinace, sedí ∃
    c = s.say("Slouží auto k přesunu osob?")
    assert c.verdict.value in ("ANO", "NEVÍM")  # type: ignore[union-attr]


def test_dialog_b_what_does_not_follow(s: Session) -> None:
    s.say("Citron je ovoce.")
    s.say("Ovoce obsahuje vitamíny.")
    s.say("Vitamín C je vitamín.")
    assert v(s, "Obsahuje citron vitamín C?") == "NEVÍM"
    assert v(s, "Obsahuje citron nějaký vitamín?") == "ANO"
    s.say("Citron obsahuje vitamín C.")
    assert v(s, "Obsahuje citron vitamín C?") == "ANO"


def test_dialog_c_syllogism_and_witness(s: Session) -> None:
    s.say("Každý spisovatel je člověk.")
    s.say("Žádný stroj není člověk.")
    s.say("Hrabal je spisovatel.")
    s.say("Hrabal napsal Postřižiny.")
    a = s.say("Je Hrabal stroj?")
    assert a.verdict.value == "NE" and "∦" in a.text  # type: ignore[union-attr]
    assert v(s, "Napsal Postřižiny spisovatel?") == "ANO"
    b = s.say("Napsal Postřižiny i nějaký stroj?")
    assert b.verdict.value == "NEVÍM"  # type: ignore[union-attr]
    kdo = s.say("Kdo je Hrabal?")
    assert "spisovatel" in kdo.text


def test_dialog_d_space_and_time(s: Session) -> None:
    s.say("Petr jel v pondělí do Prahy.")
    s.say("V úterý jel Petr do Brna.")
    s.say("Praha je v Česku.")
    assert v(s, "Byl Petr v pondělí v Česku?") == "NEVÍM"
    s.say("!pravidlo jet(kam:X) => být(kde:X)")
    assert v(s, "Byl Petr v pondělí v Česku?") == "ANO"
    kam = s.say("Kam jel Petr v pondělí?")
    assert "Praha" in kam.text and "Brno" not in kam.text.split("→")[1]
    kdy = s.say("Kdy jel Petr do Prahy?")
    assert "pondělí" in kdy.text
    w = s.say("Byl Petr ve středu v Česku?")
    assert w.verdict.value == "NEVÍM"  # type: ignore[union-attr]


def test_dialog_e_exception_without_default_logic(s: Session) -> None:
    s.say("Ptáci létají.")
    s.say("Tučňák je pták.")
    assert v(s, "Létá tučňák?") == "ANO"
    a = s.say("Tučňák nelétá.")
    assert a.conflict is not None
    s.say("!výjimka létat pták tučňák")
    s.say("Vrabec je pták.")
    assert v(s, "Létá vrabec?") == "ANO"
    b = s.say("Létá tučňák?")
    assert b.verdict.value == "NE" and "s0" in b.text  # type: ignore[union-attr]


def test_dialog_f_instance_description_and_name(s: Session) -> None:
    s.say("Filip má auto.")
    s.say("Filipovo auto je modré.")
    a = s.say("Co má Filip?")
    assert "auto (modrý)" in a.text
    b = s.say("Jaké je Filipovo auto?")
    assert "modrý" in b.text


def test_adversarial_no_silent_lies(s: Session) -> None:
    s.say("Petr bydlí v Praze.")
    assert v(s, "Bydlí Petr v Brně?") == "NEVÍM"
    assert v(s, "Bydlí Petr v Praze v roce 2020?") == "NEVÍM"
    s.say("Vesmír se rozšířil do dnešní podoby.")
    s.say("Paralelní vesmír je vesmír.")
    # kdo je · (epizoda, minulý čas) — z „vesmír“ neplyne nic o paralelním vesmíru
    assert v(s, "Rozšířil se paralelní vesmír?") == "NEVÍM"
    assert v(s, "Rozšířil se vesmír?") == "ANO"
    s.say("Pes štěká.")
    assert v(s, "Štěká jezevčík?") == "NEVÍM"
    s.say("Jezevčík je pes.")
    a = s.say("Štěká jezevčík?")
    assert a.verdict.value == "ANO" and "generický" in a.text  # type: ignore[union-attr]
