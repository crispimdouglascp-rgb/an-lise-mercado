"""Utilidades: caminhos, JSON, datas em BRT e formatação pt-BR."""
from __future__ import annotations

import json
import os
import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BRT = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019


_CARTEIRA: ContextVar[str | None] = ContextVar("rvlocal_carteira", default=None)
CARTEIRA_PADRAO = "principal"


def raiz_projeto() -> Path:
    """Pasta do código (config padrão, prompts, exemplos)."""
    return Path(__file__).resolve().parents[2]


def raiz_base() -> Path:
    """Pasta de DADOS: mercado.db, cadastro de ativos, carteira principal e carteiras/.

    Ordem: RVLOCAL_HOME; o arquivo .rvlocal-home na pasta do código (escrito por
    `rvlocal iniciar`); a própria pasta do código.
    """
    env = os.environ.get("RVLOCAL_HOME")
    if env:
        return Path(env).expanduser()
    marcador = raiz_projeto() / ".rvlocal-home"
    if marcador.exists():
        destino = marcador.read_text(encoding="utf-8").strip()
        if destino:
            return Path(destino).expanduser()
    return raiz_projeto()


def carteira_atual() -> str:
    return _CARTEIRA.get() or os.environ.get("RVLOCAL_CARTEIRA") or CARTEIRA_PADRAO


def raiz() -> Path:
    """Pasta da carteira atual. A principal é a própria base; as outras ficam em carteiras/<id>/."""
    c = carteira_atual()
    return raiz_base() if c == CARTEIRA_PADRAO else raiz_base() / "carteiras" / c


@contextmanager
def usar_carteira(carteira: str | None):
    tok = _CARTEIRA.set(carteira or CARTEIRA_PADRAO)
    try:
        yield
    finally:
        _CARTEIRA.reset(tok)


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


def config(nome: str, padrao: dict | None = None) -> dict:
    """Configuração da carteira atual; se ela não tiver o arquivo, a da base; depois a padrão do código."""
    for pasta in (raiz(), raiz_base(), raiz_projeto()):
        caminho = pasta / "config" / nome
        if caminho.exists():
            return ler_toml(caminho)
    if padrao is not None:
        return padrao
    raise FileNotFoundError(f"config/{nome} não encontrado")


def p_livro(nome: str) -> Path:
    """Livros: fonte da verdade, só por acréscimo (data/livros/)."""
    return raiz() / "data" / "livros" / nome


def p_gerado(*partes: str) -> Path:
    """Vistas geradas por código: podem ser apagadas e refeitas (data/gerado/)."""
    return raiz() / "data" / "gerado" / Path(*partes)


def gravar_texto(caminho: Path, texto: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(caminho)


def brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {s}"


def pct(v: float, casas: int = 2, sinal: bool = False) -> str:
    s = f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}"
    return s.replace(".", ",") + "%"
