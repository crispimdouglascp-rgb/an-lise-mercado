# Fase 2: arquitetura proposta

> Evolução do `rv-local`, sem reescrita. Tudo o que está na seção 4.5 do diagnóstico é reaproveitado.
> Itens marcados **[decisão]** dependem de você (lista consolidada em `03-plano.md`).

## 1. Princípios e como cada um é garantido

| Regra de governança | Mecanismo técnico |
|---|---|
| 1. O código calcula; a IA interpreta | A IA recebe um **pacote de fatos** pronto (JSON). Um validador rejeita o texto que traz número ausente do pacote |
| 2. Nenhum dado inventado | `Leitura` com status; lacuna é lacuna; o validador da IA bloqueia números sem origem |
| 3. Toda informação tem fonte | Todo valor gravado carrega `fonte`, `capturado_em` e `qualidade`; o painel mostra fonte e hora ao passar o mouse |
| 4. Toda decisão tem registro | Livro de decisões append-only; operação de compra/venda sem decisão vinculada é violação |
| 5. Nenhuma operação sem autorização | **Não existe módulo de execução de ordens** nem credencial de corretora. Por desenho, não por configuração |
| 6. Não alterar posições automaticamente | Só o usuário escreve no livro de operações (CLI ou formulário, com confirmação). Captura por print gera **rascunho** que exige "sim" |
| 7. Não sobrescrever histórico | Livros append-only; correção = estorno + nova linha; teste automatizado que falha se uma linha antiga mudar |
| 8. Separar real, demo, estimativa e hipótese | Campo obrigatório `natureza` ∈ {`real`, `demo`, `estimativa`, `hipotese`} em todo registro; selo visual no painel |
| 9. Recomendação com riscos e limitações | Template de saída dos agentes exige as seções "riscos" e "limitações"; o validador confere |
| 10. Segurança | Segredos só em variáveis de ambiente; `.gitignore` para dados reais e banco; repositório privado; nenhuma credencial de corretora |

## 2. Visão geral

```
                    ┌────────────────────────── LIVROS (fonte da verdade, append-only) ──────────────────────────┐
                    │ instrumentos · operacoes · decisoes · teses · hipoteses · placar_hipoteses · eventos ·      │
                    │ alertas · boletins · heartbeat                                       (JSONL, versionado git)│
                    └───────▲─────────────────▲──────────────────▲───────────────────────▲────────────────────────┘
                            │ usuário (CLI/UI)│ código           │ código                │ IA (só rascunho)
┌───────────────┐   ┌───────┴───────┐  ┌──────┴────────┐  ┌──────┴──────────┐   ┌────────┴──────────┐
│ 01 COLETA     │──►│ SÉRIES        │─►│ 02 VIGILÂNCIA │─►│ 04 PLACAR       │   │ 03 SÍNTESE (IA)   │
│ fontes ×2,    │   │ mercado.db    │  │ regras, risco,│  │ hipóteses,      │   │ lê pacote de fatos│
│ consolidação, │   │ (SQLite)      │  │ alertas, mesa │  │ boletim 0–5     │   │ escreve, valida   │
│ qualidade     │   └───────────────┘  └───────────────┘  └─────────────────┘   └───────────────────┘
└───────────────┘          │                  │                   │                        ▲
                           └──────────────────┴─────── QUANT · VALUATION · OPÇÕES ──────────┤
                                                       (código, determinístico)             │
                                    VISTAS GERADAS: diario/ risco/ fatos/ relatorios/ painel ─┘
```

**Regra de ouro (da referência):** o que vem de fora entra **uma vez** nos livros ou nas séries; rotinas e agentes leem os livros, nunca o painel; o painel e os relatórios são vistas geradas, nunca a fonte.

## 3. Modelo de dados: os livros

**[decisão D-1] Armazenamento.** Recomendação: **híbrido**.
- **Livros em JSONL append-only, versionados no git.** São pequenos, auditáveis linha a linha e o `git log` vira trilha de auditoria. É o que o projeto já faz.
- **Séries de mercado em SQLite** (`data/mercado.db`). Histórico de 10 anos, barras intradiárias, cadeias de opções e fundamentos não cabem em JSON. São re-coletáveis, então o banco fica fora do git, com backup.

