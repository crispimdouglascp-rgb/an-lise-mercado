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
"""
from __future__ import annotations

from .series import retorno_dia


def _sinal(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def avaliar(h: dict, fech: dict, dia: str) -> dict:
    t = h.get("teste") or {}
    tipo = t.get("tipo")

    def r(s):
        return retorno_dia(fech, s, dia)

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
        partes, ok = [], True
        for a in t["ativos"]:
            ra = r(a)
            if ra is None:
                return {"data": dia, "resultado": "sem_dado", "detalhe": f"sem retorno de {a}"}
            partes.append(f"{a} {ra:+.2f}%")
            ok = ok and ra > rb
        return {"data": dia, "resultado": "acerto" if ok else "erro",
                "detalhe": f"{cond['serie']} {rc:+.2f}%, {t['benchmark']} {rb:+.2f}%; " + ", ".join(partes)}

    if tipo == "mesma_direcao":
        rs = {a: r(a) for a in t["ativos"]}
        if any(v is None for v in rs.values()):
            return {"data": dia, "resultado": "sem_dado", "detalhe": "falta retorno de algum ativo"}
        sinais = {_sinal(v) for v in rs.values()}
        ok = len(sinais) == 1 and 0 not in sinais
        return {"data": dia, "resultado": "acerto" if ok else "erro",
                "detalhe": ", ".join(f"{a} {v:+.2f}%" for a, v in rs.items())}

    if tipo == "segue_driver":
        rd, ra = r(t["driver"]), r(t["ativo"])
        if rd is None or ra is None:
            return {"data": dia, "resultado": "sem_dado", "detalhe": "falta retorno do driver ou do ativo"}
        if abs(rd) < t.get("limiar_driver_pct", 0.0):
            return {"data": dia, "resultado": "nao_aplicavel",
                    "detalhe": f"driver {t['driver']} {rd:+.2f}% abaixo do limiar"}
        ok = _sinal(rd) == _sinal(ra) and _sinal(ra) != 0
        return {"data": dia, "resultado": "acerto" if ok else "erro",
                "detalhe": f"{t['driver']} {rd:+.2f}%, {t['ativo']} {ra:+.2f}%"}

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
