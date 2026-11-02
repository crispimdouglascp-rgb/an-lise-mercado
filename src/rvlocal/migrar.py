"""Migração do formato da fase 1 (data/*.json) para os livros (data/livros/).

  data/operacoes.jsonl   -> data/livros/operacoes.jsonl     (linhas copiadas como estão)
  data/ativos.json       -> data/livros/instrumentos.json   (setor) + 1 ficha de tese por ativo (alvo/stop)
  data/hipoteses.json    -> data/livros/hipoteses.jsonl      (placar antigo congelado em "legado")
  data/decisoes.jsonl    -> data/livros/decisoes.jsonl       (ganham id)
  data/fechamentos.json  -> data/mercado.db

Não apaga os arquivos antigos: renomeia para *.migrado, para você conferir antes de remover.
Recusa rodar se os livros de destino já tiverem conteúdo (não mistura históricos).
"""
from __future__ import annotations

import json

from . import livros, series
from .util import gravar_json, ler_json, ler_jsonl, p_livro, raiz


def migrar(natureza: str = "real") -> list[str]:
    d = raiz() / "data"
    log: list[str] = []
    destinos = [p_livro(a) for a in ("operacoes.jsonl", "hipoteses.jsonl", "decisoes.jsonl", "teses.jsonl")]
    if any(p.exists() and p.read_text().strip() for p in destinos):
        raise RuntimeError("os livros de destino já têm conteúdo; migração recusada para não misturar históricos")

    def marcar(r: dict) -> dict:
        return {**r, "natureza": r.get("natureza", natureza)}

    ops = d / "operacoes.jsonl"
    if ops.exists():
        for o in ler_jsonl(ops):
            livros.anexar("operacoes", marcar(o))
        log.append(f"operações: {len(ler_jsonl(ops))}")
        ops.rename(ops.with_suffix(".jsonl.migrado"))

    at = d / "ativos.json"
    if at.exists():
        ativos = ler_json(at, {}) or {}
        cad = {t: {"classe": "acao", "moeda": "BRL", "pais": "BR", "setor": v.get("setor", "sem setor")}
               for t, v in ativos.items()}
        gravar_json(p_livro("instrumentos.json"), cad)
        for t, v in ativos.items():
            if v.get("alvo") is not None or v.get("stop") is not None:
                livros.anexar("teses", marcar({
                    "tese_id": f"T-{t}", "versao": 1, "data": "2000-01-01", "ativo": t,
                    "titulo": f"{t} (migrada da fase 1)", "tese": "Migrada de ativos.json: complete a ficha.",
                    "alvo": v.get("alvo"), "stop": v.get("stop"), "hipotese_ligada": v.get("tese_id"),
                    "origem": "usuario"}))
        log.append(f"instrumentos: {len(cad)}")
        at.rename(at.with_suffix(".json.migrado"))

    hp = d / "hipoteses.json"
    if hp.exists():
        hs = ler_json(hp, []) or []
        for h in hs:
            med = [m for m in h.get("medicoes", []) if m["resultado"] in {"acerto", "erro"}]
            reg = {k: v for k, v in h.items() if k not in {"medicoes", "criada_em", "arquivar_apos_falhas_consecutivas"}}
            reg.update(formulada_em=h.get("criada_em", "2000-01-01"), origem=h.get("origem", "usuario"),
                       limiar_pp=0.75, min_gates=8,
                       legado={"acertos": sum(1 for m in med if m["resultado"] == "acerto"),
                               "erros": sum(1 for m in med if m["resultado"] == "erro"),
                               "nota": "placar da fase 1 (sem limiar), congelado; não entra na curva"})
            livros.anexar("hipoteses", marcar(reg))
        log.append(f"hipóteses: {len(hs)}")
        hp.rename(hp.with_suffix(".json.migrado"))

    dc = d / "decisoes.jsonl"
    if dc.exists():
        for i, x in enumerate(ler_jsonl(dc), 1):
            livros.anexar("decisoes", marcar({"id": f"DEC-legado-{i:03d}", **x}))
        dc.rename(dc.with_suffix(".jsonl.migrado"))
        log.append("decisões migradas")

    fj = d / "fechamentos.json"
    if fj.exists():
        n = series.importar_json_legado(fj)
        fj.rename(fj.with_suffix(".json.migrado"))
        log.append(f"fechamentos: {n} valores no mercado.db")
    return log


if __name__ == "__main__":
    print(json.dumps(migrar(), ensure_ascii=False, indent=2))
