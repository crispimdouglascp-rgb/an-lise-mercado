# Fase 1: auditoria e engenharia reversa

> Status: **diagnóstico entregue, nenhuma linha do projeto foi alterada.** O código original está em `rv-local/` exatamente como veio no ZIP (commit base).
> Data da auditoria: 02/11/2026.

## 1. O que foi auditado

| Material | Conteúdo | Observação |
|---|---|---|
| `rv-local.zip` | 34 arquivos, ~2.000 linhas (Python, TOML, YAML, JSON, Markdown) | Copiado sem alterações para `rv-local/` |
| *RV Local, a plataforma que me deu F* (Parte 1) | Rotina, 4 camadas, painel, hipóteses, proteções, TWR de setembro, boletim F (1,15) | Enviado em duplicata (2 arquivos idênticos) |
| *Conferência mensal* (Parte 2, 11/10) | 3 pregões sem rotinas, mesa de pendências, fichas, painel de 11 para 7 abas, boletim D, rotinas mais leves, NLU/NLG | |
| *Update #3* (12 a 16/10) | Fichas de input, 8 regras de NLG, motor de valuation (6 labs), workflow quant, Balanço semanal D− | Enviado em duplicata |
| *Update #4* (19 a 23/10) | Placar de hipóteses (6 regras, Wilson), "livros", mapa de 9 etapas, monitor de risco em 2 níveis | |
| *Update #5* (26 a 30/10) | Pré-registro do 2º turno, 13 labs, canais do juro, testes de Marks (A/B/C), brapi Pro, plataforma parada por limite de uso, Boletim #6 | |
| *Modelos e o novo governo* (26/10) | 4 modelos de fluxo de caixa sob 3 trilhas de juro real, juro implícito no preço | |

Os números de carteira das apresentações **não** foram usados como dados. Eles servem só como referência de forma, profundidade e regras.

## 2. Engenharia reversa do projeto atual

### 2.1 Stack

| Item | Escolha atual | Avaliação |
|---|---|---|
| Linguagem | Python 3.12, **só biblioteca padrão** (`urllib`, `tomllib`, `json`, `statistics`) | Ótimo: zero dependências, fácil de auditar |
| Armazenamento | JSON/JSONL em `data/`, versionado pelo git | Bom para os livros; não escala para séries longas, opções e fundamentos |
| Configuração | TOML em `config/` (regras, séries, feriados) | Bom, manter |
| Agendamento | GitHub Actions (cron em UTC) | Funciona, mas usa ~1.100 a 1.400 de 2.000 min/mês e atrasa alguns minutos |
| Notificação | Telegram (token só em variável de ambiente, nunca em log) | Bom |
| IA | 1 prompt de tarefa agendada do Claude (recap 18:15) + 1 guia de hipótese | Correto conceitualmente, mas ainda mínimo |
| Testes | 38 testes `pytest`, todos com dados simulados | **38/38 passam** (verificado aqui, Python 3.13) |
| Interface | Nenhuma (saída em texto, Telegram e JSON) | Precisa ser construída |

### 2.2 Módulos

| Módulo | Linhas | O que faz | Estado |
|---|---|---|---|
| `util.py` | 89 | Caminhos, relógio em BRT (fixável para testes), JSON atômico, JSONL, formatação pt-BR | Sólido |
| `calendario.py` | 19 | Dia útil (fim de semana + feriados) e janela de pregão | Funciona; feriados não verificados e só de 2026 |
| `fontes.py` | 209 | Yahoo, brapi, BCB (dólar SGS 1); `consolidar()` compara as duas fontes e transforma divergência em lacuna | Desenho excelente; 1 defeito comprovado (D1); APIs nunca testadas ao vivo |
| `coleta.py` | 102 | Coleta manhã/flash/fechamento; grava fechamentos só se conferidos; confere o dólar contra o BCB | Funciona |
| `series.py` | 46 | Histórico de fechamentos, retorno diário, sigma de 60 dias | Funciona |
| `razao.py` | 180 | Razão de operações (compra, venda, aporte, resgate, provento), posições, preço médio, caixa, fluxos, realizado, validação | Núcleo sólido; 1 defeito comprovado (D2) |
| `regras.py` | 113 | Teto/piso de posição, teto de setor, caixa mínimo, stop sem decisão, realização sem decisão, operação sem tese, excesso de giro | Funciona; é a semente da Camada 02 |
| `vigilancia.py` | 89 | Alertas intradiários: alvo, perto do alvo, stop, movimento > 2σ, fonte congelada, fontes divergentes; 1 alerta por chave por dia | Funciona |
| `hipoteses.py` | 115 | 3 tipos de teste pré-registrado; medição diária; placar com sugestão de arquivar | Boa semente; não segue as regras de placar da referência (D4 a D6) |
| `diario.py` | 133 | Fechamento 18:05: patrimônio, TWR diário e acumulado, Ibovespa, pesos, regras, hipóteses, alertas | Funciona; 1 defeito comprovado (D3) |
| `notificar.py` | 34 | Telegram com divisão em blocos de 3.800 caracteres | Sólido |
| `cli.py` | 77 | `validar`, `testar-fontes`, `coletar`, `vigiar`, `fechar`, `decisao` | Funciona |

