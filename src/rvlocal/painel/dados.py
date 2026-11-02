"""Monta o contexto de cada tela a partir dos livros e de data/gerado. Nenhum número é calculado aqui
que não venha de um módulo de código (desempenho, risco, boletim, fiscal...)."""
from __future__ import annotations

from datetime import date

from .. import (boletim, cobranca, decisoes, desempenho, diario, fiscal, hipoteses, instrumentos, livros, mesa,
                razao, series, teses)
from ..util import config, hoje, ler_json, p_gerado, raiz_base
from . import graficos as G


def eh_demo() -> bool:
    return (raiz_base() / "DADOS-DEMO.md").exists() or any(
        r.get("natureza") == "demo" for r in livros.ler("operacoes")[:5])


def ultimo_diario() -> dict | None:
    ds = diario.dias_com_diario()
    return ler_json(diario.p_diario(ds[-1])) if ds else None


def comum() -> dict:
    d = ultimo_diario()
    return {"demo": eh_demo(), "data_ref": d["data"] if d else None, "hoje": hoje().isoformat()}


def _curvas(ds: list[dict]) -> str:
    if not ds:
        return G.linhas([])
    base = ds[0]["data"]
    fech = series.carregar()
    ibov = [(d["data"], fech[d["data"]]["IBOV"] / fech[base]["IBOV"] * 100)
            for d in ds if "IBOV" in fech.get(d["data"], {}) and "IBOV" in fech.get(base, {})]
    s = [{"nome": "Consolidada (TWR)", "pontos": desempenho.curva(ds), "cor": "var(--s1)", "grossa": True},
         {"nome": "RV Brasil", "pontos": desempenho.curva(ds, sleeve="BR"), "cor": "var(--s2)"},
         {"nome": "RV Exterior em R$", "pontos": desempenho.curva(ds, sleeve="EXT"), "cor": "var(--s3)"},
         {"nome": "Ibovespa", "pontos": ibov, "cor": "var(--tinta-3)"}]
    return G.linhas([x for x in s if len([p for p in x["pontos"] if p[1] is not None]) > 1])


def _acum(ds: list[dict], sleeve: str | None = None, sub: str = "retorno_pct") -> float | None:
    c = desempenho.curva(ds, sleeve=sleeve, sub=sub)
    return c[-1][1] - 100 if c else None


def dashboard() -> dict:
    d = ultimo_diario()
    ds = diario.carregar_diarios()
    ctx = comum()
    if not d:
        return {**ctx, "vazio": True}
    ref = d["data"]
    mes_ini = ref[:8] + "01"
    ds_mes = [x for x in ds if x["data"] >= mes_ini]
    sem = boletim.historico("semanal")
    hb = [h for h in livros.ler("heartbeat") if h.get("data") == ref]
    status = []
    for r in config("rotina.toml", {}).get("rotina", []):
        rodou = [h for h in hb if h["rotina"] == r["nome"]]
        status.append({"nome": r["nome"], "horario": r["horario"], "motor": r["motor"],
                       "rodou": rodou[-1]["fim"][11:16] if rodou else None,
                       "status": rodou[-1]["status"] if rodou else None})
    m = mesa.estado(ref)
    pend = [a for a in m if a["status"] in {"aberto", "vencido"}]
    rk = ler_json(diario.p_risco(ref)) or {}
    expo = rk.get("exposicao_pct", {})
    decs = sorted(decisoes.carregar(), key=lambda x: x.get("data", ""))[-6:][::-1]
    placar = hipoteses.placar_v2(ate=ref)
    destaque = _destaque(d, pend, placar)
    return {**ctx, "d": d, "curvas": _curvas(ds_mes if len(ds_mes) > 2 else ds[-30:]),
            "mes": {"consolidada": _acum(ds_mes), "br": _acum(ds_mes, "BR"), "ext": _acum(ds_mes, "EXT"),
                    "ext_local": _acum(ds_mes, "EXT", "retorno_local_pct"),
                    "ibov": _acum_bench(ds_mes, "BR"), "spx": _acum_bench(ds_mes, "EXT", "benchmark_local_pct")},
            "boletim": sem[-1] if sem else None, "historico_notas": [(b["fim"], b["letra"], b["nota_final"]) for b in sem[-8:]],
            "status": status, "pendencias": pend[:8], "n_vencidas": sum(1 for a in pend if a["status"] == "vencido"),
            "alertas": d.get("alertas_do_dia", []), "placar": placar, "decisoes": decs,
            "classe": G.barra_100(list(expo.get("classe", {}).items())),
            "setor": G.barras(list(expo.get("setor", {}).items())[:8], limite=config("regras.toml")["carteira"]["teto_setor_pct"]),
            "destaque": destaque}


