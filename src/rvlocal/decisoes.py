"""Livro de decisões (data/livros/decisoes.jsonl) e checklist pré-operação.

Toda compra/venda deveria nascer de uma decisão com os 9 itens abaixo. A completude é
medida por código e pesa 15% do boletim (Qualidade das decisões). Operação sem tese
vale ZERO nesse critério.

Tipos: entrada | saida | aumentar | reduzir | stop | realizacao | manter | hedge | revisao
"""
from __future__ import annotations

from datetime import date

from . import livros

TIPOS = {"entrada", "saida", "aumentar", "reduzir", "stop", "realizacao", "manter", "hedge", "revisao"}

CHECKLIST = [
    ("tese_id", "Tese formalizada"),
    ("justificativa", "Justificativa de entrada"),
    ("preco_entrada", "Preço de entrada"),
    ("horizonte", "Horizonte de investimento"),
    ("tamanho_pct", "Tamanho da posição (% do patrimônio)"),
    ("risco_max_pct", "Risco máximo aceitável (% do patrimônio)"),
    ("invalidacao", "Stop ou condição de invalidação"),
    ("objetivo", "Objetivo de retorno (alvo)"),
    ("risco_retorno", "Relação risco-retorno"),
]


def carregar() -> list[dict]:
    return livros.ler("decisoes")


def por_id() -> dict[str, dict]:
    return {d["id"]: d for d in carregar() if d.get("id")}


def risco_retorno(preco: float | None, stop, alvo, lado: str = "compra") -> float | None:
    if not all(isinstance(x, (int, float)) for x in (preco, stop, alvo)):
        return None
    risco = (preco - stop) if lado == "compra" else (stop - preco)
    retorno = (alvo - preco) if lado == "compra" else (preco - alvo)
    return round(retorno / risco, 2) if risco > 0 else None


def completar(chk: dict, lado: str = "compra") -> dict:
    """Calcula o risco-retorno quando há preço, stop numérico e alvo numérico."""
    c = dict(chk)
    if c.get("risco_retorno") in (None, ""):
        rr = risco_retorno(c.get("preco_entrada"), c.get("invalidacao"), c.get("objetivo"), lado)
        if rr is not None:
            c["risco_retorno"] = rr
    return c


def completude(chk: dict) -> tuple[float, list[str]]:
    """(fração preenchida 0..1, itens faltando). Sem tese => 0, sem crédito parcial."""
    faltam = [rot for campo, rot in CHECKLIST if chk.get(campo) in (None, "", [])]
    if chk.get("tese_id") in (None, ""):
        return 0.0, faltam
    return (len(CHECKLIST) - len(faltam)) / len(CHECKLIST), faltam


def checklist_da_operacao(op: dict, decs: dict[str, dict] | None = None) -> dict:
    """Checklist de uma operação: da decisão vinculada, ou dos campos antigos da própria operação."""
    decs = por_id() if decs is None else decs
    d = decs.get(op.get("decisao_id") or "")
    if d:
        base = dict(d.get("checklist") or {})
    else:  # formato da fase 1: tese_id, gatilho, horizonte na própria operação
        base = {"tese_id": op.get("tese_id"), "justificativa": op.get("gatilho"),
                "horizonte": op.get("horizonte")}
    base.setdefault("preco_entrada", op.get("preco"))
    lado = "venda" if op.get("tipo") == "venda" else "compra"
    if lado == "venda":  # numa venda, "entrada" é o preço de saída e o checklist cobra o motivo
        base.setdefault("preco_entrada", op.get("preco"))
    return completar(base, lado)


def registrar(dec: dict) -> dict:
    d = dict(dec)
    dia = d.get("data") or date.today().isoformat()
    d["data"] = dia
    if d.get("tipo") not in TIPOS:
        raise ValueError(f"tipo de decisão inválido {d.get('tipo')!r} (use {sorted(TIPOS)})")
    if not d.get("motivo"):
        raise ValueError("decisão sem 'motivo': toda decisão precisa do porquê")
    d.setdefault("id", livros.proximo_id("decisoes", "DEC", dia))
    d.setdefault("origem", "usuario")
    if "checklist" in d:
        d["checklist"] = completar(d["checklist"], "venda" if d["tipo"] in {"saida", "reduzir"} else "compra")
    return livros.anexar("decisoes", d)
