"""Boletim do gestor: o código calcula, com regras que a IA não pode alterar."""
from datetime import date

import pytest

from rvlocal import boletim
from rvlocal.util import config


def test_letras_reproduzem_os_boletins_da_referencia(home):
    cfg = config("placar.toml")
    assert boletim.letra(1.15, cfg) == "F"
    assert boletim.letra(1.575, cfg) == "D-"
    for n in (1.60, 1.625, 1.675, 1.725):
        assert boletim.letra(n, cfg) == "D"
    assert boletim.letra(2.10, cfg) == "D+"


def test_periodos():
    assert boletim.periodo("semanal", date(2026, 10, 28)) == (date(2026, 10, 26), date(2026, 10, 30))
    assert boletim.periodo("mensal", date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert boletim.periodo("trimestral", date(2026, 11, 3)) == (date(2026, 10, 1), date(2026, 12, 31))


def _calcular_com(monkeypatch, notas: dict):
    """Substitui os critérios por notas fixas para testar a montagem (pesos, tetos, letra)."""
    for k, n in notas.items():
        monkeypatch.setitem(boletim.FUNCOES, k, lambda ctx, n=n: {"nota": n, "evidencias": [f"nota {n}"]})
    monkeypatch.setattr(boletim, "contexto", lambda t, r: {"diarios": [], "pregoes": ["d"] * 5,
                                                           "ini": "2026-10-26", "fim": "2026-10-30"})
    return boletim.calcular("semanal", date(2026, 10, 30))


TUDO_5 = {k: 5.0 for k, _ in boletim.CRITERIOS}


def test_regra_ignorada_zera_aderencia_e_limita_a_nota(home, monkeypatch):
    b = _calcular_com(monkeypatch, {**TUDO_5, "aderencia_regras": 0.0})
    assert b["nota_bruta"] == pytest.approx(4.0)           # 80% dos pesos com 5
    assert b["nota_final"] == 2.0 and b["letra"] == "D+"   # teto: retorno bom não salva regra ignorada
    assert b["tetos_aplicados"]


def test_risco_ruim_limita_mesmo_com_retorno_maximo(home, monkeypatch):
    b = _calcular_com(monkeypatch, {**TUDO_5, "gestao_risco": 1.0})
    assert b["nota_bruta"] == pytest.approx(4.2)
    assert b["nota_final"] == 2.5


def test_reproduz_o_boletim_f_da_referencia(home, monkeypatch):
    # Boletim real #1 da referência: 2,0 · 0,0 · 0,5 · 1,0 · 1,0 · 2,5 · 2,5 = 1,15 (F)
    notas = {"retorno_benchmark": 2.0, "aderencia_regras": 0.0, "gestao_risco": 0.5, "qualidade_decisoes": 1.0,
             "construcao_carteira": 1.0, "execucao_custos_fiscal": 2.5, "realizacao": 2.5}
    b = _calcular_com(monkeypatch, notas)
    assert b["nota_final"] == pytest.approx(1.15) and b["letra"] == "F"


def test_criterio_sem_base_redistribui_o_peso(home, monkeypatch):
    b = _calcular_com(monkeypatch, {**TUDO_5, "realizacao": None, "retorno_benchmark": 0.0})
    assert b["criterios"]["realizacao"]["peso_efetivo"] == 0
    assert b["nota_final"] == pytest.approx(5 * 75 / 90, abs=1e-3)
    assert b["sem_base"] == ["Realização de resultados"]


def test_nota_por_criterio_e_deterministica(home, monkeypatch):
    a = _calcular_com(monkeypatch, {**TUDO_5, "realizacao": 3.3})
    b = _calcular_com(monkeypatch, {**TUDO_5, "realizacao": 3.3})
    assert a == b
