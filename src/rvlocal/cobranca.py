"""Cobrança das 07:45: o que o sistema precisa de você hoje. Código puro.

Inclui o ALARME DE FALHA (D11): rotina esperada que não rodou no último pregão vira item da
cobrança. A referência ficou dois pregões parada "em silêncio"; aqui o silêncio é cobrado.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import hipoteses, livros, mesa, razao, teses
from .calendario import aviso_calendario, dia_util
from .notificar import ENVIAR
from .util import config


def ultimo_pregao_antes(d: date) -> date:
    x = d - timedelta(days=1)
    while not dia_util(x):
        x -= timedelta(days=1)
    return x


def itens(hoje: date) -> list[dict]:
    out: list[dict] = []
    ontem = ultimo_pregao_antes(hoje)
    for r in config("rotina.toml", {}).get("rotina", []):
        if r.get("esperada") and not livros.rodou(r["nome"], ontem):
            out.append({"tipo": "rotina_ausente", "urgencia": "alta",
                        "texto": f"A rotina '{r['nome']}' ({r['horario']}) não registrou execução em {ontem}. "
                                 "Rode a repescagem: python -m rvlocal fechar --data " + ontem.isoformat()})
    for a in mesa.estado(hoje.isoformat()):
        if a["status"] == "vencido":
            out.append({"tipo": "pendencia_vencida", "urgencia": "alta" if a["severidade"] == "alta" else "media",
                        "texto": f"[{a['id']}] {a['motivo']} Prazo era {a['prazo']}. {a['acao_requerida']}"})
        elif a["status"] == "aberto":
            out.append({"tipo": "pendencia", "urgencia": "media",
                        "texto": f"[{a['id']}] {a['motivo']} Prazo {a['prazo']}."})
    est = razao.calcular_estado(razao.carregar_operacoes(), ate=hoje.isoformat())
    fichas = teses.todas_vigentes(hoje.isoformat())
    for a in sorted(est.posicoes):
        f = fichas.get(a)
        if not f:
            out.append({"tipo": "sem_ficha", "urgencia": "media",
                        "texto": f"{a} está na carteira sem ficha de tese. Sem tese, a qualidade da decisão é zero."})
        elif teses.revisao_vencida(f, hoje.isoformat()):
            out.append({"tipo": "revisao_vencida", "urgencia": "baixa",
                        "texto": f"Ficha de {a} com revisão vencida desde {f['proxima_revisao']}."})
    for h in hipoteses.carregar():
        if h.get("status") == "rascunho":
            out.append({"tipo": "hipotese_rascunho", "urgencia": "baixa",
                        "texto": f"Hipótese {h['id']} (origem {h.get('origem')}) aguarda o seu sim para pontuar: "
                                 f"python -m rvlocal hipotese --ativar {h['id']} --motivo \"...\""})
    p = razao.validar()
    if p:
        out.append({"tipo": "razao", "urgencia": "alta", "texto": "Razão com problemas: " + "; ".join(p[:3])})
    imut = livros.verificar_imutabilidade()
    for x in imut:
        out.append({"tipo": "imutabilidade", "urgencia": "alta", "texto": x})
    av = aviso_calendario(hoje)
    if av:
        out.append({"tipo": "calendario", "urgencia": "baixa", "texto": av})
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    return sorted(out, key=lambda i: ordem[i["urgencia"]])


def executar(hoje: date, enviar: bool = True) -> list[dict]:
    with livros.rotina("cobranca"):
        its = itens(hoje)
    texto = f"RV Local, cobrança {hoje.isoformat()}: {len(its)} itens\n" + \
        "\n".join(f"• [{i['urgencia']}] {i['texto']}" for i in its[:15])
    print(texto)
    if enviar and its:
        ENVIAR(texto)
    return its
