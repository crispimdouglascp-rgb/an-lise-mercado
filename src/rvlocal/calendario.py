"""Dia útil e janela de pregão da B3.

Os feriados são CALCULADOS para qualquer ano (fixos nacionais + móveis a partir da
Páscoa + 24/12 e 31/12, sem pregão na B3). `config/feriados.toml` permite acrescentar
ou remover datas e registra quais anos você já conferiu contra o calendário oficial.
Ano não conferido gera aviso na validação e na cobrança da manhã (nunca silêncio).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from .util import config

FIXOS = ["01-01", "04-21", "05-01", "09-07", "10-12", "11-02", "11-15", "12-25"]
SEM_PREGAO_B3 = ["12-24", "12-31"]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo gregoriano anônimo)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def _cfg() -> dict:
    return config("feriados.toml", {})


@lru_cache(maxsize=64)
def _calculados(ano: int) -> frozenset[str]:
    p = pascoa(ano)
    moveis = [p - timedelta(days=48), p - timedelta(days=47),   # Carnaval (seg e ter)
              p - timedelta(days=2),                             # Sexta-feira Santa
              p + timedelta(days=60)]                            # Corpus Christi
    fixos = FIXOS + (["11-20"] if ano >= 2024 else [])           # Consciência Negra, nacional desde 2024
    return frozenset([f"{ano}-{md}" for md in fixos + SEM_PREGAO_B3] + [d.isoformat() for d in moveis])


def feriados_ano(ano: int) -> set[str]:
    cfg = _cfg()
    extras = set(cfg.get("extras", [])) | set(cfg.get("dias", []))   # "dias" = formato antigo
    remover = set(cfg.get("remover", []))
    return {d for d in (set(_calculados(ano)) | {x for x in extras if x.startswith(str(ano))}) if d not in remover}


def feriados() -> set[str]:
    hoje = date.today().year
    return feriados_ano(hoje) | feriados_ano(hoje + 1)


def dia_util(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in feriados_ano(d.year)


def dias_uteis(inicio: date, fim: date) -> list[date]:
    out, d = [], inicio
    while d <= fim:
        if dia_util(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def somar_dias_uteis(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if dia_util(d):
            n -= 1
    return d


def na_janela(agora: datetime, inicio: str, fim: str) -> bool:
    h = agora.strftime("%H:%M")
    return inicio <= h <= fim


def aviso_calendario(d: date) -> str | None:
    conferidos = set(_cfg().get("anos_conferidos", []))
    faltam = [a for a in (d.year, d.year + 1) if a not in conferidos]
    if faltam:
        return (f"Calendário da B3 não conferido para {', '.join(map(str, faltam))}: feriados calculados, "
                "confira em b3.com.br e registre em config/feriados.toml (anos_conferidos).")
    return None
