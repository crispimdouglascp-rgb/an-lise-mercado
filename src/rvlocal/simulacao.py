"""Testar e acompanhar carteiras: pesos-alvo, rebalanceamento e reprocessamento do histórico.

  rebalancear()   transforma pesos-alvo (ex.: carteira recomendada de um analista) em ordens
                  REGISTRADAS no livro da carteira, a preço de fechamento da data. Nada vai à corretora.
  reprocessar()   roda o fechamento pregão a pregão num intervalo (o mesmo código da rotina diária)
                  e emite os boletins nas viradas de semana, mês e trimestre.
  carregar_historico()  backfill de fechamentos no mercado.db (Yahoo, fonte única, marcado como tal).

Honestidade: preço ausente na data recusa o rebalanceamento (nunca estima); a quantidade é
arredondada para baixo ao lote do ativo; o que sobra fica em caixa e aparece no peso efetivo.
"""
from __future__ import annotations

import math
import os
from datetime import date, timedelta

from . import boletim, decisoes, diario, instrumentos, livros, razao, series
from .calendario import dia_util


def interpretar_pesos(texto: str) -> dict[str, float]:
    """'PETR4=20, VALE3=15' -> {'PETR4': 20.0, 'VALE3': 15.0}"""
    out = {}
    for parte in texto.replace(";", ",").split(","):
        if parte.strip():
            t, v = parte.split("=")
            out[t.strip().upper()] = float(v.strip().replace("%", ""))
    return out


def _preco_na_data(fech: dict, ativo: str, dia: str) -> float | None:
    return fech.get(dia, {}).get(ativo)


