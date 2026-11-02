"""A mesa de pendências: alertas que exigem uma decisão sua, com prazo.

Livro: data/livros/alertas.jsonl (só por acréscimo). Eventos:
  {"evento": "abertura", "id", "chave", "data", "regra", "severidade", "ativo", "motivo",
   "evidencia", "acao_requerida", "prazo", "origem"}
  {"evento": "resolvido", "id", "em", "decisao_id"}      decisão registrada
  {"evento": "encerrado", "id", "em", "motivo"}          condição desapareceu

Status calculado: aberto | vencido (prazo passou sem decisão) | resolvido | encerrado.
Resolvido depois do prazo conta como atraso no boletim. Nada é executado: informação, nunca ordem.
"""
from __future__ import annotations

from datetime import date

from . import livros
from .calendario import somar_dias_uteis
from .util import config

# Que tipo de decisão resolve que regra (para decisões sem alerta_id, no mesmo ativo)
RESOLVE = {
    "stop": {"stop_sem_decisao", "stop_intradiario"},
    "realizacao": {"realizacao_sem_decisao", "alvo", "perto_do_alvo"},
}
QUALQUER_DO_ATIVO = {"saida", "reduzir", "manter", "aumentar", "revisao", "hedge"}

ACOES = {
    "stop_sem_decisao": "Registrar decisão de stop: sair, reduzir ou manter (com a nova invalidação).",
    "stop_intradiario": "O preço tocou o stop no pregão. Registrar decisão de stop.",
    "realizacao_sem_decisao": "Registrar decisão de realização: vender parte, tudo, ou manter e por quê.",
    "teto_posicao": "Reduzir a posição ou registrar decisão de manter com justificativa.",
    "teto_setor": "Reduzir exposição ao setor ou registrar decisão (com alerta_id).",
    "caixa_minimo": "Recompor caixa ou registrar decisão (com alerta_id).",
    "piso_posicao": "Aumentar, encerrar ou justificar a posição pequena.",
}


def _prazo_dias(regra: str) -> int:
    cfg = config("regras.toml").get("mesa", {})
    return int(cfg.get(regra, cfg.get("padrao_dias_uteis", 2)))


def _eventos() -> list[dict]:
    return livros.ler("alertas")


def estado(ate: str | None = None, decisoes: list[dict] | None = None) -> list[dict]:
    """Alertas com status calculado na data `ate` (padrão: todos os eventos)."""
    from . import razao
    decisoes = razao.carregar_decisoes() if decisoes is None else decisoes
    alertas: dict[str, dict] = {}
    for e in _eventos():
        if ate and (e.get("data") or e.get("em") or "") > ate:
            continue
        if e.get("evento") == "abertura":
            alertas[e["id"]] = {**e, "status": "aberto"}
        elif e["id"] in alertas:
            a = alertas[e["id"]]
            a["status"] = e["evento"]
            a["fechado_em"] = e.get("em")
            if e.get("decisao_id"):
                a["decisao_id"] = e["decisao_id"]
            if e.get("motivo"):
                a["motivo_fechamento"] = e["motivo"]
    # resolução dinâmica por decisões ainda não refletidas no livro
    for a in alertas.values():
        if a["status"] != "aberto":
            continue
        d = decisao_que_resolve(a, decisoes, ate)
        if d:
            a.update(status="resolvido", fechado_em=d["data"], decisao_id=d.get("id"))
    hoje = ate or date.today().isoformat()
    for a in alertas.values():
        if a["status"] == "aberto" and a.get("prazo") and a["prazo"] < hoje:
            a["status"] = "vencido"
        if a["status"] == "resolvido":
            a["no_prazo"] = (a.get("fechado_em") or "") <= (a.get("prazo") or "9999")
    return sorted(alertas.values(), key=lambda a: (a.get("prazo") or "", a["id"]))


def decisao_que_resolve(a: dict, decisoes: list[dict], ate: str | None = None) -> dict | None:
    for d in decisoes:
        if ate and d.get("data", "") > ate:
            continue
        if d.get("alerta_id") == a["id"]:
            return d
        if d.get("alerta_id") or not a.get("ativo") or d.get("ativo") != a.get("ativo"):
            continue
        if d.get("data", "") < a["data"]:
            continue
        if a["regra"] in RESOLVE.get(d.get("tipo"), set()) or d.get("tipo") in QUALQUER_DO_ATIVO:
            return d
    return None


def sincronizar(dia: str, condicoes: list[dict], origem: str, encerrar_ausentes: bool = True) -> list[dict]:
    """Abre pendências para condições novas e encerra as que sumiram (da mesma origem).

    `condicoes`: [{chave, regra, severidade, ativo, motivo, evidencia, acao_requerida?}]
    """
    atuais = estado(dia)
    abertas = {a["chave"]: a for a in atuais if a["status"] in {"aberto", "vencido"}}
    novas = []
    chaves_hoje = set()
    for c in condicoes:
        chaves_hoje.add(c["chave"])
        if c["chave"] in abertas:
            continue
        prazo = somar_dias_uteis(date.fromisoformat(dia), _prazo_dias(c["regra"])).isoformat() \
            if _prazo_dias(c["regra"]) > 0 else dia
        reg = {"evento": "abertura", "id": livros.proximo_id("alertas", "AL", dia), "data": dia,
               "origem": origem, "prazo": prazo,
               "acao_requerida": c.get("acao_requerida") or ACOES.get(c["regra"], "Registrar decisão."),
               **{k: c.get(k) for k in ("chave", "regra", "severidade", "ativo", "motivo", "evidencia")}}
        novas.append(livros.anexar("alertas", reg))
    # gravar resoluções por decisão (para o livro refletir o estado)
    for a in atuais:
        if a["status"] == "resolvido" and not any(e.get("evento") == "resolvido" and e["id"] == a["id"]
                                                  for e in _eventos()):
            livros.anexar("alertas", {"evento": "resolvido", "id": a["id"], "em": a["fechado_em"],
                                      "decisao_id": a.get("decisao_id")})
    if encerrar_ausentes:
        for ch, a in abertas.items():
            if a.get("origem") == origem and ch not in chaves_hoje and a["data"] < dia:
                livros.anexar("alertas", {"evento": "encerrado", "id": a["id"], "em": dia,
                                          "motivo": "condição deixou de ocorrer"})
    return novas


def de_violacoes(violacoes, ignorar: set[str] | None = None) -> list[dict]:
    ignorar = ignorar or set()
    out = []
    for v in violacoes:
        if v.severidade == "info" or v.regra in ignorar:
            continue
        out.append({"chave": v.chave, "regra": v.regra, "severidade": v.severidade, "ativo": v.ativo,
                    "motivo": v.detalhe, "evidencia": {"valor": v.valor, "limite": v.limite, "ref": v.ref}})
    return out
