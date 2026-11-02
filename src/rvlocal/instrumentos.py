"""Cadastro de instrumentos (data/livros/instrumentos.json).

Atributos estáveis de cada ticker. Parâmetros de posição (alvo, stop, nível de compra)
moram na ficha de tese vigente; `parametros()` junta os dois.

Exemplo:
  "WEGE3": {"classe": "acao", "moeda": "BRL", "pais": "BR", "setor": "industria",
            "fatores": ["exportadora"], "receita_usd_pct": 50, "nome": "WEG"}
  "VOO":   {"classe": "etf_ext", "moeda": "USD", "pais": "US", "setor": "indice_eua"}
"""
from __future__ import annotations

from datetime import date

from .util import ler_json, p_livro

CLASSES = {"acao", "fii", "etf", "bdr", "acao_ext", "etf_ext", "opcao", "rf", "fundo", "cripto"}
PADRAO = {"classe": "acao", "moeda": "BRL", "pais": "BR", "setor": "sem setor", "fatores": [],
          "receita_usd_pct": 0, "lote": 1}


def caminho():
    return p_livro("instrumentos.json")


def carregar() -> dict[str, dict]:
    return ler_json(caminho(), {}) or {}


def info(ticker: str, cad: dict | None = None) -> dict:
    cad = carregar() if cad is None else cad
    return {**PADRAO, **cad.get(ticker, {})}


def sleeve(ticker: str, cad: dict | None = None) -> str:
    """BR = renda variável listada no Brasil; EXT = exterior."""
    return "BR" if info(ticker, cad)["pais"] == "BR" else "EXT"


def moeda(ticker: str, cad: dict | None = None) -> str:
    return info(ticker, cad)["moeda"]


def simbolo_yahoo(ticker: str, cad: dict | None = None) -> str:
    i = info(ticker, cad)
    if i.get("yahoo"):
        return i["yahoo"]
    return f"{ticker}.SA" if i["pais"] == "BR" else ticker


def usa_brapi(ticker: str, cad: dict | None = None) -> bool:
    i = info(ticker, cad)
    return i["pais"] == "BR" and i.get("brapi", True)


def validar(cad: dict | None = None) -> list[str]:
    cad = carregar() if cad is None else cad
    probs = []
    for t, i in cad.items():
        if i.get("classe", "acao") not in CLASSES:
            probs.append(f"instrumento {t}: classe inválida {i.get('classe')!r}")
        if not isinstance(i.get("fatores", []), list):
            probs.append(f"instrumento {t}: 'fatores' deve ser lista")
    return probs


def parametros(dia: date | str | None = None, cad: dict | None = None) -> dict[str, dict]:
    """Instrumento + ficha de tese vigente (alvo, stop, nível de compra, tese_id, rating)."""
    from . import teses
    cad = carregar() if cad is None else cad
    out = {t: info(t, cad) for t in cad}
    d = dia.isoformat() if isinstance(dia, date) else dia
    for t in out:
        f = teses.vigente(t, d)
        if f:
            for campo in ("alvo", "stop", "nivel_compra", "rating", "conviccao", "preco_justo"):
                if f.get(campo) is not None:
                    out[t][campo] = f[campo]
            out[t]["tese_id"] = f["tese_id"]
            out[t]["tese_versao"] = f["versao"]
    return out
