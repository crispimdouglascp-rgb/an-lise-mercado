"""Testes de ponta a ponta: coleta, fechamento, vigilância e retorno ponderado pelo tempo."""
import json
from datetime import datetime

import pytest

from rvlocal import coleta, diario, fontes, notificar, razao, series, vigilancia
from rvlocal.util import BRT, ler_json, ler_jsonl

DIA = "2026-11-03"   # terça, dia útil
DIA2 = "2026-11-04"


def ts(dia, hora=17, minuto=55):
    y, m, d = map(int, dia.split("-"))
    return int(datetime(y, m, d, hora, minuto, tzinfo=BRT).timestamp())


def yahoo(preco, dia, anterior=None):
    ant_dia = "2026-11-03" if dia == DIA2 else "2026-10-30"
    return json.dumps({"chart": {"result": [{
        "meta": {"regularMarketPrice": preco, "regularMarketTime": ts(dia)},
        "timestamp": [ts(ant_dia), ts(dia)],
        "indicators": {"quote": [{"close": [anterior or preco, preco]}]},
    }]}})


def brapi(preco, dia):
    return json.dumps({"results": [{"regularMarketPrice": preco, "regularMarketTime": ts(dia),
                                    "regularMarketPreviousClose": None}]})


def montar_projeto(home):
    (home / "data" / "ativos.json").write_text(json.dumps({
        "PETR4": {"setor": "petroleo", "alvo": 42.0, "stop": 33.0}}))
    (home / "data" / "hipoteses.json").write_text(json.dumps([{
        "id": "H1", "status": "ativa",
        "teste": {"tipo": "segue_driver", "ativo": "PETR4", "driver": "BRENT", "limiar_driver_pct": 1.0}}]))
    (home / "data" / "operacoes.jsonl").write_text("\n".join(json.dumps(o) for o in [
        {"id": "1", "data": DIA, "tipo": "aporte", "valor": 100000.0},
        {"id": "2", "data": DIA, "tipo": "compra", "ativo": "PETR4", "qtd": 1000, "preco": 36.0,
         "tese_id": "H1", "gatilho": "g", "horizonte": "h"},
    ]) + "\n")


def fake_rede(petr, dia, ibov=100000.0, usd=5.0, brent=80.0, petr_brapi=None, ibov_brapi=None):
    petr_brapi = petr if petr_brapi is None else petr_brapi
    ibov_brapi = ibov if ibov_brapi is None else ibov_brapi

    def _f(url, headers=None):
        if "PETR4.SA" in url:
            return yahoo(petr, dia)
        if "quote/PETR4" in url:
            return brapi(petr_brapi, dia)
        if "BVSP" in url and "yahoo" in url:
            return yahoo(ibov, dia)
        if "BVSP" in url:
            return brapi(ibov_brapi, dia)
        if "BRL%3DX" in url:
            return yahoo(usd, dia)
        if "BZ%3DF" in url:
            return yahoo(brent, dia)
        raise fontes.ErroFonte("url inesperada: " + url)
    return _f


@pytest.fixture
def projeto(home, monkeypatch):
    montar_projeto(home)
    enviados = []
    monkeypatch.setattr(notificar, "ENVIAR", lambda t: enviados.append(t) or True)
    monkeypatch.setattr(vigilancia, "ENVIAR", lambda t: enviados.append(t) or True)
    monkeypatch.setattr(diario, "ENVIAR", lambda t: enviados.append(t) or True)
    return home, enviados


def relogio(monkeypatch, dia, hora):
    monkeypatch.setenv("RVLOCAL_AGORA", f"{dia}T{hora}:00-03:00")


def test_fechamento_grava_so_dado_conferido(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.5, DIA))
    log = coleta.coletar("fechamento")
    fech = series.carregar()
    assert fech[DIA]["PETR4"] == 36.5
    assert "USDBRL" in fech[DIA] and "BRENT" in fech[DIA]   # fonte única esperada: ok
    assert log["fechamento"]["lacunas"] == {}


def test_fechamento_com_fontes_divergentes_deixa_lacuna(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.5, DIA, petr_brapi=39.0))
    log = coleta.coletar("fechamento")
    assert "PETR4" not in series.carregar().get(DIA, {})
    assert log["fechamento"]["lacunas"]["PETR4"] == "divergente"


def test_cotacao_de_ontem_nao_vira_fechamento_de_hoje(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA2, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.5, DIA))   # fonte congelada no dia anterior
    log = coleta.coletar("fechamento")
    assert log["fechamento"]["lacunas"].get("PETR4") == "cotacao_defasada"


def test_feriado_e_fim_de_semana_pulam(projeto, monkeypatch):
    for dia in ("2026-11-02", "2026-11-07", "2026-11-08"):   # Finados, sáb, dom
        relogio(monkeypatch, dia, "18:00")
        assert coleta.coletar("fechamento").get("pulado") == "sem pregão"


