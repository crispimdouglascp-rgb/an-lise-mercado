"""Fontes de preço. Duas por ativo, sempre comparadas. Nunca inventar preço.

- Yahoo Finance (endpoint público de gráfico; não oficial, sem chave).
- brapi.dev (cotações B3; precisa de token gratuito para a maioria dos tickers).
- BCB SGS (dólar), usado só para conferir o fechamento do dia anterior.

ATENÇÃO: o formato dessas APIs foi escrito a partir da documentação e de
memória, e NÃO foi testado contra os servidores reais neste ambiente.
Rode `python -m rvlocal testar-fontes` na sua máquina antes de confiar.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable
from urllib.parse import quote

from .util import BRT, agora


class ErroFonte(Exception):
    pass


def http_get(url: str, headers: dict | None = None, timeout: int = 20) -> str:
    h = {"User-Agent": "Mozilla/5.0 (rv-local)", "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ErroFonte(f"HTTP {e.code} em {url.split('?')[0]}") from e
    except Exception as e:  # rede, timeout, DNS
        raise ErroFonte(f"falha de rede em {url.split('?')[0]}: {e}") from e


# Os testes trocam esta função por uma falsa.
FETCH: Callable[[str, dict | None], str] = http_get


@dataclass
class Cotacao:
    simbolo: str
    preco: float
    anterior: float | None
    ts: datetime  # horário da cotação informado pela fonte (BRT)
    fonte: str

    def variacao_pct(self) -> float | None:
        if self.anterior:
            return (self.preco / self.anterior - 1) * 100
        return None


@dataclass
class Leitura:
    """Resultado da comparação das fontes para um símbolo."""
    simbolo: str
    status: str            # ok | fonte_unica | fonte_unica_esperada | divergente | sem_dado
    preco: float | None    # None = lacuna honesta
    anterior: float | None
    ts: datetime | None
    cotacoes: list[Cotacao]
    erros: list[str]
    divergencia_pct: float | None = None

    @property
    def aceitavel_no_fechamento(self) -> bool:
        return self.status in {"ok", "fonte_unica_esperada"} and self.preco is not None


# ------------------------------------------------------------------ Yahoo

def _yahoo_chart(simbolo: str, intervalo: str = "1d", periodo: str = "5d") -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(simbolo)}?interval={intervalo}&range={periodo}"
    )
    j = json.loads(FETCH(url, None))
    chart = j.get("chart", {})
    res = chart.get("result")
    if not res:
        raise ErroFonte(f"Yahoo sem resultado para {simbolo}: {chart.get('error')}")
    return res[0]


def fetch_yahoo(simbolo_yahoo: str, nome: str | None = None) -> Cotacao:
    r = _yahoo_chart(simbolo_yahoo)
    meta = r["meta"]
    preco = meta.get("regularMarketPrice")
    t = meta.get("regularMarketTime")
    if preco is None or t is None:
        raise ErroFonte(f"Yahoo sem preço/horário para {simbolo_yahoo}")
    ts = datetime.fromtimestamp(t, BRT)
    anterior = None
    stamps = r.get("timestamp") or []
    closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    for st, c in zip(stamps, closes):
        if c is None:
            continue
        if datetime.fromtimestamp(st, BRT).date() < ts.date():
            anterior = c  # último fechamento anterior ao dia da cotação
    if anterior is None:
        anterior = meta.get("previousClose")
    return Cotacao(nome or simbolo_yahoo, float(preco), anterior, ts, "yahoo")


def fetch_yahoo_historico(simbolo_yahoo: str, periodo: str = "3mo") -> dict[str, float]:
    """Fechamentos diários {data ISO: fechamento}. Usado em backfill."""
    r = _yahoo_chart(simbolo_yahoo, "1d", periodo)
    out: dict[str, float] = {}
    for st, c in zip(r.get("timestamp") or [], (r["indicators"]["quote"][0].get("close") or [])):
        if c is not None:
            out[datetime.fromtimestamp(st, BRT).date().isoformat()] = float(c)
    return out


# ------------------------------------------------------------------ brapi

def _parse_ts(v) -> datetime:
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, BRT)
    s = str(v).replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(BRT)


def fetch_brapi(simbolo: str) -> Cotacao:
    base = os.environ.get("BRAPI_URL", "https://brapi.dev/api/quote")  # a conferir na doc
    token = os.environ.get("BRAPI_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    j = json.loads(FETCH(f"{base}/{quote(simbolo)}", headers))
    res = j.get("results") or []
    if not res:
        raise ErroFonte(f"brapi sem resultado para {simbolo}: {j.get('message') or j.get('error')}")
    r = res[0]
    preco = r.get("regularMarketPrice")
    t = r.get("regularMarketTime")
    if preco is None or t is None:
        raise ErroFonte(f"brapi sem preço/horário para {simbolo}")
    return Cotacao(
        simbolo, float(preco), r.get("regularMarketPreviousClose"), _parse_ts(t), "brapi"
    )


# ------------------------------------------------------------------ BCB

def fetch_bcb_dolar() -> tuple[str, float]:
    """Último valor da série SGS 1 (dólar comercial venda): (data ISO, valor)."""
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/1?formato=json"
    j = json.loads(FETCH(url, None))
    if not j:
        raise ErroFonte("BCB sem dados")
    d = datetime.strptime(j[0]["data"], "%d/%m/%Y").date().isoformat()
    return d, float(str(j[0]["valor"]).replace(",", "."))


# ------------------------------------------------------------------ comparação

def consolidar(simbolo: str, obtencoes: list[Callable[[], Cotacao]], tolerancia_pct: float) -> Leitura:
    """Executa as fontes, compara e decide. Divergência => lacuna, não média."""
    cots: list[Cotacao] = []
    erros: list[str] = []
    for fn in obtencoes:
        try:
            cots.append(fn())
        except (ErroFonte, ValueError, KeyError, json.JSONDecodeError) as e:
            erros.append(f"{type(e).__name__}: {e}")
    esperadas = len(obtencoes)
    if not cots:
        return Leitura(simbolo, "sem_dado", None, None, None, [], erros)
    if len(cots) == 1:
        c = cots[0]
        status = "fonte_unica_esperada" if esperadas == 1 else "fonte_unica"
        return Leitura(simbolo, status, c.preco, c.anterior, c.ts, cots, erros)
    a, b = cots[0], cots[1]
    div = abs(a.preco / b.preco - 1) * 100
    if div > tolerancia_pct:
        return Leitura(simbolo, "divergente", None, a.anterior, a.ts, cots, erros, div)
    return Leitura(simbolo, "ok", a.preco, a.anterior or b.anterior, max(a.ts, b.ts), cots, erros, div)


def obtencoes_ativo(ticker: str) -> list[Callable[[], Cotacao]]:
    return [
        lambda: fetch_yahoo(f"{ticker}.SA", ticker),
        lambda: fetch_brapi(ticker),
    ]


def obtencoes_serie(nome: str, cfg: dict) -> list[Callable[[], Cotacao]]:
    fs: list[Callable[[], Cotacao]] = []
    if "yahoo" in cfg:
        fs.append(lambda: fetch_yahoo(cfg["yahoo"], nome))
    if "brapi" in cfg:
        fs.append(lambda: fetch_brapi(cfg["brapi"]))
    return fs


def idade_min(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    return (agora() - ts).total_seconds() / 60
