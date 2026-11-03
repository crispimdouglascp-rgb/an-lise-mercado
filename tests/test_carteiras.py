"""Várias carteiras: isolamento dos livros, universo e preços compartilhados, regras por carteira,
rebalanceamento para pesos-alvo, histórico e reprocessamento."""
import json

import pytest

from rvlocal import carteiras, cli, fontes, instrumentos, livros, razao, series, simulacao
from rvlocal.util import config, usar_carteira

CAD = {"AAA3": {"setor": "a"}, "BBB4": {"setor": "b"}, "USX": {"classe": "acao_ext", "moeda": "USD", "pais": "US"}}
DIAS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]


@pytest.fixture
def base(home):
    (home / "data" / "livros" / "instrumentos.json").write_text(json.dumps(CAD))
    for s, vals in {"AAA3": [10.0, 11.0, 12.0, 12.0], "BBB4": [20.0, 20.0, 19.0, 21.0],
                    "USX": [100.0, 101.0, 102.0, 103.0], "USDBRL": [5.0, 5.0, 5.1, 5.1],
                    "IBOV": [100.0, 101.0, 101.0, 102.0], "SPX": [10.0, 10.0, 10.1, 10.2]}.items():
        series.gravar_historico(s, dict(zip(DIAS, vals)), "teste")
    return home


def test_criar_carteira_e_natureza_pelo_tipo(base):
    c = carteiras.criar("analista-x", "Casa X", "analista", fonte="Casa X")
    assert c["natureza"] == "simulada" and carteiras.ids() == ["principal", "analista-x"]
    with usar_carteira("analista-x"):
        assert livros.natureza_padrao() == "simulada"
    with pytest.raises(ValueError):
        carteiras.criar("principal", "x", "propria")
    with pytest.raises(ValueError, match="LGPD"):
        carteiras.criar("cliente-1", "João, CPF 123.456.789-00", "cliente")


def test_livros_isolados_universo_e_precos_compartilhados(base):
    carteiras.criar("teste", "Teste", "simulacao")
    with usar_carteira("teste"):
        livros.anexar("operacoes", {"id": "1", "data": DIAS[0], "tipo": "aporte", "valor": 1000.0})
        assert set(instrumentos.carregar()) == set(CAD)          # universo compartilhado
        assert series.carregar()[DIAS[0]]["AAA3"] == 10.0         # preços compartilhados
    assert livros.ler("operacoes") == []                          # a principal não vê
    assert (base / "carteiras" / "teste" / "data" / "livros" / "operacoes.jsonl").read_text()


def test_regras_proprias_da_carteira_com_fallback(base):
    carteiras.criar("cli-1", "Cliente 1", "cliente")
    cfg = base / "carteiras" / "cli-1" / "config"
    cfg.mkdir()
    (cfg / "regras.toml").write_text((base / "config" / "regras.toml").read_text()
                                     .replace("teto_posicao_pct = 25", "teto_posicao_pct = 40"))
    with usar_carteira("cli-1"):
        assert config("regras.toml")["carteira"]["teto_posicao_pct"] == 40
        assert "limites" in config("risco.toml")                  # sem arquivo próprio: usa o da base
    assert config("regras.toml")["carteira"]["teto_posicao_pct"] == 25


def test_rebalancear_para_pesos_alvo_com_exterior(base):
    carteiras.criar("rec", "Recomendada", "analista")
    with usar_carteira("rec"):
        r = simulacao.rebalancear({"AAA3": 50, "USX": 40}, DIAS[0], capital=10000.0, fonte="Casa X")
        est = razao.calcular_estado(razao.carregar_operacoes())
        assert est.posicoes["AAA3"].qtd == 500                     # 5.000 / 10
        assert est.posicoes["USX"].qtd == 8                        # 4.000 / (100 × 5)
        assert est.caixa_moeda["USD"] >= 0 and est.caixa >= 0      # câmbio arredondado para cima
        assert razao.validar() == []
        d = livros.ler("decisoes")[-1]
        assert d["tipo"] == "rebalanceamento" and d["pesos_alvo"] == {"AAA3": 50, "USX": 40}
        assert all(o.get("decisao_id") == r["decisao_id"] for o in livros.ler("operacoes") if o["tipo"] == "compra")
        # novo mês: sai de USX, entra em BBB4
        simulacao.rebalancear({"AAA3": 50, "BBB4": 40}, DIAS[2])
        est = razao.calcular_estado(razao.carregar_operacoes())
        assert "USX" not in est.posicoes and est.posicoes["BBB4"].qtd > 0


