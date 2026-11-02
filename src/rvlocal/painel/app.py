"""Painel web (FastAPI + Jinja2). Servidor local: python -m rvlocal painel.

O painel só ESCREVE em um lugar: o livro de decisões, quando você registra uma decisão pela mesa.
Nenhuma ordem é enviada a lugar nenhum. A exportação estática gera as telas em HTML puro.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import dados
from .graficos import num

AQUI = Path(__file__).parent

TELAS = [
    ("dashboard", "", "Capa"),
    ("carteira", "carteira", "Carteira"),
    ("posicoes", "posicoes", "Posições"),
    ("encerradas", "encerradas", "Encerradas"),
    ("teses", "teses", "Teses"),
    ("hipoteses", "hipoteses", "Hipóteses"),
    ("monitoramento", "monitoramento", "Mesa e monitoramento"),
    ("risco", "risco", "Risco"),
    ("auditoria", "auditoria", "Auditoria"),
    ("relatorios", "relatorios", "Boletins e relatórios"),
]
CICLO3 = [("fundamentalista", "Valuation"), ("quant", "Quantitativa"), ("opcoes", "Opções"), ("backtest", "Backtesting")]

FONTES = {"dashboard": dados.dashboard, "carteira": dados.carteira, "posicoes": dados.posicoes,
          "encerradas": dados.encerradas, "teses": dados.fichas, "hipoteses": dados.hipoteses_tela,
          "monitoramento": dados.monitoramento, "risco": dados.risco_tela, "auditoria": dados.auditoria,
          "relatorios": dados.relatorios}


def _brl(v, casas=2):
    if v is None:
        return "—"
    return ("−" if v < 0 else "") + "R$ " + num(abs(v), casas)


def _pct(v, casas=2, sinal=True):
    if v is None:
        return "—"
    s = num(abs(v), casas)
    return (("+" if v > 0 else "−" if v < 0 else "") if sinal else ("−" if v < 0 else "")) + s + "%"


def _data(d):
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else (d or "—")


def _cls(v):
    return "" if v is None else ("pos" if v > 0 else "neg" if v < 0 else "")


def ambiente(estatico: bool = False) -> Environment:
    env = Environment(loader=FileSystemLoader(AQUI / "templates"), autoescape=select_autoescape(["html"]))
    env.filters.update(brl=_brl, pct=_pct, num=lambda v, c=2: "—" if v is None else num(v, c), data=_data, cls=_cls)

    def link(nome: str, extra: str = "") -> str:
        rota = dict((n, r) for n, r, _ in TELAS).get(nome, nome)
        if estatico:
            return (rota or "index") + ".html"
        return "/" + rota + extra

    from .. import boletim as _b
    env.globals.update(link=link, TELAS=TELAS, CICLO3=CICLO3, estatico=estatico,
                       ORDEM=[k for k, _ in _b.CRITERIOS],
                       css=(AQUI / "static" / "painel.css").read_text(encoding="utf-8"))
    return env


def render(nome: str, estatico: bool = False, **kw) -> str:
    env = ambiente(estatico)
    ctx = FONTES[nome](**kw) if nome in FONTES else dados.comum()
    return env.get_template(f"{nome}.html").render(tela=nome, **ctx)


def criar_app():
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, RedirectResponse

    app = FastAPI(title="RV Local", docs_url=None, redoc_url=None)

    def _tela(nome: str):
        if nome == "relatorios":
            def handler(b: str | None = None):
                return HTMLResponse(render(nome, boletim_id=b))
        else:
            def handler():
                return HTMLResponse(render(nome))
        return handler

    def _ciclo3(nome: str):
        def handler():
            return HTMLResponse(ambiente().get_template("ciclo3.html").render(tela=nome, nome=nome, **dados.comum()))
        return handler

    for nome, rota, _ in TELAS:
        app.add_api_route("/" + rota, _tela(nome), methods=["GET"], name=nome)
    for nome, _ in CICLO3:
        app.add_api_route("/" + nome, _ciclo3(nome), methods=["GET"], name=nome)

    @app.post("/decisao")
    def registrar_decisao(alerta_id: str = Form(""), ativo: str = Form(""), tipo: str = Form(...),
                          decisao: str = Form(...), motivo: str = Form(...), nova_invalidacao: str = Form(""),
                          data: str = Form(...)):
        from .. import decisoes
        d = {"data": data, "tipo": tipo, "ativo": ativo or None, "decisao": decisao, "motivo": motivo,
             "origem": "usuario", "canal": "painel"}
        if alerta_id:
            d["alerta_id"] = alerta_id
        if nova_invalidacao:
            d["nova_invalidacao"] = nova_invalidacao
        decisoes.registrar(d)
        return RedirectResponse("/monitoramento?ok=1", status_code=303)

    return app


def exportar(pasta: str) -> list[Path]:
    """Gera todas as telas em HTML estático (sem formulários), para abrir no celular ou arquivar."""
    dest = Path(pasta)
    dest.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome, rota, _ in TELAS:
        p = dest / f"{rota or 'index'}.html"
        p.write_text(render(nome, estatico=True), encoding="utf-8")
        feitos.append(p)
    return feitos
