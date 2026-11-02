"""Monitor de risco: código, não modelo. Lê posições e séries, grava gerado/risco/<dia>.json.

Nível 1 (patrimônio): alocação por grupo de classe × alvo com banda; exposição cambial
econômica (inclui receita em dólar das empresas brasileiras).
Nível 2 (renda variável): pesos por setor/país/moeda/fator, HHI, volatilidade, beta,
correlação, drawdown, VaR/CVaR histórico, contribuição ao risco e stress pré-registrado.

Regra de honestidade: métrica sem dados mínimos sai como {"status": "insuficiente", "obs": n,
"minimo": m}. Nunca é estimada. Toda banda rompida vira alerta. Informação, nunca ordem.
"""
from __future__ import annotations

import math
import statistics

from . import instrumentos, series
from .razao import Estado, valor_carteira, valor_posicao
from .regras import Violacao
from .util import config


def _insuf(n: int, m: int) -> dict:
    return {"status": "insuficiente", "obs": n, "minimo": m}


def _cfg() -> dict:
    return config("risco.toml", {})


def retornos_brl(fech: dict, ativo: str, moeda: str, ate: str) -> dict[str, float]:
    """Retornos diários em BRL (ativo em USD: combina preço e câmbio). Frações."""
    r = series.retornos(fech, ativo, ate)
    if moeda == "BRL":
        return r
    rfx = series.retornos(fech, "USDBRL", ate)
    return {d: (1 + v) * (1 + rfx[d]) - 1 for d, v in r.items() if d in rfx}


def _percentil(xs: list[float], q: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def _beta(y: list[float], x: list[float]) -> float | None:
    if len(x) < 2:
        return None
    vx = statistics.pvariance(x)
    if vx == 0:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x) / vx


def _drawdown(niveis: list[float]) -> tuple[float, float]:
    """(drawdown atual %, drawdown máximo %), ambos <= 0."""
    pico, maxdd, atual = -math.inf, 0.0, 0.0
    for v in niveis:
        pico = max(pico, v)
        atual = (v / pico - 1) * 100 if pico > 0 else 0.0
        maxdd = min(maxdd, atual)
    return round(atual, 2), round(maxdd, 2)


