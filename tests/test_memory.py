"""Paměť: deterministická id, group se zúžením, uzávěry, revoke, aktivace, JSON."""

from pathlib import Path

from cb5.chronos import TimeSpec
from cb5.memory import Memory, Provenance, Role, Statement


def S(pred: str | None, kind: str = "verb", *, kernel: str | None = None, neg: bool = False, roles: list[Role] | None = None, grade: str = "read") -> Statement:
    return Statement("", pred, kind, neg=neg, kernel=kernel, roles=roles or [], grade=grade, prov=Provenance("t", 1, "věta"))  # type: ignore[arg-type]


def test_ids_are_deterministic() -> None:
    m = Memory()
    a = m.ensure_group("pes")
    b = m.ensure_entity(["Petr"])[0]
    assert (a.id, b.id) == ("g0001", "e0001")
    st = m.attach(S("štěkat", roles=[Role("kdo", [a.id], "∀")]))
    assert st.id == "s0001"


def test_restricted_group_is_subset_of_base() -> None:
    m = Memory()
    g = m.ensure_group("mazlíček", ("domácí",))
    base = m.ensure_group("mazlíček")
    assert g.base == base.id
    proof = m.subset_star(g.id, base.id)
    assert proof == [f"restricts:{g.id}"]
    assert m.ensure_group("mazlíček", ("domácí",)) is g


def test_find_entity_partial_names_and_merge() -> None:
    m = Memory()
    n, new = m.ensure_entity(["Alois", "Jirásek"], ["Alois", "Jirásek"])
    assert new
    again, new2 = m.ensure_entity(["Jirásek"], ["Jiráskem"])
    assert not new2 and again is n and "Jiráskem" in n.names
    other, new3 = m.ensure_entity(["Karel", "Čapek"])
    assert new3 and other is not n


def test_member_subset_chain_and_disjoint() -> None:
    m = Memory()
    hrabal = m.ensure_entity(["Hrabal"])[0]
    spis, clovek, stroj = m.ensure_group("spisovatel"), m.ensure_group("člověk"), m.ensure_group("stroj")
    s1 = m.attach(S("být", "copula", kernel="member", roles=[Role("kdo", [hrabal.id], "·"), Role("co", [spis.id], "∃")]))
    s2 = m.attach(S("být", "copula", kernel="subset", roles=[Role("kdo", [spis.id], "∀"), Role("co", [clovek.id], "∃")]))
    s3 = m.attach(S("být", "copula", kernel="subset", neg=True, roles=[Role("kdo", [stroj.id], "∀"), Role("co", [clovek.id], "∃")]))
    assert m.member_star(hrabal.id, clovek.id) == [s1.id, s2.id]
    assert m.member_star(hrabal.id, stroj.id) is None
    assert m.disjoint(spis.id, stroj.id) == s3.id
    assert m.known_members(clovek.id) == [(hrabal.id, [s1.id, s2.id])]


def test_within_and_time() -> None:
    m = Memory()
    praha, cesko = m.ensure_place(["Praha"]), m.ensure_place(["Česko"])
    s = m.attach(S("být", "copula", kernel="within", roles=[Role("kdo", [praha.id], "·"), Role("kde", [cesko.id], "·")]))
    assert m.within_star(praha.id, cesko.id) == [s.id]
    t1 = m.ensure_time(TimeSpec("point", "23. 8. 1851", (1851, 8, 23), (1851, 8, 23)))
    t2 = m.ensure_time(TimeSpec("year", "1851", (1851, 0, 0), (1851, 0, 0)))
    assert m.time_within(t1.id, t2.id) is True and m.before(t2.id, t1.id) is False
    assert m.ensure_time(TimeSpec("year", "1851", (1851, 0, 0), (1851, 0, 0))) is t2


def test_revoke_cascades_and_keeps_history() -> None:
    m = Memory()
    petr = m.ensure_entity(["Petr"])[0]
    s = m.attach(S("bydlet", roles=[Role("kdo", [petr.id], "·")]))
    nested = m.attach(Statement("", "role", "nmod", derived_from=s.id))
    revoked = m.revoke(s.id, "oprava")
    assert set(revoked) == {s.id, nested.id}
    assert list(m.active()) == [] and m.statements[s.id].reason == "oprava"
    assert any("✗" in line for line in m.program())


def test_activation_decays_and_filters() -> None:
    m = Memory()
    j = m.ensure_entity(["Jirásek"], gender="Masc", number="Sing")[0]
    b = m.ensure_entity(["Božena"], gender="Fem", number="Sing")[0]
    m.activate([j.id], 1.0)
    m.tick()
    m.activate([b.id], 1.0)
    assert m.most_active()[0] is b
    assert m.most_active(gender="Masc")[0] is j
    assert 0 < m.activation(j.id) < 1


def test_json_round_trip_and_graph(tmp_path: Path) -> None:
    m = Memory()
    pes, jez = m.ensure_group("pes"), m.ensure_group("jezevčík")
    m.attach(S("být", "copula", kernel="subset", roles=[Role("kdo", [jez.id], "∀"), Role("co", [pes.id], "∃")]))
    m.attach(S("štěkat", roles=[Role("kdo", [pes.id], "∀")]))
    m.add_open("role_name", "v+Loc", "Co znamená v+Loc?", "s0002")
    m.save(tmp_path / "m.json")
    again = Memory.load(tmp_path / "m.json")
    assert again.to_json() == m.to_json()
    assert again.subset_star(jez.id, pes.id) == ["s0001"]
    g = m.graph()
    types = {d["type"] for _, _, d in g.edges(data=True)}
    assert {"role:kdo", "subset", "co_mention"} <= types
    assert any(d.get("soft") for _, _, d in g.edges(data=True))
    assert len(again.open_items()) == 1
