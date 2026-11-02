"""Hipóteses com teste escrito antes. O acerto é medido por código.

Tipos de teste suportados (campo "teste" da hipótese):

  excesso_em_condicao
    {"tipo": "excesso_em_condicao", "ativos": ["SUZB3","WEGE3"], "benchmark": "IBOV",
     "condicao": {"serie": "USDBRL", "sinal": "alta", "limiar_pct": 0.3}}
    Nos dias em que a condição vale, TODOS os ativos devem render mais que o benchmark.
    Fora da condição: nao_aplicavel.

  mesma_direcao
    {"tipo": "mesma_direcao", "ativos": ["ITUB4","BBDC4"]}
    Todos os ativos devem fechar na mesma direção (todos em alta ou todos em queda).

  segue_driver
    {"tipo": "segue_driver", "ativo": "PETR4", "driver": "BRENT", "limiar_driver_pct": 1.0}
    Quando o driver se move pelo menos o limiar, o ativo deve ir na mesma direção.

  diferenca_vs_referencia
    {"tipo": "diferenca_vs_referencia", "ativos": ["ITUB4"], "referencia": "IBOV", "sentido": -1,
     "gate": [{"serie": "DI35", "min_pct": 0.5}]}
    Média dos ativos menos a referência, em pp, no sentido previsto (+1 sobe mais, -1 sobe menos).

Qualquer tipo aceita "gate": lista de condições {"serie", "min_pct"?, "max_pct"?} sobre o
retorno do dia; gate fechado = nao_aplicavel.

PLACAR v2 (regras do Update #4 da referência), livro data/livros/placar_hipoteses.jsonl:
  1. sem limiar, não pontua: |valor| >= limiar_pp (padrão 0,75) => favor/contra; entre => neutro;
  2. data de formulação é sagrada: só pontua a partir de `formulada_em`, nunca retroage;
  3. reescrever o teste = hipótese nova (mesmo id com teste diferente é erro de validação);
  4. ponto é linha imutável (um por hipótese por dia);
  5. veredito só com >= min_gates (padrão 8) e pelo intervalo de Wilson a 95% contra 50%;
  6. origem "ia" ou "usuario"; hipótese da IA nasce rascunho e só pontua depois do seu "sim".
"""
from __future__ import annotations

import math

from . import livros
from .series import retorno_dia
from .util import config


