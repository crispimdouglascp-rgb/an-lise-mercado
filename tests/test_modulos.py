"""Módulos novos: multi-moeda, teses, decisões, mesa, risco, fiscal, migração, operar."""
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from rvlocal import (cli, decisoes, desempenho, fiscal, instrumentos, livros, mesa, migrar, razao, risco,
                     series, teses)

CAD = {"PETR4": {"setor": "petroleo", "fatores": ["commodities"]},
       "VOO": {"classe": "etf_ext", "moeda": "USD", "pais": "US", "setor": "indice_eua"}}


def _cad(home, cad=CAD):
    (home / "data" / "livros" / "instrumentos.json").write_text(json.dumps(cad))


# ------------------------------------------------------------------ multi-moeda
def test_posicao_em_dolar_usa_cambio_e_lacuna_sem_cambio():
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 10000.0},
           {"data": "2026-11-03", "tipo": "cambio", "de": "BRL", "para": "USD", "valor_de": 5000.0, "valor_para": 1000.0},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "VOO", "qtd": 2, "preco": 450.0, "moeda": "USD"}]
    est = razao.calcular_estado(ops)
    assert est.caixa == 5000.0 and est.caixa_moeda["USD"] == pytest.approx(100.0)
    assert est.fluxos == {"2026-11-03": 10000.0}                       # câmbio não é fluxo
    v, lac = razao.valor_carteira(est, {"VOO": 460.0}, {"USD": 5.0})
    assert v == pytest.approx(5000 + 100 * 5 + 2 * 460 * 5)
    v, lac = razao.valor_carteira(est, {"VOO": 460.0}, {})
    assert "VOO" in lac and "câmbio USD" in lac                        # nunca estima câmbio


def test_retorno_de_sleeve_trata_compra_como_entrada():
    assert desempenho.retorno_sleeve(100.0, 210.0, 100.0, 0.0) == pytest.approx(5.0)
    assert desempenho.retorno_sleeve(100.0, 0.0, 0.0, 103.0) == pytest.approx(3.0)