### 2.3 Fluxo de dados atual

```
GitHub Actions (cron UTC)
  08:20 coletar manha ──┐
  09:40 coletar flash ──┤      fontes.py: Yahoo + brapi (+ BCB no dólar)
  09:45–18:15 vigiar ───┼──►   consolidar(): ok | fonte_unica | divergente | sem_dado
  18:00 coletar fech. ──┘          │
                                   ▼
                 data/fechamentos.json  (só preço conferido)
                                   │
  18:05 fechar ──► razao + regras + hipoteses ──► data/diario/<dia>.json ──► Telegram
                                   │
  18:15 (Claude) ──► prompts/recap_1815.md lê o diário ──► data/recaps/<dia>_recap.md
```

### 2.4 Princípios já implementados (ponto forte do projeto)

1. **O código calcula, a IA escreve.** O prompt do recap proíbe recalcular, opinar sobre regras ou recomendar.
2. **Nunca inventar preço.** Ativo sem preço fica fora do cálculo e aparece como lacuna. Divergência entre fontes vira lacuna, nunca média.
3. **Duas fontes, sempre comparadas**, com o status de cada leitura registrado.
4. **Razão append-only.** Erro se corrige com nova linha.
5. **Regras em código.** "Realizar a 90% do alvo" é conferido em Python.
6. **O humano decide.** O código só *sugere* arquivar hipótese; nada executa ordens.
7. **TWR correto** para aportes e resgates (fluxo no início do dia).

Esses princípios são idênticos aos da referência ("Mantendo o modelo honesto") e devem ser preservados integralmente.

## 3. Comparação com a referência

| Capacidade da referência | Projeto atual | Situação |
|---|---|---|
| **Coleta**: preço com 2 fontes, câmbio, macro | Ações BR e IBOV com 2 fontes; dólar e Brent com 1 fonte; dólar conferido com o BCB no dia seguinte | Parcial |
| Universo amplo (brapi Pro, 167 papéis, 10 anos, barras de 5 min) | Só posições + ativos das hipóteses; histórico começa no 1º dia de coleta | Ausente |
| Sleeve EUA, câmbio, TWR por sleeve em R$ e US$ | Só Brasil e só BRL | Ausente |
| Calendário de resultados por posição | Não existe | Ausente |
| **Vigilância** a cada 10 min | Implementada | Pronto |
| Mesa de pendências com prazo ("Na sua mesa", "6 vencidas") | Alertas soltos; decisões sem prazo nem vínculo com o alerta | Parcial |
| Monitor de risco nível 1 (patrimônio por classe com banda) e nível 2 (fator, HHI, VaR/CVaR, beta, drawdown, stress, gregas) | Teto de posição, setor e caixa | Mínimo |
| Alarme de falha e regra "atrasou, não publica" | Não existe | Ausente (a referência parou 2 dias em silêncio) |
| **Síntese**: briefing 8h30, flash 9h45, recap 18h15, retrô sexta | Só o prompt do recap | Parcial |
| Captura da carteira por print → JSON → "sim" humano → razão | Lançamento manual em JSONL | Ausente (manual é aceitável) |
| Regras de NLG (fonte e hora em todo número, "sem leitura", cadeia evento → efeito) | Algumas no prompt do recap | Parcial |
| Fichas por posição (tese, preço médio, alvo, upside, rating, "muda de ideia se", histórico de versões) | `ativos.json` com setor/alvo/stop/tese_id, sem versões | Mínimo |
| **Placar de hipóteses**: limiar ±0,75 pp, 8 gates mínimos, intervalo de Wilson, origem IA × usuário, ponto é linha, data de formulação sagrada | Acerto/erro sem limiar, sem intervalo, arquivo reescrito a cada fechamento | Parcial, com defeitos |
| **Boletim do gestor** (7 critérios, nota 0 a 5, letra, evidência por critério, histórico de notas) | Só contagem de violações | Ausente |
| Laboratórios de valuation (DCF, juro implícito, cenários, convenções versionadas, validade) | Não existe | Ausente |
| Testes de Marks (A/B/C) que só **limitam** o rating | Não existe | Ausente |
| Backtest e stress test | Não existe | Ausente |
| Opções (risco, gregas, exercício × caixa) | Não existe | Ausente |
| Fiscal (DARF, limite de isenção de R$ 20 mil) | Não existe | Ausente |
| Painel visual (capa, fichas, balanço semanal) | Não existe | Ausente |