def calcular(est: Estado, precos: dict, fx: dict, fech: dict, dia: str, diarios: list[dict],
             cad: dict | None = None) -> dict:
    cad = instrumentos.carregar() if cad is None else cad
    cfg = _cfg()
    lim = cfg.get("limites", {})
    pat, lacunas = valor_carteira(est, precos, fx)
    out: dict = {"data": dia, "patrimonio": round(pat, 2), "lacunas": lacunas, "bandas": []}
    if pat <= 0:
        return out

    # ---------------- pesos e exposições
    valores: dict[str, float] = {}
    for a, pos in est.posicoes.items():
        p = precos.get(a)
        v = valor_posicao(pos, p, fx) if p is not None else None
        if v is not None:
            valores[a] = v
    pesos = {a: v / pat * 100 for a, v in valores.items()}
    caixa_total = est.caixa + sum(v * fx.get(m, 0.0) for m, v in est.caixa_moeda.items())
    expo: dict[str, dict[str, float]] = {"classe": {}, "setor": {}, "pais": {}, "moeda": {}, "fator": {}}
    usd_economico = sum(v * fx.get(m, 0.0) for m, v in est.caixa_moeda.items() if m == "USD") / pat * 100
    for a, w in pesos.items():
        i = instrumentos.info(a, cad)
        for dim in ("classe", "setor", "pais", "moeda"):
            expo[dim][i[dim]] = expo[dim].get(i[dim], 0.0) + w
        for f in i.get("fatores") or []:
            expo["fator"][f] = expo["fator"].get(f, 0.0) + w
        usd_economico += w * (1.0 if i["moeda"] == "USD" else i.get("receita_usd_pct", 0) / 100)
    expo["classe"]["caixa"] = caixa_total / pat * 100
    out["pesos_pct"] = {a: round(w, 2) for a, w in sorted(pesos.items(), key=lambda x: -x[1])}
    out["exposicao_pct"] = {k: {kk: round(vv, 2) for kk, vv in sorted(v.items(), key=lambda x: -x[1])}
                            for k, v in expo.items()}
    out["exposicao_usd_economica_pct"] = round(usd_economico, 2)
    rv = sum(pesos.values())
    hhi = sum((w / rv) ** 2 for w in pesos.values()) if rv else 0.0
    out["hhi"] = round(hhi, 4)
    out["n_efetivo"] = round(1 / hhi, 1) if hhi else None

    # ---------------- nível 1
    n1 = cfg.get("nivel1", {})
    grupos = cfg.get("grupos", {})
    aloc: dict[str, float] = {}
    for c, w in expo["classe"].items():
        g = grupos.get(c, c)
        aloc[g] = aloc.get(g, 0.0) + w
    out["nivel1"] = {"alocacao_pct": {g: round(w, 2) for g, w in sorted(aloc.items(), key=lambda x: -x[1])},
                     "alvos": n1.get("alvos", {}) if n1.get("ativo") else {}}
    if n1.get("ativo"):
        for g, ab in n1.get("alvos", {}).items():
            w = aloc.get(g, 0.0)
            if abs(w - ab["alvo"]) > ab["banda"]:
                out["bandas"].append(Violacao("banda_nivel1", "media", None,
                                              f"{g} em {w:.1f}% (alvo {ab['alvo']}% ± {ab['banda']}).",
                                              ref=g, valor=round(w, 2), limite=ab["alvo"]))

    # ---------------- séries de retorno com os pesos de hoje (simulação histórica)
    rets = {a: retornos_brl(fech, a, est.posicoes[a].moeda, dia) for a in valores}
    datas = sorted(set.intersection(*[set(r) for r in rets.values()])) if rets else []
    pnl = [sum(valores[a] * rets[a][d] for a in valores) for d in datas]       # BRL
    rport = [x / pat for x in pnl]                                            # fração do patrimônio
    n = len(rport)
    out["observacoes_comuns"] = n

    def vol_anual(xs):
        return round(statistics.pstdev(xs) * math.sqrt(252) * 100, 2)

    if n >= 20:
        janela = rport[-60:]
        ew, peso, lam = 0.0, 1.0, 0.94
        for x in reversed(rport[-250:]):
            ew += peso * x * x
            peso *= lam
        ew *= (1 - lam)
        out["volatilidade"] = {"anual_60d_pct": vol_anual(janela),
                               "anual_ewma_pct": round(math.sqrt(ew * 252) * 100, 2),
                               "base": "pesos atuais × retornos históricos"}
    else:
        out["volatilidade"] = _insuf(n, 20)

    ibov = series.retornos(fech, "IBOV", dia)
    comuns = [d for d in datas if d in ibov][-252:]
    if len(comuns) >= 60:
        y = [rport[datas.index(d)] for d in comuns]
        out["beta_ibov"] = round(_beta(y, [ibov[d] for d in comuns]) or 0.0, 3)
    else:
        out["beta_ibov"] = _insuf(len(comuns), 60)

    if n >= 250:
        ult = pnl[-250:]
        q = _percentil(ult, 0.05)
        cauda = [x for x in ult if x <= q]
        out["var95_1d"] = {"brl": round(-q, 2), "pct": round(-q / pat * 100, 3),
                           "cvar_brl": round(-statistics.fmean(cauda), 2),
                           "cvar_pct": round(-statistics.fmean(cauda) / pat * 100, 3),
                           "metodo": "simulação histórica, 250 pregões, pesos atuais"}
        if lim.get("var95_max_pct") and out["var95_1d"]["pct"] > lim["var95_max_pct"]:
            out["bandas"].append(Violacao("banda_var", "media", None,
                                          f"VaR 95% 1d em {out['var95_1d']['pct']:.2f}% "
                                          f"(limite {lim['var95_max_pct']}%).",
                                          valor=out["var95_1d"]["pct"], limite=lim["var95_max_pct"]))
    else:
        out["var95_1d"] = _insuf(n, 250)

    # contribuição ao risco e correlação
    if n >= 60:
        ativos = list(valores)
        jan = {a: [rets[a][d] for d in datas[-120:]] for a in ativos}
        w = {a: valores[a] / pat for a in ativos}
        med = {a: statistics.fmean(jan[a]) for a in ativos}
        cov = {(a, b): statistics.fmean([(x - med[a]) * (y - med[b]) for x, y in zip(jan[a], jan[b])])
               for a in ativos for b in ativos}
        var_p = sum(w[a] * w[b] * cov[(a, b)] for a in ativos for b in ativos)
        if var_p > 0:
            sp = math.sqrt(var_p)
            out["contribuicao_risco_pct"] = {
                a: round(w[a] * sum(w[b] * cov[(a, b)] for b in ativos) / var_p * 100, 1) for a in ativos}
            pares = []
            for i, a in enumerate(ativos):
                for b in ativos[i + 1:]:
                    den = math.sqrt(cov[(a, a)] * cov[(b, b)])
                    if den > 0:
                        pares.append((a, b, round(cov[(a, b)] / den, 2)))
            out["correlacoes_mais_altas"] = sorted(pares, key=lambda x: -x[2])[:5]
            out["vol_carteira_120d_pct"] = round(sp * math.sqrt(252) * 100, 2)
    else:
        out["contribuicao_risco_pct"] = _insuf(n, 60)

    # ---------------- drawdown
    curva = [100.0]
    for d in diarios:
        if d.get("retorno_dia_pct") is not None:
            curva.append(curva[-1] * (1 + d["retorno_dia_pct"] / 100))
    dd_at, dd_max = _drawdown(curva)
    out["drawdown_carteira"] = {"atual_pct": dd_at, "maximo_pct": dd_max, "pregoes": len(curva) - 1}
    if lim.get("drawdown_max_pct") and -dd_at > lim["drawdown_max_pct"]:
        out["bandas"].append(Violacao("banda_drawdown", "alta", None,
                                      f"Drawdown da carteira em {dd_at:.1f}% (limite −{lim['drawdown_max_pct']}%).",
                                      valor=-dd_at, limite=lim["drawdown_max_pct"]))
    out["drawdown_ativos"] = {}
    for a in valores:
        s = [v for _, v in series.serie(fech, a, dia)][-252:]
        if s:
            at, mx = _drawdown(s)
            out["drawdown_ativos"][a] = {"atual_pct": at, "maximo_252d_pct": mx}

    # ---------------- bandas de exposição
    tf = lim.get("teto_fator_pct")
    for f, w in expo["fator"].items():
        if tf and w > tf:
            out["bandas"].append(Violacao("banda_fator", "alta", None,
                                          f"Fator {f} soma {w:.1f}% (teto {tf}%).", ref=f,
                                          valor=round(w, 2), limite=tf))
    if lim.get("exposicao_usd_max_pct") and usd_economico > lim["exposicao_usd_max_pct"]:
        out["bandas"].append(Violacao("banda_usd", "media", None,
                                      f"Exposição econômica ao dólar {usd_economico:.1f}% "
                                      f"(máx. {lim['exposicao_usd_max_pct']}%).",
                                      valor=round(usd_economico, 2), limite=lim["exposicao_usd_max_pct"]))
    if lim.get("hhi_max") and hhi > lim["hhi_max"]:
        out["bandas"].append(Violacao("banda_hhi", "media", None,
                                      f"Concentração HHI {hhi:.3f} (máx. {lim['hhi_max']}).",
                                      valor=round(hhi, 4), limite=lim["hhi_max"]))

    # ---------------- stress pré-registrado
    out["stress"] = stress(est, precos, fx, cad, pat)
    pior = min((s["pnl_pct"] for s in out["stress"]), default=0.0)
    if lim.get("stress_perda_max_pct") and -pior > lim["stress_perda_max_pct"]:
        out["bandas"].append(Violacao("banda_stress", "media", None,
                                      f"Pior cenário de stress perde {pior:.1f}% "
                                      f"(limite −{lim['stress_perda_max_pct']}%).",
                                      valor=-pior, limite=lim["stress_perda_max_pct"]))
    out["liquidez"] = {"status": "sem_dado", "motivo": "volume negociado ainda não é coletado (Ciclo 3)"}
    out["bandas"] = [v.dict() | {"chave": v.chave} for v in out["bandas"]]
    return out


