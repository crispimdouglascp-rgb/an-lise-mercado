"""Fichas de tese por posição, versionadas (data/livros/teses.jsonl).

Tese ≠ hipótese: a TESE é o porquê de ter o ativo (valor, cenários, invalidação);
a HIPÓTESE é uma relação testável medida pelo placar.

Cada mudança é uma NOVA VERSÃO (com `motivo_mudanca`); nada é reescrito.
Ficha escrita pela IA (`origem: "ia"`) só vale depois do seu "sim" (`confirmado_em`).

Campos: tese_id, versao, data, ativo, titulo, tese, fundamentacao, analise_fundamentalista,
crescimento, vantagens, riscos[], catalisadores[], horizonte, preco_justo, metodo_valuation,
cenarios{otimista|base|pessimista: {preco, prob}}, muda_de_ideia_se, nivel_compra, alvo, stop,
rating (BUY|HOLD|SELL), conviccao (1-5), proxima_revisao, motivo_mudanca, origem, natureza.
"""
from __future__ import annotations

from datetime import date

from . import livros

CENARIOS = ("otimista", "base", "pessimista")
RATINGS = {"BUY", "HOLD", "SELL"}


def versoes() -> list[dict]:
    return livros.ler("teses")


def _valida(f: dict) -> bool:
    return f.get("origem", "usuario") != "ia" or bool(f.get("confirmado_em"))


def historico(ativo: str) -> list[dict]:
    return [f for f in versoes() if f.get("ativo") == ativo]


def vigente(ativo: str, dia: str | None = None) -> dict | None:
    """Última versão válida da ficha do ativo com data <= dia."""
    cands = [f for f in versoes() if f.get("ativo") == ativo and _valida(f)
             and (dia is None or f.get("data", "") <= dia)]
    return cands[-1] if cands else None


def todas_vigentes(dia: str | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in versoes():
        if _valida(f) and (dia is None or f.get("data", "") <= dia):
            out[f["ativo"]] = f
    return out


def nova_versao(ficha: dict, dia: date | str) -> dict:
    d = dia.isoformat() if isinstance(dia, date) else dia
    ativo = ficha["ativo"]
    ant = [f for f in versoes() if f.get("ativo") == ativo]
    tese_id = ficha.get("tese_id") or (ant[-1]["tese_id"] if ant else f"T-{ativo}")
    reg = {**ficha, "tese_id": tese_id, "versao": len([f for f in ant if f["tese_id"] == tese_id]) + 1,
           "data": d}
    if ant and not reg.get("motivo_mudanca"):
        raise ValueError("nova versão de ficha exige 'motivo_mudanca' (a memória de mudanças conta no boletim)")
    probs = validar_ficha(reg)
    if probs:
        raise ValueError("; ".join(probs))
    return livros.anexar("teses", reg)


def validar_ficha(f: dict) -> list[str]:
    probs = []
    if not f.get("ativo"):
        probs.append("ficha sem 'ativo'")
    if f.get("rating") and f["rating"] not in RATINGS:
        probs.append(f"rating inválido {f['rating']!r} (use {sorted(RATINGS)})")
    if f.get("conviccao") is not None and not (1 <= f["conviccao"] <= 5):
        probs.append("conviccao deve estar entre 1 e 5")
    cen = f.get("cenarios") or {}
    probs_soma = [c.get("prob") for c in cen.values() if isinstance(c, dict) and c.get("prob") is not None]
    if probs_soma and abs(sum(probs_soma) - 1) > 0.01:
        probs.append(f"probabilidades dos cenários somam {sum(probs_soma):.2f}, não 1")
    st, al = f.get("stop"), f.get("alvo")
    if isinstance(st, (int, float)) and isinstance(al, (int, float)) and st >= al:
        probs.append("stop deve ser menor que o alvo")
    return probs


def validar() -> list[str]:
    probs = []
    vistos: dict[str, list[dict]] = {}
    for f in versoes():
        vistos.setdefault(f.get("tese_id", "?"), []).append(f)
        probs += [f"tese {f.get('tese_id')} v{f.get('versao')}: {p}" for p in validar_ficha(f)]
    for tid, vs in vistos.items():
        if [v.get("versao") for v in vs] != list(range(1, len(vs) + 1)):
            probs.append(f"tese {tid}: versões fora de sequência {[v.get('versao') for v in vs]}")
        if [v.get("data") for v in vs] != sorted(v.get("data") for v in vs):
            probs.append(f"tese {tid}: datas das versões fora de ordem")
        if len({v.get("ativo") for v in vs}) > 1:
            probs.append(f"tese {tid}: mudou de ativo entre versões")
    return probs


# ------------------------------------------------------------------ números da ficha (código)

def valor_esperado(f: dict) -> float | None:
    cen = f.get("cenarios") or {}
    itens = [(c["preco"], c["prob"]) for c in cen.values()
             if isinstance(c, dict) and c.get("preco") is not None and c.get("prob") is not None]
    if not itens or abs(sum(p for _, p in itens) - 1) > 0.01:
        return None
    return sum(v * p for v, p in itens)


def margem_seguranca_pct(f: dict, preco: float | None) -> float | None:
    pj = f.get("preco_justo")
    if not pj or not preco:
        return None
    return (pj / preco - 1) * 100


def upside_pct(f: dict, preco: float | None) -> float | None:
    al = f.get("alvo")
    return (al / preco - 1) * 100 if al and preco else None


def revisao_vencida(f: dict, dia: str) -> bool:
    return bool(f.get("proxima_revisao")) and f["proxima_revisao"] < dia
