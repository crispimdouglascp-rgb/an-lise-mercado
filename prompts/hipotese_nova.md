# Como registrar uma hipótese (antes de operar)

Uma hipótese só entra se o teste puder ser medido por código. Peça ao Claude:

> Transforme esta ideia numa hipótese em JSON para `python -m rvlocal hipotese --arquivo h.json`: [sua ideia].
> Use um dos tipos de teste suportados (`excesso_em_condicao`, `mesma_direcao`, `segue_driver`,
> `diferenca_vs_referencia`, com `gate` opcional), escreva "muda_de_ideia_se", use `origem: "ia"`
> e NÃO ative: eu confirmo com `python -m rvlocal hipotese --ativar <id> --motivo "..."`.

Regras do placar (código, não opinião):
- limiar de ±0,75 pp: entre os dois, o dia é neutro;
- só pontua a partir de `formulada_em` (nunca retroage);
- veredito só com 8+ gates, pelo intervalo de Wilson a 95% contra 50%;
- reescrever o teste = hipótese nova com outro id (a antiga fica com o placar dela).

Tipos de teste: veja o topo de `src/rvlocal/hipoteses.py`.
Tese de investimento (ficha da posição) é outra coisa: `python -m rvlocal tese --arquivo ficha.json`.
