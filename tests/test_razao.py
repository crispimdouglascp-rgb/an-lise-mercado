import json

import pytest

from rvlocal import razao


def ops_base():
    return [
        {"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 100000.0},
        {"id": "2", "data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 30.0, "custos": 10.0},
        {"id": "3", "data": "2026-11-04", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 40.0, "custos": 10.0},
    ]


def test_preco_medio_e_caixa():
    est = razao.calcular_estado(ops_base())
    pos = est.posicoes["PETR4"]
    assert pos.qtd == 200
    assert pos.pm == pytest.approx((3010 + 4010) / 200)
    assert est.caixa == pytest.approx(100000 - 3010 - 4010)


def test_venda_parcial_realiza_lucro_e_mantem_pm():
    ops = ops_base() + [{"id": "4", "data": "2026-11-05", "tipo": "venda", "ativo": "PETR4",
                         "qtd": 100, "preco": 50.0, "custos": 10.0}]
    est = razao.calcular_estado(ops)
    pm = 7020 / 200
    assert est.posicoes["PETR4"].qtd == 100
    assert est.posicoes["PETR4"].pm == pytest.approx(pm)
    assert est.realizado["2026-11-05"] == pytest.approx((50 - pm) * 100 - 10)


def test_venda_acima_da_posicao_e_erro():
    ops = ops_base() + [{"id": "4", "data": "2026-11-05", "tipo": "venda", "ativo": "PETR4", "qtd": 500, "preco": 50.0}]
    with pytest.raises(ValueError):
        razao.calcular_estado(ops)


def test_ate_ignora_futuro():
    est = razao.calcular_estado(ops_base(), ate="2026-11-03")
    assert est.posicoes["PETR4"].qtd == 100


def test_ativo_sem_preco_nao_e_estimado():
    est = razao.calcular_estado(ops_base())
    valor, sem = razao.valor_carteira(est, {})
    assert sem == ["PETR4"]
    assert valor == pytest.approx(est.caixa)  # posição fora, não estimada


def test_validar_pega_problemas(home):
    (home / "data" / "livros" / "instrumentos.json").write_text("{}")
    ops = [{"id": "x", "data": "2026-13-45", "tipo": "compra", "ativo": "ABCD3", "qtd": -1, "preco": 10, "tese_id": "H-X"},
           {"id": "x", "data": "2026-11-03", "tipo": "xyz"}]
    probs = razao.validar(ops)
    texto = " | ".join(probs)
    assert "data inválida" in texto
    assert "positivo" in texto
    assert "não está em data/livros/instrumentos.json" in texto
    assert "H-X não existe" in texto
    assert "id duplicado" in texto
    assert "tipo inválido" in texto


def test_jsonl_com_erro_aponta_linha(home):
    (home / "data" / "livros" / "operacoes.jsonl").write_text('# c\n{"ok": 1}\n{quebrado\n')
    (home / "data" / "livros" / "instrumentos.json").write_text("{}")
    probs = razao.validar()
    assert any("linha 3" in p for p in probs)
