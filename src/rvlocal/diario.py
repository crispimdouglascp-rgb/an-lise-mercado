"""Fechamento do dia (18:05): números, regras, risco, mesa, hipóteses. Tudo por código.

Lê os livros e o mercado.db; grava SÓ vistas (data/gerado/diario, risco, recaps) e
acréscimos nos livros de pendências (alertas) e de pontos de hipótese.
"""
from __future__ import annotations

from datetime import date

from . import desempenho, hipoteses as hip, instrumentos, livros, mesa, razao, regras as regras_mod, risco, series, teses
from .notificar import ENVIAR
from .util import brl, config, gravar_json, gravar_texto, hoje, ler_json, ler_jsonl, p_gerado, pct

# Violações que não viram pendência na mesa (não há decisão que as resolva: pesam direto no boletim)
FORA_DA_MESA = {"operacao_sem_tese", "excesso_giro", "lacuna_preco"}


def p_diario(dia: str):
    return p_gerado("diario", f"{dia}.json")


def p_risco(dia: str):
    return p_gerado("risco", f"{dia}.json")


def dias_com_diario(antes_de: str | None = None) -> list[str]:
    pasta = p_gerado("diario")
    if not pasta.exists():
        return []
    return sorted(p.stem for p in pasta.glob("*.json") if antes_de is None or p.stem < antes_de)


def carregar_diarios(inicio: str | None = None, fim: str | None = None) -> list[dict]:
    return [ler_json(p_diario(d)) for d in dias_com_diario()
            if (inicio is None or d >= inicio) and (fim is None or d <= fim)]


def fechar_dia(dia: str | None = None, enviar: bool = True) -> dict:
    with livros.rotina("fechamento") as hb:
        dia = dia or hoje().isoformat()
        hb["dia_apurado"] = dia
        saida = _fechar(dia)
        hb["status"] = "ok" if not saida.get("aviso") else "parcial"
    texto = resumo_texto(saida)
    gravar_texto(p_gerado("recaps", f"{dia}_numeros.txt"), texto)
    print(texto)
    if enviar:
        ENVIAR(texto)
    return saida


