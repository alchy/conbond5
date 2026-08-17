"""Měření nad korpusem conBond2: míra zápisu a přesnost odpovědí.

    python -m cb5.bench                      # všechny dokumenty se zlatými otázkami
    python -m cb5.bench --dok alois_jirásek  # jeden dokument
    python -m cb5.bench --strop 60           # nejvýš 60 řádků na dokument

Hlavní metrika (spec § 10): **znalost získaná z textu** — kolik z vět se
zapsalo jako výrok s rolí, kolik zbylo ve zbytku, a hlavně kolik zlatých
otázek (`otazky.json` 682 kde/kdy s číslem zdrojové věty; `etalon.json`,
`conbond.json` ručně psané) systém zodpoví správně **z vloženého textu**.
Chyby se rozkládají podle příčiny, aby bylo vidět, kde se opravuje.

Korpus se klonuje z GitHubu do `data/corpus/conBond2` (mělce), rozbory
se kešují v `data/cache/parses.json`. Jedna paměť na dokument — otázky
jsou vázané na dokument.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from cb5.dialog import Session
from cb5.memory import Memory
from cb5.oracle import CachedOracle, OracleUnavailable, UDPipeOracle
from cb5.render import describe_node

HERE = Path(__file__).resolve().parent.parent
CORPUS = HERE / "data" / "corpus" / "conBond2"
CACHE = HERE / "data" / "cache" / "parses.json"
MERENI = HERE / "mereni"
CONBOND2 = "https://github.com/alchy/conBond2.git"


def ensure_corpus() -> Path:
    if not CORPUS.exists():
        CORPUS.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", CONBOND2, str(CORPUS)], check=True)
    return CORPUS


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower().strip()
    return re.sub(r"\s+", " ", s)


def _years(s: str) -> set[str]:
    return set(re.findall(r"\b(1\d{3}|20\d{2})\b", s))


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[\s.,;:()–\-]+", _norm(s)) if t]


#: Předpony zdrojů v ručních sadách, které korpus ve jménech souborů nemá.
_PREFIXES = ("wiki_", "wikisofia_")


def doc_key(name: str) -> str:
    """Jméno dokumentu → porovnatelný klíč (bez předpony zdroje, diakritiky
    a interpunkce): `wiki_pes_domácí` = `pes_domácí`, `rodina_novakovi` =
    `rodina_novákovi`, `wiki_r.u.r.` = `rur`. Zlatá sada a korpus se ve
    jménech rozešly (poznatek conbond4-utils); co nesedne ani takhle
    (bible), se vypíše, ne zamlčí."""
    text = name.strip().lower()
    for pre in _PREFIXES:
        if text.startswith(pre):
            text = text[len(pre):]
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if ch.isalnum())


def _refs(item: dict[str, Any], key: str) -> list[str]:
    """Odkaz na dokument(y) — smí být i „a+b“."""
    raw = str(item.get(key) or "")
    return [x for x in raw.split("+") if x]


def gold_questions(corpus: Path, doc: str) -> list[dict[str, Any]]:
    """Zlaté otázky k dokumentu: `otazky` = generované šablonou (levné,
    velké, gramaticky kostrbaté — conBond2 to o nich sám říká), `etalon`
    a `conbond` = psané ručně. Sady se v reportu **nesčítají do jednoho
    čísla**."""
    out: list[dict[str, Any]] = []
    gold = corpus / "data" / "gold"
    dk = doc_key(doc)
    for item in json.loads((gold / "otazky.json").read_text(encoding="utf-8")):
        if item.get("dok") == doc:
            out.append({"q": item["text"], "expect": [item["odpoved"]], "sada": "otazky", "veta": item.get("veta"), "typ": item.get("typ", "")})
    for name, key in (("etalon.json", "dok"), ("conbond.json", "src")):
        for item in json.loads((gold / name).read_text(encoding="utf-8")):
            if any(doc_key(r) == dk for r in _refs(item, key)):
                out.append({"q": item["q"], "expect": list(item.get("expect", [])), "sada": name.split(".")[0], "veta": None, "typ": item.get("mode", "")})
    return out


def docs_with_gold(corpus: Path) -> list[str]:
    gold = corpus / "data" / "gold"
    available = {doc_key(p.stem): p.stem for p in (corpus / "data" / "raw").glob("*.txt")}
    names: set[str] = set()
    unmatched: set[str] = set()
    for item in json.loads((gold / "otazky.json").read_text(encoding="utf-8")):
        names.add(str(item["dok"]))
    for name, key in (("etalon.json", "dok"), ("conbond.json", "src")):
        for item in json.loads((gold / name).read_text(encoding="utf-8")):
            for r in _refs(item, key):
                if doc_key(r) in available:
                    names.add(available[doc_key(r)])
                else:
                    unmatched.add(r)
    if unmatched:
        print("ruční otázky bez textu v korpusu: " + ", ".join(sorted(unmatched)), file=sys.stderr)
    return sorted(n for n in names if (corpus / "data" / "raw" / f"{n}.txt").exists())


def answer_matches(memory: Memory, expect: list[str], fillers: list[str], text: str) -> tuple[bool, bool]:
    """(sedí výplň, sedí aspoň text odpovědi). Výplň sedí, když očekávaný
    řetězec (nebo jeho letopočet) je mezi jmény/popiskou některé výplně."""
    labels: list[str] = []
    for f in fillers:
        if f.startswith("count:"):
            labels.append(f.split(":", 1)[1])
            continue
        n = memory.nodes.get(f)
        if n is None:
            continue
        labels.append(describe_node(memory, f))
        labels.extend(n.names)
        if n.time is not None:
            labels.append(n.time.label)
        if n.kind == "entity" and n.base:
            labels.append(memory.nodes[n.base].lemma)
    norm_labels = [_norm(x) for x in labels]
    hit = False
    for e in expect:
        en = _norm(e)
        ey = _years(en)
        for lab in norm_labels:
            if en == lab or en in lab or lab in en and len(lab) > 3:
                hit = True
            if ey and ey & _years(lab):
                hit = True
            et = _tokens(en)
            if et and all(any(t == w or (len(t) > 4 and (w.startswith(t[:-2]) or t.startswith(w[:-2]))) for w in _tokens(lab)) for t in et):
                hit = True
    text_hit = any(_norm(e) in _norm(text) or (_years(e) and _years(e) & _years(text)) for e in expect)
    return hit, text_hit


def classify_miss(session: Session, q: str, verdict: object) -> str:
    """Proč otázka neprošla — hrubý rozklad podle stavu paměti."""
    m = session.memory
    if verdict is None:
        return "nepřečteno"
    v = verdict
    if getattr(v, "fillers", None):
        return "špatná výplň"
    missing = list(getattr(v, "missing", []))
    if any("nevím nic" in x for x in missing):
        return "entita neznámá"
    if any("nemám žádný výrok" in x for x in missing):
        return "predikát chybí"
    if getattr(v, "near", None):
        return "role/logika (blízký výrok je)"
    return "bez výroku"


#: Sdílená znalost k dokumentu (conBond2 ji měl v jedné bázi): definice pojmů, které
#: otázky k dokumentu předpokládají. Vypisuje se — není to skrytá nápověda.
SHARED: dict[str, tuple[str, ...]] = {"rodina_novákovi": ("vztahy_příbuzenské",)}


def run_doc(doc: str, corpus: Path, oracle: CachedOracle, strop: int) -> dict[str, Any]:
    text = (corpus / "data" / "raw" / f"{doc}.txt").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if l.strip()]
    if strop:
        lines = lines[:strop]
    session = Session(Memory(), oracle)
    t0 = time.time()
    for shared in SHARED.get(doc, ()):
        sp = corpus / "data" / "raw" / f"{shared}.txt"
        if sp.exists():
            session.ingest(sp.read_text(encoding="utf-8"), shared)
            print(f"   + sdílená znalost: {shared}", file=sys.stderr)
    reports = session.ingest("\n".join(lines), doc)
    t_ingest = time.time() - t0
    n_sent = len(reports)
    n_written = sum(1 for r in reports if r.get("statements"))
    n_with_role = 0
    n_tokens = 0
    n_residue = 0
    n_open = 0
    for r in reports:
        if r.get("error"):
            continue
        n_residue += len(r.get("residue", []))  # type: ignore[arg-type]
        n_open += len(r.get("open", []))  # type: ignore[arg-type]
        reading = str(r.get("reading", ""))
        if "(" in reading and reading.split("(", 1)[1].strip(")"):
            n_with_role += 1
    m = session.memory
    n_tokens = sum(len(n.text.split()) for n in m.nodes.values() if n.kind == "sentence")
    questions = gold_questions(corpus, doc)
    results: list[dict[str, Any]] = []
    hits = 0
    text_hits = 0
    misses: Counter[str] = Counter()
    t1 = time.time()
    for item in questions:
        q = str(item["q"])
        try:
            a = session.say(q)
        except Exception as exc:  # noqa: BLE001 — bench nesmí spadnout na jedné otázce
            results.append({"q": q, "expect": item["expect"], "ok": False, "text_ok": False, "why": f"pád: {exc}"})
            misses["pád"] += 1
            continue
        v = a.verdict
        fillers = [t for t, _ in v.fillers] if v is not None else []
        if not item["expect"]:
            # mode=unsure: zlatá sada čeká, že systém NIC netvrdí. Správně = NEVÍM.
            # (Když přesto odpoví, může mít pravdu — etalon je starý; hlásí se to zvlášť.)
            ok = bool(v is None or v.value == "NEVÍM")
            text_ok = ok
        else:
            ok, text_ok = answer_matches(m, list(item["expect"]), fillers, a.text)
        hits += ok
        text_hits += text_ok
        why = "" if ok else ("odpověděl navíc (etalon čekal NEVÍM)" if not item["expect"] else classify_miss(session, q, v))
        if not ok:
            misses[why] += 1
        results.append({"q": q, "expect": item["expect"], "sada": item["sada"], "ok": ok, "text_ok": text_ok,
                        "verdict": v.value if v else None, "fillers": [describe_node(m, f) if not f.startswith("count:") else f for f in fillers][:6],
                        "why": why, "reading": a.reading})
    t_ask = time.time() - t1
    return {
        "doc": doc, "sentences": n_sent, "written": n_written, "with_role": n_with_role,
        "statements": len(list(m.active())), "residue_tokens": n_residue, "tokens": n_tokens,
        "open": n_open, "questions": len(questions), "hits": hits, "text_hits": text_hits,
        "misses": dict(misses), "results": results, "t_ingest": round(t_ingest, 1), "t_ask": round(t_ask, 1),
    }


def render_report(rows: list[dict[str, Any]]) -> str:
    out = ["| dokument | vět | zapsáno | výroků | zbytek tok. | otevř. | otázek | správně | v textu |", "|---|---|---|---|---|---|---|---|---|"]
    tot: Counter[str] = Counter()
    for r in rows:
        pct = f"{100 * int(r['hits']) / max(int(r['questions']), 1):.0f} %" if r["questions"] else "—"
        out.append(f"| {r['doc']} | {r['sentences']} | {r['written']} | {r['statements']} | {r['residue_tokens']}/{r['tokens']} | {r['open']} | {r['questions']} | {r['hits']} ({pct}) | {r['text_hits']} |")
        for k in ("sentences", "written", "statements", "residue_tokens", "tokens", "open", "questions", "hits", "text_hits"):
            tot[k] += int(r[k])
    pct = f"{100 * tot['hits'] / max(tot['questions'], 1):.1f} %"
    out.append(f"| **celkem** | {tot['sentences']} | {tot['written']} | {tot['statements']} | {tot['residue_tokens']}/{tot['tokens']} | {tot['open']} | {tot['questions']} | {tot['hits']} ({pct}) | {tot['text_hits']} |")
    # po sadách: ruční × generované se nesčítají
    per: dict[str, list[int]] = {}
    for r in rows:
        for q in r["results"]:
            sada = str(q.get("sada", "?"))
            per.setdefault(sada, [0, 0, 0])
            per[sada][0] += 1
            per[sada][1] += int(bool(q.get("ok")))
            per[sada][2] += int(bool(q.get("text_ok")))
    out.append("")
    out.append("| sada | druh | otázek | správně | v textu |")
    out.append("|---|---|---|---|---|")
    labels = {"otazky": "generované šablonou (kde/kdy)", "etalon": "ručně psané", "conbond": "ručně psané (starý conBond)"}
    for sada in ("etalon", "conbond", "otazky"):
        if sada in per:
            n, h, th = per[sada]
            out.append(f"| {sada} | {labels.get(sada, sada)} | {n} | {h} ({100 * h / max(n, 1):.0f} %) | {th} |")
    misses: Counter[str] = Counter()
    for r in rows:
        misses.update(r["misses"])
    if misses:
        out.append("")
        out.append("Rozklad chyb: " + "; ".join(f"{k}: {v}" for k, v in misses.most_common()))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dok", action="append", help="jméno dokumentu (bez .txt); lze víckrát")
    ap.add_argument("--strop", type=int, default=0, help="nejvýš N řádků na dokument (0 = vše)")
    ap.add_argument("--vypis", action="store_true", help="vypsat každou otázku s odpovědí")
    ap.add_argument("--jen-chyby", action="store_true", help="vypsat jen chybné otázky")
    args = ap.parse_args(argv)
    corpus = ensure_corpus()
    try:
        oracle = CachedOracle(UDPipeOracle(), CACHE)
    except OracleUnavailable:
        print("služba UDPipe neběží — jedu jen z keše", file=sys.stderr)
        oracle = CachedOracle(None, CACHE)
    docs = args.dok or docs_with_gold(corpus)
    rows: list[dict[str, Any]] = []
    for doc in docs:
        print(f"… {doc}", file=sys.stderr, flush=True)
        try:
            row = run_doc(doc, corpus, oracle, args.strop)
        except KeyError as exc:
            print(f"   přeskočeno: {exc}", file=sys.stderr)
            continue
        oracle.flush()
        rows.append(row)
        if args.vypis or args.jen_chyby:
            for r in row["results"]:
                if args.jen_chyby and r["ok"]:
                    continue
                mark = "✓" if r["ok"] else ("~" if r["text_ok"] else "✗")
                print(f"  {mark} {r['q']}  →  {r.get('fillers')}  (čekáno {r['expect']}) {r.get('why', '')}")
    report = render_report(rows)
    print(report)
    MERENI.mkdir(exist_ok=True)
    stamp = "vse" if not args.dok else "+".join(args.dok)[:60]
    (MERENI / f"bench-{stamp}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (MERENI / f"bench-{stamp}.md").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
