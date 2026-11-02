"""Reproduz os defeitos D1, D2 e D3 do diagnóstico (docs/01-diagnostico.md, seção 4.2).

Uso, a partir da raiz do repositório:
    H=$(mktemp -d) && mkdir -p $H/data/diario $H/data/state && cp -r rv-local/config $H/
    RVLOCAL_HOME=$H python docs/evidencias/reproducao_defeitos.py rv-local/src

Não altera nada em rv-local/. Usa uma pasta temporária (RVLOCAL_HOME).
"""
import json, sys
from datetime import datetime
sys.path.insert(0, sys.argv[1])
from rvlocal import fontes, razao, diario, series
from rvlocal.util import BRT

print("== Bug 1: staleness escondido por max(ts) ==")
ontem = fontes.Cotacao("PETR4", 36.00, 35.9, datetime(2026,11,3,17,55,tzinfo=BRT), "yahoo")
hoje  = fontes.Cotacao("PETR4", 36.10, 36.0, datetime(2026,11,4,17,55,tzinfo=BRT), "brapi")
l = fontes.consolidar("PETR4", [lambda: ontem, lambda: hoje], 0.5)
print("status:", l.status, "| preco gravado:", l.preco, "(do yahoo, de ONTEM) | ts usado:", l.ts.date())

print("== Bug 2: caixa negativo passa na validação ==")
ops = [{"id":"1","data":"2026-11-03","tipo":"aporte","valor":1000.0},
       {"id":"2","data":"2026-11-03","tipo":"compra","ativo":"PETR4","qtd":1000,"preco":36.0,"tese_id":"H","gatilho":"g","horizonte":"h"}]
est = razao.calcular_estado(ops)
print("caixa:", est.caixa, "| problemas de validação de caixa:", [p for p in razao.validar(ops) if "caixa" in p])

print("== Bug 3: dia com lacuna apaga o retorno do período do acumulado ==")
import os
from pathlib import Path
home = Path(os.environ["RVLOCAL_HOME"])
(home/"data/ativos.json").write_text(json.dumps({"PETR4":{"setor":"x"}}))
(home/"data/hipoteses.json").write_text("[]")
(home/"data/operacoes.jsonl").write_text("\n".join(json.dumps(o) for o in [
 {"id":"1","data":"2026-11-03","tipo":"aporte","valor":0.0},
 {"id":"2","data":"2026-11-03","tipo":"aporte","valor":36000.0},
 {"id":"3","data":"2026-11-03","tipo":"compra","ativo":"PETR4","qtd":1000,"preco":36.0,"tese_id":"","gatilho":"g","horizonte":"h"}]))
# 03: 36 | 04: SEM PREÇO (subiu p/ 40) | 05: 40 | 06: 40
(home/"data/fechamentos.json").write_text(json.dumps({"2026-11-03":{"PETR4":36.0},"2026-11-05":{"PETR4":40.0},"2026-11-06":{"PETR4":40.0}}))
import io, contextlib
for d in ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]:
    with contextlib.redirect_stdout(io.StringIO()):
        s = diario.fechar_dia(d, enviar=False)
    print(d, "patrimonio", s["patrimonio"], "ret_dia", s["retorno_dia_pct"], "acum", s["retorno_acumulado_pct"])
print("Retorno real do período: +11,11% (36 -> 40). O acumulado mostra 0%.")
