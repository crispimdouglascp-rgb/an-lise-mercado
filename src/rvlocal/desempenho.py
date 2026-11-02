"""Desempenho: retorno ponderado pelo tempo (TWR), consolidado e por sleeve.

Consolidado: R = V_fim / (V_ini + fluxo) - 1, fluxos (aportes/resgates) no início do período.
D3: quando há dias sem patrimônio (lacuna), o retorno é medido contra o ÚLTIMO dia válido,
somando os fluxos do intervalo, e marcado como "retorno de N pregões". Antes, o período
da lacuna sumia do acumulado.

Sleeve (só posições, sem caixa): compras são entradas; vendas e proventos são saídas:
  R = (V_fim + saídas) / (V_ini + entradas) - 1
"""
from __future__ import annotations

from . import instrumentos, series
from .razao import Estado, valor_posicao


def encadear(rets_pct: list[float | None]) -> float | None:
    base, algum = 1.0, False
    for r in rets_pct:
        if r is not None:
            base *= 1 + r / 100
            algum = True
    return (base - 1) * 100 if algum else None


def fluxo_intervalo(fluxos: dict[str, float], d0: str, d1: str) -> float:
    """Soma dos fluxos com d0 < data <= d1."""
    return sum(v for d, v in fluxos.items() if d0 < d <= d1)


def retorno_consolidado(patrimonio: float | None, dia: str, fluxos: dict[str, float],
                        anteriores: list[dict]) -> dict:
    """anteriores: diários anteriores (ordenados). Devolve retorno, base e nº de pregões cobertos."""
    validos = [a for a in anteriores if a.get("patrimonio")]
    if patrimonio is None or not validos:
        return {"retorno_pct": None, "desde": None, "pregoes": None}
    ant = validos[-1]
    fluxo = fluxo_intervalo(fluxos, ant["data"], dia)
    den = ant["patrimonio"] + fluxo
    if den <= 0:
        return {"retorno_pct": None, "desde": ant["data"], "pregoes": None}
    pregoes = 1 + sum(1 for a in anteriores if a["data"] > ant["data"])
    return {"retorno_pct": (patrimonio / den - 1) * 100, "desde": ant["data"], "pregoes": pregoes,
            "fluxo": fluxo}


# ------------------------------------------------------------------ sleeves

def valores_sleeve(est: Estado, precos: dict, fx: dict, cad: dict) -> dict[str, dict]:
    """{sleeve: {valor_brl, valor_local, completo, moeda_local}} das posições abertas."""
    out: dict[str, dict] = {}
    for a, pos in est.posicoes.items():
        s = instrumentos.sleeve(a, cad)
        o = out.setdefault(s, {"valor_brl": 0.0, "valor_local": 0.0, "completo": True,
                               "moeda_local": "BRL" if s == "BR" else pos.moeda})
        p = precos.get(a)
        v = valor_posicao(pos, p, fx) if p is not None else None
        if v is None:
            o["completo"] = False
            continue
        o["valor_brl"] += v
        o["valor_local"] += pos.qtd * p
    return out


def fluxos_sleeve(ops: list[dict], d0: str, d1: str, cad: dict, fech: dict) -> dict[str, dict]:
    """Entradas/saídas por sleeve com d0 < data <= d1, em BRL e na moeda local."""
    out: dict[str, dict] = {}
    for op in ops:
        if not (d0 < op["data"] <= d1) or op["tipo"] not in {"compra", "venda", "provento"}:
            continue
        s = instrumentos.sleeve(op["ativo"], cad)
        o = out.setdefault(s, {"entradas_brl": 0.0, "saidas_brl": 0.0, "entradas_local": 0.0,
                               "saidas_local": 0.0, "completo": True})
        custos = float(op.get("custos", 0.0))
        if op["tipo"] == "compra":
            local = float(op["qtd"]) * float(op["preco"]) + custos
        elif op["tipo"] == "venda":
            local = float(op["qtd"]) * float(op["preco"]) - custos
        else:
            local = float(op["valor"])
        moeda = op.get("moeda", "BRL")
        taxa = 1.0 if moeda == "BRL" else (op.get("cambio") or series.fx(fech, op["data"]).get(moeda))
        lado = "entradas" if op["tipo"] == "compra" else "saidas"
        o[f"{lado}_local"] += local
        if taxa:
            o[f"{lado}_brl"] += local * taxa
        else:
            o["completo"] = False
    return out


def retorno_sleeve(v_ini: float, v_fim: float, entradas: float, saidas: float) -> float | None:
    den = v_ini + entradas
    if den <= 0:
        return None
    return ((v_fim + saidas) / den - 1) * 100


BENCHMARKS = {"BR": "IBOV", "EXT": "SPX"}


def sleeves_do_dia(est: Estado, precos: dict, fx: dict, cad: dict, ops: list[dict], fech: dict,
                   dia: str, anterior: dict | None) -> dict[str, dict]:
    """Valores e retornos por sleeve contra o diário anterior válido."""
    hoje = valores_sleeve(est, precos, fx, cad)
    out: dict[str, dict] = {}
    ant_sl = (anterior or {}).get("sleeves") or {}
    d0 = (anterior or {}).get("data")
    fl = fluxos_sleeve(ops, d0, dia, cad, fech) if d0 else {}
    for s in sorted(set(hoje) | set(ant_sl)):
        h = hoje.get(s, {"valor_brl": 0.0, "valor_local": 0.0, "completo": True,
                         "moeda_local": "BRL" if s == "BR" else "USD"})
        o = {"valor_brl": round(h["valor_brl"], 2) if h["completo"] else None,
             "valor_local": round(h["valor_local"], 2) if h["completo"] else None,
             "moeda_local": h["moeda_local"], "benchmark": BENCHMARKS.get(s)}
        a = ant_sl.get(s)
        f = fl.get(s, {"entradas_brl": 0, "saidas_brl": 0, "entradas_local": 0, "saidas_local": 0, "completo": True})
        if a and a.get("valor_brl") is not None and o["valor_brl"] is not None and f["completo"]:
            o["retorno_pct"] = retorno_sleeve(a["valor_brl"], o["valor_brl"], f["entradas_brl"], f["saidas_brl"])
        if a and a.get("valor_local") is not None and o["valor_local"] is not None:
            o["retorno_local_pct"] = retorno_sleeve(a["valor_local"], o["valor_local"],
                                                    f["entradas_local"], f["saidas_local"])
        b = BENCHMARKS.get(s)
        if b and d0:
            rb = series.retorno_entre(fech, b, d0, dia)
            o["benchmark_local_pct"] = rb
            if s == "EXT" and rb is not None:
                rfx = series.retorno_entre(fech, "USDBRL", d0, dia)
                o["benchmark_pct"] = ((1 + rb / 100) * (1 + rfx / 100) - 1) * 100 if rfx is not None else None
            else:
                o["benchmark_pct"] = rb
        for k in ("retorno_pct", "retorno_local_pct", "benchmark_pct", "benchmark_local_pct"):
            if o.get(k) is not None:
                o[k] = round(o[k], 4)
        out[s] = o
    return out


def curva(diarios: list[dict], campo: str = "retorno_dia_pct", sleeve: str | None = None,
          sub: str = "retorno_pct") -> list[tuple[str, float]]:
    """Índice base 100 ao longo dos diários (para gráficos e boletim)."""
    nivel, out = 100.0, []
    for d in diarios:
        r = ((d.get("sleeves") or {}).get(sleeve) or {}).get(sub) if sleeve else d.get(campo)
        if r is not None:
            nivel *= 1 + r / 100
        out.append((d["data"], round(nivel, 4)))
    return out
