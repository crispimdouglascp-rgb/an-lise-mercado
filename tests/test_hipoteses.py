from rvlocal import hipoteses as H

FECH = {
    "2026-11-03": {"IBOV": 100.0, "USDBRL": 5.00, "SUZB3": 50.0, "WEGE3": 40.0, "PETR4": 30.0, "BRENT": 80.0},
    "2026-11-04": {"IBOV": 101.0, "USDBRL": 5.05, "SUZB3": 51.5, "WEGE3": 40.8, "PETR4": 30.6, "BRENT": 81.0},   # dólar +1%
    "2026-11-05": {"IBOV": 102.0, "USDBRL": 5.05, "SUZB3": 50.0, "WEGE3": 40.0, "PETR4": 30.0, "BRENT": 80.0},   # dólar 0%
    "2026-11-06": {"IBOV": 101.0, "USDBRL": 5.20, "SUZB3": 49.0, "WEGE3": 39.9, "PETR4": 29.0, "BRENT": 78.0},   # dólar +3%, errou
}
HIP = {
    "id": "H1",
    "teste": {"tipo": "excesso_em_condicao", "ativos": ["SUZB3", "WEGE3"], "benchmark": "IBOV",
              "condicao": {"serie": "USDBRL", "sinal": "alta", "limiar_pct": 0.3}},
}


def test_excesso_acerto_erro_e_nao_aplicavel():
    assert H.avaliar(HIP, FECH, "2026-11-04")["resultado"] == "acerto"     # SUZB3 +3% e WEGE3 +2% > IBOV +1%
    assert H.avaliar(HIP, FECH, "2026-11-05")["resultado"] == "nao_aplicavel"
    assert H.avaliar(HIP, FECH, "2026-11-06")["resultado"] == "erro"


def test_primeiro_dia_sem_retorno_e_sem_dado():
    assert H.avaliar(HIP, FECH, "2026-11-03")["resultado"] == "sem_dado"


def test_segue_driver():
    h = {"id": "H2", "teste": {"tipo": "segue_driver", "ativo": "PETR4", "driver": "BRENT", "limiar_driver_pct": 1.0}}
    assert H.avaliar(h, FECH, "2026-11-04")["resultado"] == "acerto"          # Brent +1,25%, PETR4 +2%
    assert H.avaliar(h, FECH, "2026-11-05")["resultado"] == "acerto"          # Brent -1,2%, PETR4 -2%: mesma direção


def test_segue_driver_erro_e_limiar():
    h = {"id": "H2", "teste": {"tipo": "segue_driver", "ativo": "PETR4", "driver": "BRENT", "limiar_driver_pct": 5.0}}
    assert H.avaliar(h, FECH, "2026-11-04")["resultado"] == "nao_aplicavel"   # driver abaixo do limiar de 5%
    h["teste"]["limiar_driver_pct"] = 1.0
    f = {"2026-11-03": {"BRENT": 80.0, "PETR4": 30.0}, "2026-11-04": {"BRENT": 82.0, "PETR4": 29.0}}
    assert H.avaliar(h, f, "2026-11-04")["resultado"] == "erro"


def test_mesma_direcao():
    h = {"id": "H3", "teste": {"tipo": "mesma_direcao", "ativos": ["SUZB3", "WEGE3"]}}
    assert H.avaliar(h, FECH, "2026-11-04")["resultado"] == "acerto"
    f = {"2026-11-03": {"SUZB3": 50.0, "WEGE3": 40.0}, "2026-11-04": {"SUZB3": 51.0, "WEGE3": 39.0}}
    assert H.avaliar(h, f, "2026-11-04")["resultado"] == "erro"


def test_tipo_desconhecido_nao_inventa_resultado():
    assert H.avaliar({"id": "X", "teste": {"tipo": "magia"}}, FECH, "2026-11-04")["resultado"] == "sem_dado"


def test_medir_dia_e_idempotente_e_placar_sugere_arquivar():
    h = dict(HIP, arquivar_apos_falhas_consecutivas=1, status="ativa")
    H.medir_dia([h], FECH, "2026-11-06")
    H.medir_dia([h], FECH, "2026-11-06")  # repetir não duplica
    assert len(h["medicoes"]) == 1
    p = H.placar([h])[0]
    assert p["medicoes"] == 1 and p["acertos"] == 0 and p["erros_consecutivos"] == 1
    assert p["sugestao"] == "arquivar"
    assert h["status"] == "ativa"  # o código só sugere; quem arquiva é o usuário
