# Como registrar uma hipótese (antes de operar)

Uma hipótese só entra se o teste puder ser medido por código. Peça ao Claude:

> Transforme esta ideia numa hipótese de `data/hipoteses.json`: [sua ideia].
> Use um dos tipos de teste suportados (`excesso_em_condicao`, `mesma_direcao`, `segue_driver`),
> escreva "muda_de_ideia_se" e o limite de falhas para arquivar. Não ative sem eu confirmar.

Tipos de teste: veja o topo de `src/rvlocal/hipoteses.py`.
Regra: tese e teste escritos ANTES da operação. Toda compra/venda leva `tese_id`, `gatilho` e `horizonte`.
