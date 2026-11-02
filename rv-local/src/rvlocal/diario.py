"""Fechamento do dia (18:05): números, regras, hipóteses e placar. Tudo por código.

Retorno do dia ponderado pelo tempo, com fluxos (aportes/resgates) tratados como
ocorridos no início do dia:  R = V_fim / (V_ini + fluxo) - 1.
Retorno acumulado = encadeamento dos retornos diários (não é afetado por aportes).
"""
from __future__ import annotations

from . import hipoteses as hip
from . import razao, regras as regras_mod, series
from .notificar import ENVIAR
from .util import brl, config, gravar_json, hoje, ler_json, pct, raiz


def p_diario(dia: str):
    return raiz() / "data" / "diario" / f"{dia}.json"


def _dias_anteriores(dia: str) -> list[str]:
    pasta = raiz() / "data" / "diario"
    if not pasta.exists():
        return []
    return sorted(p.stem for p in pasta.glob("*.json") if p.stem < dia)


def fechar_dia(dia: str | None = None, enviar: bool = True) -> dict:
    dia = dia or hoje().isoformat()
    regras = config("regras.toml")
    ops = razao.carregar_operacoes()
    problemas = razao.validar(ops)
    est = razao.calcular_estado(ops, ate=dia)
    fech = series.carregar()
    ativos = razao.carregar_ativos()
    precos = fech.get(dia, {})

    saida: dict = {"data": dia, "problemas_razao": problemas}
    patrimonio, sem_preco = razao.valor_carteira(est, precos)
    saida["lacunas_preco"] = sem_preco
    completo = not sem_preco and bool(est.posicoes or est.caixa)

    # retorno do dia
    ants = _dias_anteriores(dia)
    ant = ler_json(p_diario(ants[-1])) if ants else None
    fluxo = est.fluxos.get(dia, 0.0)
    ret = None
    if completo and ant and ant.get("patrimonio") and (ant["patrimonio"] + fluxo) > 0:
        ret = (patrimonio / (ant["patrimonio"] + fluxo) - 1) * 100
    saida.update({"patrimonio": round(patrimonio, 2) if completo else None,
                  "caixa": round(est.caixa, 2), "fluxo_dia": round(fluxo, 2),
                  "retorno_dia_pct": round(ret, 4) if ret is not None else None})
    if not completo:
        saida["aviso"] = "dia incompleto: faltam preços; retorno e patrimônio não calculados."

    # acumulado encadeado
    base = 1.0
    for d in ants:
        r = (ler_json(p_diario(d)) or {}).get("retorno_dia_pct")
        if r is not None:
            base *= 1 + r / 100
    acum = (base * (1 + ret / 100) - 1) * 100 if ret is not None else None
    saida["retorno_acumulado_pct"] = round(acum, 4) if acum is not None else None

    # benchmark
    rb = series.retorno_dia(fech, "IBOV", dia)
    saida["ibov_dia_pct"] = round(rb, 4) if rb is not None else None

    # posições
    saida["posicoes"] = []
    for a, pos in sorted(est.posicoes.items()):
        p = precos.get(a)
        saida["posicoes"].append({
            "ativo": a, "qtd": pos.qtd, "pm": round(pos.pm, 4), "preco": p,
            "valor": round(pos.qtd * p, 2) if p else None,
            "pl_pct": round((p / pos.pm - 1) * 100, 2) if p and pos.pm else None,
            "dia_pct": round(series.retorno_dia(fech, a, dia), 2) if series.retorno_dia(fech, a, dia) is not None else None,
        })
    saida["pesos_pct"] = {a: round(w, 2) for a, w in regras_mod.pesos(est, precos).items()}

    # regras
    viol = regras_mod.checar(est, precos, ativos, regras, ops, razao.carregar_decisoes(),
                             __import__("datetime").date.fromisoformat(dia))
    saida["violacoes"] = [v.dict() for v in viol]
    saida["aderencia"] = {
        "violacoes_alta": sum(1 for v in viol if v.severidade == "alta"),
        "violacoes_media": sum(1 for v in viol if v.severidade == "media"),
    }

    # hipóteses
    hs = razao.carregar_hipoteses()
    hs = hip.medir_dia(hs, fech, dia)
    gravar_json(razao.p_hipoteses(), hs)
    saida["hipoteses"] = [
        {"id": h["id"], "titulo": h.get("titulo"), "hoje": next((m for m in h.get("medicoes", []) if m["data"] == dia), None)}
        for h in hs if h.get("status", "ativa") == "ativa"
    ]
    saida["placar_hipoteses"] = hip.placar(hs)

    # alertas do dia
    from .util import ler_jsonl
    saida["alertas_do_dia"] = ler_jsonl(raiz() / "data" / "state" / f"alertas_{dia}.jsonl")

    gravar_json(p_diario(dia), saida)
    texto = resumo_texto(saida)
    (raiz() / "data" / "recaps").mkdir(parents=True, exist_ok=True)
    (raiz() / "data" / "recaps" / f"{dia}_numeros.txt").write_text(texto, encoding="utf-8")
    print(texto)
    if enviar:
        ENVIAR(texto)
    return saida


def resumo_texto(s: dict) -> str:
    L = [f"RV Local, fechamento {s['data']}"]
    if s.get("aviso"):
        L.append("⚠ " + s["aviso"] + (f" Sem preço: {', '.join(s['lacunas_preco'])}." if s["lacunas_preco"] else ""))
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
    for h in s["hipoteses"]:
        m = h["hoje"]
        L.append(f"Hipótese {h['id']}: {m['resultado']} ({m['detalhe']})" if m else f"Hipótese {h['id']}: sem medição")
    if s["problemas_razao"]:
        L.append("⚠ Razão com problemas: " + "; ".join(s["problemas_razao"][:3]))
    return "\n".join(L)
