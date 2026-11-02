from datetime import date

from rvlocal import razao
from rvlocal import regras as R
from rvlocal.util import config

ATIVOS = {
    "PETR4": {"setor": "petroleo", "alvo": 42.0, "stop": 33.0},
    "VALE3": {"setor": "mineracao", "alvo": 80.0, "stop": 55.0},
}


def estado(ops):
    return razao.calcular_estado(ops)


def tipos(vs):
    return {v.regra for v in vs}


def test_teto_posicao_e_setor(home):
    regras = config("regras.toml")
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 100000},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 2000, "preco": 30.0}]  # 60%
    est = estado(ops)
    vs = R.checar(est, {"PETR4": 30.0}, ATIVOS, regras, ops, [], date(2026, 11, 3))
    assert "teto_posicao" in tipos(vs)
    assert "teto_setor" in tipos(vs)


def test_stop_sem_decisao_e_com_decisao(home):
    regras = config("regras.toml")
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 100000},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 35.0,
            "tese_id": "T", "gatilho": "g", "horizonte": "h"}]
    est = estado(ops)
    vs = R.checar(est, {"PETR4": 32.0}, ATIVOS, regras, ops, [], date(2026, 11, 4))
    assert "stop_sem_decisao" in tipos(vs)
    dec = [{"data": "2026-11-04", "tipo": "stop", "ativo": "PETR4", "decisao": "manter", "motivo": "tese intacta"}]
    vs = R.checar(est, {"PETR4": 32.0}, ATIVOS, regras, ops, dec, date(2026, 11, 4))
    assert "stop_sem_decisao" not in tipos(vs)


def test_realizacao_a_90pct_do_alvo(home):
    regras = config("regras.toml")
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 100000},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 35.0,
            "tese_id": "T", "gatilho": "g", "horizonte": "h"}]
    est = estado(ops)
    vs = R.checar(est, {"PETR4": 38.5}, ATIVOS, regras, ops, [], date(2026, 11, 4))  # 38.5 >= 0.9*42=37.8
    assert "realizacao_sem_decisao" in tipos(vs)
    vs = R.checar(est, {"PETR4": 37.0}, ATIVOS, regras, ops, [], date(2026, 11, 4))
    assert "realizacao_sem_decisao" not in tipos(vs)


def test_operacao_sem_tese_so_conta_na_semana_corrente(home):
    regras = config("regras.toml")
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 100000},
           {"data": "2026-10-20", "tipo": "compra", "ativo": "PETR4", "qtd": 10, "preco": 35.0},   # semana passada
           {"data": "2026-11-04", "tipo": "compra", "ativo": "VALE3", "qtd": 10, "preco": 60.0, "tese_id": "T"}]
    est = estado(ops)
    vs = R.checar(est, {"PETR4": 35.0, "VALE3": 60.0}, ATIVOS, regras, ops, [], date(2026, 11, 5))
    sem_tese = [v for v in vs if v.regra == "operacao_sem_tese"]
    assert len(sem_tese) == 1 and sem_tese[0].ativo == "VALE3"
    assert "gatilho" in sem_tese[0].detalhe and "horizonte" in sem_tese[0].detalhe


def test_lacuna_de_preco_vira_info_e_nao_quebra(home):
    regras = config("regras.toml")
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 100000},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 35.0,
            "tese_id": "T", "gatilho": "g", "horizonte": "h"}]
    est = estado(ops)
    vs = R.checar(est, {}, ATIVOS, regras, ops, [], date(2026, 11, 4))
    assert [v.regra for v in vs] == ["lacuna_preco"]
