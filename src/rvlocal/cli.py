"""Linha de comando.  python -m rvlocal <comando>   (python -m rvlocal -h para a lista)"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import diario, livros, razao


def _hoje(a) -> date:
    from .util import hoje
    return date.fromisoformat(a.data) if getattr(a, "data", None) else hoje()


def _validar(_a) -> int:
    from . import calendario, hipoteses, instrumentos, teses
    probs = razao.validar() + instrumentos.validar() + teses.validar() + hipoteses.validar_livro() \
        + livros.validar_naturezas() + livros.verificar_imutabilidade()
    av = calendario.aviso_calendario(_hoje(_a))
    if av:
        print("aviso:", av)
    if probs:
        print("LIVROS COM PROBLEMAS:")
        for p in probs:
            print(" -", p)
        return 1
    print("livros ok")
    return 0


def _testar_fontes(_a) -> int:
    from . import fontes
    falhas = 0
    for nome, fn in [("yahoo PETR4", lambda: fontes.fetch_yahoo("PETR4.SA")),
                     ("brapi PETR4", lambda: fontes.fetch_brapi("PETR4")),
                     ("yahoo IBOV", lambda: fontes.fetch_yahoo("^BVSP")),
                     ("yahoo S&P 500", lambda: fontes.fetch_yahoo("^GSPC")),
                     ("bcb dólar", fontes.fetch_bcb_dolar)]:
        try:
            print(f"OK   {nome}: {fn()}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"FALHOU {nome}: {e}")
    return 1 if falhas else 0


def _decisao(a) -> int:
    from . import decisoes
    d = {"data": a.data, "tipo": a.tipo, "ativo": a.ativo, "decisao": a.decisao, "motivo": a.motivo}
    if a.alerta:
        d["alerta_id"] = a.alerta
    if a.nova_invalidacao:
        d["nova_invalidacao"] = a.nova_invalidacao
    r = decisoes.registrar(d)
    print(f"decisão registrada: {r['id']}")
    return 0


def _operar(a) -> int:
    from . import decisoes, instrumentos
    cad = instrumentos.carregar()
    if a.ativo not in cad:
        print(f"{a.ativo} não está em data/livros/instrumentos.json. Cadastre o instrumento primeiro.")
        return 1
    dia = _hoje(a).isoformat()
    lado = "compra" if a.tipo == "compra" else "venda"
    chk = decisoes.completar({
        "tese_id": a.tese, "justificativa": a.justificativa, "preco_entrada": a.preco, "horizonte": a.horizonte,
        "tamanho_pct": a.tamanho_pct, "risco_max_pct": a.risco_max_pct,
        "invalidacao": a.stop if a.stop is not None else a.invalidacao, "objetivo": a.alvo,
        "risco_retorno": a.risco_retorno}, lado)
    frac, faltam = decisoes.completude(chk)
    moeda = instrumentos.moeda(a.ativo, cad)
    op = {"data": dia, "tipo": a.tipo, "ativo": a.ativo, "qtd": a.qtd, "preco": a.preco, "custos": a.custos}
    if moeda != "BRL":
        op["moeda"] = moeda
        if a.cambio:
            op["cambio"] = a.cambio
    ops = razao.carregar_operacoes()
    op["id"] = f"op-{dia}-{sum(1 for o in ops if o['data'] == dia) + 1:03d}"
    probs = [p for p in razao.validar(ops + [op]) if p not in razao.validar(ops)]
    print(f"\n{a.tipo.upper()} {a.qtd:g} {a.ativo} a {a.preco} {moeda} (+ custos {a.custos}) em {dia}")
    print(f"Checklist: {frac * 9:.0f}/9" + (f"  faltam: {', '.join(faltam)}" if faltam else "  completo"))
    if chk.get("risco_retorno") is not None:
        print(f"Risco-retorno: {chk['risco_retorno']}")
    if probs:
        print("RECUSADA, o razão ficaria inconsistente:")
        for p in probs:
            print(" -", p)
        return 1
    if faltam and not a.aceito_incompleto:
        print("\nRecusada: checklist incompleto. Complete os itens ou use --aceito-incompleto "
              "(a operação vai pontuar menos no boletim; sem tese pontua zero).")
        return 1
    if not a.sim:
        if input("Confirma o registro? Nada é enviado à corretora. [s/N] ").strip().lower() not in {"s", "sim"}:
            print("nada gravado.")
            return 1
    tipo_dec = {"compra": "entrada", "venda": "saida"}[a.tipo] if not a.tipo_decisao else a.tipo_decisao
    d = decisoes.registrar({"data": dia, "tipo": tipo_dec, "ativo": a.ativo, "decisao": a.tipo,
                            "motivo": a.justificativa or "(sem justificativa)", "checklist": chk,
                            "alerta_id": a.alerta})
    op["decisao_id"] = d["id"]
    if a.tese:
        op["tese_id"] = a.tese
    razao.registrar_operacao(op)
    print(f"gravado: decisão {d['id']} + operação {op['id']}")
    return 0


def _tese(a) -> int:
    from . import teses
    ficha = json.loads(open(a.arquivo, encoding="utf-8").read())
    if a.motivo:
        ficha["motivo_mudanca"] = a.motivo
    r = teses.nova_versao(ficha, _hoje(a))
    print(f"ficha {r['tese_id']} versão {r['versao']} gravada ({r['ativo']})")
    return 0


def _hipotese(a) -> int:
    from . import hipoteses
    if a.arquivo:
        h = json.loads(open(a.arquivo, encoding="utf-8").read())
        h.setdefault("formulada_em", _hoje(a).isoformat())
        r = hipoteses.registrar(h)
        print(f"hipótese {r['id']} registrada com status {r['status']}")
    elif a.ativar or a.encerrar:
        hid = a.ativar or a.encerrar
        hipoteses.mudar_status(hid, "ativa" if a.ativar else "encerrada", _hoje(a).isoformat(), a.motivo or "")
        print(f"hipótese {hid}: {'ativada' if a.ativar else 'encerrada'}")
    else:
        for p in hipoteses.placar_v2():
            print(f"{p['id']:<10} {p['veredito']:<26} favor {p['favor']} contra {p['contra']} neutro {p['neutro']}"
                  + (f"  IC95 {p['ic95_pct']}" if p['ic95_pct'] else "") + f"  {p['titulo']}")
    return 0


def _mesa(a) -> int:
    from . import mesa
    for x in mesa.estado(_hoje(a).isoformat()):
        if x["status"] in {"aberto", "vencido"} or a.todas:
            print(f"[{x['status']:<9}] {x['id']} prazo {x['prazo']} {x['severidade']:<5} {x['motivo']}")
    return 0


def _boletim(a) -> int:
    from . import boletim
    b = boletim.emitir(a.tipo, _hoje(a))
    print(f"Boletim {b['tipo']} {b['inicio']}..{b['fim']} edição {b['edicao']}: {b['letra']} "
          f"{b['nota_final']:.3f}/5" + (" (PARCIAL)" if b["cobertura"]["parcial"] else ""))
    for k, c in b["criterios"].items():
        n = "sem base" if c["nota"] is None else f"{c['nota']:.1f}"
        print(f"  {c['nome']:<28} {c['peso']:>3}%  {n:>8}   {c['evidencias'][0] if c['evidencias'] else ''}")
    for t in b["tetos_aplicados"]:
        print("  teto:", t)
    return 0


def _fiscal(a) -> int:
    from . import fiscal
    for m in fiscal.apurar(razao.carregar_operacoes(), a.mes or _hoje(a).isoformat()[:7]):
        print(json.dumps(m, ensure_ascii=False))
    return 0


def _painel(a) -> int:
    from .painel import app as painel
    if a.exportar:
        for p in painel.exportar(a.exportar):
            print("gerado:", p)
        return 0
    import uvicorn
    print(f"Painel em http://127.0.0.1:{a.porta}  (Ctrl+C para sair)")
    uvicorn.run(painel.criar_app(), host=a.host, port=a.porta, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rvlocal", description="RV Local: o código calcula; a IA interpreta.")
    sp = p.add_subparsers(dest="cmd", required=True)

    v = sp.add_parser("validar", help="valida livros, razão, fichas, hipóteses e imutabilidade")
    v.add_argument("--data")
    v.set_defaults(f=_validar)
    sp.add_parser("testar-fontes", help="testa as APIs de preço ao vivo").set_defaults(f=_testar_fontes)

    c = sp.add_parser("coletar", help="coleta de preços (manha | flash | fechamento)")
    c.add_argument("--modo", choices=["manha", "flash", "fechamento"], required=True)
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(f=lambda a: (__import__("rvlocal.coleta", fromlist=["x"]).coletar(a.modo, a.forcar), 0)[1])

    vg = sp.add_parser("vigiar", help="vigilância intradiária")
    vg.add_argument("--forcar", action="store_true")
    vg.add_argument("--sem-envio", action="store_true")
    vg.set_defaults(f=lambda a: (__import__("rvlocal.vigilancia", fromlist=["x"]).vigiar(a.forcar, not a.sem_envio), 0)[1])

    f = sp.add_parser("fechar", help="fechamento do dia (também serve de repescagem: --data)")
    f.add_argument("--data")
    f.add_argument("--sem-envio", action="store_true")
    f.set_defaults(f=lambda a: (diario.fechar_dia(a.data, not a.sem_envio), 0)[1])

    cb = sp.add_parser("cobranca", help="07:45: o que o sistema precisa de você")
    cb.add_argument("--data")
    cb.add_argument("--sem-envio", action="store_true")
    cb.set_defaults(f=lambda a: (__import__("rvlocal.cobranca", fromlist=["x"]).executar(_hoje(a), not a.sem_envio), 0)[1])

    d = sp.add_parser("decisao", help="registra decisão (stop, realização, manter...)")
    d.add_argument("--data", required=True)
    d.add_argument("--tipo", required=True,
                   choices=sorted(["entrada", "saida", "aumentar", "reduzir", "stop", "realizacao", "manter",
                                   "hedge", "revisao"]))
    d.add_argument("--ativo")
    d.add_argument("--decisao", required=True)
    d.add_argument("--motivo", required=True)
    d.add_argument("--alerta", help="id da pendência da mesa que esta decisão resolve")
    d.add_argument("--nova-invalidacao", help="ao manter após stop: a nova condição de saída")
    d.set_defaults(f=_decisao)

    o = sp.add_parser("operar", help="registra operação COM decisão e checklist (não envia ordem)")
    o.add_argument("--tipo", choices=["compra", "venda"], required=True)
    o.add_argument("--ativo", required=True)
    o.add_argument("--qtd", type=float, required=True)
    o.add_argument("--preco", type=float, required=True)
    o.add_argument("--custos", type=float, default=0.0)
    o.add_argument("--cambio", type=float, help="câmbio da data, para ativos em moeda estrangeira")
    o.add_argument("--data")
    o.add_argument("--tese")
    o.add_argument("--justificativa")
    o.add_argument("--horizonte")
    o.add_argument("--tamanho-pct", type=float)
    o.add_argument("--risco-max-pct", type=float)
    o.add_argument("--stop", type=float)
    o.add_argument("--invalidacao", help="condição de invalidação em texto (se não houver stop numérico)")
    o.add_argument("--alvo", type=float)
    o.add_argument("--risco-retorno", type=float)
    o.add_argument("--tipo-decisao", choices=["entrada", "aumentar", "saida", "reduzir", "realizacao", "stop"])
    o.add_argument("--alerta")
    o.add_argument("--aceito-incompleto", action="store_true")
    o.add_argument("--sim", action="store_true", help="não perguntar confirmação")
    o.set_defaults(f=_operar)

    t = sp.add_parser("tese", help="grava nova versão de ficha a partir de um JSON")
    t.add_argument("--arquivo", required=True)
    t.add_argument("--motivo")
    t.add_argument("--data")
    t.set_defaults(f=_tese)

    h = sp.add_parser("hipotese", help="registra, ativa (o seu sim), encerra ou lista hipóteses")
    h.add_argument("--arquivo")
    h.add_argument("--ativar")
    h.add_argument("--encerrar")
    h.add_argument("--motivo")
    h.add_argument("--data")
    h.set_defaults(f=_hipotese)

    m = sp.add_parser("mesa", help="pendências abertas e vencidas")
    m.add_argument("--data")
    m.add_argument("--todas", action="store_true")
    m.set_defaults(f=_mesa)

    b = sp.add_parser("boletim", help="emite boletim do gestor (nota 0 a 5)")
    b.add_argument("--tipo", choices=["diario", "semanal", "mensal", "trimestral"], default="semanal")
    b.add_argument("--data")
    b.set_defaults(f=_boletim)

    fi = sp.add_parser("fiscal", help="apuração fiscal mensal (estimativa a validar com o contador)")
    fi.add_argument("--mes")
    fi.add_argument("--data")
    fi.set_defaults(f=_fiscal)

    dp = sp.add_parser("darf-pago", help="registra o pagamento do DARF de um mês (evento no livro)")
    dp.add_argument("--mes", required=True)
    dp.add_argument("--valor", type=float)
    dp.add_argument("--data")
    dp.set_defaults(f=lambda a: (livros.anexar("eventos", {"tipo": "darf_pago", "mes": a.mes, "valor": a.valor,
                                                           "data": _hoje(a).isoformat()}), print("registrado"), 0)[2])

    mg = sp.add_parser("migrar", help="converte os arquivos da fase 1 para os livros")
    mg.set_defaults(f=lambda a: (print("\n".join(__import__("rvlocal.migrar", fromlist=["x"]).migrar())), 0)[1])

    de = sp.add_parser("demo", help="gera uma base DEMO completa numa pasta separada")
    de.add_argument("--destino", default="demo")
    de.set_defaults(f=lambda a: (__import__("rvlocal.demo", fromlist=["x"]).gerar(a.destino), 0)[1])

    pn = sp.add_parser("painel", help="abre o painel web local (ou exporta HTML estático)")
    pn.add_argument("--porta", type=int, default=8765)
    pn.add_argument("--host", default="127.0.0.1")
    pn.add_argument("--exportar", help="pasta para exportar a capa e o balanço em HTML estático")
    pn.set_defaults(f=_painel)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
