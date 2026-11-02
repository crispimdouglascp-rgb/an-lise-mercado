"""Boletim do gestor: nota de 0 a 5 calculada SÓ por código, com evidência por critério.

Critérios e pesos (config/placar.toml):
  Retorno × benchmark 15 · Aderência às regras 20 · Gestão de risco 20 · Qualidade das decisões 15
  Construção da carteira 10 · Execução, custos e fiscal 10 · Realização de resultados 10

Princípios:
  * regra ignorada = 0 no critério de aderência, sem crédito parcial;
  * tetos SÓ LIMITAM a nota final (retorno bom não compensa processo ruim);
  * critério sem base no período (ex.: nenhuma realização a julgar) fica "sem base" e o peso
    é redistribuído entre os outros, declarado no boletim;
  * cobertura de dados abaixo do mínimo => boletim "parcial"; revisão = NOVA edição.
  * a IA comenta o boletim, mas não altera nenhuma nota.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import decisoes as dec_mod, diario, fiscal, instrumentos, livros, mesa, razao
from .calendario import dias_uteis
from .util import agora, config, ler_json

CRITERIOS = [
    ("retorno_benchmark", "Retorno × benchmark"),
    ("aderencia_regras", "Aderência às regras"),
    ("gestao_risco", "Gestão de risco"),
    ("qualidade_decisoes", "Qualidade das decisões"),
    ("construcao_carteira", "Construção da carteira"),
    ("execucao_custos_fiscal", "Execução, custos e fiscal"),
    ("realizacao", "Realização de resultados"),
]
TIPOS = ("diario", "semanal", "mensal", "trimestral")


def _cfg() -> dict:
    return config("placar.toml")


def _clamp(x: float) -> float:
    return max(0.0, min(5.0, x))


def periodo(tipo: str, ref: date) -> tuple[date, date]:
    if tipo == "diario":
        return ref, ref
    if tipo == "semanal":
        ini = ref - timedelta(days=ref.weekday())
        return ini, ini + timedelta(days=4)
    if tipo == "mensal":
        ini = ref.replace(day=1)
        prox = (ini + timedelta(days=32)).replace(day=1)
        return ini, prox - timedelta(days=1)
    if tipo == "trimestral":
        m0 = 3 * ((ref.month - 1) // 3) + 1
        ini = date(ref.year, m0, 1)
        prox = date(ref.year + (m0 + 3 > 12), (m0 + 3 - 1) % 12 + 1, 1)
        return ini, prox - timedelta(days=1)
    raise ValueError(f"tipo de boletim inválido: {tipo}")


def letra(nota: float, cfg: dict | None = None) -> str:
    esc = sorted((cfg or _cfg())["letras"].items(), key=lambda x: -x[1])
    for l, minimo in esc:
        if nota >= minimo - 1e-9:
            return l
    return "F"


# ====================================================================== critérios

def c_retorno(ctx: dict) -> dict:
    cfg = _cfg()["retorno"]
    k = cfg["k_pp"][ctx["tipo"]]
    ds, ev = ctx["diarios"], []
    alfas, pesos = {}, {}
    base = ctx["diario_base"]
    for s in ("BR", "EXT"):
        rs = [((d.get("sleeves") or {}).get(s) or {}) for d in ds]
        pares = [(x.get("retorno_pct"), x.get("benchmark_pct")) for x in rs
                 if x.get("retorno_pct") is not None and x.get("benchmark_pct") is not None]
        if not pares:
            continue
        r = (math.prod(1 + a / 100 for a, _ in pares) - 1) * 100
        b = (math.prod(1 + c / 100 for _, c in pares) - 1) * 100
        alfas[s] = r - b
        w = (((base or {}).get("sleeves") or {}).get(s) or {}).get("valor_brl") \
            or ((ds[0].get("sleeves") or {}).get(s) or {}).get("valor_brl") or 0.0
        pesos[s] = w
        nome_b = "IBOV" if s == "BR" else "S&P 500 em R$"
        ev.append(f"{'Brasil' if s == 'BR' else 'Exterior'} {r:+.2f}% × {nome_b} {b:+.2f}% "
                  f"(alfa {r - b:+.2f} pp, {len(pares)} pregões)")
    if alfas and sum(pesos.values()) > 0:
        alfa = sum(alfas[s] * pesos[s] for s in alfas) / sum(pesos[s] for s in alfas)
    else:
        rets = [d.get("retorno_dia_pct") for d in ds]
        ibov = [d.get("ibov_dia_pct") for d in ds]
        pares = [(a, b) for a, b in zip(rets, ibov) if a is not None and b is not None]
        if not pares:
            return {"nota": None, "evidencias": ["sem retorno medido no período"]}
        r = (math.prod(1 + a / 100 for a, _ in pares) - 1) * 100
        b = (math.prod(1 + c / 100 for _, c in pares) - 1) * 100
        alfa = r - b
        ev.append(f"Carteira consolidada {r:+.2f}% × Ibovespa {b:+.2f}% (sem sleeves; inclui caixa)")
    # concentração do ganho
    contrib: dict[str, float] = {}
    for prev, d in zip([base] + ds[:-1], ds):
        pw = {p["ativo"]: p.get("peso_pct") for p in (prev or {}).get("posicoes", [])}
        for p in d.get("posicoes", []):
            if p.get("dia_pct") is not None and pw.get(p["ativo"]):
                contrib[p["ativo"]] = contrib.get(p["ativo"], 0) + pw[p["ativo"]] / 100 * p["dia_pct"]
    positivos = {a: c for a, c in contrib.items() if c > 0}
    if positivos:
        top = max(positivos, key=positivos.get)
        share = positivos[top] / sum(positivos.values()) * 100
        if share >= cfg["concentracao_ganho_pct"]:
            ev.append(f"{share:.0f}% do ganho veio de uma ação só ({top})")
    nota = _clamp(2.5 + alfa / k)
    ev.insert(0, f"alfa ponderado {alfa:+.2f} pp; escala {k} pp por ponto a partir de 2,5")
    return {"nota": nota, "evidencias": ev, "alfa_pp": round(alfa, 3)}


def _alertas_relevantes(ctx: dict, origens: set[str]) -> list[dict]:
    ini, fim = ctx["ini"], ctx["fim"]
    out = []
    for a in ctx["mesa"]:
        if a.get("origem") not in origens or not a.get("prazo"):
            continue
        if a["prazo"] > fim:
            continue
        if a["prazo"] >= ini or a["status"] == "vencido":
            out.append(a)
    return out


def _ignorado(a: dict) -> bool:
    if a["status"] == "vencido":
        return True
    if a["status"] in {"resolvido", "encerrado"} and (a.get("fechado_em") or "") > a["prazo"]:
        return a["status"] == "encerrado" or not a.get("no_prazo", True)
    return False


def c_aderencia(ctx: dict) -> dict:
    cfg = _cfg()["aderencia"]
    rel = _alertas_relevantes(ctx, {"regras", "vigilancia"})
    ev = []
    alta_ign = [a for a in rel if a["severidade"] == "alta" and _ignorado(a)]
    if alta_ign:
        for a in alta_ign[:4]:
            ev.append(f"regra ignorada: {a['motivo']} (prazo {a['prazo']}, {a['status']})")
        return {"nota": 0.0, "evidencias": ["regra ignorada = 0, sem crédito parcial"] + ev}
    media_ign = [a for a in rel if a["severidade"] == "media" and a["status"] == "vencido"]
    atrasadas = [a for a in rel if a["severidade"] == "media" and a["status"] != "vencido" and _ignorado(a)]
    nota = _clamp(5 - cfg["penalidade_media"] * len(media_ign) - cfg["penalidade_atraso"] * len(atrasadas))
    ev.append(f"{len(rel)} pendências de regra com prazo no período; {len(media_ign)} médias vencidas; "
              f"{len(atrasadas)} resolvidas com atraso")
    ev += [f"vencida: {a['motivo']}" for a in media_ign[:3]]
    return {"nota": nota, "evidencias": ev}


def c_risco(ctx: dict) -> dict:
    cfg = _cfg()["risco"]
    riscos = ctx["riscos"]
    if not riscos:
        return {"nota": None, "evidencias": ["sem dia com patrimônio completo: risco não medido"]}
    pen, grave, ev, cont = 0.0, False, [], {}
    for r in riscos:
        for b in r.get("bandas", []):
            pen += cfg["penalidade_alta"] if b["severidade"] == "alta" else cfg["penalidade_media"]
            cont[b["detalhe"].split(" (")[0]] = cont.get(b["detalhe"].split(" (")[0], 0) + 1
            if b.get("valor") is not None and b.get("limite") and b["regra"] != "banda_nivel1" \
                    and b["valor"] > 1.5 * b["limite"]:
                grave = True
    for desc, n in sorted(cont.items(), key=lambda x: -x[1])[:4]:
        ev.append(f"{desc}: {n} pregão(ões)")
    # stops: fechou abaixo do stop e seguiu sem decisão de stop/saída (ou "manter" sem nova invalidação)
    tocados = {}
    for d in ctx["diarios"]:
        for p in d.get("posicoes", []):
            if p.get("stop") and p.get("preco") and p["preco"] <= p["stop"]:
                tocados.setdefault(p["ativo"], d["data"])
    for a, dia in tocados.items():
        ds = [x for x in ctx["decisoes"] if x.get("ativo") == a and dia <= x.get("data", "") <= ctx["fim"]
              and x.get("tipo") in {"stop", "saida", "reduzir"}]
        ok = any(x.get("decisao") != "manter" or x.get("nova_invalidacao") or x.get("tipo") != "stop" for x in ds)
        if not ok:
            pen += cfg["penalidade_stop_mantido"]
            ev.append(f"{a} fechou abaixo do stop em {dia} e seguiu sem decisão de stop com nova invalidação")
    nota = _clamp(5 - pen)
    if grave:
        nota = min(nota, cfg["teto_rompimento_grave"])
        ev.append(f"rompimento acima de 1,5× o limite: critério limitado a {cfg['teto_rompimento_grave']}")
    if not ev:
        ev.append(f"nenhuma banda rompida em {len(riscos)} pregões medidos")
    return {"nota": nota, "evidencias": ev}


def c_decisoes(ctx: dict) -> dict:
    cfg = _cfg()["decisoes"]
    ops = [o for o in ctx["ops_periodo"] if o["tipo"] in {"compra", "venda"}]
    decs = {d["id"]: d for d in ctx["decisoes"] if d.get("id")}
    ev = []
    if ops:
        fracs, fora = [], 0
        for o in ops:
            chk = dec_mod.checklist_da_operacao(o, decs)
            f, faltam = dec_mod.completude(chk)
            fracs.append(f)
            if f < 1:
                ev.append(f"{o['tipo']} de {o['ativo']} em {o['data']}: {f * 9:.0f}/9"
                          + (f", sem tese" if not chk.get("tese_id") else f", faltam {', '.join(faltam[:3])}"))
            par = ctx["params"].get(o["ativo"], {})
            if o["tipo"] == "compra" and par.get("nivel_compra") and o["preco"] > par["nivel_compra"]:
                fora += 1
                ev.append(f"compra de {o['ativo']} a {o['preco']} acima do seu nível de compra {par['nivel_compra']}")
            rr = chk.get("risco_retorno")
            if o["tipo"] == "compra" and isinstance(rr, (int, float)) and rr < cfg["rr_minimo"]:
                fora += 1
                ev.append(f"compra de {o['ativo']} com risco-retorno {rr} (mínimo {cfg['rr_minimo']})")
        media = sum(fracs) / len(fracs)
        ev.insert(0, f"{len(ops)} operações; completude média do checklist {media * 100:.0f}%; "
                     f"{fora} fora da própria régua")
        return {"nota": _clamp(5 * media - cfg["penalidade_fora_da_regua"] * fora), "evidencias": ev}
    pos = (ctx["diarios"][-1] if ctx["diarios"] else {}).get("posicoes", [])
    if not pos:
        return {"nota": None, "evidencias": ["sem operações nem posições no período"]}
    ok = [p for p in pos if p.get("tese_id") and not p.get("revisao_vencida")]
    ev.append(f"sem operações: {len(ok)} de {len(pos)} posições com ficha vigente e revisão em dia")
    ev += [f"{p['ativo']}: {'sem ficha' if not p.get('tese_id') else 'revisão vencida'}"
           for p in pos if p not in ok][:4]
    return {"nota": _clamp(5 * len(ok) / len(pos)), "evidencias": ev}


def c_construcao(ctx: dict) -> dict:
    cfg = _cfg()["construcao"]
    if not ctx["diarios"]:
        return {"nota": None, "evidencias": ["sem diário no período"]}
    ult = ctx["diarios"][-1]
    pos = ult.get("posicoes", [])
    if not pos:
        return {"nota": None, "evidencias": ["sem posições"]}
    piso = [v for v in ult.get("violacoes", []) if v["regra"] == "piso_posicao"]
    sem_ficha = [p["ativo"] for p in pos if not p.get("tese_id") or p.get("conviccao") is None]
    rk = ctx["riscos"][-1] if ctx["riscos"] else {}
    hhi_max = config("risco.toml", {}).get("limites", {}).get("hhi_max")
    pen = cfg["penalidade_piso"] * len(piso) + cfg["penalidade_sem_ficha"] * len(sem_ficha)
    ev = [f"{len(pos)} posições; {len(piso)} abaixo do piso; {len(sem_ficha)} sem ficha ou convicção"]
    if sem_ficha:
        ev.append("sem ficha/convicção: " + ", ".join(sem_ficha[:5]))
    if rk.get("hhi") and hhi_max and rk["hhi"] > hhi_max:
        pen += cfg["penalidade_hhi"]
        ev.append(f"HHI {rk['hhi']:.3f} acima de {hhi_max} (n efetivo {rk.get('n_efetivo')})")
    n1 = [b for b in rk.get("bandas", []) if b["regra"] == "banda_nivel1"]
    pen += cfg["penalidade_nivel1"] * len(n1)
    ev += [b["detalhe"] for b in n1]
    return {"nota": _clamp(5 - pen), "evidencias": ev}


def c_execucao(ctx: dict) -> dict:
    cfg = _cfg()["execucao"]
    reg = config("regras.toml")["operacoes"]
    ops = [o for o in ctx["ops_periodo"] if o["tipo"] in {"compra", "venda"}]
    n_preg = max(1, len(ctx["pregoes"]))
    max_ordens = reg["max_ordens_semana"] * n_preg / 5
    pen, ev = 0.0, [f"{len(ops)} ordens no período (máx. {max_ordens:.0f} para {n_preg} pregões)"]
    if len(ops) > max_ordens:
        pen += cfg["penalidade_giro"]
        ev.append("excesso de giro")
    custos = sum(float(o.get("custos", 0)) for o in ops)
    realizado = sum(v["lucro"] for v in ctx["vendas_periodo"] if v["moeda"] == "BRL")
    if realizado > 0 and custos / realizado * 100 > cfg["custos_max_pct_do_realizado"]:
        pen += cfg["penalidade_custos"]
        ev.append(f"custos R$ {custos:,.2f} = {custos / realizado * 100:.0f}% do realizado R$ {realizado:,.2f}")
    elif ops:
        ev.append(f"custos R$ {custos:,.2f}; realizado R$ {realizado:,.2f}")
    pagos = {e.get("mes") for e in ctx["eventos"] if e.get("tipo") == "darf_pago"}
    for m in ctx["fiscal"]:
        if m["darf"] and m["vencimento"] and ctx["ini"] <= m["vencimento"] <= ctx["fim"] and m["mes"] not in pagos:
            pen += cfg["penalidade_darf_vencido"]
            ev.append(f"DARF de {m['mes']} (R$ {m['darf']:,.2f}, venc. {m['vencimento']}) sem pagamento registrado")
    ev.append("opções: lançamento coberto avaliado a partir do módulo de opções (Ciclo 3)")
    return {"nota": _clamp(5 - pen), "evidencias": ev}


def c_realizacao(ctx: dict) -> dict:
    cfg = _cfg()["realizacao"]
    reg = config("regras.toml")["alvo"]
    gat = {}
    for d in ctx["diarios"]:
        for p in d.get("posicoes", []):
            if p.get("alvo") and p.get("preco") and p["preco"] >= p["alvo"] * reg["realizar_em_pct_do_alvo"] / 100:
                gat.setdefault(p["ativo"], d["data"])
    ev, notas_parciais = [], []
    if gat:
        ok = 0
        for a, dia in gat.items():
            ini = (date.fromisoformat(dia) - timedelta(days=reg["validade_decisao_dias"])).isoformat()
            if any(x.get("ativo") == a and ini <= x.get("data", "") <= ctx["fim"]
                   and x.get("tipo") in {"realizacao", "saida", "reduzir", "manter"} for x in ctx["decisoes"]):
                ok += 1
            else:
                ev.append(f"{a} passou de {reg['realizar_em_pct_do_alvo']}% do alvo em {dia} sem decisão")
        ev.insert(0, f"{ok} de {len(gat)} gatilhos de realização com decisão")
        notas_parciais.append(5 * ok / len(gat))
    perdas = 0
    for v in ctx["vendas_periodo"]:
        if v["lucro"] >= 0 or v["moeda"] != "BRL":
            continue
        dlist = [x for x in ctx["decisoes"] if x.get("ativo") == v["ativo"] and x.get("data", "") <= v["data"]
                 and (x.get("checklist") or {}).get("risco_max_pct") is not None]
        pat = next((d.get("patrimonio") for d in ctx["diarios"] if d["data"] == v["data"]), None)
        if dlist and pat:
            rmax = dlist[-1]["checklist"]["risco_max_pct"]
            perda = -v["lucro"] / pat * 100
            if perda > rmax:
                perdas += 1
                ev.append(f"saída de {v['ativo']} com perda de {perda:.2f}% do patrimônio (risco máx. {rmax}%)")
    if ctx["vendas_periodo"]:
        neg = sum(1 for v in ctx["vendas_periodo"] if v["lucro"] < 0)
        ev.append(f"{len(ctx['vendas_periodo'])} saídas, {neg} com prejuízo")
        if not gat:
            notas_parciais.append(5.0)
    if not notas_parciais:
        return {"nota": None, "evidencias": ["nenhuma realização a julgar no período"]}
    nota = sum(notas_parciais) / len(notas_parciais) - cfg["penalidade_perda_acima_do_risco"] * perdas
    return {"nota": _clamp(nota), "evidencias": ev}


FUNCOES = {"retorno_benchmark": c_retorno, "aderencia_regras": c_aderencia, "gestao_risco": c_risco,
           "qualidade_decisoes": c_decisoes, "construcao_carteira": c_construcao,
           "execucao_custos_fiscal": c_execucao, "realizacao": c_realizacao}


# ====================================================================== montagem

def contexto(tipo: str, ref: date) -> dict:
    ini_d, fim_d = periodo(tipo, ref)
    ini, fim = ini_d.isoformat(), fim_d.isoformat()
    ds = diario.carregar_diarios(ini, fim)
    antes = [d for d in diario.dias_com_diario(ini)]
    base = ler_json(diario.p_diario(antes[-1])) if antes else None
    ops = razao.carregar_operacoes()
    est = razao.calcular_estado(ops, ate=fim)
    riscos = [r for r in (ler_json(diario.p_risco(d["data"])) for d in ds) if r]
    return {
        "tipo": tipo, "ini": ini, "fim": fim, "diarios": ds, "diario_base": base,
        "pregoes": [d.isoformat() for d in dias_uteis(ini_d, fim_d)],
        "ops_periodo": [o for o in ops if ini <= o["data"] <= fim],
        "vendas_periodo": [v for v in est.vendas if ini <= v["data"] <= fim],
        "decisoes": razao.carregar_decisoes(), "mesa": mesa.estado(fim), "riscos": riscos,
        "params": instrumentos.parametros(fim), "eventos": livros.ler("eventos"),
        "fiscal": fiscal.apurar(ops, fim[:7]),
    }


def calcular(tipo: str, ref: date) -> dict:
    cfg = _cfg()
    ctx = contexto(tipo, ref)
    crit = {}
    for k, nome in CRITERIOS:
        r = FUNCOES[k](ctx)
        crit[k] = {"nome": nome, "peso": cfg["pesos"][k],
                   "nota": round(r["nota"], 2) if r["nota"] is not None else None,
                   "evidencias": r["evidencias"]}
    validos = {k: c for k, c in crit.items() if c["nota"] is not None}
    soma_p = sum(c["peso"] for c in validos.values())
    bruta = sum(c["peso"] * c["nota"] for c in validos.values()) / soma_p if soma_p else 0.0
    for k, c in crit.items():
        c["pts"] = round(c["peso"] / 100 * c["nota"], 3) if c["nota"] is not None else None
        c["peso_efetivo"] = round(c["peso"] / soma_p * 100, 1) if c["nota"] is not None and soma_p else 0
    tetos, final = [], bruta
    tc = cfg["tetos"]
    if crit["aderencia_regras"]["nota"] == 0:
        final = min(final, tc["aderencia_zero_nota_max"])
        tetos.append(f"regra ignorada: nota final limitada a {tc['aderencia_zero_nota_max']}")
    rn = crit["gestao_risco"]["nota"]
    if rn is not None and rn < tc["risco_baixo_limite"]:
        final = min(final, tc["risco_baixo_nota_max"])
        tetos.append(f"gestão de risco abaixo de {tc['risco_baixo_limite']}: nota final limitada a "
                     f"{tc['risco_baixo_nota_max']}")
    validos_d = [d for d in ctx["diarios"] if d.get("patrimonio")]
    cobertura = len(validos_d) / len(ctx["pregoes"]) * 100 if ctx["pregoes"] else 0.0
    return {
        "tipo": tipo, "inicio": ctx["ini"], "fim": ctx["fim"], "criterios": crit,
        "nota_bruta": round(bruta, 3), "nota_final": round(final, 3), "letra": letra(final, cfg),
        "tetos_aplicados": tetos,
        "sem_base": [crit[k]["nome"] for k in crit if crit[k]["nota"] is None],
        "cobertura": {"pregoes": len(ctx["pregoes"]), "com_dados": len(validos_d), "pct": round(cobertura, 1),
                      "parcial": cobertura < tc["cobertura_minima_pct"]},
    }


def edicoes(tipo: str | None = None) -> list[dict]:
    return [b for b in livros.ler("boletins") if tipo is None or b["tipo"] == tipo]


def emitir(tipo: str, ref: date) -> dict:
    """Calcula e grava uma edição. Se nada mudou desde a última edição do período, não grava."""
    b = calcular(tipo, ref)
    mesmas = [e for e in edicoes(tipo) if e["inicio"] == b["inicio"]]
    if mesmas:
        ult = mesmas[-1]
        if ult["nota_final"] == b["nota_final"] and \
                {k: c["nota"] for k, c in ult["criterios"].items()} == {k: c["nota"] for k, c in b["criterios"].items()} \
                and ult["cobertura"] == b["cobertura"]:
            return ult
    anteriores = [e for e in edicoes(tipo) if e["fim"] < b["inicio"]]
    if anteriores:
        prev = anteriores[-1]
        for k, c in b["criterios"].items():
            pn = prev["criterios"].get(k, {}).get("nota")
            c["seta"] = None if pn is None or c["nota"] is None else ("↑" if c["nota"] > pn else
                                                                        "↓" if c["nota"] < pn else "→")
        b["anterior"] = {"id": prev["id"], "letra": prev["letra"], "nota_final": prev["nota_final"]}
    n = len(mesmas) + 1
    b.update(id=f"B-{tipo}-{b['inicio']}-e{n}", edicao=n, revisa=mesmas[-1]["id"] if mesmas else None,
             emitido_em=agora().isoformat())
    return livros.anexar("boletins", b)


def historico(tipo: str = "semanal") -> list[dict]:
    """Última edição de cada período, em ordem (para a evolução das notas)."""
    ult: dict[str, dict] = {}
    for e in edicoes(tipo):
        ult[e["inicio"]] = e
    return [ult[k] for k in sorted(ult)]
