"""Propad (recall): když logika nedá ANO/NE, co paměť o věcech z otázky ví.

Proč (spec § 7, conBond3): retrieval nad **týmž** grafem — místo mlčení
okolí uzlů z otázky, seřazené překryvem s otázkou, stupněm a čerstvostí.
Nikdy netvrdí: verdikt zůstává NEVÍM, tohle je jen „vím o X: …“.
"""

from __future__ import annotations

from typing import Sequence

from cb5.defaults import synonym_class
from cb5.logic import GRADE_RANK
from cb5.memory import Memory, Statement


def recall(memory: Memory, node_ids: Sequence[str], k: int = 3, *, pred: str | None = None,
           exclude: Sequence[str] = ()) -> list[Statement]:
    """Nejvýš `k` aktivních výroků o uzlech z otázky.

    Skóre = počet uzlů otázky ve výroku (hlavně) + shoda predikátu přes
    synonyma + stupeň + aktivace termů; při rovnosti novější výrok dřív.
    Vnořené a jádrové `member` výroky z instancí se řadí níž — jsou to
    technické řádky, ne odpověď.
    """
    ids = [i for i in node_ids if i in memory.nodes]
    if not ids:
        return []
    scored: list[tuple[float, int, Statement]] = []
    seen: set[str] = set()
    for i in ids:
        for st in memory.statements_about(i):
            if st.id in seen or st.id in exclude or st.derived_from:
                continue
            seen.add(st.id)
            terms = set(st.term_ids())
            overlap = len(terms & set(ids))
            score = 3.0 * overlap
            if pred and st.pred and synonym_class(st.pred) == synonym_class(pred):
                score += 2.0
            score += 0.3 * GRADE_RANK[st.grade]
            score += 0.1 * sum(memory.activation(t) for t in terms)
            if st.kernel == "member" and st.defaults and st.defaults[0].startswith("instance"):
                score -= 2.0
            if st.kind == "nmod":
                score -= 1.0
            scored.append((score, int(st.id[1:]), st))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [st for _, _, st in scored[:k]]
