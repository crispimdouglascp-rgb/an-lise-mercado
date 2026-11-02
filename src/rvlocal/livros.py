"""Livros: a fonte da verdade da plataforma. Só se escreve por ACRÉSCIMO.

Regras (governança):
  * linha gravada nunca é editada nem apagada; correção = nova linha;
  * todo registro carrega `natureza` (real | demo | estimativa | hipotese);
  * `verificar_imutabilidade()` compara cada livro com o último commit do git:
    o conteúdo commitado precisa ser PREFIXO do conteúdo atual.

Painel, relatórios e diários são vistas geradas a partir daqui (data/gerado/).
"""
from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from .util import agora, anexar_jsonl, ler_jsonl, p_livro, raiz

NATUREZAS = {"real", "demo", "simulada", "estimativa", "hipotese"}

ARQUIVOS = {
    "operacoes": "operacoes.jsonl",
    "decisoes": "decisoes.jsonl",
    "teses": "teses.jsonl",
    "hipoteses": "hipoteses.jsonl",
    "placar_hipoteses": "placar_hipoteses.jsonl",
    "eventos": "eventos.jsonl",
    "alertas": "alertas.jsonl",
    "boletins": "boletins.jsonl",
    "heartbeat": "heartbeat.jsonl",
}


def caminho(nome: str):
    return p_livro(ARQUIVOS[nome])


def ler(nome: str) -> list[dict]:
    return ler_jsonl(caminho(nome))


def natureza_padrao() -> str:
    """RVLOCAL_NATUREZA, senão a natureza declarada da carteira (analista e simulação = simulada)."""
    env = os.environ.get("RVLOCAL_NATUREZA")
    if env:
        return env
    from . import carteiras
    return carteiras.info().get("natureza", "real")


def anexar(nome: str, registro: dict[str, Any]) -> dict:
    reg = dict(registro)
    reg.setdefault("natureza", natureza_padrao())
    if reg["natureza"] not in NATUREZAS:
        raise ValueError(f"natureza inválida {reg['natureza']!r} (use {sorted(NATUREZAS)})")
    anexar_jsonl(caminho(nome), reg)
    return reg


def proximo_id(nome: str, prefixo: str, dia: str) -> str:
    base = f"{prefixo}-{dia}-"
    n = sum(1 for r in ler(nome) if str(r.get("id", "")).startswith(base))
    return f"{base}{n + 1:03d}"


def validar_naturezas() -> list[str]:
    probs = []
    for nome in ARQUIVOS:
        try:
            regs = ler(nome)
        except ValueError as e:
            probs.append(str(e))
            continue
        for i, r in enumerate(regs, 1):
            if r.get("natureza", "real") not in NATUREZAS:
                probs.append(f"{ARQUIVOS[nome]} registro {i}: natureza inválida {r.get('natureza')!r}")
    return probs


def verificar_imutabilidade() -> list[str]:
    """Falha se alguma linha já commitada de um livro foi alterada ou removida."""
    rz = raiz()
    try:
        subprocess.run(["git", "-C", str(rz), "rev-parse", "HEAD"], capture_output=True, check=True)
        topo = Path(subprocess.run(["git", "-C", str(rz), "rev-parse", "--show-toplevel"], capture_output=True,
                                   check=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return []  # fora de um repositório git: nada a comparar
    probs = []
    for arq in ARQUIVOS.values():
        atual_p = p_livro(arq)
        try:
            rel = atual_p.resolve().relative_to(topo.resolve()).as_posix()
        except ValueError:
            continue
        r = subprocess.run(["git", "-C", str(topo), "show", f"HEAD:{rel}"], capture_output=True)
        if r.returncode != 0:
            continue  # livro ainda não commitado
        antigo = r.stdout
        atual = atual_p.read_bytes() if atual_p.exists() else b""
        if not atual.startswith(antigo):
            probs.append(f"{rel}: conteúdo já commitado foi ALTERADO ou removido (livro é só por acréscimo)")
    return probs


# ------------------------------------------------------------------ heartbeat

@contextmanager
def rotina(nome: str) -> Iterator[dict]:
    """Registra início, fim e status de cada rotina. Rotina ausente vira alerta na cobrança."""
    info: dict = {"rotina": nome, "inicio": agora().isoformat(), "data": agora().date().isoformat()}
    try:
        yield info
        info["status"] = info.get("status", "ok")
    except Exception as e:
        info["status"] = "erro"
        info["erro"] = f"{type(e).__name__}: {e}"[:300]
        raise
    finally:
        info["fim"] = agora().isoformat()
        anexar("heartbeat", info)


def rodou(nome: str, dia: date) -> bool:
    return any(h.get("rotina") == nome and h.get("data") == dia.isoformat() and h.get("status") == "ok"
               for h in ler("heartbeat"))
