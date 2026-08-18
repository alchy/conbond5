"""Vygeneruje ukázkové dialogy pro docs/UVOD.md — skutečné výstupy systému.

    .venv/bin/python docs/ukazky.py [vystup.md]

Vypíše markdown se scénami (každá = čerstvá paměť); bloky se pak vloží do UVOD.md
(sekce 5.x podle jména scény). Potřebuje UDPipe nebo keš `data/cache/parses.json`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cb5.dialog import Session  # noqa: E402
from cb5.memory import Memory  # noqa: E402
from cb5.oracle import live_or_recorded  # noqa: E402
from cb5.cli import _restorer  # noqa: E402

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "parses.json"

SCENES: list[tuple[str, list[str]]] = [
    ("fakta", ["Alois Jirásek se narodil roku 1851 v Hronově.", "Působil jako učitel v Litomyšli.",
               "Kde se narodil Alois Jirásek?", "Kdy se narodil?", "Kde učil Jirásek?", "ano", "Bydlí Jirásek v Brně?", "!program"]),
    ("tridy", ["Pes je šelma.", "Šelmy jedí maso.", "Rex je pes.", "Jedí psi maso?", "Je Rex šelma?", "Tučňák je pták.", "Ptáci létají.",
               "!výjimka létat pták tučňák", "Létá tučňák?", "Létá vrabec?", "Vrabec je pták.", "Létá vrabec?"]),
    ("zajmena", ["Petr má psa.", "Jmenuje se Rex.", "Petr ho venčí každý den.", "Kdo venčí Rexe?", "Čí je Rex?",
                 "Než Jana odešla, zamkla dveře.", "Kdo zamkl dveře?"]),
    ("vztahy", ["Petr Novák je manžel Jany Novákové.", "Karel Novák je otec Petra Nováka.",
                "Tchán je otec manžela nebo manželky.", "Kdo je tchán Jany Novákové?",
                "Otec je rodič.", "Je Karel Novák rodič Petra Nováka?", "Pavla a Jindřich mají syna Matěje.", "Kdo je matka Matěje?"]),
    ("srovnani", ["Pavla se narodila v roce 1980.", "Jindřich se narodil v roce 1975.", "Je Pavla starší než Jindřich?",
                  "Kdo je starší, Pavla nebo Jindřich?"]),
    ("veliciny", ["Telefon má na délku 10 cm.", "Kapsa je na délku 8 cm.", "Vejde se telefon do kapsy?", "ano",
                  "V úlu je 30 000 až 50 000 dělnic.", "Je v úlu 40 000 dělnic?", "Kolik dělnic je v úlu?"]),
    ("cas", ["Magdalena žila mezi lety 1900 až 2000.", "Superman žil mezi lety 2001 až 3001.", "Mohli se Magdalena a Superman potkat?", "ano",
             "Jindřich se narodil v dubnu.", "Jindřich se narodil roku 1975.", "Kdy se narodil Jindřich?",
             "První sinice se objevily před 2 miliardami let.", "Kdy se objevily první sinice?"]),
    ("pravidla", ["Petr půjde na oslavu, pokud půjde Karel.", "Půjde Petr na oslavu?", "Karel půjde na oslavu.", "Půjde Petr na oslavu?",
                  "Každý, kdo bydlí v Praze, bydlí v Česku.", "Petr bydlí v Praze.", "Bydlí Petr v Česku?", "Kdo bydlí v Česku?",
                  "Každý pes, který štěká, je hlídač.", "Rex je pes.", "Rex štěká.", "Alík je pes.", "Je Rex hlídač?", "Je Alík hlídač?", "Štěká každý pes?", "!program"]),
    ("proc", ["Petr nepřišel, protože byl nemocný.", "Proč Petr nepřišel?", "Proč Petr přišel?",
              "Petr šel do obchodu, aby koupil chleba.", "Proč šel Petr do obchodu?", "Koupil Petr chleba?",
              "Ježíš kázal, že Bůh je láska.", "Je Bůh láska?"]),
    ("mista", ["Prací prášek je v krabici.", "Krabice je v koupelně.", "Kde je prací prášek?",
               "Petr žije v Brně.", "Brno leží na Moravě.", "Žije Petr na Moravě?"]),
    ("opravy", ["Ronik je pes.", "Ronik bydlí v Petrovicích.", "Ne, Ronik bydlí v Praze.", "Kde bydlí Ronik?", "!zapomeň s0001", "Je Ronik pes?", "!program"]),
    ("moduly", ["!šablony", "!uč překryv potkat_se žít", "!uč složený tchán otec manžel manželka", "!ulož-vazby /tmp/vazby-ukazka.txt", "!zapomeň s0001", "!program"]),
]


def run(name: str, lines: list[str], *, out: list[str]) -> None:
    s = Session(Memory(), live_or_recorded(CACHE), restorer=_restorer())
    out.append(f"<!-- scéna: {name} -->")
    out.append("```text")
    for line in lines:
        out.append(f"» {line}")
        try:
            text = s.say(line).text
        except Exception as exc:  # noqa: BLE001
            text = f"✗ chyba: {exc}"
        for l in text.splitlines():
            out.append(l)
        out.append("")
    out.append("```")
    out.append("")


def main() -> None:
    out: list[str] = []
    for name, lines in SCENES:
        run(name, lines, out=out)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text("\n".join(out), encoding="utf-8")
        print("hotovo:", sys.argv[1])
    else:
        print("\n".join(out))


if __name__ == "__main__":
    main()