def test_ciclo_dois_dias_retorno_ponderado_pelo_tempo(projeto, monkeypatch):
    home, enviados = projeto
    # Dia 1: compra a 36, fecha a 36 => retorno do dia 1 indefinido (não há dia anterior)
    relogio(monkeypatch, DIA, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.0, DIA))
    coleta.coletar("fechamento")
    d1 = diario.fechar_dia(DIA, enviar=False)
    assert d1["patrimonio"] == pytest.approx(100000.0)   # 64000 caixa + 1000*36
    assert d1["retorno_dia_pct"] is None

    # Dia 2: aporte de 50 mil no dia; PETR4 sobe 36 -> 37,8 (+5%)
    with (home / "data" / "operacoes.jsonl").open("a") as f:
        f.write(json.dumps({"id": "3", "data": DIA2, "tipo": "aporte", "valor": 50000.0}) + "\n")
    relogio(monkeypatch, DIA2, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(37.8, DIA2))
    coleta.coletar("fechamento")
    d2 = diario.fechar_dia(DIA2, enviar=False)
    assert d2["patrimonio"] == pytest.approx(64000 + 50000 + 37800)
    # R = V_fim / (V_ini + fluxo) - 1 = 151800 / 150000 - 1 = 1,2%: o aporte NÃO infla o retorno
    assert d2["retorno_dia_pct"] == pytest.approx(1.2, abs=1e-6)
    assert d2["retorno_acumulado_pct"] == pytest.approx(1.2, abs=1e-6)
    assert "peso" not in d2 and d2["pesos_pct"]["PETR4"] == pytest.approx(37800 / 151800 * 100, abs=0.01)


def test_dia_incompleto_nao_inventa_retorno(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.0, DIA, petr_brapi=40.0))  # divergente => lacuna
    coleta.coletar("fechamento")
    d = diario.fechar_dia(DIA, enviar=False)
    assert d["patrimonio"] is None and d["lacunas_preco"] == ["PETR4"]
    assert "aviso" in d and d["retorno_dia_pct"] is None


def test_fechar_dia_mede_hipotese_e_grava_arquivo(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.0, DIA, brent=80.0))
    coleta.coletar("fechamento")
    diario.fechar_dia(DIA, enviar=False)
    relogio(monkeypatch, DIA2, "18:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(37.0, DIA2, brent=82.0))   # Brent +2,5%, PETR4 +2,8%
    coleta.coletar("fechamento")
    d = diario.fechar_dia(DIA2, enviar=False)
    assert d["hipoteses"][0]["hoje"]["resultado"] == "acerto"
    assert d["placar_hipoteses"][0]["taxa_acerto_pct"] == 100.0
    assert (home / "data" / "diario" / f"{DIA2}.json").exists()
    assert (home / "data" / "recaps" / f"{DIA2}_numeros.txt").exists()
    assert ler_json(home / "data" / "hipoteses.json")[0]["medicoes"][-1]["resultado"] == "acerto"


def test_vigilancia_stop_dispara_uma_vez_por_dia(projeto, monkeypatch):
    home, enviados = projeto
    relogio(monkeypatch, DIA, "11:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(32.0, DIA))   # abaixo do stop 33
    novos = vigilancia.vigiar(forcar=True)
    assert any(a["tipo"] == "stop" and a["simbolo"] == "PETR4" for a in novos)
    novos2 = vigilancia.vigiar(forcar=True)                       # 10 min depois, mesma condição
    assert [a for a in novos2 if a["tipo"] == "stop"] == []       # sem repetir
    assert len(enviados) == 1
    assert len(ler_jsonl(home / "data" / "state" / f"alertas_{DIA}.jsonl")) >= 1


def test_vigilancia_fonte_divergente_suspende_alertas_de_preco(projeto, monkeypatch):
    home, enviados = projeto
    relogio(monkeypatch, DIA, "11:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(32.0, DIA, petr_brapi=36.0))
    novos = vigilancia.vigiar(forcar=True)
    tipos = {a["tipo"] for a in novos if a["simbolo"] == "PETR4"}
    assert tipos == {"fontes_divergentes"}      # nada de stop com preço duvidoso


def test_vigilancia_fonte_congelada(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA2, "11:00")
    monkeypatch.setattr(fontes, "FETCH", fake_rede(36.0, DIA))   # cotação de ontem, em pregão hoje
    novos = vigilancia.vigiar(forcar=True)
    assert any(a["tipo"] == "fonte_congelada" for a in novos)


def test_vigilancia_fora_da_janela_e_feriado_nao_roda(projeto, monkeypatch):
    home, enviados = projeto
    monkeypatch.setattr(fontes, "FETCH", fake_rede(32.0, DIA))
    relogio(monkeypatch, DIA, "19:30")
    assert vigilancia.vigiar() == []
    relogio(monkeypatch, "2026-11-02", "11:00")   # Finados
    assert vigilancia.vigiar() == []
    assert enviados == []


def test_vigilancia_movimento_usa_sigma_padrao_sem_historico(projeto, monkeypatch):
    home, _ = projeto
    relogio(monkeypatch, DIA, "11:00")
    # anterior = 36,0; preço 37,5 = +4,2% > 2 * 1,8% (sigma padrão)
    monkeypatch.setattr(fontes, "FETCH", fake_rede(37.5, DIA))
    monkeypatch.setattr(fontes, "fetch_brapi", lambda s: fontes.Cotacao(s, 37.5, 36.0, datetime.fromtimestamp(ts(DIA), BRT), "brapi"))
    monkeypatch.setattr(fontes, "fetch_yahoo", lambda s, n=None: fontes.Cotacao(n or s, 37.5, 36.0, datetime.fromtimestamp(ts(DIA), BRT), "yahoo"))
    novos = vigilancia.vigiar(forcar=True)
    assert any(a["tipo"] == "movimento" and a["simbolo"] == "PETR4" for a in novos)