def _acum_bench(ds, sleeve, sub="benchmark_pct"):
    return _acum(ds, sleeve, sub)


def _destaque(d: dict, pend: list[dict], placar: list[dict]) -> str:
    """A frase do topo: gerada por regra (NLG por script), com o item mais urgente."""
    venc = [a for a in pend if a["status"] == "vencido"]
    if venc:
        a = venc[0]
        prazo = f"{a['prazo'][8:10]}/{a['prazo'][5:7]}"
        return f"Pendência vencida desde {prazo}: {a['motivo']} {a['acao_requerida']}"
    perto = [p for p in d.get("posicoes", []) if p.get("dist_alvo_pct") is not None and 0 < p["dist_alvo_pct"] <= 3]
    if perto:
        p = perto[0]
        return f"Um alvo que você definiu está a menos de 3%: {p['ativo']} a {p['preco']}, a {p['dist_alvo_pct']:.1f}% do alvo de {p['alvo']}."
    if pend:
        return f"{len(pend)} pendência(s) aguardando decisão dentro do prazo."
    conf = [p for p in placar if p["veredito"] == "confirmada"]
    return ("Nada pede decisão hoje." + (f" {len(conf)} hipótese(s) confirmada(s) pelo placar." if conf else ""))


def carteira() -> dict:
    ds = diario.carregar_diarios()
    ctx = comum()
    d = ds[-1] if ds else None
    rk = ler_json(diario.p_risco(d["data"])) if d else None
    return {**ctx, "d": d, "curvas": _curvas(ds), "rk": rk or {},
            "acum": {"consolidada": _acum(ds), "br": _acum(ds, "BR"), "ext": _acum(ds, "EXT"),
                     "ext_local": _acum(ds, "EXT", "retorno_local_pct"), "ibov": _acum(ds, "BR", "benchmark_pct"),
                     "spx_brl": _acum(ds, "EXT", "benchmark_pct"), "spx": _acum(ds, "EXT", "benchmark_local_pct")},
            "por": {k: G.barra_100(list((rk or {}).get("exposicao_pct", {}).get(k, {}).items()))
                    for k in ("classe", "pais", "moeda")},
            "nivel1": (rk or {}).get("nivel1", {}), "primeiro": ds[0]["data"] if ds else None}


def posicoes() -> dict:
    d = ultimo_diario()
    ctx = comum()
    cad = instrumentos.carregar()
    fichas = teses.todas_vigentes(d["data"] if d else None)
    linhas = []
    for p in (d or {}).get("posicoes", []):
        f = fichas.get(p["ativo"])
        linhas.append({**p, "nome": cad.get(p["ativo"], {}).get("nome", ""),
                       "margem": teses.margem_seguranca_pct(f, p["preco"]) if f else None,
                       "upside": teses.upside_pct(f, p["preco"]) if f else None})
    return {**ctx, "d": d, "linhas": linhas, "teto": config("regras.toml")["carteira"]["teto_posicao_pct"]}


def encerradas() -> dict:
    ctx = comum()
    ops = razao.carregar_operacoes()
    est = razao.calcular_estado(ops)
    decs = decisoes.por_id()
    ops_id = {o.get("id"): o for o in ops}
    linhas = []
    for v in est.vendas[::-1]:
        o = ops_id.get(v.get("op_id"), {})
        chk = decisoes.checklist_da_operacao(o, decs) if o else {}
        frac, _ = decisoes.completude(chk) if chk else (0.0, [])
        linhas.append({**v, "pct": (v["preco"] / v["pm"] - 1) * 100 if v["pm"] else None,
                       "decisao": decs.get(v.get("decisao_id") or ""), "completude": frac})
    realizado = sum(v["lucro"] for v in est.vendas if v["moeda"] == "BRL")
    return {**ctx, "linhas": linhas, "encerradas": est.encerradas[::-1], "realizado_brl": realizado,
            "realizado_usd": sum(v["lucro"] for v in est.vendas if v["moeda"] == "USD")}


def fichas() -> dict:
    ctx = comum()
    d = ultimo_diario()
    precos = {p["ativo"]: p for p in (d or {}).get("posicoes", [])}
    cards = []
    for a, f in sorted(teses.todas_vigentes().items()):
        p = precos.get(a, {})
        cards.append({"f": f, "p": p, "hist": teses.historico(a)[::-1],
                      "margem": teses.margem_seguranca_pct(f, p.get("preco")),
                      "upside": teses.upside_pct(f, p.get("preco")), "ve": teses.valor_esperado(f),
                      "vencida": teses.revisao_vencida(f, ctx["data_ref"] or hoje().isoformat())})
    sem = [p["ativo"] for p in (d or {}).get("posicoes", []) if p["ativo"] not in {c["f"]["ativo"] for c in cards}]
    return {**ctx, "cards": cards, "sem_ficha": sem}


