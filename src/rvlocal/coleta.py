"""Coleta de preços (código puro, custo de IA zero).

Modos:
  manha       08:20 BRT  contexto da madrugada + conferência do dólar contra o BCB
  flash       09:40 BRT  o que mudou antes da abertura
  fechamento  18:00 BRT  grava no mercado.db só dado conferido e do dia; lacuna é lacuna
"""
from __future__ import annotations

from dataclasses import asdict

from . import fontes, hipoteses, instrumentos, razao, series
from .calendario import dia_util
from .util import agora, config, gravar_json, hoje, p_gerado


def tickers_de_interesse() -> list[str]:
    """Posições abertas + ativos das hipóteses ativas + instrumentos marcados `monitorar`."""
    est = razao.calcular_estado(razao.carregar_operacoes())
    nomes_serie = set(config("series.toml"))
    ts = set(est.posicoes)
    for t, i in instrumentos.carregar().items():
        if i.get("monitorar"):
            ts.add(t)
    for h in hipoteses.ativas():
        ts |= {c for c in hipoteses.simbolos(h) if c not in nomes_serie}
    return sorted(ts)


def ler_tudo(tol_pct: float) -> dict[str, fontes.Leitura]:
    cad = instrumentos.carregar()
    out: dict[str, fontes.Leitura] = {}
    for t in tickers_de_interesse():
        out[t] = fontes.consolidar(t, fontes.obtencoes_ativo(t, cad), tol_pct)
    for nome, cfg in config("series.toml").items():
        out[nome] = fontes.consolidar(nome, fontes.obtencoes_serie(nome, cfg), tol_pct)
    return out


def _ser(l: fontes.Leitura) -> dict:
    d = asdict(l)
    d["ts"] = l.ts.isoformat() if l.ts else None
    for c in d["cotacoes"]:
        c["ts"] = c["ts"].isoformat()
    return d


def conferir_dolar_bcb(log: dict) -> None:
    fech = series.carregar()
    try:
        data_bcb, valor = fontes.fetch_bcb_dolar()
    except Exception as e:  # noqa: BLE001 - qualquer falha vira nota no log
        log["conferencia_bcb"] = {"status": "falhou", "erro": str(e)}
        return
    meu = fech.get(data_bcb, {}).get("USDBRL")
    if meu is None:
        log["conferencia_bcb"] = {"status": "sem_fechamento_proprio", "data": data_bcb, "bcb": valor}
        return
    div = abs(meu / valor - 1) * 100
    log["conferencia_bcb"] = {
        "status": "ok" if div <= 1.0 else "divergente",
        "data": data_bcb, "bcb": valor, "meu": meu, "divergencia_pct": round(div, 3),
    }


def p_log(dia: str, modo: str):
    return p_gerado("coleta", f"coleta_{dia}_{modo}.json")


def coletar(modo: str, forcar: bool = False) -> dict:
    dia = hoje()
    if not forcar and not dia_util(dia):
        print(f"{dia} sem pregão: nada a coletar.")
        return {"data": dia.isoformat(), "modo": modo, "pulado": "sem pregão"}
    tol = config("regras.toml")["coleta"]["tolerancia_fontes_pct"]
    leituras = ler_tudo(tol)
    log: dict = {
        "data": dia.isoformat(), "modo": modo, "gerado_em": agora().isoformat(),
        "leituras": {k: _ser(v) for k, v in leituras.items()},
    }
    if modo == "manha":
        conferir_dolar_bcb(log)
    if modo == "fechamento":
        gravados, lacunas = {}, {}
        for s, l in leituras.items():
            motivo = None
            if not l.aceitavel_no_fechamento:
                motivo = l.status
            elif l.ts is None or l.ts.date() != dia:
                motivo = "cotacao_defasada"
            if motivo:
                lacunas[s] = motivo
            else:
                gravados[s] = {"valor": l.preco, "status": l.status,
                               "fonte": "+".join(c.fonte for c in l.cotacoes)}
        conflitos = series.gravar_fechamentos(dia.isoformat(), gravados) if gravados else {}
        log["fechamento"] = {"gravados": {s: v["valor"] for s, v in gravados.items()},
                             "lacunas": lacunas, "conflitos": conflitos}
    gravar_json(p_log(dia.isoformat(), modo), log)
    resumo = {s: (l.status, l.preco) for s, l in leituras.items()}
    print(f"coleta {modo} {dia}: {resumo}")
    if modo == "fechamento":
        print("lacunas:", log["fechamento"]["lacunas"] or "nenhuma")
    return log
