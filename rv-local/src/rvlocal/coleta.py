"""Coleta de preços (código puro, custo de IA zero).

Modos:
  manha       08:20 BRT  contexto da madrugada + conferência do dólar contra o BCB
  flash       09:40 BRT  o que mudou antes da abertura
  fechamento  18:00 BRT  grava fechamentos.json (só dado conferido; lacuna é lacuna)
"""
from __future__ import annotations

from dataclasses import asdict

from . import fontes, razao, series
from .calendario import dia_util
from .util import agora, config, gravar_json, hoje, raiz


def tickers_de_interesse() -> list[str]:
    """Posições abertas + ativos citados nas hipóteses (exceto séries de contexto)."""
    est = razao.calcular_estado(razao.carregar_operacoes())
    nomes_serie = set(config("series.toml"))
    ts = set(est.posicoes)
    for h in razao.carregar_hipoteses():
        if h.get("status", "ativa") != "ativa":
            continue
        t = h.get("teste", {})
        cand = list(t.get("ativos", [])) + [t.get("ativo"), t.get("benchmark"), t.get("driver")]
        cand += [t.get("condicao", {}).get("serie")]
        ts |= {c for c in cand if c and c not in nomes_serie}
    return sorted(ts)


def ler_tudo(tol_pct: float) -> dict[str, fontes.Leitura]:
    out: dict[str, fontes.Leitura] = {}
    for t in tickers_de_interesse():
        out[t] = fontes.consolidar(t, fontes.obtencoes_ativo(t), tol_pct)
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
        fech = series.carregar()
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
                gravados[s] = l.preco
        if gravados:
            fech.setdefault(dia.isoformat(), {}).update(gravados)
            gravar_json(series.caminho(), fech)
        log["fechamento"] = {"gravados": gravados, "lacunas": lacunas}
    gravar_json(raiz() / "data" / "state" / f"coleta_{dia.isoformat()}_{modo}.json", log)
    resumo = {s: (l.status, l.preco) for s, l in leituras.items()}
    print(f"coleta {modo} {dia}: {resumo}")
    if modo == "fechamento":
        print("lacunas:", log["fechamento"]["lacunas"] or "nenhuma")
    return log
