"""Vigilância durante o pregão (roda a cada 10 min no GitHub Actions).

Alertas por regra, sem IA: alvo próximo, stop, movimento fora do padrão,
fonte congelada, fontes divergentes. Cada alerta dispara uma vez por dia por chave.
"""
from __future__ import annotations

from . import fontes, razao, series
from .calendario import dia_util, na_janela
from .coleta import ler_tudo
from .notificar import ENVIAR
from .util import agora, anexar_jsonl, config, hoje, ler_jsonl, raiz


def _gerar(leituras: dict[str, fontes.Leitura], ativos: dict, regras: dict, fech: dict, dia: str) -> list[dict]:
    vig, alvo_cfg = regras["vigilancia"], regras["alvo"]
    est = razao.calcular_estado(razao.carregar_operacoes())
    alertas: list[dict] = []
    for s, l in leituras.items():
        em_carteira = s in est.posicoes
        if l.status == "divergente":
            alertas.append({"chave": f"diverge:{s}", "tipo": "fontes_divergentes", "simbolo": s,
                            "texto": f"{s}: fontes divergem {l.divergencia_pct:.2f}% (limite "
                                     f"{vig['divergencia_max_pct']}%). Preço NÃO confiável; sem alertas de preço."})
            continue
        if l.preco is None:
            if em_carteira:
                alertas.append({"chave": f"semdado:{s}", "tipo": "sem_dado", "simbolo": s,
                                "texto": f"{s}: sem cotação de nenhuma fonte. {'; '.join(l.erros)[:200]}"})
            continue
        idade = fontes.idade_min(l.ts)
        if idade is not None and idade > vig["fonte_congelada_min"]:
            alertas.append({"chave": f"congelada:{s}", "tipo": "fonte_congelada", "simbolo": s,
                            "texto": f"{s}: cotação com {idade:.0f} min de idade em pregão. "
                                     "Fonte possivelmente congelada; alertas de preço suspensos."})
            continue
        par = ativos.get(s, {})
        if em_carteira:
            alvo, stop = par.get("alvo"), par.get("stop")
            if stop is not None and l.preco <= stop:
                alertas.append({"chave": f"stop:{s}", "tipo": "stop", "simbolo": s,
                                "texto": f"STOP {s}: {l.preco:.2f} <= {stop:.2f}. Registre a decisão "
                                         "(manter/sair e por quê) hoje."})
            if alvo is not None:
                gap = (alvo / l.preco - 1) * 100
                if l.preco >= alvo:
                    alertas.append({"chave": f"alvo:{s}", "tipo": "alvo", "simbolo": s,
                                    "texto": f"ALVO {s}: {l.preco:.2f} >= {alvo:.2f}. Decida realização."})
                elif gap <= alvo_cfg["alerta_proximidade_pct"]:
                    alertas.append({"chave": f"perto_alvo:{s}", "tipo": "perto_do_alvo", "simbolo": s,
                                    "texto": f"{s} a {l.preco:.2f}, faltam {gap:.1f}% para o alvo {alvo:.2f}."})
        # movimento fora do padrão (referência: fechamento anterior)
        ant = l.anterior or series.ultimo_fechamento_antes(fech, s, dia)
        if ant:
            mov = (l.preco / ant - 1) * 100
            sig = series.sigma_pct(fech, s, dia) or vig["sigma_padrao_pct"]
            if abs(mov) >= vig["movimento_sigma"] * sig:
                alertas.append({"chave": f"mov:{s}:{'alta' if mov > 0 else 'queda'}", "tipo": "movimento",
                                "simbolo": s,
                                "texto": f"{s} {mov:+.2f}% no dia ({abs(mov) / sig:.1f} desvios; "
                                         f"sigma {sig:.2f}%)."})
    return alertas


def vigiar(forcar: bool = False, enviar: bool = True) -> list[dict]:
    ag = agora()
    regras = config("regras.toml")
    vig = regras["vigilancia"]
    if not forcar:
        if not dia_util(ag.date()):
            print("sem pregão hoje.")
            return []
        if not na_janela(ag, vig["janela_inicio"], vig["janela_fim"]):
            print(f"fora da janela {vig['janela_inicio']}-{vig['janela_fim']} ({ag:%H:%M}).")
            return []
    dia = hoje().isoformat()
    leituras = ler_tudo(regras["coleta"]["tolerancia_fontes_pct"])
    candidatos = _gerar(leituras, razao.carregar_ativos(), regras, series.carregar(), dia)

    arq = raiz() / "data" / "state" / f"alertas_{dia}.jsonl"
    ja = {a["chave"] for a in ler_jsonl(arq)}
    novos = [a for a in candidatos if a["chave"] not in ja]
    for a in novos:
        a["hora"] = ag.strftime("%H:%M")
        anexar_jsonl(arq, a)
    if novos and enviar:
        ENVIAR("RV Local " + ag.strftime("%H:%M") + "\n" + "\n".join("• " + a["texto"] for a in novos))
    print(f"vigilância {ag:%H:%M}: {len(candidatos)} condições, {len(novos)} alertas novos.")
    return novos
