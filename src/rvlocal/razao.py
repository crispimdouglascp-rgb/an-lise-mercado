"""Razão: posições, caixa, fluxos e realizado reconstruídos a partir do livro de operações.

Livro: data/livros/operacoes.jsonl (só por acréscimo; erro se corrige com nova linha).

Tipos de operação:
  aporte / resgate   {"valor": R$}                       fluxo externo, sempre em BRL
  compra / venda     {"ativo","qtd","preco","custos","moeda"?}  preço na moeda do instrumento
  provento           {"ativo","valor","moeda"?}           crédito no caixa da moeda
  cambio             {"de":"BRL","para":"USD","valor_de","valor_para","custos"?}
                     transferência interna entre caixas; NÃO é fluxo
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from . import livros
from .util import p_livro

TIPOS = {"compra", "venda", "aporte", "resgate", "provento", "cambio"}
TIPOS_COM_ATIVO = {"compra", "venda", "provento"}
TOL_CAIXA = 0.01


def p_operacoes():
    return p_livro("operacoes.jsonl")


def p_decisoes():
    return p_livro("decisoes.jsonl")


@dataclass
class Posicao:
    ativo: str
    qtd: float = 0.0
    custo_total: float = 0.0  # custo de aquisição das ações em carteira (moeda do ativo)
    moeda: str = "BRL"

    @property
    def pm(self) -> float:
        return self.custo_total / self.qtd if self.qtd else 0.0


@dataclass
class Estado:
    posicoes: dict[str, Posicao] = field(default_factory=dict)
    caixa: float = 0.0                                            # caixa em BRL
    caixa_moeda: dict[str, float] = field(default_factory=dict)  # caixas em outras moedas
    fluxos: dict[str, float] = field(default_factory=dict)       # data -> aportes - resgates (BRL)
    realizado: dict[str, float] = field(default_factory=dict)    # data -> realizado em BRL (ativos BRL)
    realizado_moeda: dict[str, dict[str, float]] = field(default_factory=dict)  # moeda -> data -> valor
    proventos: dict[str, float] = field(default_factory=dict)    # data -> proventos em BRL
    vendas: list[dict] = field(default_factory=list)             # cada venda com PM e lucro (fiscal, boletim)
    encerradas: list[dict] = field(default_factory=list)         # posições zeradas

    def caixa_em(self, moeda: str) -> float:
        return self.caixa if moeda == "BRL" else self.caixa_moeda.get(moeda, 0.0)

    def _mover_caixa(self, moeda: str, v: float) -> None:
        if moeda == "BRL":
            self.caixa += v
        else:
            self.caixa_moeda[moeda] = self.caixa_moeda.get(moeda, 0.0) + v


def carregar_operacoes() -> list[dict]:
    ops = livros.ler("operacoes")
    return sorted(ops, key=lambda o: o["data"])  # estável: mantém a ordem do arquivo no dia


def carregar_decisoes() -> list[dict]:
    return livros.ler("decisoes")


def calcular_estado(ops: list[dict], ate: str | None = None,
                    ao_fim_do_dia: Callable[[str, Estado], None] | None = None) -> Estado:
    """Reconstrói posições e caixas a partir das operações, até `ate` (inclusive)."""
    est = Estado()
    dia_atual = None
    for op in ops:
        d = op["data"]
        if ate and d > ate:
            continue
        if ao_fim_do_dia and dia_atual is not None and d != dia_atual:
            ao_fim_do_dia(dia_atual, est)
        dia_atual = d
        t = op["tipo"]
        custos = float(op.get("custos", 0.0))
        moeda = op.get("moeda", "BRL")
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
            est._mover_caixa(moeda, v)
            if moeda == "BRL":
                est.proventos[d] = est.proventos.get(d, 0.0) + v
        elif t == "cambio":
            est._mover_caixa(op["de"], -float(op["valor_de"]) - custos)
            est._mover_caixa(op["para"], float(op["valor_para"]))
        elif t == "compra":
            a, q, p = op["ativo"], float(op["qtd"]), float(op["preco"])
            pos = est.posicoes.setdefault(a, Posicao(a, moeda=moeda))
            pos.qtd += q
            pos.custo_total += q * p + custos
            est._mover_caixa(moeda, -(q * p + custos))
        elif t == "venda":
            a, q, p = op["ativo"], float(op["qtd"]), float(op["preco"])
            pos = est.posicoes.setdefault(a, Posicao(a, moeda=moeda))
            if q > pos.qtd + 1e-9:
                raise ValueError(f"venda de {q} {a} em {d} excede a posição ({pos.qtd})")
            pm = pos.pm
            lucro = (p - pm) * q - custos
            if moeda == "BRL":
                est.realizado[d] = est.realizado.get(d, 0.0) + lucro
            else:
                rm = est.realizado_moeda.setdefault(moeda, {})
                rm[d] = rm.get(d, 0.0) + lucro
            est.vendas.append({"data": d, "ativo": a, "qtd": q, "preco": p, "pm": pm, "custos": custos,
                               "valor": q * p, "lucro": lucro, "moeda": moeda, "op_id": op.get("id"),
                               "decisao_id": op.get("decisao_id")})
            pos.qtd -= q
            pos.custo_total -= pm * q
            est._mover_caixa(moeda, q * p - custos)
            if pos.qtd < 1e-9:
                est.encerradas.append({"ativo": a, "data": d, "moeda": moeda})
                del est.posicoes[a]
    if ao_fim_do_dia and dia_atual is not None:
        ao_fim_do_dia(dia_atual, est)
    return est


def valor_posicao(pos: Posicao, preco: float, fx: dict[str, float] | None = None) -> float | None:
    """Valor em BRL. None se faltar câmbio (nunca estimado)."""
    v = pos.qtd * preco
    if pos.moeda == "BRL":
        return v
    taxa = (fx or {}).get(pos.moeda)
    return v * taxa if taxa else None


def valor_carteira(est: Estado, precos: dict[str, float], fx: dict[str, float] | None = None
                   ) -> tuple[float, list[str]]:
    """Patrimônio em BRL = caixas + posições a mercado. Retorna (valor, lacunas).

    Ativo sem preço (ou sem câmbio) NÃO é estimado: fica fora e é listado como lacuna.
    """
    total = est.caixa
    sem_preco: list[str] = []
    for m, v in est.caixa_moeda.items():
        if abs(v) < 1e-9:
            continue
        taxa = (fx or {}).get(m)
        if taxa:
            total += v * taxa
        else:
            sem_preco.append(f"câmbio {m}")
    for a, pos in est.posicoes.items():
        p = precos.get(a)
        v = valor_posicao(pos, p, fx) if p is not None else None
        if v is None:
            sem_preco.append(a)
        else:
            total += v
    return total, sem_preco


def validar(ops: list[dict] | None = None) -> list[str]:
    """Checagens de consistência do razão. Lista vazia = ok."""
    from . import hipoteses, instrumentos, teses
    problemas: list[str] = []
    try:
        ops = ops if ops is not None else carregar_operacoes()
    except ValueError as e:
        return [str(e)]
    cad = instrumentos.carregar()
    try:
        tese_ids = {h["id"] for h in hipoteses.carregar()} | {t["tese_id"] for t in teses.versoes()}
    except ValueError as e:
        problemas.append(str(e))
        tese_ids = set()
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
        if op.get("natureza", "real") not in livros.NATUREZAS:
            problemas.append(f"{rot}: natureza inválida {op.get('natureza')!r}")
        if op["tipo"] in TIPOS_COM_ATIVO and not op.get("ativo"):
            problemas.append(f"{rot}: falta 'ativo'")
        if op["tipo"] in {"compra", "venda"}:
            for c in ("qtd", "preco"):
                if not isinstance(op.get(c), (int, float)) or op[c] <= 0:
                    problemas.append(f"{rot}: '{c}' deve ser número positivo")
            if op.get("ativo") and op["ativo"] not in cad:
                problemas.append(f"{rot}: {op['ativo']} não está em data/livros/instrumentos.json")
            elif op.get("ativo") and op.get("moeda", "BRL") != instrumentos.moeda(op["ativo"], cad):
                problemas.append(f"{rot}: moeda {op.get('moeda', 'BRL')} difere da moeda do instrumento "
                                 f"{op['ativo']} ({instrumentos.moeda(op['ativo'], cad)})")
            if op.get("tese_id") and op["tese_id"] not in tese_ids:
                problemas.append(f"{rot}: tese_id {op['tese_id']} não existe em teses nem em hipóteses")
        if op["tipo"] in {"aporte", "resgate", "provento"} and not isinstance(op.get("valor"), (int, float)):
            problemas.append(f"{rot}: falta 'valor' numérico")
        if op["tipo"] in {"aporte", "resgate"} and op.get("moeda", "BRL") != "BRL":
            problemas.append(f"{rot}: aporte/resgate só em BRL (use uma operação 'cambio' para outra moeda)")
        if op["tipo"] == "cambio":
            for c in ("de", "para", "valor_de", "valor_para"):
                if c not in op:
                    problemas.append(f"{rot}: câmbio sem '{c}'")

    def _caixa_nao_negativo(dia: str, est: Estado) -> None:
        for m in {"BRL", *est.caixa_moeda}:
            v = est.caixa_em(m)
            if v < -TOL_CAIXA:
                problemas.append(f"caixa {m} negativo no fim de {dia}: {v:,.2f}. Falta um aporte/câmbio "
                                 "ou a operação está errada (alavancagem não é suportada).")

    try:
        calcular_estado([o for o in ops if o.get("tipo") in TIPOS and "data" in o],
                        ao_fim_do_dia=_caixa_nao_negativo)
    except (ValueError, KeyError) as e:
        problemas.append(str(e))
    return problemas


def registrar_operacao(op: dict[str, Any]) -> dict:
    return livros.anexar("operacoes", op)


def registrar_decisao(dec: dict[str, Any]) -> dict:
    from . import decisoes
    return decisoes.registrar(dec)
