"""Razão: fonte da verdade da carteira (operações, posições, caixa, fluxos).

Arquivos (em data/):
  operacoes.jsonl  uma operação por linha (append-only; erro se corrige com nova linha)
  ativos.json      parâmetros por ativo (setor, alvo, stop, tese)
  hipoteses.json   hipóteses com teste escrito antes
  decisoes.jsonl   decisões registradas (stop, realização, etc.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .util import anexar_jsonl, ler_json, ler_jsonl, raiz

TIPOS = {"compra", "venda", "aporte", "resgate", "provento"}
TIPOS_COM_ATIVO = {"compra", "venda", "provento"}


def p_operacoes():
    return raiz() / "data" / "operacoes.jsonl"


def p_ativos():
    return raiz() / "data" / "ativos.json"


def p_hipoteses():
    return raiz() / "data" / "hipoteses.json"


def p_decisoes():
    return raiz() / "data" / "decisoes.jsonl"


@dataclass
class Posicao:
    ativo: str
    qtd: float = 0.0
    custo_total: float = 0.0  # custo de aquisição das ações em carteira

    @property
    def pm(self) -> float:
        return self.custo_total / self.qtd if self.qtd else 0.0


@dataclass
class Estado:
    posicoes: dict[str, Posicao] = field(default_factory=dict)
    caixa: float = 0.0
    fluxos: dict[str, float] = field(default_factory=dict)       # data ISO -> aportes - resgates
    realizado: dict[str, float] = field(default_factory=dict)    # data ISO -> lucro realizado
    proventos: dict[str, float] = field(default_factory=dict)    # data ISO -> proventos


def carregar_operacoes() -> list[dict]:
    ops = ler_jsonl(p_operacoes())
    # ordenação estável: por data, mantendo a ordem do arquivo dentro do dia
    return sorted(ops, key=lambda o: o["data"])


def carregar_ativos() -> dict[str, dict]:
    return ler_json(p_ativos(), {}) or {}


def carregar_hipoteses() -> list[dict]:
    return ler_json(p_hipoteses(), []) or []


def carregar_decisoes() -> list[dict]:
    return ler_jsonl(p_decisoes())


def calcular_estado(ops: list[dict], ate: str | None = None) -> Estado:
    """Reconstrói posições e caixa a partir das operações, até a data `ate` (inclusive)."""
    est = Estado()
    for op in ops:
        d = op["data"]
        if ate and d > ate:
            continue
        t = op["tipo"]
        custos = float(op.get("custos", 0.0))
        if t == "aporte":
            v = float(op["valor"])
            est.caixa += v
            est.fluxos[d] = est.fluxos.get(d, 0.0) + v
        elif t == "resgate":
            v = float(op["valor"])
            est.caixa -= v
            est.fluxos[d] = est.fluxos.get(d, 0.0) - v
        elif t == "provento":
            v = float(op["valor"])
            est.caixa += v
            est.proventos[d] = est.proventos.get(d, 0.0) + v
        elif t == "compra":
            a, q, p = op["ativo"], float(op["qtd"]), float(op["preco"])
            pos = est.posicoes.setdefault(a, Posicao(a))
            pos.qtd += q
            pos.custo_total += q * p + custos
            est.caixa -= q * p + custos
        elif t == "venda":
            a, q, p = op["ativo"], float(op["qtd"]), float(op["preco"])
            pos = est.posicoes.setdefault(a, Posicao(a))
            if q > pos.qtd + 1e-9:
                raise ValueError(f"venda de {q} {a} em {d} excede a posição ({pos.qtd})")
            pm = pos.pm
            est.realizado[d] = est.realizado.get(d, 0.0) + (p - pm) * q - custos
            pos.qtd -= q
            pos.custo_total -= pm * q
            est.caixa += q * p - custos
            if pos.qtd < 1e-9:
                del est.posicoes[a]
    return est


def valor_carteira(est: Estado, precos: dict[str, float]) -> tuple[float, list[str]]:
    """Patrimônio = caixa + posições a mercado. Retorna (valor, ativos sem preço).

    Ativo sem preço NÃO é estimado: fica fora do valor e é listado como lacuna.
    """
    total = est.caixa
    sem_preco = []
    for a, pos in est.posicoes.items():
        p = precos.get(a)
        if p is None:
            sem_preco.append(a)
        else:
            total += pos.qtd * p
    return total, sem_preco


def validar(ops: list[dict] | None = None) -> list[str]:
    """Checagens de consistência do razão. Lista vazia = ok."""
    problemas: list[str] = []
    try:
        ops = ops if ops is not None else carregar_operacoes()
    except ValueError as e:
        return [str(e)]
    ativos = carregar_ativos()
    hip_ids = {h["id"] for h in carregar_hipoteses()}
    ids_vistos: set[str] = set()
    for i, op in enumerate(ops, 1):
        rot = f"op {op.get('id', i)}"
        if op.get("id"):
            if op["id"] in ids_vistos:
                problemas.append(f"{rot}: id duplicado")
            ids_vistos.add(op["id"])
        if op.get("tipo") not in TIPOS:
            problemas.append(f"{rot}: tipo inválido {op.get('tipo')!r}")
            continue
        try:
            date.fromisoformat(op["data"])
        except Exception:
            problemas.append(f"{rot}: data inválida {op.get('data')!r}")
        if op["tipo"] in TIPOS_COM_ATIVO and not op.get("ativo"):
            problemas.append(f"{rot}: falta 'ativo'")
        if op["tipo"] in {"compra", "venda"}:
            for c in ("qtd", "preco"):
                if not isinstance(op.get(c), (int, float)) or op[c] <= 0:
                    problemas.append(f"{rot}: '{c}' deve ser número positivo")
            if op.get("ativo") and op["ativo"] not in ativos:
                problemas.append(f"{rot}: {op['ativo']} não está em data/ativos.json")
            if op.get("tese_id") and op["tese_id"] not in hip_ids:
                problemas.append(f"{rot}: tese_id {op['tese_id']} não existe em hipoteses.json")
        if op["tipo"] in {"aporte", "resgate", "provento"} and not isinstance(op.get("valor"), (int, float)):
            problemas.append(f"{rot}: falta 'valor' numérico")
    try:
        calcular_estado(ops)
    except ValueError as e:
        problemas.append(str(e))
    return problemas


def registrar_operacao(op: dict[str, Any]) -> None:
    anexar_jsonl(p_operacoes(), op)


def registrar_decisao(dec: dict[str, Any]) -> None:
    anexar_jsonl(p_decisoes(), dec)
