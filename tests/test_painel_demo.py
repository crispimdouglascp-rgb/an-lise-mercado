"""Fumaça de ponta a ponta: gera a base demo pelo código de produção e renderiza todas as telas."""
import json

import pytest

from rvlocal import boletim, demo, livros, mesa

pytest.importorskip("fastapi")
pytest.importorskip("jinja2")


@pytest.fixture(scope="module")
def base_demo(tmp_path_factory):
    import os
    destino = tmp_path_factory.mktemp("demo") / "demo"
    antes = os.environ.get("RVLOCAL_HOME")
    os.environ.pop("RVLOCAL_HOME", None)
    demo.gerar(str(destino))
    os.environ["RVLOCAL_HOME"] = str(destino)
    yield destino
    if antes is None:
        os.environ.pop("RVLOCAL_HOME", None)
    else:
        os.environ["RVLOCAL_HOME"] = antes


def test_demo_e_toda_marcada_como_demo(base_demo):
    for nome in ("operacoes", "decisoes", "teses", "hipoteses", "boletins"):
        regs = livros.ler(nome)
        assert regs and all(r["natureza"] == "demo" for r in regs), nome


def test_demo_mostra_as_falhas_roteirizadas(base_demo):
    notas = [b["nota_final"] for b in boletim.historico("semanal")]
    assert min(notas) <= 2.0 < max(notas)                 # houve semana com regra ignorada (teto 2,0)
    abertas = [a for a in mesa.estado("2026-10-30") if a["status"] in {"aberto", "vencido"}]
    assert any(a["regra"] == "teto_posicao" and a["ativo"] == "INDX11" for a in abertas)


def test_todas_as_telas_renderizam(base_demo):
    from fastapi.testclient import TestClient
    from rvlocal.painel import app as A
    c = TestClient(A.criar_app())
    for nome, rota, _ in A.TELAS:
        r = c.get("/" + rota)
        assert r.status_code == 200, nome
        assert "DADOS DEMO" in r.text
    assert c.get("/opcoes").status_code == 200


def test_registrar_decisao_pelo_painel_grava_no_livro(base_demo):
    from fastapi.testclient import TestClient
    from rvlocal.painel import app as A
    alvo = next(a for a in mesa.estado("2026-10-30") if a["status"] in {"aberto", "vencido"})
    n = len(livros.ler("decisoes"))
    r = TestClient(A.criar_app()).post("/decisao", data={
        "alerta_id": alvo["id"], "ativo": alvo.get("ativo") or "", "tipo": "revisao", "decisao": "reduzir",
        "motivo": "teste", "data": "2026-10-30"}, follow_redirects=False)
    assert r.status_code == 303
    assert livros.ler("decisoes")[-1]["alerta_id"] == alvo["id"] and len(livros.ler("decisoes")) == n + 1
    assert next(a for a in mesa.estado("2026-10-30") if a["id"] == alvo["id"])["status"] == "resolvido"


def test_exportacao_estatica(base_demo, tmp_path):
    from rvlocal.painel import app as A
    arquivos = A.exportar(str(tmp_path / "html"))
    assert len(arquivos) == len(A.TELAS)
    assert 'action="/decisao"' not in (tmp_path / "html" / "monitoramento.html").read_text()