def rebalancear(pesos: dict[str, float], dia: str, capital: float | None = None, custos_pct: float = 0.0,
                justificativa: str | None = None, fonte: str | None = None, tese_id: str | None = None,
                horizonte: str | None = None, gravar: bool = True) -> dict:
    """Gera as ordens para levar a carteira aos pesos-alvo (% do patrimônio) no fechamento de `dia`.

    Ativos fora de `pesos` e presentes na carteira são zerados. `capital` = aporte inicial em R$
    (só quando a carteira ainda não tem patrimônio). Retorna o plano; com gravar=True, registra
    UMA decisão de rebalanceamento e as operações vinculadas a ela.
    """
    soma = sum(pesos.values())
    if soma > 100.0001 or any(v < 0 for v in pesos.values()):
        raise ValueError(f"pesos somam {soma:.2f}% (máximo 100%; o resto fica em caixa) e não podem ser negativos")
    cad = instrumentos.carregar()
    faltam_cad = [a for a in pesos if a not in cad]
    if faltam_cad:
        raise ValueError(f"cadastre no universo antes: {', '.join(faltam_cad)} (rvlocal ativo ...)")
    fech = series.carregar()
    fx = series.fx(fech, dia)
    ops = razao.carregar_operacoes()
    est = razao.calcular_estado(ops, ate=dia)
    novas: list[dict] = []
    if capital:
        novas.append({"tipo": "aporte", "valor": float(capital)})
    caixa_brl = est.caixa + (capital or 0.0)
    ativos = sorted(set(pesos) | set(est.posicoes))
    precos = {a: _preco_na_data(fech, a, dia) for a in ativos}
    sem_preco = [a for a, p in precos.items() if p is None]
    if sem_preco:
        raise ValueError(f"sem fechamento em {dia} para {', '.join(sem_preco)}: carregue o histórico "
                         "(rvlocal historico) ou escolha outra data. Preço não é estimado.")
    moedas = {a: instrumentos.moeda(a, cad) for a in ativos}
    if any(m != "BRL" for m in moedas.values()) and "USD" not in fx:
        raise ValueError(f"sem câmbio USDBRL em {dia}: carregue o histórico do dólar")
    taxa = {a: 1.0 if moedas[a] == "BRL" else fx[moedas[a]] for a in ativos}
    pat = caixa_brl + sum(v * fx.get(m, 0.0) for m, v in est.caixa_moeda.items()) + \
        sum(est.posicoes[a].qtd * precos[a] * taxa[a] for a in est.posicoes)
    if pat <= 0:
        raise ValueError("carteira sem patrimônio: informe o capital inicial (--capital)")
    plano = []
    for a in ativos:
        lote = max(1, int(instrumentos.info(a, cad).get("lote", 1)))
        atual = est.posicoes[a].qtd if a in est.posicoes else 0.0
        alvo_brl = pat * pesos.get(a, 0.0) / 100
        alvo_qtd = math.floor(alvo_brl / (precos[a] * taxa[a]) / lote) * lote
        delta = alvo_qtd - atual
        plano.append({"ativo": a, "atual": atual, "alvo": alvo_qtd, "delta": delta, "preco": precos[a],
                      "moeda": moedas[a], "peso_alvo": pesos.get(a, 0.0),
                      "peso_efetivo": round(alvo_qtd * precos[a] * taxa[a] / pat * 100, 2)})
    # vendas primeiro (liberam caixa), depois câmbio do que faltar em USD, depois compras
    usd_disp = est.caixa_moeda.get("USD", 0.0)
    for p in plano:
        if p["delta"] < 0:
            v = -p["delta"] * p["preco"]
            novas.append(_ordem("venda", p, -p["delta"], custos_pct))
            if p["moeda"] == "USD":
                usd_disp += v * (1 - custos_pct / 100)
            else:
                caixa_brl += v * (1 - custos_pct / 100)
    usd_compras = sum(p["delta"] * p["preco"] * (1 + custos_pct / 100) for p in plano
                      if p["delta"] > 0 and p["moeda"] == "USD")
    brl_compras = sum(p["delta"] * p["preco"] * (1 + custos_pct / 100) for p in plano
                      if p["delta"] > 0 and p["moeda"] == "BRL")
    sobra_usd = usd_disp - usd_compras
    if brl_compras > caixa_brl + 1e-6 and sobra_usd > 0 and "USD" in fx:
        # saiu do exterior para comprar no Brasil: converte de volta só o necessário (arredondado a favor)
        usd_vender = min(sobra_usd, math.ceil((brl_compras - caixa_brl) / fx["USD"] * 100) / 100)
        valor_para = math.floor(usd_vender * fx["USD"] * 100) / 100
        novas.append({"tipo": "cambio", "de": "USD", "para": "BRL", "valor_de": usd_vender, "valor_para": valor_para})
        caixa_brl += valor_para
        usd_disp -= usd_vender
    if usd_compras > usd_disp + 1e-6:
        precisa = math.ceil((usd_compras - usd_disp) * 100) / 100   # arredonda PARA CIMA: nunca falta centavo
        valor_de = math.ceil(precisa * fx["USD"] * 100) / 100
        novas.append({"tipo": "cambio", "de": "BRL", "para": "USD", "valor_de": valor_de, "valor_para": precisa})
        caixa_brl -= valor_de
    for p in plano:
        if p["delta"] > 0:
            novas.append(_ordem("compra", p, p["delta"], custos_pct))
            if p["moeda"] == "BRL":
                caixa_brl -= p["delta"] * p["preco"] * (1 + custos_pct / 100)
    resumo = {"data": dia, "patrimonio": round(pat, 2), "plano": plano, "operacoes": novas,
              "caixa_final_brl": round(caixa_brl, 2), "peso_caixa_pct": round(caixa_brl / pat * 100, 2)}
    if not gravar:
        return resumo
    seq = sum(1 for o in ops if o["data"] == dia)
    teste = ops + [{**o, "data": dia, "id": f"x{i}"} for i, o in enumerate(novas)]
    probs = [p for p in razao.validar(teste) if p not in razao.validar(ops)]
    if probs:
        raise ValueError("rebalanceamento deixaria o razão inconsistente: " + "; ".join(probs))
    d = None
    if any(o["tipo"] in {"compra", "venda"} for o in novas):
        d = decisoes.registrar({
            "data": dia, "tipo": "rebalanceamento", "ativo": None, "decisao": "rebalancear para pesos-alvo",
            "motivo": justificativa or (f"Carteira recomendada de {fonte}" if fonte else "Pesos-alvo da carteira"),
            "pesos_alvo": pesos, "fonte": fonte,
            "checklist": {"tese_id": tese_id, "justificativa": justificativa or (f"Recomendação de {fonte}" if fonte else None),
                          "horizonte": horizonte}})
    for i, o in enumerate(novas, 1):
        reg = {"id": f"op-{dia}-r{seq + i:03d}", "data": dia, **o}
        if d and o["tipo"] in {"compra", "venda"}:
            reg["decisao_id"] = d["id"]   # a "tese" (ex.: a recomendação) fica no checklist da decisão
        livros.anexar("operacoes", reg)
    resumo["decisao_id"] = d["id"] if d else None
    return resumo


