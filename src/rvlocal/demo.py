"""Base DEMO: uma carteira fictícia completa para explorar a plataforma.

* Tickers FICTÍCIOS (EXPO3, BANK4, TECHX...) para que nenhum preço sintético seja confundido
  com cotação real. Todo registro sai com natureza "demo" e o painel mostra o selo DADOS DEMO.
* Preços gerados por um modelo de fatores com semente fixa (o mesmo comando gera a mesma base).
* Os fechamentos são produzidos pelo MESMO código de produção, pregão a pregão: o que você vê
  no painel demo é exatamente o que a plataforma faria com dados reais.
"""
from __future__ import annotations

import math
import os
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

MARCADOR = "DADOS-DEMO.md"
FIM = date(2026, 10, 30)
N_PREGOES = 330
N_OPERANDO = 110
CAPITAL = 500_000.0

INSTRUMENTOS = {
    "EXPO3": {"nome": "Exportadora de Celulose (fictícia)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "papel_celulose", "fatores": ["exportadora"], "receita_usd_pct": 80},
    "INDU3": {"nome": "Indústria de Motores (fictícia)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "industria", "fatores": ["exportadora"], "receita_usd_pct": 50},
    "BANK4": {"nome": "Banco Nacional (fictício)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "bancos", "fatores": ["ciclo_domestico"]},
    "ENER3": {"nome": "Transmissora de Energia (fictícia)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "energia", "fatores": ["juro_longo"]},
    "OLEO3": {"nome": "Petroleira Júnior (fictícia)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "petroleo", "fatores": ["commodities"], "receita_usd_pct": 60},
    "VARE3": {"nome": "Varejo Popular (fictício)", "classe": "acao", "moeda": "BRL", "pais": "BR",
              "setor": "varejo", "fatores": ["juro_longo", "ciclo_domestico"]},
    "INDX11": {"nome": "ETF de Ibovespa (fictício)", "classe": "etf", "moeda": "BRL", "pais": "BR",
               "setor": "indice_br"},
    "IMOB11": {"nome": "FII de Lajes (fictício)", "classe": "fii", "moeda": "BRL", "pais": "BR",
               "setor": "imobiliario", "fatores": ["juro_longo"]},
    "TECHX": {"nome": "Big Tech (fictícia)", "classe": "acao_ext", "moeda": "USD", "pais": "US",
              "setor": "tecnologia"},
    "PAGX": {"nome": "Rede de Pagamentos (fictícia)", "classe": "acao_ext", "moeda": "USD", "pais": "US",
             "setor": "pagamentos"},
    "VOOX": {"nome": "ETF de S&P 500 (fictício)", "classe": "etf_ext", "moeda": "USD", "pais": "US",
             "setor": "indice_eua"},
}

# preço inicial, alfa diário, cargas (br, us, fx, brent, juro), vol idiossincrática
MODELO = {
    "EXPO3": (50, 0.0012, {"br": 0.8, "fx": 0.9}, 0.012),
    "INDU3": (40, 0.0005, {"br": 0.9, "fx": 0.5}, 0.011),
    "BANK4": (30, 0.0003, {"br": 1.1, "juro": 0.2}, 0.010),
    "ENER3": (35, 0.0002, {"br": 0.7, "juro": -0.6}, 0.009),
    "OLEO3": (38, 0.0002, {"br": 0.9, "brent": 0.8}, 0.012),
    "VARE3": (12, -0.0008, {"br": 1.3, "juro": -0.9}, 0.018),
    "INDX11": (120, 0.0, {"br": 1.0}, 0.002),
    "IMOB11": (95, 0.0001, {"br": 0.3, "juro": -0.5}, 0.006),
    "TECHX": (180, 0.0004, {"us": 1.3}, 0.016),
    "PAGX": (260, 0.0002, {"us": 1.0}, 0.012),
    "VOOX": (520, 0.0, {"us": 1.0}, 0.001),
    "IBOV": (120000, 0.0, {"br": 1.0}, 0.001),
    "SPX": (5800, 0.0, {"us": 1.0}, 0.0005),
    "USDBRL": (5.40, 0.0, {"fx": 1.0}, 0.0005),
    "BRENT": (75, 0.0, {"brent": 1.0}, 0.002),
}


def _pregoes() -> list[date]:
    from .calendario import dia_util
    out, d = [], FIM
    while len(out) < N_PREGOES:
        if dia_util(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _precos(dias: list[date], choque: dict[tuple[str, int], float]) -> dict[str, dict[str, float]]:
    rng = random.Random(42)
    nivel = {s: m[0] for s, m in MODELO.items()}
    out: dict[str, dict[str, float]] = {s: {} for s in MODELO}
    for i, d in enumerate(dias):
        z = [rng.gauss(0, 1) for _ in range(5)]
        br = 0.0004 + 0.011 * z[0]
        f = {"br": br, "us": 0.0005 + 0.009 * (0.3 * z[0] + math.sqrt(1 - 0.09) * z[1]),
             "fx": 0.0001 + 0.007 * z[2] - 0.25 * (br - 0.0004), "brent": 0.0002 + 0.018 * z[3],
             "juro": 0.009 * z[4]}
        for s, (_, alfa, cargas, idio) in MODELO.items():
            if i > 0:
                r = alfa + sum(c * f[k] for k, c in cargas.items()) + idio * rng.gauss(0, 1) + choque.get((s, i), 0.0)
                nivel[s] *= 1 + r
            out[s][d.isoformat()] = round(nivel[s], 2 if nivel[s] < 1000 else 0) if s != "USDBRL" else round(nivel[s], 4)
    return out


def gerar(destino: str = "demo") -> Path:
    from .util import raiz_projeto
    origem = raiz_projeto()
    dest = Path(destino).resolve()
    if dest.exists() and any(dest.iterdir()):
        if not (dest / MARCADOR).exists():
            raise RuntimeError(f"{dest} já existe e não é uma base demo; nada foi apagado.")
        shutil.rmtree(dest)
    (dest / "data" / "livros").mkdir(parents=True)
    shutil.copytree(origem / "config", dest / "config")
    (dest / MARCADOR).write_text("# DADOS DEMO\n\nBase fictícia gerada por `python -m rvlocal demo`. "
                                 "Tickers e preços SINTÉTICOS. Não é recomendação nem dado de mercado.\n",
                                 encoding="utf-8")
    ambiente = {k: os.environ.get(k) for k in ("RVLOCAL_HOME", "RVLOCAL_NATUREZA", "RVLOCAL_AGORA",
                                               "RVLOCAL_CARTEIRA")}
    os.environ.pop("RVLOCAL_CARTEIRA", None)
    os.environ.update(RVLOCAL_HOME=str(dest), RVLOCAL_NATUREZA="demo")
    try:
        _montar(dest)
    finally:
        for k, v in ambiente.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print(f"base demo pronta em {dest}")
    print(f"painel:  RVLOCAL_HOME={dest} python -m rvlocal painel")
    return dest


def _montar(dest: Path) -> None:
    from . import boletim, decisoes, diario, hipoteses, livros, series, teses
    from .util import gravar_json

    dias = _pregoes()
    s0 = N_PREGOES - N_OPERANDO
    iso = [d.isoformat() for d in dias]
    choque = {("OLEO3", s0 + 70): -0.13, ("BANK4", s0 + 33): 0.04}
    px = _precos(dias, choque)
    gravar_json(dest / "data" / "livros" / "instrumentos.json", INSTRUMENTOS)
    (dest / "carteira.toml").write_text('nome = "Carteira própria (DEMO)"\ntipo = "propria"\nnatureza = "demo"\n'
                                        'benchmark = "IBOV"\n', encoding="utf-8")
    for s, vals in px.items():
        series.gravar_historico(s, vals, "demo-sintetico", natureza="demo")

    def p(s, i):
        return px[s][iso[i]]

    ops: list[dict] = []
    nop = [0]

    def op(i, **kw):
        nop[0] += 1
        o = {"id": f"op-demo-{nop[0]:03d}", "data": iso[i], **kw}
        ops.append(o)
        return o

    def comprar(i, ativo, peso_pct, chk: dict | None, tipo_dec="entrada", motivo=None, base=CAPITAL):
        preco = p(ativo, i)
        moeda = INSTRUMENTOS[ativo]["moeda"]
        if moeda == "USD":
            qtd = math.floor(base * peso_pct / 100 / (preco * p("USDBRL", i)))
        else:
            qtd = math.floor(base * peso_pct / 100 / preco / 100) * 100
        kw = {"tipo": "compra", "ativo": ativo, "qtd": qtd, "preco": preco, "custos": 5.0 if moeda == "BRL" else 1.0}
        if moeda != "BRL":
            kw.update(moeda=moeda, cambio=p("USDBRL", i))
        if chk is not None:
            d = decisoes.registrar({"data": iso[i], "tipo": tipo_dec, "ativo": ativo, "decisao": "compra",
                                    "motivo": motivo or chk.get("justificativa", ""),
                                    "checklist": {"preco_entrada": preco, **chk}})
            kw.update(decisao_id=d["id"], tese_id=chk.get("tese_id"))
        return op(i, **kw)

    def vender(i, ativo, qtd, chk: dict | None, tipo_dec="saida", motivo=None):
        preco = p(ativo, i)
        moeda = INSTRUMENTOS[ativo]["moeda"]
        kw = {"tipo": "venda", "ativo": ativo, "qtd": qtd, "preco": preco, "custos": 5.0 if moeda == "BRL" else 1.0}
        if moeda != "BRL":
            kw.update(moeda=moeda, cambio=p("USDBRL", i))
        if chk is not None:
            d = decisoes.registrar({"data": iso[i], "tipo": tipo_dec, "ativo": ativo, "decisao": "venda",
                                    "motivo": motivo or chk.get("justificativa", ""),
                                    "checklist": {"preco_entrada": preco, **chk}})
            kw.update(decisao_id=d["id"])
        return op(i, **kw)

    # ---------------- teses (fichas) escritas antes das entradas
    def ficha(i, ativo, **kw):
        preco = p(ativo, i)
        base = {"ativo": ativo, "titulo": kw.pop("titulo"), "tese": kw.pop("tese"), "horizonte": "12 meses",
                "rating": "BUY", "conviccao": 4, "origem": "usuario",
                "proxima_revisao": iso[min(i + 60, len(iso) - 1)],
                "muda_de_ideia_se": kw.pop("invalida", "a premissa central deixar de valer por 2 trimestres"),
                "riscos": kw.pop("riscos", ["execução", "macro doméstico"]),
                "catalisadores": kw.pop("catalisadores", ["resultado trimestral"])}
        up = kw.pop("up", 1.30)
        base.update(alvo=round(preco * up, 2), stop=round(preco * kw.pop("st", 0.85), 2),
                    preco_justo=round(preco * (up - 0.05), 2), nivel_compra=round(preco * 1.03, 2),
                    metodo_valuation="DCF (lab no Ciclo 3)",
                    cenarios={"otimista": {"preco": round(preco * (up + 0.2), 2), "prob": 0.25},
                              "base": {"preco": round(preco * (up - 0.05), 2), "prob": 0.5},
                              "pessimista": {"preco": round(preco * 0.8, 2), "prob": 0.25}})
        base.update(kw)
        return teses.nova_versao(base, iso[i])

    s = s0
    ficha(s, "EXPO3", titulo="Celulose em dólar com custo em real",
          tese="Receita dolarizada e custo caixa em real: dólar forte expande margem acima do índice.",
          catalisadores=["preço da celulose na China", "dólar"], up=1.30)
    ficha(s, "INDU3", titulo="Exportadora industrial de qualidade",
          tese="Metade da receita no exterior e retorno sobre capital alto e estável.", up=1.35)
    ficha(s, "BANK4", titulo="Banco barato com ROE em recuperação",
          tese="ROE volta a 18% com inadimplência em queda; múltiplo abaixo da média histórica.", up=1.30)
    ficha(s, "ENER3", titulo="Transmissão: renda indexada à inflação",
          tese="Receita regulada indexada ao IPCA; sensível ao juro longo.", up=1.25, st=0.88)
    ficha(s, "OLEO3", titulo="Petroleira júnior alavancada no Brent",
          tese="Produção crescente e custo de extração baixo: ganha com Brent acima de 70.",
          riscos=["Brent", "execução de campos"], up=1.35, st=0.90)
    ficha(s, "INDX11", titulo="Núcleo indexado", tese="Exposição barata ao índice como base da carteira.",
          rating="HOLD", conviccao=3, up=1.20, st=0.80)
    ficha(s, "IMOB11", titulo="Lajes AAA com desconto patrimonial",
          tese="Cota abaixo do valor patrimonial; ganha com juro longo em queda.", up=1.20, st=0.88)
    for a, t in (("TECHX", "Plataforma dominante com caixa líquido"), ("PAGX", "Rede de pagamentos com pedágio"),
                 ("VOOX", "Núcleo EUA indexado")):
        ficha(s + 2, a, titulo=t, tese=t + ".", up=1.25)

    # ---------------- hipóteses (pré-registradas)
    hipoteses.registrar({"id": "H-EXP-USD", "titulo": "Exportadoras batem o Ibovespa em dia de dólar em alta",
                         "tese": "Receita em dólar: EXPO3 e INDU3 rendem mais que o índice quando o dólar sobe 0,3%+.",
                         "teste": {"tipo": "excesso_em_condicao", "ativos": ["EXPO3", "INDU3"], "benchmark": "IBOV",
                                   "condicao": {"serie": "USDBRL", "sinal": "alta", "limiar_pct": 0.3}},
                         "muda_de_ideia_se": "o intervalo de confiança ficar abaixo de 50% com 8+ gates",
                         "formulada_em": iso[s], "origem": "usuario"})
    hipoteses.registrar({"id": "H-OLEO-BRENT", "titulo": "OLEO3 acompanha o Brent em dia de movimento relevante",
                         "tese": "Com Brent mexendo 1%+, OLEO3 vai na mesma direção por pelo menos 0,75 pp.",
                         "teste": {"tipo": "segue_driver", "ativo": "OLEO3", "driver": "BRENT", "limiar_driver_pct": 1.0},
                         "formulada_em": iso[s], "origem": "usuario"})
    hipoteses.registrar({"id": "H-FII-DEFESA", "titulo": "IMOB11 cai menos que o Ibovespa em dia de queda forte",
                         "tese": "Renda de aluguel amortece: em queda de 1%+ do índice, o FII perde menos.",
                         "teste": {"tipo": "diferenca_vs_referencia", "ativos": ["IMOB11"], "referencia": "IBOV",
                                   "sentido": 1, "gate": [{"serie": "IBOV", "max_pct": -1.0}]},
                         "formulada_em": iso[s + 3], "origem": "ia"})
    hipoteses.mudar_status("H-FII-DEFESA", "ativa", iso[s + 10], "li a premissa e concordo: sim")
    hipoteses.registrar({"id": "H-TECH-PAG", "titulo": "TECHX e PAGX andam juntas",
                         "teste": {"tipo": "mesma_direcao", "ativos": ["TECHX", "PAGX"]},
                         "formulada_em": iso[s + 2], "origem": "usuario"})

    # ---------------- operações
    def chk(tese, just, tam, stop_mult=0.85, alvo_mult=1.30, ativo=None, i=s, rmax=1.0):
        pr = p(ativo, i)
        return {"tese_id": tese, "justificativa": just, "horizonte": "12 meses", "tamanho_pct": tam,
                "risco_max_pct": rmax, "invalidacao": round(pr * stop_mult, 2), "objetivo": round(pr * alvo_mult, 2)}

    op(s, tipo="aporte", valor=CAPITAL)
    for a, w, sm, am in (("EXPO3", 8, 0.85, 1.30), ("INDU3", 10, 0.85, 1.35), ("BANK4", 12, 0.85, 1.30),
                         ("ENER3", 8, 0.88, 1.25), ("OLEO3", 6, 0.90, 1.35), ("INDX11", 12, 0.80, 1.20),
                         ("IMOB11", 5, 0.88, 1.20)):
        comprar(s, a, w, chk(f"T-{a}", f"Entrada planejada da ficha T-{a}", w, sm, am, a))
    fx1 = p("USDBRL", s + 1)
    op(s + 1, tipo="cambio", de="BRL", para="USD", valor_de=110000.0, valor_para=round(110000 / fx1, 2), custos=150.0)
    for a, w in (("TECHX", 7), ("PAGX", 6), ("VOOX", 8)):
        comprar(s + 2, a, w, chk(f"T-{a}", f"Entrada planejada da ficha T-{a}", w, 0.85, 1.25, a, s + 2))
    # compra por impulso, sem tese nem plano
    comprar(s + 20, "VARE3", 3, {"justificativa": "caiu muito, parece barata"}, motivo="caiu muito")
    # aumento de BANK4 que estoura o teto de posição; decisão de reduzir 1 dia depois (no prazo)
    comprar(s + 32, "BANK4", 12, chk("T-BANK4", "Resultado acima do esperado", 25, 0.88, 1.25, "BANK4", s + 32),
            tipo_dec="aumentar")
    decisoes.registrar({"data": iso[s + 33], "tipo": "reduzir", "ativo": "BANK4", "decisao": "reduzir para 18%",
                        "motivo": "teto de posição estourado após o aumento; voltar abaixo de 25%"})
    pos_bank = sum(o["qtd"] for o in ops if o.get("ativo") == "BANK4")
    vender(s + 34, "BANK4", math.floor(pos_bank * 0.30 / 100) * 100,
           chk("T-BANK4", "Ajuste ao teto de posição", 18, 0.88, 1.25, "BANK4", s + 34), tipo_dec="reduzir")
    op(s + 50, tipo="provento", ativo="BANK4", valor=4200.0)
    # realização parcial de EXPO3 (decisão registrada)
    pos_expo = sum(o["qtd"] for o in ops if o.get("ativo") == "EXPO3")
    vender(s + 60, "EXPO3", math.floor(pos_expo * 0.4 / 100) * 100,
           chk("T-EXPO3", "Realização parcial: perto do alvo, 1º degrau", 5, 0.95, 1.30, "EXPO3", s + 60),
           tipo_dec="realizacao")
    # OLEO3: o choque leva abaixo do stop; a decisão de stop só vem 2 pregões depois, e sem nova invalidação
    decisoes.registrar({"data": iso[s + 72], "tipo": "stop", "ativo": "OLEO3", "decisao": "manter",
                        "motivo": "acho que exageraram na queda"})
    teses.nova_versao({**teses.vigente("ENER3"), "conviccao": 3, "rating": "HOLD",
                       "motivo_mudanca": "juro longo subiu: reduzi a convicção"}, iso[s + 45])
    comprar(s + 75, "VARE3", 2, None)
    pos_tech = sum(o["qtd"] for o in ops if o.get("ativo") == "TECHX")
    vender(s + 85, "TECHX", max(1, pos_tech // 3),
           chk("T-TECHX", "Rebalanceamento: TECHX acima do peso planejado", 5, 0.85, 1.25, "TECHX", s + 85),
           tipo_dec="reduzir")

    # última semana: aumento grande de INDX11 que estoura o teto de posição; a pendência é ignorada
    k = len(dias) - 4
    comprar(k, "INDX11", 16, {**chk("T-INDX11", "Aproveitar a queda do índice", 28, 0.85, 1.35, "INDX11", k)},
            tipo_dec="aumentar")

    for o in sorted(ops, key=lambda o: o["data"]):
        livros.anexar("operacoes", o)
    livros.anexar("eventos", {"tipo": "resultado", "data": iso[s + 55], "ativo": "BANK4",
                              "texto": "Resultado trimestral (fictício): lucro acima do consenso.",
                              "fonte": "demo"})
    # DARF de julho fica SEM pagamento registrado: o boletim cobra na semana do vencimento.

    # ---------------- fechamento pregão a pregão (mesmo código de produção)
    ult = len(dias) - 1
    for i in range(s, len(dias)):
        d = dias[i]
        os.environ["RVLOCAL_AGORA"] = f"{iso[i]}T18:05:00-03:00"
        diario.fechar_dia(iso[i], enviar=False)
        _gestor_simulado(i, s, ult, iso, px)
        prox = dias[i + 1] if i + 1 < len(dias) else None
        if prox is None or prox.isocalendar()[1] != d.isocalendar()[1]:
            boletim.emitir("semanal", d)
        if prox is None or prox.month != d.month:
            boletim.emitir("mensal", d)
            if d.month % 3 == 0 or prox is None:
                boletim.emitir("trimestral", d)
    boletim.emitir("diario", dias[-1])
    _outras_carteiras(iso, s)


def _outras_carteiras(iso: list[str], s: int) -> None:
    """Duas carteiras extras, para mostrar a comparação: uma recomendada de analista (rebalanceada
    todo mês) e uma de cliente (alocação moderada, rebalanceada a cada trimestre). Mesmo universo e
    mesmos preços da principal; gerenciadas por pesos-alvo com `simulacao.rebalancear`."""
    from . import carteiras, simulacao
    from .util import usar_carteira
    carteiras.criar("analista-demo", "Recomendada da Casa Fictícia", "analista", natureza="demo",
                    fonte="Casa de Análise Fictícia (DEMO)", descricao="carteira mensal de ações brasileiras")
    carteiras.criar("cliente-001", "Cliente 001 · moderado", "cliente", natureza="demo",
                    descricao="perfil moderado, metade no exterior e em índice")
    meses = sorted({d[:7] for d in iso[s:]})
    primeiros = [next(d for d in iso[s:] if d.startswith(m)) for m in meses]
    recomendacoes = [
        {"EXPO3": 15, "INDU3": 15, "BANK4": 20, "ENER3": 15, "OLEO3": 15, "VARE3": 10},
        {"EXPO3": 20, "INDU3": 15, "BANK4": 20, "ENER3": 15, "OLEO3": 10, "VARE3": 10},
        {"EXPO3": 20, "INDU3": 20, "BANK4": 15, "ENER3": 15, "OLEO3": 10, "IMOB11": 10},
        {"EXPO3": 20, "INDU3": 20, "BANK4": 15, "ENER3": 20, "IMOB11": 15},
    ]
    with usar_carteira("analista-demo"):
        for k, d in enumerate(primeiros):
            simulacao.rebalancear(recomendacoes[min(k, len(recomendacoes) - 1)], d,
                                  capital=100_000.0 if k == 0 else None, custos_pct=0.05,
                                  fonte="Casa de Análise Fictícia (DEMO)", tese_id="REC-CASA-FICTICIA",
                                  justificativa=f"carteira recomendada de {d[:7]}", horizonte="1 mês")
        simulacao.reprocessar(iso[s], iso[-1])
    alvo_cliente = {"INDX11": 30, "IMOB11": 15, "ENER3": 10, "VOOX": 25, "PAGX": 10}
    # regras PRÓPRIAS da carteira: a política do cliente aceita até 35% num ETF de índice
    from .util import raiz_base
    cfg = raiz_base() / "carteiras" / "cliente-001" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    regras_txt = (raiz_base() / "config" / "regras.toml").read_text(encoding="utf-8")
    (cfg / "regras.toml").write_text(regras_txt.replace("teto_posicao_pct = 25", "teto_posicao_pct = 35"),
                                     encoding="utf-8")
    risco_txt = (raiz_base() / "config" / "risco.toml").read_text(encoding="utf-8")
    (cfg / "risco.toml").write_text(risco_txt.replace("hhi_max = 0.20", "hhi_max = 0.30"), encoding="utf-8")
    with usar_carteira("cliente-001"):
        trimestrais = [d for d in primeiros if int(d[5:7]) in (1, 4, 7, 10)] or primeiros[:1]
        if primeiros[0] not in trimestrais:
            trimestrais = [primeiros[0]] + trimestrais
        for k, d in enumerate(trimestrais):
            simulacao.rebalancear(alvo_cliente, d, capital=250_000.0 if k == 0 else None, custos_pct=0.05,
                                  tese_id="ALOCACAO-MODERADA", justificativa="política de alocação do cliente",
                                  horizonte="3 anos")
        simulacao.reprocessar(iso[s], iso[-1])


def _gestor_simulado(i: int, s: int, ult: int, iso: list[str], px: dict) -> None:
    """Responde às pendências abertas hoje, como um gestor disciplinado... quase sempre.

    Falhas ROTEIRIZADAS (para o boletim e a mesa terem o que mostrar):
      * stop de OLEO3 ignorado do choque (s+70) até s+72, e "manter" sem nova invalidação;
      * realizações da última semana ignoradas (ficam vencidas na mesa).
    """
    from . import decisoes, mesa, teses
    hoje = iso[i]
    for a in mesa.estado(hoje):
        if a["status"] != "aberto" or a["data"] != hoje:
            continue
        regra, ativo = a["regra"], a.get("ativo")
        if ativo == "OLEO3" and regra.startswith("stop") and s + 70 <= i <= s + 73:
            continue
        if regra == "realizacao_sem_decisao" and i >= ult - 5:
            continue
        if regra in {"teto_posicao", "caixa_minimo"} and i >= ult - 3:
            continue
        if regra == "teto_posicao" and ativo == "BANK4" and i <= s + 34:
            continue  # resolvida pela decisão roteirizada de reduzir
        preco = px[ativo][hoje] if ativo in px else None
        f = teses.vigente(ativo, hoje) if ativo else None
        if regra.startswith("stop") and preco:
            novo = round(preco * 0.92, 2)
            decisoes.registrar({"data": hoje, "tipo": "stop", "ativo": ativo, "decisao": "manter",
                                "motivo": "queda sem mudança de tese; stop recalibrado",
                                "nova_invalidacao": f"fechamento abaixo de {novo}", "alerta_id": a["id"]})
            if f:
                teses.nova_versao({**f, "stop": novo, "motivo_mudanca": "stop recalibrado após teste"}, hoje)
        elif regra == "realizacao_sem_decisao" and preco:
            decisoes.registrar({"data": hoje, "tipo": "realizacao", "ativo": ativo, "decisao": "manter",
                                "motivo": "tese intacta; alvo revisto para cima", "alerta_id": a["id"]})
            if f:
                teses.nova_versao({**f, "alvo": round(preco * 1.15, 2),
                                   "motivo_mudanca": "alvo revisto após atingir 90%"}, hoje)
        else:
            decisoes.registrar({"data": hoje, "tipo": "revisao" if not ativo else "manter", "ativo": ativo,
                                "decisao": "ciente", "motivo": "ajuste no próximo aporte", "alerta_id": a["id"]})
    if i == s + 73:  # depois de ignorar, a correção: nova ficha de OLEO3 com a nova invalidação
        f = teses.vigente("OLEO3", hoje)
        teses.nova_versao({**f, "stop": round(px["OLEO3"][hoje] * 0.88, 2), "conviccao": 2, "rating": "HOLD",
                           "motivo_mudanca": "stop ignorado por 2 pregões; tese revista, convicção menor"}, hoje)
        decisoes.registrar({"data": hoje, "tipo": "stop", "ativo": "OLEO3", "decisao": "manter",
                            "motivo": "tese revista", "nova_invalidacao": "novo stop na ficha v3"})
    # revisão periódica das fichas (exceto VARE3, que nunca teve ficha)
    for a, f in teses.todas_vigentes(hoje).items():
        if teses.revisao_vencida(f, hoje) and i < ult - 3:
            teses.nova_versao({**f, "proxima_revisao": iso[min(i + 60, ult)],
                               "motivo_mudanca": "revisão periódica: tese mantida"}, hoje)