def _fechar(dia: str) -> dict:
    regras = config("regras.toml")
    ops = razao.carregar_operacoes()
    problemas = razao.validar(ops)
    ops_ate = [o for o in ops if o["data"] <= dia]
    est = razao.calcular_estado(ops, ate=dia)
    fech = series.carregar()
    cad = instrumentos.carregar()
    params = instrumentos.parametros(dia, cad)
    precos = fech.get(dia, {})
    fx = series.fx(fech, dia)

    saida: dict = {"data": dia, "problemas_razao": problemas, "cambio": fx}
    patrimonio, sem_preco = razao.valor_carteira(est, precos, fx)
    saida["lacunas_preco"] = sem_preco
    completo = not sem_preco and bool(est.posicoes or est.caixa or est.caixa_moeda)

    # retorno consolidado (D3: atravessa lacunas contra o último dia válido)
    ants = [ler_json(p_diario(d)) for d in dias_com_diario(dia)]
    rc = desempenho.retorno_consolidado(patrimonio if completo else None, dia, est.fluxos, ants)
    ret = rc["retorno_pct"]
    saida.update({"patrimonio": round(patrimonio, 2) if completo else None,
                  "caixa": round(est.caixa, 2),
                  "caixa_moeda": {m: round(v, 2) for m, v in est.caixa_moeda.items() if abs(v) > 1e-9},
                  "fluxo_dia": round(est.fluxos.get(dia, 0.0), 2),
                  "retorno_dia_pct": round(ret, 4) if ret is not None else None,
                  "retorno_desde": rc["desde"], "retorno_pregoes": rc["pregoes"]})
    if not completo:
        saida["aviso"] = "dia incompleto: faltam preços; retorno e patrimônio não calculados."
    elif rc["pregoes"] and rc["pregoes"] > 1:
        saida["aviso_retorno"] = (f"retorno cobre {rc['pregoes']} pregões desde {rc['desde']} "
                                  "(dias intermediários sem preço completo)")
    acum = desempenho.encadear([a.get("retorno_dia_pct") for a in ants] + [ret])
    saida["retorno_acumulado_pct"] = round(acum, 4) if acum is not None and ret is not None else None

    rb = series.retorno_entre(fech, "IBOV", rc["desde"], dia) if rc["desde"] else series.retorno_dia(fech, "IBOV", dia)
    saida["ibov_dia_pct"] = round(rb, 4) if rb is not None else None

    # sleeves (contra o último diário válido)
    validos = [a for a in ants if a.get("patrimonio")]
    saida["sleeves"] = desempenho.sleeves_do_dia(est, precos, fx, cad, ops_ate, fech, dia,
                                                 validos[-1] if validos and completo else None)

    # posições
    fichas = teses.todas_vigentes(dia)
    saida["posicoes"] = []
    pesos = regras_mod.pesos(est, precos, fx)
    for a, pos in sorted(est.posicoes.items()):
        p = precos.get(a)
        par = params.get(a, instrumentos.info(a, cad))
        v = razao.valor_posicao(pos, p, fx) if p is not None else None
        rd = series.retorno_dia(fech, a, dia)
        f = fichas.get(a)
        saida["posicoes"].append({
            "ativo": a, "classe": par.get("classe"), "sleeve": instrumentos.sleeve(a, cad), "moeda": pos.moeda,
            "qtd": pos.qtd, "pm": round(pos.pm, 4), "preco": p, "valor_brl": round(v, 2) if v is not None else None,
            "peso_pct": round(pesos[a], 2) if a in pesos else None,
            "pl_pct": round((p / pos.pm - 1) * 100, 2) if p and pos.pm else None,
            "dia_pct": round(rd, 2) if rd is not None else None,
            "alvo": par.get("alvo"), "stop": par.get("stop"),
            "dist_alvo_pct": round((par["alvo"] / p - 1) * 100, 2) if p and par.get("alvo") else None,
            "dist_stop_pct": round((par["stop"] / p - 1) * 100, 2) if p and par.get("stop") else None,
            "tese_id": f.get("tese_id") if f else None, "rating": f.get("rating") if f else None,
            "conviccao": f.get("conviccao") if f else None,
            "revisao_vencida": teses.revisao_vencida(f, dia) if f else None,
        })
    saida["pesos_pct"] = {a: round(w, 2) for a, w in pesos.items()}

    # regras
    viol = regras_mod.checar(est, precos, params, regras, ops, razao.carregar_decisoes(),
                             date.fromisoformat(dia), fx)
    saida["violacoes"] = [v.dict() | {"chave": v.chave} for v in viol]
    saida["aderencia"] = {
        "violacoes_alta": sum(1 for v in viol if v.severidade == "alta"),
        "violacoes_media": sum(1 for v in viol if v.severidade == "media"),
    }

    # risco (só com patrimônio completo: risco sobre carteira com lacuna seria estimativa)
    if completo:
        rk = risco.calcular(est, precos, fx, fech, dia, ants + [saida], cad)
        gravar_json(p_risco(dia), rk)
        saida["risco"] = {k: rk.get(k) for k in ("hhi", "n_efetivo", "exposicao_usd_economica_pct", "beta_ibov",
                                                 "volatilidade", "var95_1d", "drawdown_carteira")}
        saida["risco"]["bandas"] = rk["bandas"]
        saida["risco"]["pior_stress"] = min(rk["stress"], key=lambda s: s["pnl_pct"] or 0) if rk["stress"] else None
        mesa.sincronizar(dia, [{"chave": b["chave"], "regra": b["regra"], "severidade": b["severidade"],
                                "ativo": b["ativo"], "motivo": b["detalhe"],
                                "evidencia": {"valor": b["valor"], "limite": b["limite"], "ref": b["ref"]}}
                               for b in rk["bandas"]], origem="risco")
    mesa.sincronizar(dia, mesa.de_violacoes(viol, FORA_DA_MESA), origem="regras", encerrar_ausentes=completo)

    # hipóteses: um ponto por hipótese por dia, só por acréscimo (D4, D5, D6)
    novos = hip.medir_dia_livro(fech, dia)
    saida["hipoteses"] = [{"id": p["hipotese_id"], "veredito": p["veredito"], "valor_pp": p["valor_pp"],
                           "detalhe": p["detalhe"]} for p in novos]
    saida["placar_hipoteses"] = hip.placar_v2(ate=dia)

    # vigilância e mesa
    saida["alertas_do_dia"] = ler_jsonl(p_gerado("estado", f"alertas_{dia}.jsonl"))
    est_mesa = mesa.estado(dia)
    saida["mesa"] = {"abertas": sum(1 for a in est_mesa if a["status"] == "aberto"),
                     "vencidas": sum(1 for a in est_mesa if a["status"] == "vencido")}
    gravar_json(p_diario(dia), saida)
    return saida


def resumo_texto(s: dict) -> str:
    L = [f"RV Local, fechamento {s['data']}"]
    if s.get("aviso"):
        L.append("⚠ " + s["aviso"] + (f" Sem preço: {', '.join(s['lacunas_preco'])}." if s["lacunas_preco"] else ""))
    if s.get("aviso_retorno"):
        L.append("ℹ " + s["aviso_retorno"])
    if s.get("patrimonio") is not None:
        L.append(f"Patrimônio: {brl(s['patrimonio'])} | caixa {brl(s['caixa'])}")
    if s.get("retorno_dia_pct") is not None:
        L.append(f"Dia: {pct(s['retorno_dia_pct'], sinal=True)}"
                 + (f" (Ibovespa {pct(s['ibov_dia_pct'], sinal=True)})" if s.get("ibov_dia_pct") is not None else ""))
    if s.get("retorno_acumulado_pct") is not None:
        L.append(f"Acumulado (ponderado pelo tempo): {pct(s['retorno_acumulado_pct'], sinal=True)}")
    ad = s["aderencia"]
    L.append(f"Regras: {ad['violacoes_alta']} violações altas, {ad['violacoes_media']} médias")
    for v in s["violacoes"]:
        if v["severidade"] != "info":
            L.append(f"  - [{v['severidade']}] {v['detalhe']}")
    for b in (s.get("risco") or {}).get("bandas", []):
        L.append(f"  - [risco/{b['severidade']}] {b['detalhe']}")
    for h in s["hipoteses"]:
        L.append(f"Hipótese {h['id']}: {h['veredito']} ({h['detalhe']})")
    m = s.get("mesa") or {}
    if m.get("abertas") or m.get("vencidas"):
        L.append(f"Na sua mesa: {m.get('abertas', 0)} abertas, {m.get('vencidas', 0)} vencidas")
    if s["problemas_razao"]:
        L.append("⚠ Razão com problemas: " + "; ".join(s["problemas_razao"][:3]))
    return "\n".join(L)