def _ordem(tipo: str, p: dict, qtd: float, custos_pct: float) -> dict:
    o = {"tipo": tipo, "ativo": p["ativo"], "qtd": qtd, "preco": p["preco"],
         "custos": round(qtd * p["preco"] * custos_pct / 100, 2)}
    if p["moeda"] != "BRL":
        o["moeda"] = p["moeda"]
    return o


def pregoes_com_preco(desde: str, ate: str) -> list[str]:
    fech = series.carregar()
    return [d for d in sorted(fech) if desde <= d <= ate and dia_util(date.fromisoformat(d))]


def reprocessar(desde: str, ate: str, boletins: bool = True, ao_fechar=None) -> list[str]:
    """Fecha cada pregão com preço no intervalo (repescagem/simulação). Livros não são alterados,
    exceto pelos acréscimos normais do fechamento (pontos de hipótese, mesa, boletins)."""
    dias = pregoes_com_preco(desde, ate)
    antes = os.environ.get("RVLOCAL_AGORA")
    try:
        for i, d in enumerate(dias):
            os.environ["RVLOCAL_AGORA"] = f"{d}T18:05:00-03:00"
            diario.fechar_dia(d, enviar=False)
            if ao_fechar:
                ao_fechar(d)
            if not boletins:
                continue
            dd = date.fromisoformat(d)
            prox = date.fromisoformat(dias[i + 1]) if i + 1 < len(dias) else None
            if prox is None or prox.isocalendar()[1] != dd.isocalendar()[1]:
                boletim.emitir("semanal", dd)
            if prox is None or prox.month != dd.month:
                boletim.emitir("mensal", dd)
                if dd.month % 3 == 0 or prox is None:
                    boletim.emitir("trimestral", dd)
    finally:
        if antes is None:
            os.environ.pop("RVLOCAL_AGORA", None)
        else:
            os.environ["RVLOCAL_AGORA"] = antes
    return dias


def carregar_historico(simbolos: list[str] | None = None, periodo: str = "2y") -> dict[str, int | str]:
    """Backfill de fechamentos diários (Yahoo) para o universo e as séries de contexto.

    Fonte ÚNICA, gravada com status "historico" e fonte "yahoo-historico". Só insere datas ausentes;
    nunca sobrescreve um fechamento conferido em duas fontes.
    """
    from . import fontes
    from .util import config
    cad = instrumentos.carregar()
    alvos: dict[str, str] = {}
    for t in (simbolos or list(cad)):
        if t in cad:
            alvos[t] = instrumentos.simbolo_yahoo(t, cad)
    for nome, cfg in config("series.toml").items():
        if (simbolos is None or nome in simbolos) and cfg.get("yahoo"):
            alvos[nome] = cfg["yahoo"]
    out: dict[str, int | str] = {}
    for nome, sym in alvos.items():
        try:
            vals = fontes.fetch_yahoo_historico(sym, periodo)
            out[nome] = series.gravar_historico(nome, vals, "yahoo-historico")
        except Exception as e:  # noqa: BLE001 - registra e segue para o próximo
            out[nome] = f"falhou: {e}"
    return out


def proximo_pregao(d: date) -> date:
    x = d
    while not dia_util(x):
        x += timedelta(days=1)
    return x
