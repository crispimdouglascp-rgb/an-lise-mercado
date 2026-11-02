# Fase 3: plano de implementação

> Segue os três ciclos que você propôs, com **registro de decisões e placar antes dos agentes**. Sem histórico confiável de teses, entradas, saídas e limites, os agentes não têm o que avaliar.
> Complexidade: **P** (até 1 dia de trabalho), **M** (2 a 4 dias), **G** (1 semana ou mais).
> Cada épico tem um "pronto" medido em número, como na referência.

## Ciclo 1: diagnóstico (concluído)

- [x] Engenharia reversa do ZIP (`docs/01-diagnostico.md`)
- [x] Leitura das 6 apresentações únicas
- [x] Três defeitos reproduzidos com script (D1, D2, D3)
- [x] Arquitetura (`docs/02-arquitetura.md`)
- [x] Plano (este documento)
- [x] Decisões D-1 a D-8: "siga as recomendações" (02/11/2026)

## Ciclo 2: construção (carteira, teses, decisões, risco, placar), CONCLUÍDO

Status em 02/11/2026: todos os épicos entregues, 72 testes (38 originais + 34 novos), base demo gerada pelo
código de produção. O que ficou de fora de cada épico está em "Pendências do Ciclo 2" abaixo.

| # | Épico | Depende de | Cx. | Pronto quando |
|---|---|---|---|---|
| 2.0 | **Fundação**: corrigir D1 a D14, cada defeito com teste de regressão; pacote reorganizado (seção 14 da arquitetura); verificação de imutabilidade dos livros; campo `natureza`; heartbeat | D-1, D-2 | M | 38 testes antigos + 1 teste por defeito passando; alterar uma linha antiga de livro faz o teste falhar |
| 2.1 | **Cadastro multi-classe e multi-moeda**: `instrumentos.json`; razão com moeda e câmbio; sleeves Brasil e exterior; TWR por sleeve em R$ e na moeda local | 2.0, D-6 | M | TWR de cada sleeve e consolidado batendo com um caso calculado à mão (com aporte, resgate, provento e lacuna) |
| 2.2 | **Livro de decisões + checklist pré-operação**: `rvlocal operar` recusa compra/venda sem os 9 itens (ou grava como "sem tese", que pontua 0); decisões vinculadas a alertas, com prazo | 2.0 | M | 100% das operações novas com `decisao_id`; a mesa de pendências lista prazos e vencidas |
| 2.3 | **Fichas de tese versionadas**: `teses.jsonl`; nova versão a cada mudança, com motivo; preço justo e cenários como campos (valuation completo vem no 3.5) | 2.0 | M | Histórico de versões reconstruído para qualquer data |
| 2.4 | **Hipóteses v2 + placar append-only**: limiar, gates, Wilson, origem, versões, migração do `hipoteses.json` atual (histórico congelado como "legado") | 2.0 | M | Nenhuma reescrita de arquivo no fechamento; veredito só com 8 ou mais gates; teste que impede pontuar antes de `formulada_em` |
| 2.5 | **Monitor de risco**: nível 1 (classes × bandas) e nível 2 (pesos, HHI, vol, beta, correlação, drawdown, liquidez, stress pré-registrado); VaR/CVaR só com 250 pregões; `gerado/risco/<dia>.json`; cada banda com alerta | 2.1, D-7 | G | 3 cenários de stress com P&L; cada banda com um teste provando o alerta; backfill de histórico marcado com a fonte |
| 2.6 | **Boletim do gestor**: 7 critérios, tetos, letra, evidências, edições diária, semanal, mensal e trimestral, revisão como nova edição | 2.2, 2.4, 2.5 | G | Cada critério com teste de casos-limite; "regra ignorada = 0" e "tetos só limitam" provados por teste; o mesmo dado gera sempre a mesma nota |
| 2.7 | **Painel v1**: Dashboard, Carteira, Posições, Encerradas, Teses, Monitoramento, Risco, Auditoria, Relatórios (com histórico de notas); exportação estática da capa | 2.1 a 2.6, D-4 | G | Todas as telas lendo livros e vistas; dados demo com selo visível; funciona no celular |
| 2.8 | **Fiscal básico**: apuração mensal BR, isenção de R$ 20 mil, compensação, DARF | 2.1 | M | Apuração igual a 3 casos calculados à mão; memória de cálculo visível |

Ordem sugerida: 2.0 → 2.1 → (2.2 ∥ 2.3 ∥ 2.4) → 2.5 → 2.6 → 2.7, com 2.8 em paralelo.

### Pendências do Ciclo 2 (conhecidas)

- Liquidez (dias para zerar) espera a coleta de volume (3.3); o monitor declara "sem dado".
- Nível 1 do patrimônio está desligado por padrão: só faz sentido com renda fixa, fundos e cripto no razão.
- Fiscal: day trade com lucro pelo PM da posição; exterior só informativo (apuração anual). Validar com contador.
- Lançamento coberto e risco de opções no boletim entram com o módulo de opções (3.7).
- Captura da carteira por print (visão) não foi feita; o registro é pelo `operar` ou pelo livro.
- Fontes de preço continuam sem teste ao vivo (rede bloqueada aqui); agendamentos desligados até lá.

## Ciclo 2.1: várias carteiras, CONCLUÍDO (02/11/2026)

Pedido: dados reais no localhost, vitrine no GitHub, Vercel mais adiante; acompanhar ativos, testar carteiras
próprias, de clientes e recomendadas por analistas.

- Pasta de dados privada fora do repositório público (`rvlocal iniciar`, `.rvlocal-home`).
- Carteiras `propria`, `cliente`, `analista`, `simulacao`, cada uma com os próprios livros; universo de ativos
  e banco de preços compartilhados; regras por carteira com fallback para a configuração geral.