def hipoteses_tela() -> dict:
    ctx = comum()
    hs = {h["id"]: h for h in hipoteses.carregar()}
    pl = hipoteses.placar_v2()
    pontos = livros.ler("placar_hipoteses")
    for p in pl:
        p["h"] = hs.get(p["id"], {})
        p["recentes"] = [x for x in pontos if x["hipotese_id"] == p["id"]][-12:]
    return {**ctx, "placar": pl, "limiar": config("placar.toml")["hipoteses"]}


def monitoramento() -> dict:
    ctx = comum()
    ref = ctx["data_ref"] or hoje().isoformat()
    d = ultimo_diario() or {}
    hb = livros.ler("heartbeat")[-25:][::-1]
    try:
        cob = cobranca.itens(date.fromisoformat(ref))
    except Exception as e:  # noqa: BLE001 - a tela mostra o erro em vez de cair
        cob = [{"urgencia": "alta", "texto": f"cobrança falhou: {e}"}]
    est = mesa.estado(ref)
    return {**ctx, "mesa": [a for a in est if a["status"] in {"aberto", "vencido"}],
            "fechadas": [a for a in est if a["status"] not in {"aberto", "vencido"}][-15:][::-1],
            "alertas": d.get("alertas_do_dia", []), "heartbeat": hb, "cobranca": cob,
            "tipos": sorted(decisoes.TIPOS)}


def risco_tela() -> dict:
    ctx = comum()
    d = ultimo_diario()
    rk = ler_json(diario.p_risco(d["data"])) if d else None
    lim = config("risco.toml", {}).get("limites", {})
    r = rk or {}
    return {**ctx, "rk": r, "lim": lim,
            "fator": G.barras(list(r.get("exposicao_pct", {}).get("fator", {}).items()), limite=lim.get("teto_fator_pct")),
            "pesos": G.barras(list(r.get("pesos_pct", {}).items()),
                              limite=config("regras.toml")["carteira"]["teto_posicao_pct"]),
            "contrib": G.barras(list(r["contribuicao_risco_pct"].items()))
            if isinstance(r.get("contribuicao_risco_pct"), dict) and "status" not in r["contribuicao_risco_pct"] else None}


def auditoria() -> dict:
    ctx = comum()
    decs = decisoes.por_id()
    linhas = []
    for o in razao.carregar_operacoes()[::-1]:
        if o["tipo"] not in {"compra", "venda"}:
            continue
        chk = decisoes.checklist_da_operacao(o, decs)
        frac, faltam = decisoes.completude(chk)
        linhas.append({"o": o, "chk": chk, "frac": frac, "faltam": faltam, "itens": decisoes.CHECKLIST,
                       "dec": decs.get(o.get("decisao_id") or "")})
    return {**ctx, "linhas": linhas, "media": sum(l["frac"] for l in linhas) / len(linhas) if linhas else None,
            "rr_min": config("placar.toml")["decisoes"]["rr_minimo"]}


def relatorios(boletim_id: str | None = None) -> dict:
    ctx = comum()
    tipos = {t: boletim.historico(t) for t in boletim.TIPOS}
    todas = {b["id"]: b for b in boletim.edicoes()}
    sel = todas.get(boletim_id) if boletim_id else (tipos["semanal"][-1] if tipos["semanal"] else None)
    ops = razao.carregar_operacoes()
    ref = ctx["data_ref"] or hoje().isoformat()
    recaps = sorted(p.name for p in p_gerado("recaps").glob("*.txt"))[-10:][::-1] if p_gerado("recaps").exists() else []
    ds = diario.carregar_diarios(sel["inicio"], sel["fim"]) if sel else []
    semana = {"carteira": _acum(ds), "br": _acum(ds, "BR"), "ibov": _acum(ds, "BR", "benchmark_pct"),
              "ext": _acum(ds, "EXT", "retorno_local_pct"), "spx": _acum(ds, "EXT", "benchmark_local_pct")}
    return {**ctx, "tipos": tipos, "sel": sel, "semana": semana,
            "evolucao": G.notas(tipos["semanal"][-26:]),
            "fiscal": fiscal.apurar(ops, ref[:7])[::-1][:6],
            "recaps": [(n, (p_gerado("recaps") / n).read_text(encoding="utf-8")) for n in recaps[:3]]}


# ====================================================================== telas globais