def test_rebalancear_recusa_sem_preco_e_nao_deixa_decisao_orfa(base):
    carteiras.criar("rec2", "R2", "analista")
    with usar_carteira("rec2"):
        with pytest.raises(ValueError, match="sem fechamento"):
            simulacao.rebalancear({"AAA3": 50}, "2026-11-10", capital=1000.0)
        with pytest.raises(ValueError, match="cadastre"):
            simulacao.rebalancear({"ZZZ3": 50}, DIAS[0], capital=1000.0)
        assert livros.ler("decisoes") == [] and livros.ler("operacoes") == []


def test_reprocessar_fecha_os_dias_e_emite_boletins(base, monkeypatch):
    carteiras.criar("sim", "Simulação", "simulacao")
    with usar_carteira("sim"):
        simulacao.rebalancear({"AAA3": 60, "BBB4": 30}, DIAS[0], capital=10000.0)
        dias = simulacao.reprocessar(DIAS[0], DIAS[-1])
        assert dias == DIAS
        from rvlocal import boletim, diario
        ds = diario.carregar_diarios()
        assert len(ds) == 4 and ds[-1]["retorno_acumulado_pct"] is not None
        assert boletim.historico("semanal")


def test_historico_carrega_so_datas_ausentes(base, monkeypatch):
    monkeypatch.setattr(fontes, "fetch_yahoo_historico", lambda s, p: {"2026-11-02": 9.0, DIAS[0]: 99.0})
    out = simulacao.carregar_historico(["AAA3"])
    assert out["AAA3"] == 1                                       # só 02/11 entrou
    assert series.carregar()[DIAS[0]]["AAA3"] == 10.0             # nunca sobrescreve


def test_cli_carteira_global_e_ativo(base, capsys):
    assert cli.main(["carteira-nova", "--id", "cli-9", "--nome", "Cliente 9", "--tipo", "cliente"]) == 0
    assert cli.main(["ativo", "WEGE3", "--classe", "acao", "--setor", "industria", "--fatores", "exportadora",
                     "--monitorar"]) == 0
    assert instrumentos.carregar()["WEGE3"]["fatores"] == ["exportadora"]
    assert cli.main(["--carteira", "nao-existe", "carteiras"]) == 1
    assert cli.main(["--carteira", "cli-9", "rebalancear", "--pesos", "AAA3=50", "--data", DIAS[0],
                     "--capital", "5000", "--sim"]) == 0
    with usar_carteira("cli-9"):
        assert razao.calcular_estado(razao.carregar_operacoes()).posicoes["AAA3"].qtd == 250
    assert cli.main(["carteiras"]) == 0
    assert "cli-9" in capsys.readouterr().out


def test_iniciar_base_de_dados_privada(tmp_path):
    destino = tmp_path / "dados"
    d, marcador = carteiras.iniciar_base(destino, marcador=tmp_path / ".rvlocal-home")
    assert (destino / "data" / "livros" / "operacoes.jsonl").exists() and (destino / "config" / "regras.toml").exists()
    assert (tmp_path / ".rvlocal-home").read_text().strip() == str(destino.resolve())
    with pytest.raises(RuntimeError):
        carteiras.iniciar_base(destino, marcador=tmp_path / ".rvlocal-home")


def test_iniciar_copia_a_cola(tmp_path):
    destino = tmp_path / "d2"
    carteiras.iniciar_base(destino, marcador=tmp_path / ".m")
    assert "cola rápida" in (destino / "COLA.md").read_text(encoding="utf-8")


def test_onde_e_data_ontem(base, capsys):
    assert cli.main(["onde"]) == 0
    assert "Dados em uso" in capsys.readouterr().out
    import argparse
    from datetime import timedelta
    from rvlocal.util import hoje
    assert cli._hoje(argparse.Namespace(data="ontem")) == hoje() - timedelta(days=1)
