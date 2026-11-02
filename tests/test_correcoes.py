"""Regressão dos defeitos do diagnóstico (docs/01-diagnostico.md, seção 4.2)."""
import json
import subprocess
from datetime import date, datetime

import pytest

from rvlocal import calendario, desempenho, diario, fontes, hipoteses as H, livros, razao, series
from rvlocal.util import BRT


def _cot(dia, preco, fonte):
    y, m, d = map(int, dia.split("-"))
    return fontes.Cotacao("PETR4", preco, None, datetime(y, m, d, 17, 55, tzinfo=BRT), fonte)


def test_d1_fonte_defasada_nao_se_esconde_atras_da_outra():
    ontem, hoje = _cot("2026-11-03", 36.00, "yahoo"), _cot("2026-11-04", 36.10, "brapi")
    l = fontes.consolidar("PETR4", [lambda: ontem, lambda: hoje], 0.5)
    assert l.status == "ok"
    assert l.ts.date() == date(2026, 11, 3)     # a idade é a da fonte mais velha


def test_d2_caixa_negativo_e_apontado(home):
    (home / "data" / "livros" / "instrumentos.json").write_text(json.dumps({"PETR4": {}}))
    ops = [{"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 1000.0},
           {"id": "2", "data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 1000, "preco": 36.0}]
    probs = razao.validar(ops)
    assert any("caixa BRL negativo" in p for p in probs)


def test_d3_lacuna_nao_apaga_o_retorno_do_periodo():
    fluxos = {"2026-11-03": 36000.0}
    ants = [{"data": "2026-11-03", "patrimonio": 36000.0}, {"data": "2026-11-04", "patrimonio": None}]
    r = desempenho.retorno_consolidado(40000.0, "2026-11-05", fluxos, ants)
    assert r["retorno_pct"] == pytest.approx(11.111, abs=1e-3)
    assert r["desde"] == "2026-11-03" and r["pregoes"] == 2


def test_d3_ponta_a_ponta(home, monkeypatch):
    lv = home / "data" / "livros"
    (lv / "instrumentos.json").write_text(json.dumps({"PETR4": {"setor": "x"}}))
    (lv / "operacoes.jsonl").write_text("\n".join(json.dumps(o) for o in [
        {"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 36000.0},
        {"id": "2", "data": "2026-11-03", "tipo": "compra", "ativo": "PETR4", "qtd": 1000, "preco": 36.0,
         "tese_id": "", "gatilho": "g", "horizonte": "h"}]) + "\n")
    series.gravar_historico("PETR4", {"2026-11-03": 36.0, "2026-11-05": 40.0, "2026-11-06": 40.0}, "teste")
    monkeypatch.setenv("RVLOCAL_AGORA", "2026-11-06T18:05:00-03:00")
    for d in ("2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"):
        s = diario.fechar_dia(d, enviar=False)
    assert s["retorno_acumulado_pct"] == pytest.approx(11.111, abs=1e-3)


HIP = {"id": "H1", "status": "ativa", "origem": "usuario", "formulada_em": "2026-11-05", "limiar_pp": 0.75,
       "teste": {"tipo": "segue_driver", "ativo": "PETR4", "driver": "BRENT", "limiar_driver_pct": 1.0}}
FECH = {"2026-11-03": {"BRENT": 80.0, "PETR4": 30.0}, "2026-11-04": {"BRENT": 82.0, "PETR4": 31.0},
        "2026-11-05": {"BRENT": 84.0, "PETR4": 31.1}, "2026-11-06": {"BRENT": 86.0, "PETR4": 32.0}}


def test_d5_nao_pontua_antes_da_formulacao(home):
    livros.anexar("hipoteses", HIP)
    assert H.medir_dia_livro(FECH, "2026-11-04") == []          # anterior à formulação
    assert len(H.medir_dia_livro(FECH, "2026-11-06")) == 1


def test_d6_limiar_cria_zona_neutra():
    p = H.pontuar(HIP, FECH, "2026-11-05")                       # Brent +2,4%, PETR4 +0,32%: abaixo de 0,75 pp
    assert p["veredito"] == "neutro"
    p = H.pontuar(HIP, FECH, "2026-11-06")                       # PETR4 +2,9%
    assert p["veredito"] == "favor"


def test_d6_veredito_exige_gates_e_usa_wilson():
    h = dict(HIP, min_gates=8)
    pontos = [{"hipotese_id": "H1", "data": f"d{i}", "veredito": "favor"} for i in range(7)]
    assert H.placar_v2([h], pontos)[0]["veredito"] == "aguardando (7/8 gates)"
    pontos += [{"hipotese_id": "H1", "data": "d7", "veredito": "contra"}]
    p = H.placar_v2([h], pontos)[0]
    assert p["ic95_pct"] == [52.9, 97.8] and p["veredito"] == "confirmada"
    lo, hi = H.wilson(10, 13)                                     # referência: 77% [50%, 92%]
    assert round(lo * 100) == 50 and round(hi * 100) == 92


def test_d6_reescrever_teste_no_mesmo_id_e_erro(home):
    livros.anexar("hipoteses", HIP)
    livros.anexar("hipoteses", {**HIP, "teste": {"tipo": "mesma_direcao", "ativos": ["A", "B"]}})
    assert any("reescrito" in p for p in H.validar_livro())


def test_d9_feriados_calculados_batem_com_a_lista_manual_de_2026_e_existem_em_2027():
    manual_2026 = {"2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21", "2026-05-01",
                   "2026-06-04", "2026-09-07", "2026-10-12", "2026-11-02", "2026-11-20", "2026-12-24",
                   "2026-12-25", "2026-12-31"}
    assert manual_2026 <= calendario.feriados_ano(2026)
    assert {"2027-02-08", "2027-02-09", "2027-03-26", "2027-05-27"} <= calendario.feriados_ano(2027)
    assert calendario.aviso_calendario(date(2026, 11, 3)) is not None   # ano não conferido gera aviso


def test_imutabilidade_dos_livros_contra_o_git(home):
    lv = home / "data" / "livros"
    (lv / "operacoes.jsonl").write_text('{"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 10}\n')
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(home), *cmd], check=True, capture_output=True)
    with (lv / "operacoes.jsonl").open("a") as f:
        f.write('{"id": "2", "data": "2026-11-04", "tipo": "aporte", "valor": 5}\n')
    assert livros.verificar_imutabilidade() == []                 # acréscimo: ok
    (lv / "operacoes.jsonl").write_text('{"id": "1", "data": "2026-11-03", "tipo": "aporte", "valor": 99}\n')
    assert any("ALTERADO" in p for p in livros.verificar_imutabilidade())


def test_natureza_invalida_e_recusada(home):
    with pytest.raises(ValueError):
        livros.anexar("eventos", {"tipo": "x", "natureza": "inventado"})