def carteiras_tela() -> dict:
    """Todas as carteiras lado a lado: mesmo critério, mesmos preços, mesmo boletim."""
    import math
    from .. import carteiras as _c
    from ..util import usar_carteira
    linhas, curvas = [], []
    for c in _c.listar():
        with usar_carteira(c["id"]):
            ds = diario.carregar_diarios()
            sem = boletim.historico("semanal")
            ult = ds[-1] if ds else {}
            rk = (ler_json(diario.p_risco(ult["data"])) or {}) if ult else {}
            m = mesa.estado(ult.get("data")) if ult else []
            mes_ini = ult["data"][:8] + "01" if ult else None
            ds_mes = [x for x in ds if mes_ini and x["data"] >= mes_ini]
        bench = []
        fech = series.carregar()
        b = c.get("benchmark", "IBOV")
        if ds and b in fech.get(ds[0]["data"], {}):
            base = fech[ds[0]["data"]][b]
            bench = [fech[x["data"]][b] / base * 100 - 100 for x in ds if b in fech.get(x["data"], {})]
        vol = (rk.get("volatilidade") or {}).get("anual_60d_pct") if isinstance(rk.get("volatilidade"), dict) else None
        linhas.append({
            "c": c, "ult": ult, "n_pos": len(ult.get("posicoes", [])),
            "acum": _acum(ds), "mes": _acum(ds_mes), "bench": bench[-1] if bench else None,
            "vol": vol, "dd": (rk.get("drawdown_carteira") or {}).get("atual_pct"),
            "dd_max": (rk.get("drawdown_carteira") or {}).get("maximo_pct"),
            "boletim": sem[-1] if sem else None, "notas": [b_["nota_final"] for b_ in sem[-8:]],
            "abertas": sum(1 for a in m if a["status"] == "aberto"),
            "vencidas": sum(1 for a in m if a["status"] == "vencido"),
            "primeiro": ds[0]["data"] if ds else None,
            "ds": ds,
        })
    # curvas a partir do início comum (o primeiro dia em que todas já existem)
    com_dados = [l for l in linhas if len(l["ds"]) > 1]
    cores = ["var(--s1)", "var(--s3)", "var(--s2)", "var(--s4)", "var(--s5)", "var(--s6)"]
    grafico = ""
    if com_dados:
        inicio = max(l["primeiro"] for l in com_dados)
        for k, l in enumerate(com_dados):
            ds = [x for x in l["ds"] if x["data"] >= inicio]
            curvas.append({"nome": l["c"]["nome"], "pontos": [(inicio, 100.0)] + desempenho.curva(ds[1:]),
                           "cor": cores[k % len(cores)], "grossa": l["c"]["id"] == "principal"})
        grafico = G.linhas([x for x in curvas if len(x["pontos"]) > 1])
        inicio_txt = inicio
    else:
        inicio_txt = None
    for l in linhas:
        l.pop("ds")
    return {**comum(), "linhas": linhas, "grafico": grafico, "inicio": inicio_txt}


def ativos_tela() -> dict:
    """O universo de ativos: preço, retornos, volatilidade e em quais carteiras está, com que peso."""
    import math
    from .. import carteiras as _c, instrumentos
    from ..util import usar_carteira
    cad = instrumentos.carregar()
    fech = series.carregar()
    posse: dict[str, list] = {}
    fichas: dict[str, list] = {}
    for c in _c.listar():
        with usar_carteira(c["id"]):
            ult = ultimo_diario() or {}
            for p in ult.get("posicoes", []):
                posse.setdefault(p["ativo"], []).append({"carteira": c["id"], "nome": c["nome"], "peso": p.get("peso_pct"),
                                                          "pl": p.get("pl_pct")})
            for a, f in teses.todas_vigentes().items():
                fichas.setdefault(a, []).append({"carteira": c["id"], "rating": f.get("rating"),
                                                 "alvo": f.get("alvo"), "preco_justo": f.get("preco_justo")})

    def ret(s, n):
        return (s[-1][1] / s[-1 - n][1] - 1) * 100 if len(s) > n and s[-1 - n][1] else None

    linhas = []
    for t, i in sorted(cad.items(), key=lambda x: (x[1].get("classe", ""), x[0])):
        s = series.serie(fech, t)
        sig = series.sigma_pct(fech, t)
        linhas.append({"t": t, "i": instrumentos.info(t, cad), "preco": s[-1][1] if s else None,
                       "data": s[-1][0] if s else None, "r1": ret(s, 1), "r21": ret(s, 21), "r63": ret(s, 63),
                       "r252": ret(s, 252), "vol": sig * math.sqrt(252) if sig else None, "obs": len(s),
                       "posse": posse.get(t, []), "fichas": fichas.get(t, [])})
    return {**comum(), "linhas": linhas, "n_monitorados": sum(1 for x in cad.values() if x.get("monitorar"))}
