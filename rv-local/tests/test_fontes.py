import json
from datetime import datetime

import pytest

from rvlocal import fontes
from rvlocal.util import BRT

TS = int(datetime(2026, 11, 3, 15, 0, tzinfo=BRT).timestamp())
TS_ONTEM = int(datetime(2026, 11, 2, 15, 0, tzinfo=BRT).timestamp())


def yahoo_json(preco, anterior=None):
    return json.dumps({"chart": {"result": [{
        "meta": {"regularMarketPrice": preco, "regularMarketTime": TS},
        "timestamp": [TS_ONTEM, TS],
        "indicators": {"quote": [{"close": [anterior or preco, preco]}]},
    }]}})


def brapi_json(preco):
    return json.dumps({"results": [{"regularMarketPrice": preco, "regularMarketTime": TS,
                                    "regularMarketPreviousClose": 35.0}]})


def fake(respostas):
    def _f(url, headers=None):
        for chave, val in respostas.items():
            if chave in url:
                if isinstance(val, Exception):
                    raise val
                return val
        raise fontes.ErroFonte("sem resposta fake para " + url)
    return _f


def test_yahoo_parse_e_fechamento_anterior(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"finance.yahoo": yahoo_json(36.0, 35.0)}))
    c = fontes.fetch_yahoo("PETR4.SA", "PETR4")
    assert c.preco == 36.0 and c.anterior == 35.0 and c.fonte == "yahoo"
    assert c.variacao_pct() == pytest.approx(2.857, abs=1e-3)


def test_duas_fontes_que_batem_dao_ok(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"finance.yahoo": yahoo_json(36.00), "brapi": brapi_json(36.10)}))
    l = fontes.consolidar("PETR4", fontes.obtencoes_ativo("PETR4"), 0.5)
    assert l.status == "ok" and l.preco == 36.00 and l.divergencia_pct < 0.5


def test_fontes_divergentes_nao_viram_media(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"finance.yahoo": yahoo_json(36.0), "brapi": brapi_json(38.0)}))
    l = fontes.consolidar("PETR4", fontes.obtencoes_ativo("PETR4"), 0.5)
    assert l.status == "divergente" and l.preco is None  # lacuna honesta


def test_uma_fonte_cai_vira_fonte_unica_e_registra_erro(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"finance.yahoo": yahoo_json(36.0),
                                               "brapi": fontes.ErroFonte("HTTP 401")}))
    l = fontes.consolidar("PETR4", fontes.obtencoes_ativo("PETR4"), 0.5)
    assert l.status == "fonte_unica" and l.preco == 36.0 and l.erros
    assert not l.aceitavel_no_fechamento  # no fechamento, fonte única inesperada não grava


def test_todas_caem_sem_dado(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({}))
    l = fontes.consolidar("PETR4", fontes.obtencoes_ativo("PETR4"), 0.5)
    assert l.status == "sem_dado" and l.preco is None and len(l.erros) == 2


def test_resposta_malformada_nao_derruba(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"finance.yahoo": "<html>erro</html>", "brapi": "{}"}))
    l = fontes.consolidar("PETR4", fontes.obtencoes_ativo("PETR4"), 0.5)
    assert l.status == "sem_dado"


def test_bcb_dolar(monkeypatch):
    monkeypatch.setattr(fontes, "FETCH", fake({"bcdata": '[{"data":"03/11/2026","valor":"5,4321"}]'}))
    assert fontes.fetch_bcb_dolar() == ("2026-11-03", 5.4321)
