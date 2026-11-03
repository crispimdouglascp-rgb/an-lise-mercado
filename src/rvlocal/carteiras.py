"""Várias carteiras na mesma plataforma: a sua, as de clientes e as recomendadas por analistas.

Cada carteira tem os PRÓPRIOS livros (operações, decisões, fichas, hipóteses, mesa, boletins) e
compartilha com as outras o universo de ativos (instrumentos.json) e o banco de preços (mercado.db).

  <base>/                         carteira "principal" (a sua)
  <base>/carteiras/<id>/          as outras, cada uma com data/livros, data/gerado e carteira.toml

Tipos:
  propria     sua carteira real                                  natureza real
  cliente     carteira que você acompanha/monta para um cliente  natureza real (ou simulada, se proposta)
  analista    carteira recomendada de um analista ou casa        natureza simulada
  simulacao   teste seu: hipótese de alocação, paper trading     natureza simulada

LGPD: cliente é identificado por CÓDIGO (ex.: cliente-017). Não grave nome, CPF, e-mail ou
telefone em carteira.toml nem nos livros; o vínculo código → pessoa fica fora da plataforma.
"""
from __future__ import annotations

import re
import shutil

from .util import CARTEIRA_PADRAO, carteira_atual, ler_toml, raiz_base

TIPOS = {"propria": "real", "cliente": "real", "analista": "simulada", "simulacao": "simulada"}
ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
LIVROS = ["operacoes", "decisoes", "teses", "hipoteses", "placar_hipoteses", "eventos", "alertas",
          "boletins", "heartbeat"]
PROIBIDOS = ("cpf", "email", "e-mail", "telefone", "celular", "endereco", "rg")


def pasta(cid: str):
    return raiz_base() if cid == CARTEIRA_PADRAO else raiz_base() / "carteiras" / cid


def _padrao_principal() -> dict:
    return {"id": CARTEIRA_PADRAO, "nome": "Carteira principal", "tipo": "propria", "natureza": "real",
            "benchmark": "IBOV"}


def info(cid: str | None = None) -> dict:
    cid = cid or carteira_atual()
    meta = pasta(cid) / "carteira.toml"
    dados = ler_toml(meta) if meta.exists() else {}
    base = _padrao_principal() if cid == CARTEIRA_PADRAO else {"id": cid, "nome": cid, "tipo": "simulacao"}
    out = {**base, **dados, "id": cid}
    out.setdefault("natureza", TIPOS.get(out["tipo"], "real"))
    return out


def listar() -> list[dict]:
    out = [info(CARTEIRA_PADRAO)]
    d = raiz_base() / "carteiras"
    if d.exists():
        out += [info(p.name) for p in sorted(d.iterdir()) if (p / "carteira.toml").exists()]
    return out


def ids() -> list[str]:
    return [c["id"] for c in listar()]


def existe(cid: str) -> bool:
    return cid == CARTEIRA_PADRAO or (pasta(cid) / "carteira.toml").exists()


def _toml(dados: dict) -> str:
    def v(x):
        if isinstance(x, bool):
            return "true" if x else "false"
        if isinstance(x, (int, float)):
            return str(x)
        return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'
    return "".join(f"{k} = {v(x)}\n" for k, x in dados.items() if x is not None)


def criar(cid: str, nome: str, tipo: str, benchmark: str = "IBOV", fonte: str | None = None,
          descricao: str | None = None, natureza: str | None = None) -> dict:
    if not ID_VALIDO.match(cid) or cid == CARTEIRA_PADRAO:
        raise ValueError("id da carteira: minúsculas, números, - ou _ (até 40), diferente de 'principal'")
    if tipo not in TIPOS:
        raise ValueError(f"tipo deve ser um de {sorted(TIPOS)}")
    if natureza and natureza not in {"real", "simulada", "demo"}:
        raise ValueError("natureza deve ser real, simulada ou demo")
    texto = " ".join(str(x or "") for x in (nome, fonte, descricao)).lower()
    if tipo == "cliente" and (re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", texto) or "@" in texto
                              or any(p in texto for p in PROIBIDOS)):
        raise ValueError("carteira de cliente: use um código (ex.: cliente-017), sem dados pessoais (LGPD)")
    p = pasta(cid)
    if (p / "carteira.toml").exists():
        raise ValueError(f"carteira {cid} já existe")
    (p / "data" / "livros").mkdir(parents=True, exist_ok=True)
    for nome_livro in LIVROS:
        (p / "data" / "livros" / f"{nome_livro}.jsonl").touch()
    meta = {"nome": nome, "tipo": tipo, "natureza": natureza or TIPOS[tipo], "benchmark": benchmark,
            "fonte": fonte, "descricao": descricao}
    (p / "carteira.toml").write_text(
        "# Metadados da carteira. Sem dados pessoais: cliente é identificado só pelo código.\n" + _toml(meta),
        encoding="utf-8")
    return info(cid)


def iniciar_base(destino, marcador=None) -> list[str]:
    """Cria uma pasta de dados fora do repositório de código (para os seus dados reais)."""
    from pathlib import Path
    from .util import raiz_projeto
    d = Path(destino).expanduser().resolve()
    if (d / "data" / "livros").exists():
        raise RuntimeError(f"{d} já tem livros; nada foi alterado")
    (d / "data" / "livros").mkdir(parents=True)
    shutil.copytree(raiz_projeto() / "config", d / "config", dirs_exist_ok=True)
    (d / "data" / "livros" / "instrumentos.json").write_text("{}\n", encoding="utf-8")
    for nome_livro in LIVROS:
        (d / "data" / "livros" / f"{nome_livro}.jsonl").touch()
    (d / "LEIA-ME.md").write_text(
        "# Dados da plataforma RV Local\n\nPasta PRIVADA com os seus livros. Versione num repositório git "
        "PRIVADO (trilha de auditoria e backup):\n\n    git init && git add . && git commit -m 'base'\n\n"
        "Não coloque esta pasta dentro do repositório público do código.\n", encoding="utf-8")
    cola = raiz_projeto() / "COLA.md"
    if cola.exists():
        shutil.copy(cola, d / "COLA.md")
    marcador = Path(marcador) if marcador else raiz_projeto() / ".rvlocal-home"
    marcador.write_text(str(d) + "\n", encoding="utf-8")
    return [str(d), str(marcador)]
