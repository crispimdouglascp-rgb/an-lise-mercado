"""Utilidades: caminhos, JSON, datas em BRT e formatação pt-BR."""
from __future__ import annotations

import json
import os
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BRT = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019


def raiz() -> Path:
    """Raiz do projeto. Pode ser sobrescrita com RVLOCAL_HOME (usado nos testes)."""
    env = os.environ.get("RVLOCAL_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def agora() -> datetime:
    """Hora atual em BRT. RVLOCAL_AGORA (ISO) permite fixar o relógio nos testes."""
    fixo = os.environ.get("RVLOCAL_AGORA")
    if fixo:
        d = datetime.fromisoformat(fixo)
        return d if d.tzinfo else d.replace(tzinfo=BRT)
    return datetime.now(BRT)


def hoje() -> date:
    return agora().date()


def ler_json(caminho: Path, padrao: Any = None) -> Any:
    if not caminho.exists():
        return padrao
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(caminho)  # escrita atômica


def ler_jsonl(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    linhas = []
    with caminho.open(encoding="utf-8") as f:
        for n, linha in enumerate(f, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                linhas.append(json.loads(linha))
            except json.JSONDecodeError as e:
                raise ValueError(f"{caminho.name} linha {n}: JSON inválido ({e})") from e
    return linhas


def anexar_jsonl(caminho: Path, registro: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")


def ler_toml(caminho: Path) -> dict:
    with caminho.open("rb") as f:
        return tomllib.load(f)


def config(nome: str) -> dict:
    return ler_toml(raiz() / "config" / nome)


def brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {s}"


def pct(v: float, casas: int = 2, sinal: bool = False) -> str:
    s = f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}"
    return s.replace(".", ",") + "%"
