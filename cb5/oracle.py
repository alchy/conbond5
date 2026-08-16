"""Orákulum rozboru — tenká fasáda nad službou UDPipe (`cb-udpipe`).

Proč vlastní modul: parser je *vnější* zdroj morfologie a syntaxe. Všechno
nad ním (čtení, paměť, logika) musí vidět rozbor jako **návrh s proveniencí**
— tj. vědět, který model ho vyrobil, a umět týž rozbor přehrát bez sítě.
Proto tu jsou tři orákula se stejným rozhraním:

* `UDPipeOracle`   — živá služba na `127.0.0.1:42200`;
* `CachedOracle`   — obal, který si rozbory ukládá do JSON na disk (rychlost,
                     determinismus běhu nad korpusem);
* `RecordedOracle` — jen z JSON souboru; testy nesmějí sahat na síť.

Tvar rozboru (`Token`, `Parse`) je záměrně minimální a **imutabilní**, aby
šel uložit jako zlatá data a porovnat.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

DEFAULT_ENDPOINT = "http://127.0.0.1:42200"
DEFAULT_MODEL = "cs_all-ud-2.17-251125"
CHECK_TIMEOUT_S = 3.0
PARSE_TIMEOUT_S = 60.0


class OracleError(RuntimeError):
    """Orákulum nedokázalo odpovědět. Nikdy se nenahrazuje odhadem."""


class OracleUnavailable(OracleError):
    """Služba neběží nebo neodpovídá — provozní chyba, ne nepochopení."""


class SegmentationError(OracleError):
    """Text nese víc vět a `parse` umí jednu; volající má použít `segment`."""


# --------------------------------------------------------------------------
# Tvar rozboru
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Token:
    """Jeden token závislostního rozboru.

    Vstup: pole z odpovědi služby (`id`, `form`, `lemma`, `upos`, `head`,
    `deprel`, `feats`). Rysy se drží jako seřazená n‑tice dvojic, aby byl
    token hashovatelný a JSON round‑trip deterministický.
    """

    index: int
    form: str
    lemma: str
    upos: str
    head: int
    deprel: str
    feats: tuple[tuple[str, str], ...] = ()

    def feat(self, name: str) -> str | None:
        """Hodnota rysu (`Case`, `Number`, …) nebo `None`, když chybí."""
        for key, value in self.feats:
            if key == name:
                return value
        return None

    @property
    def base_deprel(self) -> str:
        """Deprel bez podtypu: `obl:arg` → `obl`. Porovnávat se má podle
        rysu, ne přesnou shodou (past conbond4 § 13/1)."""
        return self.deprel.split(":", 1)[0]

    def __str__(self) -> str:
        marks = "|".join(f"{k}={v}" for k, v in self.feats) or "_"
        return f"{self.index}\t{self.form}\t{self.lemma}\t{self.upos}\t{marks}\t{self.head}\t{self.deprel}"


@dataclass(frozen=True, slots=True)
class Parse:
    """Rozbor jedné věty: tokeny + provenience modelu.

    Všechny dotazy na stavbu věty jdou přes tyhle metody — čtení si nesmí
    domýšlet, co v rozboru není.
    """

    text: str
    tokens: tuple[Token, ...]
    provenance: str

    def root(self) -> Token:
        """Kořen věty (head == 0). Rozbor bez kořene je chyba služby."""
        for token in self.tokens:
            if token.head == 0:
                return token
        raise OracleError(f"rozbor bez kořene: {self.text!r}")

    def token(self, index: int) -> Token:
        return self.tokens[index - 1]

    def children(self, index: int) -> tuple[Token, ...]:
        """Přímí závislí členové tokenu, v pořadí věty."""
        return tuple(t for t in self.tokens if t.head == index)

    def subtree(self, index: int) -> tuple[Token, ...]:
        """Celý podstrom včetně hlavy, v pořadí věty."""
        wanted = {index}
        changed = True
        while changed:
            changed = False
            for t in self.tokens:
                if t.head in wanted and t.index not in wanted:
                    wanted.add(t.index)
                    changed = True
        return tuple(t for t in self.tokens if t.index in wanted)

    def path(self, index: int) -> str:
        """Cesta deprelů od kořene k tokenu (`nsubj>amod`) — pro popis zbytku."""
        parts: list[str] = []
        t = self.token(index)
        while t.head != 0:
            parts.append(t.deprel)
            t = self.token(t.head)
        return ">".join(reversed(parts)) or "root"

    def render(self) -> str:
        return "\n".join(str(t) for t in self.tokens)


def token_from_json(item: Mapping[str, object]) -> Token:
    """Token z odpovědi služby (`feats` je dict) i z našeho JSON (list dvojic)."""
    raw = item.get("feats") or {}
    feats: tuple[tuple[str, str], ...]
    if isinstance(raw, dict):
        feats = tuple(sorted((str(k), str(v)) for k, v in raw.items()))
    elif isinstance(raw, list):
        feats = tuple((str(k), str(v)) for k, v in raw)
    else:
        feats = ()
    return Token(
        index=int(str(item["id"])),
        form=str(item["form"]),
        lemma=str(item.get("lemma") or item["form"]),
        upos=str(item.get("upos") or "X"),
        head=int(str(item.get("head") or 0)),
        deprel=str(item.get("deprel") or "dep"),
        feats=feats,
    )


def parse_to_json(parse: Parse) -> dict[str, object]:
    return {
        "text": parse.text,
        "provenance": parse.provenance,
        "tokens": [
            {
                "id": t.index,
                "form": t.form,
                "lemma": t.lemma,
                "upos": t.upos,
                "head": t.head,
                "deprel": t.deprel,
                "feats": list(t.feats),
            }
            for t in parse.tokens
        ],
    }


def parse_from_json(d: Mapping[str, object]) -> Parse:
    tokens = d.get("tokens", [])
    assert isinstance(tokens, list)
    return Parse(
        text=str(d["text"]),
        tokens=tuple(token_from_json(t) for t in tokens),
        provenance=str(d.get("provenance", "")),
    )


def render_forms(tokens: Sequence[Token]) -> str:
    """Popiska věty z tvarů: před interpunkcí bez mezery."""
    out: list[str] = []
    for t in tokens:
        if out and t.upos != "PUNCT":
            out.append(" ")
        out.append(t.form)
    return "".join(out)


# --------------------------------------------------------------------------
# Živá služba
# --------------------------------------------------------------------------

Transport = Callable[[str, bytes | None, float], bytes]


def _urllib_transport(url: str, body: bytes | None, timeout: float) -> bytes:
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"} if body else {}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()  # type: ignore[no-any-return]
    except urllib.error.URLError as exc:
        raise OracleUnavailable(f"služba neodpovídá na {url}: {exc}") from exc


class UDPipeOracle:
    """Fasáda nad běžící službou `cb-udpipe`.

    Selže při vytvoření (handshake `/version`), ne až uprostřed dialogu.
    Provenience = `udpipe2 model=… tokenizer=…`; služba z conBond3 model
    ve `/version` neuvádí, proto se doplní `model_fallback` a v provenienci
    to zůstane vidět (`model?=`) — nesmí to splynout s ověřenou identitou.
    """

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        model_fallback: str = DEFAULT_MODEL,
        transport: Transport = _urllib_transport,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._transport = transport
        self._model_fallback = model_fallback
        self.provenance = self._handshake()

    def _handshake(self) -> str:
        payload = self._call("/version", None, CHECK_TIMEOUT_S)
        model = str(payload.get("model") or "")
        tokenizer = str(payload.get("tokenizer") or payload.get("version") or "?")
        if model:
            return f"udpipe2 model={model} tokenizer={tokenizer}"
        return f"udpipe2 model?={self._model_fallback} tokenizer={tokenizer}"

    def parse(self, text: str) -> Parse:
        """Rozbor JEDNÉ věty. Víc vět → `SegmentationError` (použij `segment`)."""
        parses = self._parses(text)
        if not parses:
            raise OracleError(f"služba nevrátila žádnou větu pro {text!r}")
        if len(parses) > 1:
            raise SegmentationError(
                f"text {text!r} nese {len(parses)} vět; rozděl ho přes segment()"
            )
        return Parse(text=text, tokens=parses[0].tokens, provenance=self.provenance)

    def segment(self, text: str) -> tuple[Parse, ...]:
        """Rozdělí text na věty a každou rovnou rozebere — dělič a parser
        jsou schválně táž služba."""
        return self._parses(text)

    def _parses(self, text: str) -> tuple[Parse, ...]:
        payload = self._call("/v1/parse", {"text": text}, PARSE_TIMEOUT_S)
        sentences = payload.get("sentences", [])
        if not isinstance(sentences, list):
            raise OracleError(f"neočekávaný tvar odpovědi pro {text!r}")
        out: list[Parse] = []
        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue
            tokens = tuple(
                token_from_json(t) for t in sentence.get("tokens", []) if isinstance(t, dict)
            )
            if not tokens:
                continue
            out.append(Parse(text=render_forms(tokens), tokens=tokens, provenance=self.provenance))
        return tuple(out)

    def _call(
        self, path: str, body: Mapping[str, object] | None, timeout: float
    ) -> Mapping[str, object]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        raw = self._transport(f"{self.endpoint}{path}", encoded, timeout)
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise OracleError(f"{path}: odpověď nejde přečíst — {exc}") from exc
        if not isinstance(decoded, dict):
            raise OracleError(f"{path}: očekáván objekt, přišlo {type(decoded)}")
        return decoded


# --------------------------------------------------------------------------
# Keš a nahrávka
# --------------------------------------------------------------------------


class CachedOracle:
    """Keš rozborů na disku (JSON `{text: parse}`), zapisuje se průběžně.

    Proč: běh nad korpusem se opakuje mnohokrát a rozbor je nejdražší krok;
    a keš dělá běh deterministickým i při driftu služby. Klíč je text věty;
    provenience zůstává u každého rozboru, takže drift modelu je vidět.
    """

    def __init__(self, inner: UDPipeOracle | None, path: Path) -> None:
        self.inner = inner
        self.path = Path(path)
        self._data: dict[str, dict[str, object]] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        self.provenance = inner.provenance if inner else str(
            next(iter(self._data.values()), {}).get("provenance", "recorded")
        )
        self.dirty = 0

    def parse(self, text: str) -> Parse:
        hit = self._data.get(text)
        if hit is not None:
            return parse_from_json(hit)
        if self.inner is None:
            raise KeyError(
                f"rozbor pro {text!r} není v {self.path}; pořiď ho: "
                f"python -m cb5.record <věty.txt> {self.path}"
            )
        parse = self.inner.parse(text)
        self._data[text] = parse_to_json(parse)
        self.dirty += 1
        if self.dirty % 50 == 0:
            self.flush()
        return parse

    def segment(self, text: str) -> tuple[Parse, ...]:
        key = "§segment§ " + text
        hit = self._data.get(key)
        if hit is not None:
            parts = hit.get("parts", [])
            assert isinstance(parts, list)
            return tuple(parse_from_json(p) for p in parts)
        if self.inner is None:
            raise KeyError(f"segmentace pro {text[:40]!r}… není v {self.path}")
        parses = self.inner.segment(text)
        self._data[key] = {"parts": [parse_to_json(p) for p in parses]}
        for p in parses:
            self._data.setdefault(p.text, parse_to_json(p))
        self.dirty += 1
        if self.dirty % 20 == 0:
            self.flush()
        return parses

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=0, sort_keys=True),
            encoding="utf-8",
        )
        self.dirty = 0


class RecordedOracle(CachedOracle):
    """Jen nahrané rozbory — pro testy. Chybějící věta je chyba s návodem."""

    def __init__(self, path: Path) -> None:
        super().__init__(None, path)


def live_or_recorded(cache_path: Path) -> CachedOracle:
    """Živé orákulum s keší, když služba běží; jinak jen keš."""
    try:
        return CachedOracle(UDPipeOracle(), cache_path)
    except OracleUnavailable:
        return RecordedOracle(cache_path)