- `rebalancear` (pesos-alvo, com câmbio nos dois sentidos), `reprocessar` (fechamentos de um período),
  `historico` (backfill do Yahoo, fonte única), `ativo` (universo), `--carteira` e `--todas`.
- Painel: telas Carteiras (comparação) e Ativos (universo × carteiras), seletor de carteira, exportação com
  subpasta por carteira; vitrine no GitHub Pages só com DEMO.
- Clientes por código; a criação recusa CPF e e-mail no nome (LGPD).

## Ciclo 3: inteligência (agentes, dados, quant, backtest, opções, automação)

| # | Épico | Depende de | Cx. | Pronto quando |
|---|---|---|---|---|
| 3.1 | **Executor de agentes**: pacote de fatos, prompts versionados, validador de saída, modo degradado sem IA | 2.6, D-3 | M | Texto com número inventado é rejeitado em teste; com a IA indisponível, a rotina publica números e alertas mesmo assim |
| 3.2 | **Agentes**: 5 (encerramento, evolução do recap atual) → 1 (briefing) → 3 (intradiário) → 4 (auditor) → 2 (teses); depois retrô e comentário do boletim | 3.1 | G | 5 pregões seguidos com todas as saídas aprovadas pelo validador |
| 3.3 | **Coleta ampliada**: BCB (Selic, CDI, IPCA, Focus), Tesouro, CVM, FRED, SEC, COTAHIST, eventos e resultados; `mercado.db` com carga em cópia e troca atômica | 2.0, D-5, D-8 | G | Cada série com 2 fontes ou marcada "fonte única esperada"; teste ao vivo de todas as fontes registrado |
| 3.4 | **Quant**: tendência, vol, correlação, Sharpe/Sortino, simulação de alocação, fichas de modelo | 2.5, 3.3 | M | Cada métrica conferida contra um cálculo de referência independente |
| 3.5 | **Laboratórios de valuation**: DCF, múltiplos, juro implícito, cenários, convenções versionadas, validade, testes de rating que só limitam | 2.3, 3.3 | G | 1 lab completo por posição-piloto; mudar uma convenção gera nova versão de todos os labs |
| 3.6 | **Backtest e stress**: universo sem viés de sobrevivência, custos e impostos, walk-forward, registro de experimentos, teste de vazamento | 3.3, 3.4 | G | Teste de vazamento de dados passando; todo experimento registrado, inclusive os que falharam |
| 3.7 | **Opções**: precificação, IV, gregas, estruturas, payoff, risco de exercício, simulador, integração com o monitor de risco | 2.5, 3.3 | G | Preço e gregas conferidos contra valores de referência publicados; alerta de exercício × caixa provado |
| 3.8 | **Automação completa**: rotina configurável, heartbeat, "atrasou, não publica", repescagem, relatórios mensal e trimestral | 3.2 | M | 1 semana inteira sem intervenção manual, com falha simulada detectada pelo alarme |
| 3.9 | **NLU das teses** (opcional): extrator de premissas na ficha curta, com confirmação "entendi assim" | 3.2 | M | 70% das premissas aceitas por você sem correção (meta da referência) |

## Decisões pendentes (suas)

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| **D-1** | Armazenamento | (a) JSONL para livros + SQLite para séries; (b) tudo em SQLite; (c) Postgres | **(a)**: mantém o que já funciona e a trilha de auditoria no git |
| **D-2** | Layout do repositório | (a) mover `rv-local/` para a raiz; (b) manter em subpasta | **(a)**, mas atenção: os workflows passam a valer e **a vigilância começa a rodar a cada 10 min** no branch padrão. Recomendo mover com os crons desativados até as fontes estarem validadas |
| **D-3** | Onde rodam as rotinas e a IA | Código: GitHub Actions, máquina local ou VPS. IA: tarefa agendada do Claude ou API (chave) | Código: GitHub Actions até o 3.3 e reavaliar com o volume de dados. IA: começar com tarefa agendada (sem chave), já com o executor pronto para a API |
| **D-4** | Interface | FastAPI + HTMX; Streamlit; HTML estático | **FastAPI + HTMX** + exportação estática para o celular |
| **D-5** | Fontes pagas | brapi gratuito × brapi Pro (opções, fundamentos, histórico) | Começar no gratuito; assinar o Pro antes do 3.7 (opções) |
| **D-6** | Universo e classes já no 2.1 | Ações BR, FII, ETF, BDR, ações EUA, opções, RF, cripto | Me diga quais você tem hoje; o cadastro aceita todas, mas os testes priorizam as reais |
| **D-7** | Parâmetros | Limites de posição, setor e fator; bandas do nível 1; cenários de stress; escala de letras; limiar de hipótese (±0,75 pp) e mínimo de gates (8) | Revisar os valores propostos na arquitetura; ficam todos em `config/` |
| **D-8** (pendente de ação sua) | Rede deste ambiente | Liberar `query1.finance.yahoo.com`, `brapi.dev`, `api.bcb.gov.br` (e depois `www.tesourodireto.com.br`, `dados.cvm.gov.br`, `api.stlouisfed.org`, `data.sec.gov`, `bvmf.bmfbovespa.com.br`) | Liberar, para eu validar as fontes daqui; senão, rodar `testar-fontes` na sua máquina e me mandar a saída |

## O que preciso de você para começar o Ciclo 2

1. As decisões D-1 a D-8 (pode ser só "siga as recomendações").
2. Seus dados reais, **quando quiser**, em repositório privado: operações, parâmetros por ativo e regras. Até lá, sigo com dados demo marcados como tal.
3. Suas teses atuais em texto livre, mesmo curtas: são o insumo das fichas e do placar.
