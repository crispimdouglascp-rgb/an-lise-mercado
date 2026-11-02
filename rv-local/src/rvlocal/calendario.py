"""Dia útil e janela de pregão."""
from __future__ import annotations

from datetime import date, datetime

from .util import config


def feriados() -> set[str]:
    return set(config("feriados.toml").get("dias", []))


def dia_util(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in feriados()


def na_janela(agora: datetime, inicio: str, fim: str) -> bool:
    h = agora.strftime("%H:%M")
    return inicio <= h <= fim