def test_moeda_da_operacao_deve_bater_com_o_instrumento(home):
    _cad(home)
    ops = [{"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 10000.0},
           {"id": "2", "data": "2026-11-03", "tipo": "compra", "ativo": "VOO", "qtd": 1, "preco": 10.0}]
    assert any("moeda BRL difere" in p for p in razao.validar(ops))


# ------------------------------------------------------------------ teses
def test_ficha_versionada_exige_motivo_e_ia_exige_sim(home):
    teses.nova_versao({"ativo": "PETR4", "alvo": 42.0, "stop": 33.0}, "2026-11-03")
    with pytest.raises(ValueError, match="motivo_mudanca"):
        teses.nova_versao({"ativo": "PETR4", "alvo": 45.0}, "2026-11-04")
    teses.nova_versao({"ativo": "PETR4", "alvo": 45.0, "stop": 33.0, "motivo_mudanca": "resultado"}, "2026-11-04")
    assert teses.vigente("PETR4", "2026-11-03")["alvo"] == 42.0
    assert teses.vigente("PETR4")["versao"] == 2
    teses.nova_versao({"ativo": "PETR4", "alvo": 50.0, "origem": "ia", "motivo_mudanca": "IA"}, "2026-11-05")
    assert teses.vigente("PETR4")["alvo"] == 45.0                     # sem o seu sim, não vale
    assert teses.validar() == []


def test_cenarios_devem_somar_um_e_valor_esperado():
    f = {"ativo": "X", "cenarios": {"otimista": {"preco": 60, "prob": 0.25}, "base": {"preco": 50, "prob": 0.5},
                                    "pessimista": {"preco": 30, "prob": 0.25}}}
    assert teses.valor_esperado(f) == pytest.approx(47.5)
    f["cenarios"]["base"]["prob"] = 0.4
    assert any("somam" in p for p in teses.validar_ficha(f))


# ------------------------------------------------------------------ decisões
def test_checklist_sem_tese_vale_zero_e_risco_retorno_calculado():
    chk = decisoes.completar({"tese_id": "T", "justificativa": "j", "preco_entrada": 10.0, "horizonte": "6m",
                              "tamanho_pct": 5, "risco_max_pct": 1, "invalidacao": 9.0, "objetivo": 13.0})
    assert chk["risco_retorno"] == 3.0
    assert decisoes.completude(chk) == (1.0, [])
    assert decisoes.completude({**chk, "tese_id": None})[0] == 0.0


def test_operar_recusa_checklist_incompleto_e_caixa_negativo(home, capsys):
    _cad(home)
    livros.anexar("operacoes", {"id": "a", "data": "2026-11-03", "tipo": "aporte", "valor": 1000.0})
    assert cli.main(["operar", "--tipo", "compra", "--ativo", "PETR4", "--qtd", "10", "--preco", "30",
                     "--data", "2026-11-03", "--sim"]) == 1
    assert "checklist incompleto" in capsys.readouterr().out
    assert cli.main(["operar", "--tipo", "compra", "--ativo", "PETR4", "--qtd", "1000", "--preco", "30",
                     "--data", "2026-11-03", "--sim", "--aceito-incompleto"]) == 1
    assert "negativo" in capsys.readouterr().out
    assert cli.main(["operar", "--tipo", "compra", "--ativo", "PETR4", "--qtd", "10", "--preco", "30",
                     "--data", "2026-11-03", "--sim", "--tese", "T-PETR4", "--justificativa", "j",
                     "--horizonte", "6m", "--tamanho-pct", "30", "--risco-max-pct", "1", "--stop", "27",
                     "--alvo", "40"]) == 0
    op = livros.ler("operacoes")[-1]
    d = livros.ler("decisoes")[-1]
    assert op["decisao_id"] == d["id"] and d["checklist"]["risco_retorno"] == pytest.approx(3.33, abs=0.01)


# ------------------------------------------------------------------ mesa
def test_mesa_abre_resolve_e_vence(home):
    cond = [{"chave": "teto_posicao:PETR4:", "regra": "teto_posicao", "severidade": "alta", "ativo": "PETR4",
             "motivo": "PETR4 pesa 30%"}]
    mesa.sincronizar("2026-11-03", cond, "regras")
    mesa.sincronizar("2026-11-04", cond, "regras")                    # mesma condição: não duplica
    a = mesa.estado("2026-11-04")
    assert len(a) == 1 and a[0]["status"] == "aberto" and a[0]["prazo"] == "2026-11-05"
    assert mesa.estado("2026-11-06")[0]["status"] == "vencido"
    decisoes.registrar({"data": "2026-11-05", "tipo": "reduzir", "ativo": "PETR4", "decisao": "reduzir",
                        "motivo": "teto"})
    r = mesa.estado("2026-11-06")[0]
    assert r["status"] == "resolvido" and r["no_prazo"] is True


# ------------------------------------------------------------------ risco
def test_risco_nao_estima_var_sem_250_pregoes_e_aplica_stress(home):
    _cad(home)
    ops = [{"data": "2026-11-03", "tipo": "aporte", "valor": 10000.0},
           {"data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 100, "preco": 50.0}]
    est = razao.calcular_estado(ops)
    fech = {f"2026-10-{d:02d}": {"PETR4": 50.0 + d / 10, "IBOV": 100.0 + d} for d in range(1, 31)}
    r = risco.calcular(est, {"PETR4": 50.0}, {}, fech, "2026-10-30", [], instrumentos.carregar())
    assert r["var95_1d"]["status"] == "insuficiente" and r["var95_1d"]["minimo"] == 250
    assert r["exposicao_pct"]["fator"]["commodities"] == pytest.approx(50.0)
    assert any(b["regra"] == "banda_fator" for b in r["bandas"])      # 50% > teto de 45%
    s1 = next(s for s in r["stress"] if s["id"] == "S1")
    assert s1["pnl_brl"] == pytest.approx(5000 * -0.15)               # país BR −15%
    assert r["hhi"] == 1.0


# ------------------------------------------------------------------ fiscal
def test_fiscal_isencao_tributacao_compensacao_e_vencimento(home):
    _cad(home)
    ops = [{"data": "2026-07-01", "tipo": "aporte", "valor": 200000.0},
           {"data": "2026-07-01", "tipo": "compra", "ativo": "PETR4", "qtd": 3000, "preco": 10.0},
           {"data": "2026-07-10", "tipo": "venda", "ativo": "PETR4", "qtd": 1000, "preco": 12.0},   # 12 mil: isento
           {"data": "2026-08-10", "tipo": "venda", "ativo": "PETR4", "qtd": 1000, "preco": 9.0},    # prejuízo 1 mil
           {"data": "2026-09-10", "tipo": "venda", "ativo": "PETR4", "qtd": 1000, "preco": 25.0}]   # 25 mil: tributa
    ap = {m["mes"]: m for m in fiscal.apurar(ops, "2026-09")}
    assert ap["2026-07"]["darf"] == 0 and ap["2026-07"]["isencao_acoes"]["isento"]
    assert ap["2026-08"]["prejuizo_a_compensar"]["comum"] == pytest.approx(1000.0)
    # set: lucro 15 mil - 1 mil compensado = 14 mil * 15% = 2.100 - IRRF 0,005% de 25 mil (1,25)
    assert ap["2026-09"]["darf"] == pytest.approx(2100 - 1.25)
    assert ap["2026-09"]["vencimento"] == "2026-10-30"


# ------------------------------------------------------------------ migração
def test_migracao_do_formato_da_fase_1(home):
    leg = Path(__file__).parent / "dados" / "legado"
    for f in leg.iterdir():
        shutil.copy(f, home / "data" / f.name)
    log = migrar.migrar(natureza="demo")
    assert any("operações: 3" in l for l in log)
    assert set(instrumentos.carregar()) == {"PETR4", "WEGE3", "SUZB3"}
    assert teses.vigente("PETR4")["alvo"] == 42.0
    hs = {h["id"]: h for h in __import__("rvlocal").hipoteses.carregar()}
    assert hs["H-EXEMPLO-1"]["formulada_em"] == "2026-11-02" and "legado" in hs["H-EXEMPLO-1"]
    assert (home / "data" / "operacoes.jsonl.migrado").exists()
    with pytest.raises(RuntimeError):
        migrar.migrar()                                               # não mistura históricos