## 4. Diagnóstico

### 4.1 O que já existe e funciona

- Razão de operações com preço médio, caixa, fluxos, realizado e validação (`razao.py`).
- Consolidação de duas fontes com status honesto e lacuna em vez de média (`fontes.consolidar`).
- Coleta em 3 modos, com conferência do dólar contra o BCB (`coleta.py`).
- Fechamento que só grava preço conferido e datado do dia.
- TWR diário e acumulado que neutraliza aportes e resgates.
- Motor de regras determinístico com severidade (`regras.py`).
- Vigilância intradiária com 6 tipos de alerta e deduplicação por dia.
- Hipóteses com teste pré-registrado e medição automática (3 tipos).
- Registro de decisões de stop e realização.
- Notificação por Telegram sem vazar o token.
- Relógio fixável e raiz isolável para testes (`RVLOCAL_AGORA`, `RVLOCAL_HOME`): a infraestrutura de testes é muito boa e vai servir para todo o resto.

### 4.2 O que existe, mas precisa ser corrigido

Os três primeiros defeitos foram **reproduzidos com script** (não são suposições).

| # | Defeito | Evidência | Impacto | Correção proposta |
|---|---|---|---|---|
| **D1** | `consolidar()` usa `max(ts)` das duas fontes. Se uma fonte está defasada e a outra atualizada, a leitura parece do dia | Reproduzido: Yahoo de 03/11 + brapi de 04/11 → `status=ok`, preço **de ontem** gravado como fechamento de 04/11 | Fechamento errado entra no histórico, no TWR e nas hipóteses (dias de pouco movimento ficam dentro da tolerância de 0,5%) | Usar `min(ts)` para a idade e exigir que **as duas** cotações sejam do dia no fechamento |
| **D2** | `validar()` não confere caixa negativo | Reproduzido: aporte de R$ 1.000 e compra de R$ 36.000 → caixa −R$ 35.000, validação limpa | Patrimônio, pesos e regras calculados sobre um razão impossível | Validar caixa ≥ 0 em cada data (ou registrar alavancagem explicitamente) |
| **D3** | Um dia com lacuna apaga o retorno do período do acumulado | Reproduzido: 36 → (lacuna) → 40. Acumulado mostra **0%**; o certo é +11,11% | TWR subestima ou superestima em silêncio; no boletim, o critério de retorno fica errado | Calcular o retorno contra o último dia com patrimônio válido, somando os fluxos do intervalo, e marcar como "retorno de N pregões" |
| D4 | `medir_dia()` reescreve `hipoteses.json` inteiro a cada fechamento | Leitura de `diario.py:89-91` | Viola "não sobrescrever histórico". A referência (Update #4) apontou o mesmo problema: "137 KB lido e reescrito inteiro a cada recap" | Placar em livro append-only (`placar_hipoteses.jsonl`): cada ponto é uma linha imutável |
| D5 | A medição não respeita `criada_em` | `hipoteses.medir_dia` mede qualquer `dia`, inclusive anteriores à criação (`fechar --data`) | Viola "data de formulação é sagrada": permite placar retroativo | Só pontuar a partir da data de formulação |
| D6 | Teste sem limiar nem zona neutra; placar sem amostra mínima nem intervalo de confiança | `excesso_em_condicao` considera acerto com +0,01 pp; `taxa_acerto_pct` com 2 observações | Placar confunde ruído com acerto | Limiar (padrão ±0,75 pp), veredito a favor/neutro/contra, mínimo de 8 gates, intervalo de Wilson a 95% |
| D7 | Tese e hipótese são a mesma coisa: `tese_id` aponta para uma hipótese | `ativos.json`, `operacoes.jsonl` | Não há onde registrar tese de investimento, preço justo, cenários, invalidação e versões | Separar **tese** (ficha por posição, versionada) de **hipótese** (relação testável) |
| D8 | Decisão de stop só vale se for do mesmo dia, e só é cobrada contra o preço de fechamento | `regras.py:78` | Stop tocado durante o pregão e recuperado no fechamento nunca é confrontado; a decisão não guarda preço, alerta de origem, nem prazo | Decisão com `alerta_id`, preço, prazo e status; pendências vencidas viram violação |
| D9 | Feriados da B3 montados de memória, só de 2026 | `config/feriados.toml` | A partir de 01/01/2027, feriados contam como dia útil | Calendário verificado e com vários anos; alerta quando o ano seguinte não estiver cadastrado |
| D10 | APIs nunca testadas ao vivo | README, item 1 das limitações. **Também não foi possível testar aqui**: a rede deste ambiente bloqueia Yahoo, brapi e BCB (403 no proxy) | O sistema inteiro pode estar coletando lacunas | Rodar `testar-fontes` num ambiente com acesso (detalhe na seção 6) |
| D11 | Sem alarme de falha | Não há heartbeat | Se o Actions não rodar, o silêncio parece "nenhum alerta". A referência parou em 29/10 e "nenhum alarme avisou" | Heartbeat por rotina e alerta de "rotina não rodou" |
| D12 | Uma moeda e uma classe | Razão sem `moeda`, `classe`, `pais` | Impossível medir exposição Brasil × exterior, câmbio, BDR, ETF, FII, opções | Cadastro de instrumentos com classe, moeda, país, subjacente e lote |
| D13 | A vigilância consolida as fontes com `coleta.tolerancia_fontes_pct`, mas a mensagem cita `vigilancia.divergencia_max_pct` | `vigilancia.py:77` × `:24` | Hoje os dois valem 0,5% e o erro não aparece; ao mudar um deles, o alerta mente sobre o limite aplicado | Usar o parâmetro da vigilância |
| D14 | `__import__("datetime")` dentro de `fechar_dia` | `diario.py:81` | Só estilo | Import normal |

### 4.3 O que está previsto, mas não foi implementado

Listado no próprio README ("fases 2 e 3") e confirmado nas apresentações:

- Briefing 8h30 e flash 9h45 escritos pelo Claude.
- Cobrança das 07h45 ("o que o sistema precisa de mim").
- Painel visual.
- Captura da carteira por print (visão + confirmação humana).
- Boletim de sábado (nota do gestor). O comentário em `regras.toml` já prevê: "Regra ignorada = nota zero no boletim (fase 3)".
- Modelos quantitativos e DCF.
- Opções.
- Ajuste de proventos e desdobramentos (hoje é manual).

### 4.4 O que precisa ser desenvolvido do zero

1. **Livro de decisões completo** com checklist pré-operação (tese, justificativa, preço, horizonte, tamanho, risco máximo, invalidação, objetivo, risco-retorno).
2. **Fichas de tese versionadas** (preço justo, margem de segurança, cenários, catalisadores, invalidação).
3. **Placar de hipóteses v2** (limiar, gates, Wilson, origem, versões, livro de pontos).
4. **Monitor de risco** nos níveis patrimônio e sleeve: exposição por classe, setor, país e moeda; HHI; beta; volatilidade; correlação; drawdown; VaR/CVaR; stress pré-registrado; liquidez; opções.
5. **Boletim do gestor**: 7 critérios, nota 0 a 5, letra, evidência, tetos, edições diária, semanal, mensal e trimestral, histórico.
6. **Cadastro multi-classe e multi-moeda**, com sleeves Brasil e exterior e TWR por sleeve.
7. **Fiscal**: apuração mensal, isenção de R$ 20 mil, compensação de prejuízo, DARF, exterior.
8. **Agentes de IA** com pacote de fatos gerado por código e validação automática da saída.
9. **Laboratórios de valuation**: DCF, múltiplos, juro implícito, cenários com probabilidade, convenções versionadas, validade.
10. **Camada quantitativa e backtest** sem viés de sobrevivência, com registro de cada experimento.
11. **Módulo de opções**: precificação, volatilidade implícita, gregas, payoff, estruturas, risco de exercício, simulador.
12. **Interface** com as telas pedidas.
13. **Livro de eventos** (resultados, proventos, fatos relevantes, notícias citadas).
14. **Heartbeat, repescagem e regra "atrasou, não publica"**.

### 4.5 O que pode ser reaproveitado sem reconstrução

| Peça | Como entra na plataforma nova |
|---|---|
| `fontes.consolidar` + `Leitura` | Núcleo da Camada 01 para qualquer tipo de dado (com D1 corrigido) |
| Adaptadores Yahoo, brapi, BCB | Primeiros adaptadores do registro de fontes |
| `razao.calcular_estado` | Núcleo da carteira, estendido com moeda e classe |
| `regras.checar` e `Violacao` | Motor de regras da Camada 02, com regras novas acrescentadas |
| `vigilancia._gerar` | Vigilância intradiária; passa a gravar no livro de alertas |
| `hipoteses.avaliar` (3 tipos) | Continuam valendo como tipos de teste do placar v2 |
| `diario.fechar_dia` | Vira o orquestrador do fechamento (TWR corrigido) |
| `notificar.py` | Canal de alertas |
| `util.py` (relógio, JSON atômico, JSONL) | Base de toda a plataforma |
| `config/*.toml` | Mantidos; novos arquivos se somam a eles |
| `prompts/recap_1815.md` | Base do Agente 5 (encerramento) |
| 38 testes e a fixture `home` | Rede de segurança: precisam continuar passando a cada passo |

**Nada precisa ser descartado.** O que muda é a separação de entidades (D7), a forma de guardar o placar (D4) e a extensão para várias classes e moedas (D12).

## 5. Lições operacionais da referência

A referência documenta falhas reais. Cada uma vira um requisito de projeto:

| O que aconteceu na referência | Causa | Resposta no desenho |
|---|---|---|
| 3 pregões sem rotinas (05 a 09/10) e plataforma parada em 29/10 | Cota de uso do LLM esgotada | Todo cálculo em código; a IA lê só um pacote de fatos pequeno; a degradação mantém números e alertas sem IA |
| "~90% do custo era reler o painel" (440 KB por rotina) | Rotinas liam tudo para achar o delta | Rotinas leem livros e pacotes de fatos, nunca o painel; o painel é uma vista gerada |
| Arquivo de hipóteses de 137 KB reescrito a cada recap | Estado guardado como documento | Livros append-only; vistas regeneradas |
| Fichas reescritas no lugar, "sem guardar a anterior" | Sem versionamento | Ficha versionada: cada mudança é uma nova versão datada, com motivo |
| Agendamentos rodando no horário de Londres | Fuso implícito | Fuso explícito (`America/Sao_Paulo`) em toda rotina, com teste |
| Carga corrompeu a tabela de barras | Escrita direta no banco vivo | Carga numa cópia, validação e troca atômica (já é o padrão do `gravar_json`) |
| Labs divergiram (Selic, CDS e data de preço diferentes) | Premissas soltas por sessão | Convenções da casa versionadas e lidas por todo lab; data de preço única |
| "Parou em silêncio" | Sem alarme de falha | Heartbeat e alerta de rotina ausente |
| Flash saiu vazio após filtro sem teste | Mudança sem teste | "Testar num dia só" antes de ativar: todo filtro novo passa por teste com dados gravados |
| Boletim julgou 2 de 5 pregões | Dados faltantes | O boletim declara cobertura e é revisado em **nova edição**, sem sobrescrever |

## 6. Limitações deste diagnóstico

- **Fontes de preço não testadas.** A política de rede deste ambiente bloqueia `query1.finance.yahoo.com`, `brapi.dev` e `api.bcb.gov.br`. Para testar daqui, libere esses domínios em *Network access* nas configurações do ambiente (menu do ambiente na barra de título da sessão → *Edit* → *Allowed domains*; passos em https://code.claude.com/docs/en/cloud-environments#network-access), ou rode `PYTHONPATH=src python -m rvlocal testar-fontes` na sua máquina.
- **Feriados da B3** não foram conferidos contra o calendário oficial pelo mesmo motivo.
- O "print de referência" foi interpretado como as telas de Boletim e Balanço semanal das apresentações (notas F 1,15 → D 1,725).
- A escala de letras da referência não é publicada. A proposta da arquitetura é inferida das notas vistas nos boletins e precisa da sua confirmação.
