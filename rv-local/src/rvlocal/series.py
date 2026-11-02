"""Histórico de fechamentos: {data ISO: {símbolo: fechamento}}."""
from __future__ import annotations

import statistics

from .util import ler_json, raiz


def caminho():
    return raiz() / "data" / "fechamentos.json"


def carregar() -> dict[str, dict[str, float]]:
    return ler_json(caminho(), {}) or {}


def retorno_dia(fech: dict, simbolo: str, dia: str) -> float | None:
    """Retorno % do fechamento de `dia` contra o fechamento anterior disponível do símbolo."""
    if simbolo not in fech.get(dia, {}):
        return None
    anteriores = sorted(d for d in fech if d < dia and simbolo in fech[d])
    if not anteriores:
        return None
    ant = fech[anteriores[-1]][simbolo]
    if not ant:
        return None
    return (fech[dia][simbolo] / ant - 1) * 100


def sigma_pct(fech: dict, simbolo: str, ate: str | None = None, janela: int = 60, minimo: int = 20) -> float | None:
    """Desvio-padrão dos retornos diários (%). None se houver menos que `minimo` retornos."""
    dias = sorted(d for d in fech if simbolo in fech[d] and (ate is None or d <= ate))
    rets = []
    for i in range(1, len(dias)):
        a, b = fech[dias[i - 1]][simbolo], fech[dias[i]][simbolo]
        if a:
            rets.append((b / a - 1) * 100)
    rets = rets[-janela:]
    if len(rets) < minimo:
        return None
    return statistics.pstdev(rets)


def ultimo_fechamento_antes(fech: dict, simbolo: str, dia: str) -> float | None:
    ds = sorted(d for d in fech if d < dia and simbolo in fech[d])
    return fech[ds[-1]][simbolo] if ds else None