def _choque(choques: dict, ativo: str, info: dict) -> float:
    for chave in (("ativo", ativo), ("setor", info["setor"])):
        v = choques.get(chave[0], {}).get(chave[1])
        if v is not None:
            return v
    fs = [choques.get("fator", {}).get(f) for f in info.get("fatores") or []]
    fs = [f for f in fs if f is not None]
    if fs:
        return min(fs)
    for chave in (("classe", info["classe"]), ("pais", info["pais"])):
        v = choques.get(chave[0], {}).get(chave[1])
        if v is not None:
            return v
    return choques.get("padrao", 0.0)


def stress(est: Estado, precos: dict, fx: dict, cad: dict, pat: float) -> list[dict]:
    """Aplica cenários de config/stress.toml (choques em %, do mais específico ao mais geral:
    ativo > setor > fator > classe > país > padrão; mais o choque de moeda)."""
    out = []
    for c in config("stress.toml", {}).get("cenario", []):
        ch = c.get("choques", {})
        pnl, detalhe = 0.0, {}
        for a, pos in est.posicoes.items():
            p = precos.get(a)
            v = valor_posicao(pos, p, fx) if p is not None else None
            if v is None:
                continue
            i = instrumentos.info(a, cad)
            s = _choque(ch, a, i) / 100
            m = ch.get("moeda", {}).get(pos.moeda, 0.0) / 100 if pos.moeda != "BRL" else 0.0
            d = v * ((1 + s) * (1 + m) - 1)
            pnl += d
            detalhe[a] = round(d, 2)
        for moeda, v in est.caixa_moeda.items():
            m = ch.get("moeda", {}).get(moeda, 0.0) / 100
            pnl += v * fx.get(moeda, 0.0) * m
        out.append({"id": c.get("id"), "nome": c.get("nome"), "registrado_em": c.get("registrado_em"),
                    "pnl_brl": round(pnl, 2), "pnl_pct": round(pnl / pat * 100, 2) if pat else None,
                    "por_ativo": dict(sorted(detalhe.items(), key=lambda x: x[1]))})
    return out