def _sinal(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def avaliar(h: dict, fech: dict, dia: str) -> dict:
    t = h.get("teste") or {}
    tipo = t.get("tipo")

    def r(s):
        return retorno_dia(fech, s, dia)

    for g in t.get("gate") or []:
        rg = r(g["serie"])
        if rg is None:
            return {"data": dia, "resultado": "sem_dado", "detalhe": f"sem retorno de {g['serie']} (gate)"}
        if ("min_pct" in g and rg < g["min_pct"]) or ("max_pct" in g and rg > g["max_pct"]):
            return {"data": dia, "resultado": "nao_aplicavel", "detalhe": f"gate fechado ({g['serie']} {rg:+.2f}%)"}

    if tipo == "excesso_em_condicao":
        cond = t["condicao"]
        rc = r(cond["serie"])
        if rc is None:
            return {"data": dia, "resultado": "sem_dado", "detalhe": f"sem retorno de {cond['serie']}"}
        lim = cond.get("limiar_pct", 0.0)
        vale = (rc >= lim) if cond["sinal"] == "alta" else (rc <= -lim)
        if not vale:
            return {"data": dia, "resultado": "nao_aplicavel",
                    "detalhe": f"condição não ocorreu ({cond['serie']} {rc:+.2f}%)"}
        rb = r(t["benchmark"])
        if rb is None:
            return {"data": dia, "resultado": "sem_dado", "detalhe": f"sem retorno de {t['benchmark']}"}
        partes, ok, excessos = [], True, []
        for a in t["ativos"]:
            ra = r(a)
            if ra is None:
                return {"data": dia, "resultado": "sem_dado", "detalhe": f"sem retorno de {a}"}
            partes.append(f"{a} {ra:+.2f}%")
            ok = ok and ra > rb
            excessos.append(ra - rb)
        return {"data": dia, "resultado": "acerto" if ok else "erro", "valor_pp": round(min(excessos), 4),
                "detalhe": f"{cond['serie']} {rc:+.2f}%, {t['benchmark']} {rb:+.2f}%; " + ", ".join(partes)}

    if tipo == "mesma_direcao":
        rs = {a: r(a) for a in t["ativos"]}
        if any(v is None for v in rs.values()):
            return {"data": dia, "resultado": "sem_dado", "detalhe": "falta retorno de algum ativo"}
        sinais = {_sinal(v) for v in rs.values()}
        ok = len(sinais) == 1 and 0 not in sinais
        if ok:
            valor = min(abs(v) for v in rs.values())
        else:
            pos = max([v for v in rs.values() if v > 0], default=0.0)
            neg = max([-v for v in rs.values() if v < 0], default=0.0)
            valor = -min(pos, neg)
        return {"data": dia, "resultado": "acerto" if ok else "erro", "valor_pp": round(valor, 4),
                "detalhe": ", ".join(f"{a} {v:+.2f}%" for a, v in rs.items())}

    if tipo == "segue_driver":
        rd, ra = r(t["driver"]), r(t["ativo"])
        if rd is None or ra is None:
            return {"data": dia, "resultado": "sem_dado", "detalhe": "falta retorno do driver ou do ativo"}
        if abs(rd) < t.get("limiar_driver_pct", 0.0):
            return {"data": dia, "resultado": "nao_aplicavel",
                    "detalhe": f"driver {t['driver']} {rd:+.2f}% abaixo do limiar"}
        ok = _sinal(rd) == _sinal(ra) and _sinal(ra) != 0
        return {"data": dia, "resultado": "acerto" if ok else "erro", "valor_pp": round(ra * _sinal(rd), 4),
                "detalhe": f"{t['driver']} {rd:+.2f}%, {t['ativo']} {ra:+.2f}%"}

    if tipo == "diferenca_vs_referencia":
        rref = r(t["referencia"])
        ras = {a: r(a) for a in t["ativos"]}
        if rref is None or any(v is None for v in ras.values()):
            return {"data": dia, "resultado": "sem_dado", "detalhe": "falta retorno de ativo ou referência"}
        valor = t.get("sentido", 1) * (sum(ras.values()) / len(ras) - rref)
        return {"data": dia, "resultado": "acerto" if valor > 0 else "erro", "valor_pp": round(valor, 4),
                "detalhe": f"{t['referencia']} {rref:+.2f}%; " + ", ".join(f"{a} {v:+.2f}%" for a, v in ras.items())}

    return {"data": dia, "resultado": "sem_dado", "detalhe": f"tipo de teste desconhecido: {tipo!r}"}


def medir_dia(hipoteses: list[dict], fech: dict, dia: str) -> list[dict]:
    """Mede todas as hipóteses ativas no dia. Idempotente: re-medir o dia substitui a medição."""
    for h in hipoteses:
        if h.get("status", "ativa") != "ativa":
            continue
        med = [m for m in h.get("medicoes", []) if m["data"] != dia]
        med.append(avaliar(h, fech, dia))
        h["medicoes"] = sorted(med, key=lambda m: m["data"])
    return hipoteses


def placar(hipoteses: list[dict]) -> list[dict]:
    out = []
    for h in hipoteses:
        med = [m for m in h.get("medicoes", []) if m["resultado"] in {"acerto", "erro"}]
        acertos = sum(1 for m in med if m["resultado"] == "acerto")
        seq = 0
        for m in reversed(med):
            if m["resultado"] == "erro":
                seq += 1
            else:
                break
        limite = h.get("arquivar_apos_falhas_consecutivas")
        out.append({
            "id": h["id"],
            "titulo": h.get("titulo", ""),
            "status": h.get("status", "ativa"),
            "medicoes": len(med),
            "acertos": acertos,
            "taxa_acerto_pct": round(acertos / len(med) * 100, 1) if med else None,
            "erros_consecutivos": seq,
            # só uma sugestão: mudar o status é decisão sua, registrada em hipoteses.json
            "sugestao": "arquivar" if limite and seq >= limite else None,
        })
    return out


# ====================================================================== placar v2 (livros)

def _cfg() -> dict:
    return config("placar.toml", {}).get("hipoteses", {})


def carregar() -> list[dict]:
    """Hipóteses do livro, uma por id: definição (1ª linha) + mudanças de status (linhas seguintes)."""
    defs: dict[str, dict] = {}
    for r in livros.ler("hipoteses"):
        hid = r.get("id")
        if hid not in defs:
            defs[hid] = dict(r)
            defs[hid].setdefault("status", "ativa")
            defs[hid]["_historico_status"] = []
            continue
        h = defs[hid]
        for campo in ("status", "confirmado_em", "motivo", "encerrada_em"):
            if campo in r:
                h[campo] = r[campo]
        h["_historico_status"].append({k: r.get(k) for k in ("em", "status", "motivo") if k in r})
    return list(defs.values())


def validar_livro() -> list[str]:
    probs, testes = [], {}
    for r in livros.ler("hipoteses"):
        hid = r.get("id")
        if not hid:
            probs.append("hipótese sem id")
            continue
        if "teste" in r:
            if hid in testes and testes[hid] != r["teste"]:
                probs.append(f"hipótese {hid}: teste reescrito no mesmo id (reescrever = hipótese nova)")
            testes.setdefault(hid, r["teste"])
            if r.get("origem", "usuario") not in {"ia", "usuario"}:
                probs.append(f"hipótese {hid}: origem deve ser 'ia' ou 'usuario'")
            if not r.get("formulada_em"):
                probs.append(f"hipótese {hid}: falta 'formulada_em'")
    return probs


def ativas() -> list[dict]:
    return [h for h in carregar() if h.get("status") == "ativa"]


def simbolos(h: dict) -> set[str]:
    t = h.get("teste") or {}
    cand = list(t.get("ativos", [])) + [t.get("ativo"), t.get("benchmark"), t.get("driver"), t.get("referencia")]
    cand += [(t.get("condicao") or {}).get("serie")] + [g.get("serie") for g in t.get("gate") or []]
    return {c for c in cand if c}


def registrar(h: dict) -> dict:
    h = dict(h)
    if h.get("id") in {x["id"] for x in carregar()}:
        raise ValueError(f"id {h['id']} já existe: reescrever uma hipótese = criar outra com id novo")
    h.setdefault("origem", "usuario")
    h.setdefault("status", "rascunho" if h["origem"] == "ia" else "ativa")
    h.setdefault("limiar_pp", _cfg().get("limiar_pp", 0.75))
    h.setdefault("min_gates", _cfg().get("min_gates", 8))
    return livros.anexar("hipoteses", h)


def mudar_status(hid: str, status: str, em: str, motivo: str) -> dict:
    """Ativar (o seu "sim"), encerrar ou arquivar. Quem decide é você; o código só sugere."""
    if status not in {"ativa", "encerrada", "arquivada"}:
        raise ValueError("status deve ser ativa, encerrada ou arquivada")
    reg = {"id": hid, "status": status, "em": em, "motivo": motivo}
    if status == "ativa":
        reg["confirmado_em"] = em
    return livros.anexar("hipoteses", reg)


def pontuar(h: dict, fech: dict, dia: str) -> dict:
    r = avaliar(h, fech, dia)
    ponto = {"hipotese_id": h["id"], "data": dia, "detalhe": r.get("detalhe", ""), "origem": h.get("origem", "usuario")}
    if r["resultado"] == "sem_dado":
        return {**ponto, "gate_aberto": None, "veredito": "sem_dado", "valor_pp": None}
    if r["resultado"] == "nao_aplicavel":
        return {**ponto, "gate_aberto": False, "veredito": "nao_aplicavel", "valor_pp": None}
    lim = float(h.get("limiar_pp", _cfg().get("limiar_pp", 0.75)))
    v = r.get("valor_pp")
    if v is None:
        return {**ponto, "gate_aberto": True, "veredito": "sem_dado", "valor_pp": None}
    ver = "favor" if v >= lim else ("contra" if v <= -lim else "neutro")
    return {**ponto, "gate_aberto": True, "veredito": ver, "valor_pp": v, "limiar_pp": lim}


def medir_dia_livro(fech: dict, dia: str) -> list[dict]:
    """Grava UM ponto por hipótese ativa por dia, só a partir de `formulada_em`. Nunca reescreve."""
    ja = {(p["hipotese_id"], p["data"]) for p in livros.ler("placar_hipoteses")}
    novos = []
    for h in ativas():
        if dia < h.get("formulada_em", "9999") or (h["id"], dia) in ja:
            continue
        p = pontuar(h, fech, dia)
        if p["veredito"] == "sem_dado":
            continue  # sem dado não vira ponto: se o dado chegar depois, o dia ainda pode ser medido
        novos.append(livros.anexar("placar_hipoteses", p))
    return novos


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    ph = k / n
    den = 1 + z * z / n
    centro = (ph + z * z / (2 * n)) / den
    meia = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - meia), min(1.0, centro + meia)