| Livro | Formato | Mutável? | Campos principais |
|---|---|---|---|
| `instrumentos.json` | JSON | Sim, via git (cada mudança gera evento) | `ticker`, `classe` (acao, fii, etf, bdr, acao_ext, opcao, rf, cripto, caixa), `moeda`, `pais`, `setor`, `fatores`, `receita_usd_pct`, `subjacente`, `lote`, `fonte_preco` |
| `operacoes.jsonl` | JSONL | **Não** | atual + `moeda`, `cambio`, `corretora`, `decisao_id`, `natureza`, `estorna` |
| `decisoes.jsonl` | JSONL | **Não** | `id`, `data`, `tipo` (entrada, saida, stop, realizacao, manter, reduzir, hedge), `ativo`, checklist pré-operação, `alerta_id`, `prazo`, `origem` |
| `teses.jsonl` | JSONL (versões) | **Não**; nova versão por mudança | `tese_id`, `versao`, `ativo`, texto, premissas, preço justo, cenários, catalisadores, invalidação, rating, `motivo_mudanca` |
| `hipoteses.jsonl` | JSONL (versões) | **Não**; reescrever = nova hipótese | `id`, `origem` (ia, usuario), `status` (rascunho, ativa, encerrada), `formulada_em`, teste, `limiar_pp`, `min_gates` |
| `placar_hipoteses.jsonl` | JSONL | **Não** | `hipotese_id`, `data`, `gate_aberto`, `valor_pp`, `veredito` (favor, neutro, contra, sem_dado), `fonte_dados` |
| `eventos.jsonl` | JSONL | **Não** | resultados, proventos, desdobramentos, fatos relevantes, Copom, notícias citadas (com URL) |
| `alertas.jsonl` | JSONL | **Não**; mudança de status = nova linha | `id`, `regra`, `severidade`, `evidencia`, `motivo`, `acao_requerida`, `prazo`, `status` |
| `boletins.jsonl` | JSONL | **Não**; revisão = nova edição com `revisa` | período, notas por critério, evidências, tetos aplicados, cobertura, nota final, letra |
| `heartbeat.jsonl` | JSONL | **Não** | `rotina`, `inicio`, `fim`, `status`, `duracao`, `erro` |

**Garantia de imutabilidade:** um teste compara o prefixo de cada livro com o último commit. Se uma linha antiga mudou, o teste falha e o workflow não grava.

