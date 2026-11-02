"""Regras da carteira, conferidas em código. O modelo não opina sobre aderência."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from .razao import Estado, valor_carteira


@dataclass
class Violacao:
    regra: str
    severidade: str  # alta | media | info
    ativo: str | None
    detalhe: str

    def dict(self) -> dict:
        return asdict(self)


def _semana(d: date) -> tuple[str, str]:
    ini = d - timedelta(days=d.weekday())
    return ini.isoformat(), (ini + timedelta(days=6)).isoformat()


def checar(
    est: Estado,
    precos: dict[str, float],
    ativos: dict[str, dict],
    regras: dict,
    ops: list[dict],
    decisoes: list[dict],
    dia: date,
) -> list[Violacao]:
    out: list[Violacao] = []
    patrimonio, sem_preco = valor_carteira(est, precos)
    for a in sem_preco:
        out.append(Violacao("lacuna_preco", "info", a, f"{a} sem preço confiável; fora do cálculo de pesos."))
    if patrimonio <= 0:
        return out

    cart = regras["carteira"]
    pesos: dict[str, float] = {}
    por_setor: dict[str, float] = {}
    for a, pos in est.posicoes.items():
        p = precos.get(a)
        if p is None:
            continue
        w = pos.qtd * p / patrimonio * 100
        pesos[a] = w
        setor = ativos.get(a, {}).get("setor", "sem setor")
        por_setor[setor] = por_setor.get(setor, 0.0) + w
        if w > cart["teto_posicao_pct"]:
            out.append(Violacao("teto_posicao", "alta", a,
                                f"{a} pesa {w:.1f}% (teto {cart['teto_posicao_pct']}%)."))
        if w < cart["piso_posicao_pct"]:
            out.append(Violacao("piso_posicao", "media", a,
                                f"{a} pesa {w:.1f}% (piso {cart['piso_posicao_pct']}%)."))
    for setor, w in por_setor.items():
        if w > cart["teto_setor_pct"]:
            out.append(Violacao("teto_setor", "alta", None,
                                f"Setor {setor} soma {w:.1f}% (teto {cart['teto_setor_pct']}%)."))
    caixa_pct = est.caixa / patrimonio * 100
    if caixa_pct < cart["caixa_minimo_pct"]:
        out.append(Violacao("caixa_minimo", "media", None,
                            f"Caixa em {caixa_pct:.1f}% (mínimo {cart['caixa_minimo_pct']}%)."))

    # stop e realização
    hoje_iso = dia.isoformat()
    validade = regras["alvo"].get("validade_decisao_dias", 7)
    for a, pos in est.posicoes.items():
        p = precos.get(a)
        par = ativos.get(a, {})
        if p is None:
            continue
        stop = par.get("stop")
        if stop is not None and p <= stop and regras["stop"]["exige_decisao_registrada"]:
            ok = any(d["ativo"] == a and d["tipo"] == "stop" and d["data"] == hoje_iso for d in decisoes)
            if not ok:
                out.append(Violacao("stop_sem_decisao", "alta", a,
                                    f"{a} a {p:.2f} está no/abaixo do stop {stop:.2f} sem decisão registrada hoje."))
        alvo = par.get("alvo")
        if alvo is not None:
            gatilho = alvo * regras["alvo"]["realizar_em_pct_do_alvo"] / 100
            if p >= gatilho:
                ini = (dia - timedelta(days=validade)).isoformat()
                ok = any(d["ativo"] == a and d["tipo"] == "realizacao" and ini <= d["data"] <= hoje_iso
                         for d in decisoes)
                if not ok:
                    out.append(Violacao("realizacao_sem_decisao", "media", a,
                                        f"{a} a {p:.2f} passou de {regras['alvo']['realizar_em_pct_do_alvo']}% "
                                        f"do alvo ({alvo:.2f}) sem decisão de realização registrada."))

    # operações da semana: tese obrigatória e giro
    ini, fim = _semana(dia)
    da_semana = [o for o in ops if o["tipo"] in {"compra", "venda"} and ini <= o["data"] <= min(fim, hoje_iso)]
    if regras["operacoes"]["exige_tese"]:
        for o in da_semana:
            faltam = [c for c in ("tese_id", "gatilho", "horizonte") if not o.get(c)]
            if faltam:
                out.append(Violacao("operacao_sem_tese", "alta", o["ativo"],
                                    f"{o['tipo']} de {o['ativo']} em {o['data']} sem {', '.join(faltam)}."))
    if len(da_semana) > regras["operacoes"]["max_ordens_semana"]:
        out.append(Violacao("excesso_giro", "media", None,
                            f"{len(da_semana)} ordens na semana (máx. {regras['operacoes']['max_ordens_semana']})."))
    return out


def pesos(est: Estado, precos: dict[str, float]) -> dict[str, float]:
    patrimonio, _ = valor_carteira(est, precos)
    if patrimonio <= 0:
        return {}
    return {a: pos.qtd * precos[a] / patrimonio * 100 for a, pos in est.posicoes.items() if a in precos}