def placar_v2(hs: list[dict] | None = None, pontos: list[dict] | None = None, ate: str | None = None) -> list[dict]:
    hs = carregar() if hs is None else hs
    pontos = livros.ler("placar_hipoteses") if pontos is None else pontos
    out = []
    for h in hs:
        ps = [p for p in pontos if p["hipotese_id"] == h["id"] and (ate is None or p["data"] <= ate)]
        f = sum(1 for p in ps if p["veredito"] == "favor")
        c = sum(1 for p in ps if p["veredito"] == "contra")
        n_ = sum(1 for p in ps if p["veredito"] == "neutro")
        gates = f + c + n_
        mg = int(h.get("min_gates", _cfg().get("min_gates", 8)))
        ic = wilson(f, f + c)
        if gates < mg:
            ver = f"aguardando ({gates}/{mg} gates)"
        elif ic is None:
            ver = "indefinida (só neutros)"
        elif ic[0] > 0.5:
            ver = "confirmada"
        elif ic[1] < 0.5:
            ver = "refutada"
        else:
            ver = "indefinida"
        out.append({
            "id": h["id"], "titulo": h.get("titulo", ""), "status": h.get("status"), "origem": h.get("origem"),
            "formulada_em": h.get("formulada_em"), "favor": f, "contra": c, "neutro": n_, "gates": gates,
            "min_gates": mg, "taxa_pct": round(f / (f + c) * 100, 1) if f + c else None,
            "ic95_pct": [round(ic[0] * 100, 1), round(ic[1] * 100, 1)] if ic else None,
            "veredito": ver, "legado": h.get("legado"),
            "sugestao": "arquivar" if ver == "refutada" and h.get("status") == "ativa" else None,
            "ultimo": ps[-1] if ps else None,
        })
    return out
