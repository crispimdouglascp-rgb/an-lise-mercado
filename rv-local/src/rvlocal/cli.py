"""Linha de comando.  python -m rvlocal <comando>"""
from __future__ import annotations

import argparse
import sys

from . import diario, razao
from .coleta import coletar
from .vigilancia import vigiar


def _validar(_a) -> int:
    probs = razao.validar()
    if probs:
        print("RAZÃO COM PROBLEMAS:")
        for p in probs:
            print(" -", p)
        return 1
    print("razão ok")
    return 0


def _testar_fontes(_a) -> int:
    from . import fontes
    for nome, fn in [("yahoo PETR4", lambda: fontes.fetch_yahoo("PETR4.SA")),
                     ("brapi PETR4", lambda: fontes.fetch_brapi("PETR4")),
                     ("yahoo IBOV", lambda: fontes.fetch_yahoo("^BVSP")),
                     ("bcb dólar", fontes.fetch_bcb_dolar)]:
        try:
            print(f"OK   {nome}: {fn()}")
        except Exception as e:  # noqa: BLE001
            print(f"FALHOU {nome}: {e}")
    return 0


def _registrar_decisao(a) -> int:
    razao.registrar_decisao({"data": a.data, "tipo": a.tipo, "ativo": a.ativo, "decisao": a.decisao,
                             "motivo": a.motivo})
    print("decisão registrada")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rvlocal")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("validar", help="valida o razão").set_defaults(f=_validar)
    sp.add_parser("testar-fontes", help="testa as APIs de preço").set_defaults(f=_testar_fontes)

    c = sp.add_parser("coletar")
    c.add_argument("--modo", choices=["manha", "flash", "fechamento"], required=True)
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(f=lambda a: (coletar(a.modo, a.forcar), 0)[1])

    v = sp.add_parser("vigiar")
    v.add_argument("--forcar", action="store_true")
    v.add_argument("--sem-envio", action="store_true")
    v.set_defaults(f=lambda a: (vigiar(a.forcar, not a.sem_envio), 0)[1])

    f = sp.add_parser("fechar")
    f.add_argument("--data")
    f.add_argument("--sem-envio", action="store_true")
    f.set_defaults(f=lambda a: (diario.fechar_dia(a.data, not a.sem_envio), 0)[1])

    d = sp.add_parser("decisao", help="registra decisão (stop/realizacao)")
    d.add_argument("--data", required=True)
    d.add_argument("--tipo", choices=["stop", "realizacao"], required=True)
    d.add_argument("--ativo", required=True)
    d.add_argument("--decisao", required=True)
    d.add_argument("--motivo", required=True)
    d.set_defaults(f=_registrar_decisao)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