Tabelas do `mercado.db`: `precos_diarios`, `precos_intraday`, `cambio`, `macro`, `fundamentos`, `opcoes_cadeia`, `proventos`. Todas com `(simbolo, data, valor, fonte, capturado_em, status, qualidade)`. Cargas grandes: escrever numa cópia, validar e trocar o arquivo (lição do Update #5).

**Vistas geradas** (regeneráveis, podem ser apagadas): `data/gerado/diario/`, `risco/`, `fatos/`, `relatorios/`, `painel/`.

## 4. Camada 01: Coleta

### 4.1 Registro de fontes

Interface única por adaptador: `cotacao()`, `historico()`, `metadados()`. Cada adaptador declara cobertura, atraso e se é oficial.

| Dado | Fonte primária | Fonte de conferência | Observação |
|---|---|---|---|
| Ações, FIIs, ETFs e BDRs da B3 | brapi | Yahoo | Já implementado (falta teste ao vivo) |
| Histórico B3 sem viés de sobrevivência | COTAHIST (arquivos oficiais da B3, incluem papéis deslistados) | brapi/Yahoo | Base do backtest |
| Opções B3 | brapi Pro **[decisão D-5]** | COTAHIST (fim do dia) | A referência assina o brapi Pro |
| Dólar | Yahoo (intradiário) | BCB PTAX / SGS 1 | Conferência já existe |
| Selic, CDI, IPCA | BCB SGS | Tesouro / IBGE | Oficial |
| Expectativas (Focus) | BCB Olinda | Fonte única esperada | Marcado como tal |
| Juro real (NTN-B) | Tesouro Direto | ANBIMA | |
| Ações e ETFs EUA | Yahoo | Stooq ou outra | |
| Macro EUA | FRED | Fonte única esperada | |
| Fundamentos BR | CVM dados abertos (DFP/ITR) | brapi | Oficial |
| Fundamentos EUA | SEC EDGAR | Fonte única esperada | Oficial |
| Eventos e resultados | CVM (fatos relevantes), calendários de RI, lançamento manual | | Notícia só entra com URL |

### 4.2 Qualidade do dado

O `Leitura.status` atual (`ok`, `fonte_unica`, `fonte_unica_esperada`, `divergente`, `sem_dado`) ganha uma **idade** calculada pela fonte mais velha (correção D1). Cada valor é gravado com status e idade. Regras: só `ok` e `fonte_unica_esperada` entram no fechamento; `divergente` nunca vira média; ativo sem preço nunca é estimado.

## 5. Camada 02: Vigilância e risco

### 5.1 Três motores, todos em código

1. **Regras** (`regras.py`, estendido): as atuais, mais exposição por classe, país e moeda, limite por fator, plano de stop, nível de compra e saída em campos separados, risco de opções, liquidez e concentração de vencimentos.
2. **Risco** (`risco.py`, novo): grava `gerado/risco/<dia>.json` a cada pregão.
3. **Vigilância intradiária** (atual): alerta de alvo, stop, movimento > 2σ, fonte congelada e divergência, com os limites corretos (D13).

### 5.2 Monitor de risco

**Nível 1, patrimônio** (bandas em `config/risco.toml`, exemplo da referência: RF 40 · RV 30 · Fundos 10 · Cripto 5 · USD 15): alocação real × alvo com banda; exposição cambial total, incluindo receita em dólar das empresas (`receita_usd_pct`); liquidez por prazo; concentração por emissor.

**Nível 2, sleeve de renda variável:**

| Métrica | Definição | Mínimo de dados |
|---|---|---|
| Pesos, por setor, país, moeda e fator | valor de mercado ÷ patrimônio | 1 pregão |
| HHI | Σ pesos² | 1 pregão |
| Volatilidade | desvio-padrão de 60 pregões e EWMA (λ = 0,94), anualizada √252 | 20 pregões |
| Beta | regressão contra IBOV / S&P 500 em 252 pregões | 60 pregões |
| Correlação | matriz de 120 pregões | 60 pregões |
| Drawdown | pico a vale do TWR, por ativo e consolidado | 1 pregão |
| VaR e CVaR 1 dia, 95% | simulação histórica | **250 pregões**; antes disso: "insuficiente", nunca estimado |
| Contribuição ao risco | peso × covariância marginal ÷ volatilidade da carteira | 60 pregões |
| Stress pré-registrado | cenários em `config/stress.toml` (choques em IBOV, dólar, juro e setores) → P&L | Cenário escrito antes |
| Liquidez | dias para zerar com 20% do volume médio | 20 pregões |
| Opções | delta/gama/vega agregados, nocional de exercício × caixa, vencimentos | Ver seção 9 |

Até haver histórico próprio, o backfill vem do Yahoo ou do COTAHIST, marcado com a fonte.

### 5.3 Alertas e a "mesa"

Formato único de alerta, conforme pedido:

```json
{"id": "AL-2026-11-04-007", "regra": "teto_setor", "severidade": "alta",
 "motivo": "Setor bancos acima do teto",
 "evidencia": {"valor_pct": 43.1, "limite_pct": 40, "fonte": "fechamento 04/11 18:00, brapi+yahoo ok"},
 "acao_requerida": "Registrar decisão: reduzir, manter com justificativa ou ajustar o limite",
 "prazo": "2026-11-06", "status": "aberto"}
```

Alertas abertos formam a **mesa de pendências**. Pendência vencida sem decisão vira violação e penaliza o boletim. Nada é executado: "informação, nunca ordem".

## 6. Camada 03: Síntese com IA

### 6.1 O executor de agentes

```
código monta pacote de fatos ──► prompt versionado ──► modelo ──► VALIDADOR ──► publica
 (gerado/fatos/<rotina>_<dia>.json)  (prompts/*.md)                    │
                                                                       └─ reprovou: publica só os números,
                                                                          gerados por template, + alerta
```

Regras do validador (código):
1. Todo número citado precisa existir no pacote de fatos (tolerância só de formatação).
2. Afirmação causal precisa de fonte no pacote; sem fonte, o texto deve dizer "causa não verificada".
3. Seções obrigatórias por agente (por exemplo, "riscos" e "limitações").
4. Teto de tamanho por saída.
5. A IA não escreve em livro nenhum, exceto **rascunhos** (hipótese ou premissa) com `origem=ia`, que só valem depois do seu "sim".

Cada saída é gravada com o prompt (versão), o hash do pacote de fatos, o modelo e o horário.

**[decisão D-3] Onde a IA roda.** (a) Tarefas agendadas do Claude com o repositório anexado (modelo atual, sem chave de API); ou (b) chamada pela API a partir do próprio código (exige `ANTHROPIC_API_KEY` como segredo). O executor terá os dois modos. O modelo fica configurável.

### 6.2 Os cinco agentes

| Agente | Quando | O código entrega | A IA faz | A IA não faz |
|---|---|---|---|---|
| 1. Briefing matinal | 08:30 | Movimentos da madrugada (séries), agenda do dia (eventos), posições perto de alvo/stop, hipóteses com gate possível hoje, pendências | Cenário internacional e brasileiro, o que merece atenção, riscos e oportunidades, **hipóteses em jogo hoje** (só as já registradas, ou novas como rascunho) | Criar número, recomendar ordem |
| 2. Teses | Sob demanda e semanal | Ficha atual, números do laboratório de valuation, fundamentos, eventos | Redige tese, fundamentação, vantagens, riscos, catalisadores e cenários; **extrai premissas testáveis** para sua confirmação | Calcular preço justo (é do código) |
| 3. Intradiário | Só quando a vigilância dispara | Alerta, série do dia, notícias com URL | Contextualiza em até 3 frases; sem fonte → "causa não verificada" | Confundir correlação com causa |
| 4. Auditor | A cada operação registrada, e na sexta | Checklist calculado, regras, histórico da tese | Crítica independente, perguntas que você deveria ter respondido | Alterar nota |
| 5. Encerramento | 18:15 | Diário, placar do dia, alertas, pendências | Confronta as hipóteses da manhã com o que aconteceu (evolução do `recap_1815.md`) | Recalcular |

Agentes extras de cadência (da referência): **Retrô** (sexta, a semana) e **comentário do Boletim** (sábado). A nota do boletim já chega pronta; a IA só comenta.

## 7. Camada 04: Placar

### 7.1 Placar de hipóteses (regras do Update #4)

1. **Sem limiar, não pontua.** Padrão ±0,75 pp contra a referência. Entre os limiares: neutro.
2. **Data de formulação é sagrada.** Só pontua a partir dela; o passado é contexto (corrige D5).
3. **Reescrever = hipótese nova.** A antiga é encerrada com o placar dela.
4. **Ponto é linha**, imutável (corrige D4).
5. **Veredito por conta**: mínimo de 8 gates abertos; taxa = a favor ÷ (a favor + contra); intervalo de Wilson a 95%. Limite inferior > 50% → confirmada; limite superior < 50% → refutada; caso contrário, indefinida. Refutada gera **sugestão** de arquivar.
6. **Origem IA ou usuário**, com placares separados; premissa da IA só conta como sua depois do seu "sim".

Os 3 tipos de teste atuais continuam, acrescidos de `diferenca_vs_referencia` (com gate e limiar) e `relacao` (X↑ → Y↓ em pp).

### 7.2 Boletim do gestor: nota de 0 a 5

Calculado **só por código** (`placar/boletim.py`) para os períodos diário, semanal, mensal e trimestral. Cada critério devolve `{nota, evidencias[], dados_usados}`. Parâmetros em `config/placar.toml`.

| Critério | Peso | Cálculo (proposta, parametrizável) |
|---|---|---|
| Retorno × benchmark | 15% | α = TWR da carteira − benchmark composto (peso de cada sleeve no início × índice da sleeve, ex.: IBOV e S&P 500 em R$). Nota = 2,5 + α ÷ k, limitada a [0, 5]; k = 0,25 pp (dia), 1 pp (semana), 2 pp (mês), 4 pp (trimestre). Evidência: α por sleeve e concentração do ganho (ex.: "o ganho veio de uma ação só") |
| Aderência às regras | 20% | **Violação alta não resolvida no prazo → 0, sem crédito parcial.** Senão: 5 − 1,0 × médias não resolvidas − 0,5 × pendências vencidas (mínimo 0) |
| Gestão de risco | 20% | 5 − Σ penalidades por banda rompida e pregão (alta 1,0; média 0,5), stop atingido com posição mantida sem nova invalidação, nocional de exercício > caixa. Rompimento > 1,5 × limite: nota máxima 1,0 |
| Qualidade das decisões | 15% | Cada operação é medida contra o checklist de 9 itens (completude 0 a 1). **Sem tese = 0** para aquela operação. Nota = 5 × média − 0,5 × operações fora da própria régua (ex.: compra acima do nível registrado; risco-retorno abaixo do mínimo). Sem operações: avalia se as fichas das posições estão revisadas no prazo |
| Construção da carteira | 10% | 5 − 0,5 × posições abaixo do piso − 0,5 × posições sem ficha ou convicção − penalidade por HHI acima do alvo − desvios de alocação fora da banda |
| Execução, custos e fiscal | 10% | 5 − excesso de giro − custos acima de X% do resultado − lançamento coberto sem folga − pendência fiscal (DARF vencido, limite de isenção estourado sem decisão) |
| Realização de resultados | 10% | Posições que cruzaram o gatilho de realização: fração com decisão no prazo × 5 − 0,5 × saídas com perda acima do risco máximo declarado |

**Tetos, que só limitam e nunca sobem a nota** (atendem "retorno positivo não compensa gestão de risco ruim"):
- Aderência = 0 → nota final ≤ 2,0.
- Gestão de risco < 1,5 → nota final ≤ 2,5.
- Cobertura de dados < 60% dos pregões → boletim marcado "parcial"; a revisão sai como **nova edição**.

**Letra** (escala inferida dos boletins da referência, a confirmar **[decisão D-7]**): F < 1,5 · D− < 1,6 · D < 2,0 · D+ < 2,3 · C− < 2,6 · C < 2,9 · C+ < 3,2 · B− < 3,5 · B < 3,8 · B+ < 4,1 · A− < 4,4 · A < 4,7 · A+ ≥ 4,7. Confere com as notas vistas: 1,15 = F; 1,575 = D−; 1,60 a 1,725 = D; 2,10 = D+.

**Histórico:** série de notas por critério, retorno, risco e aderência; setas ↑ → ↓ contra a edição anterior, como na referência.

## 8. Teses e valuation

**Ficha por posição** (versionada em `teses.jsonl`): tese, fundamentação econômica, análise fundamentalista, crescimento, vantagens competitivas, riscos, catalisadores, horizonte, preço justo, margem de segurança, cenários otimista/base/pessimista com probabilidades, "muda de ideia se", rating, próxima data de revisão, eventos decisivos.

**Laboratório de valuation** (código, `teses/valuation/`):
- DCF (FCFF e FCFE), múltiplos contra pares, **juro implícito** (taxa que zera o modelo no preço de hoje, como em "Modelos e o novo governo").
- Cenários ponderados por probabilidade, com trilhas de juro real.
- **Convenções da casa versionadas** (`config/convencoes.toml`): data de preço única, curva DI, Selic/CDI, CDS e prêmio de risco. Todo lab lê a mesma versão (lição do Update #5).
- Validade do lab (ex.: vence no Copom ou no resultado) e sensibilidade por variável.
- **Testes de rating que só limitam** (inspirados nos testes de Marks): A, a tese sobrevive com premissa conservadora; B, aguenta estresses históricos (2015–16, 2020, 2021–22); C, o preço já paga o cenário ruim. Reprovar limita o rating; aprovar nunca sobe.
- O resultado (valor, cenários, juro implícito) é número de código; o texto da tese é da IA ou seu.

## 9. Opções

- **Instrumento:** subjacente, call ou put, strike, vencimento, estilo (americana ou europeia), lote.
- **Precificação:** Black-Scholes para europeias, árvore binomial para americanas; volatilidade implícita por Brent/Newton; gregas Delta, Gamma, Theta, Vega e Rho.
- **Estruturas:** call e put secas, lançamento coberto, travas de alta e de baixa, put de proteção, collar. Payoff por cenário, ponto de equilíbrio, perda máxima e ganho máximo.
- **Probabilidade de lucro:** lognormal com a volatilidade implícita, **marcada como estimativa** e só com dados suficientes.
- **Risco:** exercício (dentro do dinheiro perto do vencimento, data-com de dividendos), nocional de exercício × caixa ("exercício ≈ 6× o caixa" da referência vira alerta), concentração de vencimentos.
- **Simulador** antes de operar: monta a estrutura e mostra payoff, gregas e impacto no risco da carteira. Nunca envia ordem.

## 10. Camada quantitativa e backtest

- **Métricas:** tendência (médias móveis, regressão de tendência), volatilidade, correlação, beta, drawdown, Sharpe e Sortino, comparação com benchmarks.
- **Simulação de alocação:** pesos-alvo × risco (variância mínima e paridade de risco, como referência, não como ordem).
- **Backtest:** universo **com papéis deslistados** (COTAHIST); custos e impostos; walk-forward (treino e teste separados no tempo); proibido usar dado do futuro (teste automatizado de vazamento).
- **Registro de experimentos:** cada rodada vira linha em `experimentos.jsonl` (parâmetros, período, resultado), inclusive as que falharam, para evitar overfitting por tentativa e erro.
- **Ficha do modelo** (`docs/modelos/<nome>.md`): parâmetros, dados, período, testes, limitações conhecidas, data da última validação.

## 11. Fiscal

Apuração mensal em código, com memória de cálculo exibida e regras parametrizadas em `config/fiscal.toml` (**a validar com o seu contador**): ações no swing trade (isenção para vendas até R$ 20 mil no mês), day trade, FIIs, ETFs e BDRs (sem a isenção), compensação de prejuízo por categoria, DARF com vencimento e aplicações no exterior (Lei 14.754/2023, apuração anual). Saída: DARF a pagar, uso do limite de isenção ("61% do limite de R$ 20 mil", como na referência) e prejuízo acumulado.

## 12. Interface

**[decisão D-4]** Recomendação: **FastAPI + Jinja2 + HTMX**, servidor local (`python -m rvlocal painel`), com **exportação estática** da capa e do balanço para abrir no celular. Continua sendo tudo Python, os formulários conversam com os livros e não há framework de front-end para manter. Alternativas: Streamlit (rápido, mas pouco controle visual) ou só HTML estático (sem formulários nem simulador).

**Identidade visual:** o projeto atual não tem interface, então não há identidade a preservar. A proposta adota a da referência: fundo papel claro e modo escuro, tinta quase preta, roxo como destaque, verde e vermelho só para resultado, Inter + IBM Plex Mono, cartões com borda fina e raio 4, pílulas sim/não, roscas e barra 100% para composição, e selos `DADOS DEMO` / `ESTIMATIVA` / `HIPÓTESE`.

| Tela | Conteúdo principal | Origem na referência |
|---|---|---|
| Dashboard (capa) | Resumo, resultado consolidado e por classe, benchmarks, exposição, alertas, hipóteses em jogo, status dos agentes, últimas decisões, nota | Capa do pregão + Na sua mesa |
| Carteira | Alocação nível 1 × alvo, sleeves, curva TWR | Resultado real |
| Posições abertas | Preço, PM, P&L, peso, alvo, stop, distância | Ficha (cabeçalho) |
| Operações encerradas | Realizado, duração, tese, aderência ao plano | Encerradas |
| Teses | Fichas versionadas, histórico de versões | Uma ficha por posição |
| Fundamentalista | Labs de valuation, cenários, juro implícito | Laboratórios |
| Quantitativa | Vol, correlação, beta, tendência | |
| Monitoramento | Alertas do dia, mesa de pendências, heartbeat | Status do pregão |
| Risco | Níveis 1 e 2, stress, VaR, bandas | A carteira como um todo |
| Opções | Posições, gregas, simulador | |
| Backtesting | Experimentos, resultados, fichas de modelo | |
| Auditoria | Checklist por operação, violações, comentário do auditor | Toda nota cita evidência |
| Relatórios | Briefing, recap, retrô, boletins (diário a trimestral), histórico de notas | Balanço semanal |

Todo número mostra fonte e hora; toda tela lê dos livros e das vistas, nunca de dados fixos no HTML.

## 13. Rotina operacional

Horários em `config/rotina.toml`, **com fuso explícito `America/Sao_Paulo`**.

| Horário | Rotina | Motor |
|---|---|---|
| 07:45 | Verificação de dados e pendências (cobrança da manhã) | Código |
| 08:20 | Coleta da manhã + conferência BCB | Código |
| 08:30 | Briefing e hipóteses do dia | IA (Agente 1) |
| 09:45 | Atualização pré-abertura (flash) | Código + IA curta |
| 09:45–18:15, a cada 10 min | Vigilância | Código (Agente 3 só se disparar) |
| 18:00 | Coleta de fechamento + atualização da carteira | Código |
| 18:05 | Números do dia, risco, placar de hipóteses, boletim diário | Código |
| 18:15 | Encerramento e auditoria | IA (Agentes 5 e 4) |
| Sexta 19:00 | Retrô + boletim semanal | Código + IA |
| Dia 1º | Relatório mensal, consolidação, fiscal | Código + IA |
| Trimestral | Boletim trimestral, revisão de teses e modelos | Código + IA |

**Confiabilidade:** heartbeat por rotina; a rotina das 07:45 alerta qualquer rotina ausente do dia anterior; **"atrasou, não publica"** (texto da manhã gerado depois da abertura não sai como briefing); comando `repescagem --data` refaz as vistas de um dia sem tocar nos livros.

**[decisão D-3]** Onde as rotinas de código rodam: GitHub Actions (atual), uma máquina local (cron/systemd/launchd) ou uma VPS.

## 14. Estrutura de pastas (como ficou no Ciclo 2)

Os módulos originais foram **mantidos no lugar** (mudança mínima) e os novos ficaram ao lado, em vez da
reorganização em subpacotes proposta inicialmente. A interface pública continua `python -m rvlocal`.

```
config/       regras · series · feriados · risco · stress · placar · fiscal · rotina
data/
  livros/     instrumentos.json + operacoes · decisoes · teses · hipoteses · placar_hipoteses ·
              eventos · alertas · boletins · heartbeat (.jsonl, só por acréscimo)
  mercado.db  séries (SQLite)
  gerado/     diario/ · risco/ · recaps/ · coleta/ · estado/   (vistas refeitas pelo código)
src/rvlocal/
  util · calendario · livros · instrumentos                      núcleo
  fontes · coleta · series                                       01 coleta
  razao · desempenho · fiscal                                    carteira
  regras · risco · mesa · vigilancia · cobranca                  02 vigilância e risco
  teses · decisoes · hipoteses                                   registro de processo
  boletim                                                        04 placar
  diario                                                         orquestra o fechamento
  painel/ (app, dados, graficos, templates, static)              interface
  demo · migrar · cli
prompts/      recap_1815 (Agente 5) · hipotese_nova
tests/        72 testes
exemplos/     instrumentos, ficha de tese, hipótese
```

Interface: FastAPI + Jinja2 com **formulários HTML simples** (o HTMX recomendado não foi necessário) e
gráficos em SVG gerados no servidor, que funcionam também na exportação estática.
