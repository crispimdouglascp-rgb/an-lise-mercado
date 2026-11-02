"""Séries de mercado em SQLite (data/mercado.db). Decisão D-1: livros em JSONL, séries em banco.

Cada valor guarda fonte, status da conferência, horário de captura e natureza.
Fechamento gravado não é sobrescrito: uma segunda gravação divergente é recusada e
reportada como conflito (o histórico não muda em silêncio).

A interface para o resto do código continua sendo um dicionário {data ISO: {símbolo: valor}}.
"""
from __future__ import annotations

import sqlite3
import statistics
from contextlib import closing

from .util import agora, ler_json, raiz

ESQUEMA = """
CREATE TABLE IF NOT EXISTS precos_diarios (
  simbolo TEXT NOT NULL, data TEXT NOT NULL, valor REAL NOT NULL,
  fonte TEXT, status TEXT, capturado_em TEXT, natureza TEXT DEFAULT 'real',
  PRIMARY KEY (simbolo, data));
CREATE INDEX IF NOT EXISTS ix_precos_data ON precos_diarios(data);
"""

_cache: dict = {}


def caminho():
    return raiz() / "data" / "mercado.db"


def conectar() -> sqlite3.Connection:
    p = caminho()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.executescript(ESQUEMA)
    return con


def _invalidar() -> None:
    _cache.clear()


def carregar() -> dict[str, dict[str, float]]:
    p = caminho()
    if not p.exists():
        return {}
    chave = (str(p), p.stat().st_mtime_ns)
    if chave in _cache:
        return {d: dict(v) for d, v in _cache[chave].items()}
    out: dict[str, dict[str, float]] = {}
    with closing(conectar()) as con:
        for s, d, v in con.execute("SELECT simbolo, data, valor FROM precos_diarios"):
            out.setdefault(d, {})[s] = v
    _cache.clear()
    _cache[chave] = out
    return {d: dict(v) for d, v in out.items()}


def detalhes(dia: str) -> dict[str, dict]:
    """Fonte, status e horário de cada valor do dia (para o painel mostrar a origem)."""
    if not caminho().exists():
        return {}
    with closing(conectar()) as con:
        rows = con.execute("SELECT simbolo, valor, fonte, status, capturado_em, natureza FROM precos_diarios "
                           "WHERE data = ?", (dia,)).fetchall()
    return {s: {"valor": v, "fonte": f, "status": st, "capturado_em": c, "natureza": n}
            for s, v, f, st, c, n in rows}


def gravar_fechamentos(dia: str, itens: dict[str, dict], natureza: str = "real") -> dict[str, str]:
    """Grava {símbolo: {valor, fonte, status}}. Retorna conflitos {símbolo: motivo}."""
    conflitos: dict[str, str] = {}
    ts = agora().isoformat()
    with closing(conectar()) as con, con:
        for s, it in itens.items():
            ant = con.execute("SELECT valor FROM precos_diarios WHERE simbolo=? AND data=?", (s, dia)).fetchone()
            if ant is not None:
                if abs(ant[0] - it["valor"]) > 1e-9:
                    conflitos[s] = f"já gravado {ant[0]} em {dia}; nova leitura {it['valor']} recusada"
                continue
            con.execute("INSERT INTO precos_diarios VALUES (?,?,?,?,?,?,?)",
                        (s, dia, float(it["valor"]), it.get("fonte"), it.get("status"), ts,
                         it.get("natureza", natureza)))
    _invalidar()
    return conflitos


def gravar_historico(simbolo: str, valores: dict[str, float], fonte: str, natureza: str = "real") -> int:
    """Backfill: insere só datas ainda ausentes. Retorna quantas entraram."""
    ts = agora().isoformat()
    with closing(conectar()) as con, con:
        antes = con.total_changes
        con.executemany("INSERT OR IGNORE INTO precos_diarios VALUES (?,?,?,?,?,?,?)",
                        [(simbolo, d, float(v), fonte, "historico", ts, natureza) for d, v in valores.items()])
        n = con.total_changes - antes
    _invalidar()
    return n


def importar_json_legado(caminho_json) -> int:
    """Importa o antigo data/fechamentos.json ({data: {símbolo: valor}})."""
    fech = ler_json(caminho_json, {}) or {}
    n = 0
    por_simbolo: dict[str, dict[str, float]] = {}
    for d, vals in fech.items():
        for s, v in vals.items():
            por_simbolo.setdefault(s, {})[d] = v
    for s, vals in por_simbolo.items():
        n += gravar_historico(s, vals, "legado_fechamentos_json")
    return n


# ------------------------------------------------------------------ cálculos sobre o dicionário

def retorno_dia(fech: dict, simbolo: str, dia: str) -> float | None:
    """Retorno % do fechamento de `dia` contra o fechamento anterior disponível do símbolo."""
    if simbolo not in fech.get(dia, {}):
        return None
    anteriores = sorted(d for d in fech if d < dia and simbolo in fech[d])
    if not anteriores:
        return None
    ant = fech[anteriores[-1]][simbolo]
    if not ant:
        return None
    return (fech[dia][simbolo] / ant - 1) * 100


def retorno_entre(fech: dict, simbolo: str, d0: str, d1: str) -> float | None:
    """Retorno % entre o último fechamento até d0 (inclusive) e o fechamento de d1."""
    if simbolo not in fech.get(d1, {}):
        return None
    base = ultimo_fechamento_ate(fech, simbolo, d0)
    return (fech[d1][simbolo] / base - 1) * 100 if base else None


def serie(fech: dict, simbolo: str, ate: str | None = None) -> list[tuple[str, float]]:
    return [(d, fech[d][simbolo]) for d in sorted(fech) if simbolo in fech[d] and (ate is None or d <= ate)]


def retornos(fech: dict, simbolo: str, ate: str | None = None) -> dict[str, float]:
    """{data: retorno diário em fração} contra o fechamento anterior disponível."""
    s = serie(fech, simbolo, ate)
    return {s[i][0]: s[i][1] / s[i - 1][1] - 1 for i in range(1, len(s)) if s[i - 1][1]}


def sigma_pct(fech: dict, simbolo: str, ate: str | None = None, janela: int = 60, minimo: int = 20) -> float | None:
    """Desvio-padrão dos retornos diários (%). None se houver menos que `minimo` retornos."""
    rets = [r * 100 for r in retornos(fech, simbolo, ate).values()][-janela:]
    if len(rets) < minimo:
        return None
    return statistics.pstdev(rets)


def ultimo_fechamento_antes(fech: dict, simbolo: str, dia: str) -> float | None:
    ds = sorted(d for d in fech if d < dia and simbolo in fech[d])
    return fech[ds[-1]][simbolo] if ds else None


def ultimo_fechamento_ate(fech: dict, simbolo: str, dia: str) -> float | None:
    ds = sorted(d for d in fech if d <= dia and simbolo in fech[d])
    return fech[ds[-1]][simbolo] if ds else None


def fx(fech: dict, dia: str) -> dict[str, float]:
    """Câmbio do dia em BRL por unidade da moeda. Só o que foi coletado; nunca estimado."""
    out = {}
    v = fech.get(dia, {}).get("USDBRL")
    if v:
        out["USD"] = v
    return out
