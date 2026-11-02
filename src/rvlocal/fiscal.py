"""Apuração fiscal mensal (pessoa física, renda variável na B3). Código calcula e mostra a conta.

ATENÇÃO: regras parametrizadas em config/fiscal.toml e A VALIDAR COM O SEU CONTADOR.
Simplificações declaradas:
  * day trade = compra e venda do mesmo ativo no mesmo dia (quantidade casada), lucro pelo PM da posição;
  * IRRF ("dedo-duro") de 0,005% sobre vendas comuns é abatido do imposto do mês;
  * imposto abaixo de R$ 10 acumula para o mês seguinte;
  * exterior (Lei 14.754/2023): só informativo, a apuração é anual na declaração.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import instrumentos
from .calendario import dia_util
from .razao import calcular_estado
from .util import config

CATEGORIA = {"acao": "acoes", "bdr": "bdr", "etf": "etf", "fii": "fii"}


def _cfg() -> dict:
    return config("fiscal.toml", {
        "aliquotas": {"acoes": 15, "bdr": 15, "etf": 15, "fii": 20, "day_trade": 20},
        "isencao_acoes_vendas_mes": 20000.0, "irrf_swing_pct": 0.005, "darf_minimo": 10.0,
        "grupos_compensacao": {"comum": ["acoes", "bdr", "etf"], "fii": ["fii"], "day_trade": ["day_trade"]},
    })


def ultimo_dia_util_mes_seguinte(mes: str) -> str:
    a, m = map(int, mes.split("-"))
    a2, m2 = (a + 1, 1) if m == 12 else (a, m + 1)
    a3, m3 = (a2 + 1, 1) if m2 == 12 else (a2, m2 + 1)
    d = date(a3, m3, 1) - timedelta(days=1)
    while not dia_util(d):
        d -= timedelta(days=1)
    return d.isoformat()


def _day_trades(ops: list[dict]) -> dict[tuple[str, str], float]:
    """{(data, ativo): quantidade casada em day trade}."""
    comp: dict[tuple[str, str], float] = {}
    vend: dict[tuple[str, str], float] = {}
    for o in ops:
        if o["tipo"] in {"compra", "venda"}:
            k = (o["data"], o["ativo"])
            (comp if o["tipo"] == "compra" else vend)[k] = (comp if o["tipo"] == "compra" else vend).get(k, 0) + o["qtd"]
    return {k: min(q, vend[k]) for k, q in comp.items() if k in vend}


def apurar(ops: list[dict], ate_mes: str, cad: dict | None = None) -> list[dict]:
    """Apuração mês a mês até `ate_mes` (AAAA-MM), com prejuízo acumulado por grupo."""
    cad = instrumentos.carregar() if cad is None else cad
    cfg = _cfg()
    est = calcular_estado(ops)
    dts = _day_trades(ops)
    meses: dict[str, dict] = {}
    for v in est.vendas:
        if v["moeda"] != "BRL":
            continue
        mes = v["data"][:7]
        if mes > ate_mes:
            continue
        m = meses.setdefault(mes, {"vendas": {}, "lucro": {}, "vendas_exterior": 0.0})
        classe = instrumentos.info(v["ativo"], cad)["classe"]
        cat = CATEGORIA.get(classe, "acoes")
        q_dt = min(dts.get((v["data"], v["ativo"]), 0), v["qtd"])
        if q_dt:
            frac = q_dt / v["qtd"]
            m["vendas"]["day_trade"] = m["vendas"].get("day_trade", 0) + v["valor"] * frac
            m["lucro"]["day_trade"] = m["lucro"].get("day_trade", 0) + v["lucro"] * frac
            dts[(v["data"], v["ativo"])] -= q_dt
            if frac >= 1:
                continue
            v = {**v, "valor": v["valor"] * (1 - frac), "lucro": v["lucro"] * (1 - frac)}
        m["vendas"][cat] = m["vendas"].get(cat, 0) + v["valor"]
        m["lucro"][cat] = m["lucro"].get(cat, 0) + v["lucro"]
    prejuizo = {g: 0.0 for g in cfg["grupos_compensacao"]}
    acumulado_baixo = 0.0
    saida = []
    for mes in sorted(meses):
        m = meses[mes]
        isento = m["vendas"].get("acoes", 0) <= cfg["isencao_acoes_vendas_mes"]
        linhas, imposto = [], 0.0
        for grupo, cats in cfg["grupos_compensacao"].items():
            base = 0.0
            for c in cats:
                l = m["lucro"].get(c, 0.0)
                if c == "acoes" and isento and l > 0:
                    linhas.append({"categoria": c, "lucro": round(l, 2), "isento": True})
                    continue
                base += l
                if c in m["lucro"]:
                    linhas.append({"categoria": c, "lucro": round(l, 2), "isento": False})
            if base < 0:
                prejuizo[grupo] += -base
                continue
            comp = min(base, prejuizo[grupo])
            prejuizo[grupo] -= comp
            tributavel = base - comp
            # alíquota do grupo: a da 1ª categoria com lucro tributável (simplificação documentada)
            aliq = max((cfg["aliquotas"].get(c, 15) for c in cats if m["lucro"].get(c, 0) > 0), default=15)
            imposto += tributavel * aliq / 100
            if comp:
                linhas.append({"categoria": f"compensação {grupo}", "lucro": round(-comp, 2), "isento": False})
        vendas_comuns = sum(v for c, v in m["vendas"].items() if c != "day_trade")
        irrf = vendas_comuns * cfg["irrf_swing_pct"] / 100
        devido = max(0.0, imposto - irrf) + acumulado_baixo
        darf = devido if devido >= cfg["darf_minimo"] else 0.0
        acumulado_baixo = 0.0 if darf else devido
        saida.append({
            "mes": mes, "vendas": {k: round(v, 2) for k, v in m["vendas"].items()},
            "lucro": {k: round(v, 2) for k, v in m["lucro"].items()}, "linhas": linhas,
            "isencao_acoes": {"vendas": round(m["vendas"].get("acoes", 0), 2),
                              "limite": cfg["isencao_acoes_vendas_mes"],
                              "uso_pct": round(m["vendas"].get("acoes", 0) / cfg["isencao_acoes_vendas_mes"] * 100, 1),
                              "isento": isento},
            "imposto_bruto": round(imposto, 2), "irrf_deduzido": round(irrf, 2),
            "darf": round(darf, 2), "codigo_darf": "6015" if darf else None,
            "vencimento": ultimo_dia_util_mes_seguinte(mes) if darf else None,
            "acumulado_para_proximo_mes": round(acumulado_baixo, 2),
            "prejuizo_a_compensar": {g: round(v, 2) for g, v in prejuizo.items()},
            "natureza": "estimativa",
            "aviso": "Cálculo da plataforma; valide com o seu contador antes de pagar.",
        })
    return saida


def exterior_ano(ops: list[dict], ano: str, fech: dict) -> dict:
    """Realizado no exterior no ano, em moeda e em BRL (câmbio da data). Informativo (Lei 14.754/2023)."""
    from . import series
    est = calcular_estado(ops)
    usd, brl, faltam = 0.0, 0.0, []
    for v in est.vendas:
        if v["moeda"] == "BRL" or not v["data"].startswith(ano):
            continue
        usd += v["lucro"]
        taxa = series.fx(fech, v["data"]).get(v["moeda"])
        if taxa:
            brl += v["lucro"] * taxa
        else:
            faltam.append(v["data"])
    return {"ano": ano, "realizado_moeda": round(usd, 2), "realizado_brl": round(brl, 2),
            "datas_sem_cambio": faltam, "natureza": "estimativa",
            "aviso": "Apuração anual na declaração (15%); confira com o contador."}
