# RV Local (fase 1, só Brasil)

Plataforma pessoal de acompanhamento de renda variável. **O código calcula; o Claude só julga e escreve.** A decisão de comprar ou vender é sempre sua. Carteira pessoal, não é recomendação de investimento.

## O que a fase 1 faz

| Horário (BRT) | Quem | O quê |
|---|---|---|
| 08:20 | GitHub Actions | Coleta da manhã + conferência do dólar contra o BCB |
| 09:40 | GitHub Actions | Coleta do flash (o que mudou antes da abertura) |
| 09:45–18:15, a cada 10 min | GitHub Actions | Vigilância: alvo, stop, movimento fora do padrão, fonte congelada, fontes divergentes. Alerta no Telegram, uma vez por dia por condição |
| 18:00 | GitHub Actions | Fechamento: grava preços só se as duas fontes baterem (tolerância 0,5%) |
| 18:05 | GitHub Actions | Números do dia: patrimônio, retorno ponderado pelo tempo, regras, hipóteses, placar |
| 18:15 | Tarefa agendada do Claude | Recap escrito (`prompts/recap_1815.md`) + push |

**Ainda não existe (fases 2 e 3):** briefing 8h30 e flash escritos pelo Claude, painel visual, captura da carteira por print, boletim de sábado, modelos quantitativos/DCF, opções.

## Proteções embutidas (testadas com dados simulados)

- Preço de **duas fontes** (Yahoo e brapi). Divergiu mais que 0,5%: vira lacuna, nunca média.
- Fonte única inesperada ou cotação defasada **não grava** fechamento.
- Ativo sem preço **não é estimado**: fica fora do cálculo e listado como lacuna.
- Regras (`config/regras.toml`) conferidas em Python: teto por posição e setor, caixa mínimo, stop sem decisão registrada, realização perto do alvo, operação sem tese/gatilho/horizonte, excesso de giro.
- Retorno diário tratando aporte/resgate como início do dia (aporte não infla o retorno).
- O código só **sugere** arquivar hipótese; quem arquiva é você.

## Instalação (uns 20 minutos)

1. **Repositório privado** no GitHub e suba esta pasta (`git init`, `git add .`, `git commit`, `git remote add origin ...`, `git push`).
2. **Telegram:** no app, converse com `@BotFather`, `/newbot`, guarde o token. Mande uma mensagem ao bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates` no navegador para ver seu `chat.id`.
3. **brapi (opcional, recomendado):** crie conta gratuita em brapi.dev e gere um token.
4. No repositório: *Settings → Secrets and variables → Actions* e crie `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BRAPI_TOKEN`. **Não envie esses valores no chat.**
5. *Settings → Actions → General → Workflow permissions:* "Read and write permissions" (os fluxos gravam `data/` no repo).
6. **Teste as fontes na sua máquina** (importante, veja limitações): `PYTHONPATH=src python -m rvlocal testar-fontes`.
7. **Substitua os dados de exemplo:** `data/operacoes.jsonl` (sua carteira real), `data/ativos.json` (setor, alvo, stop), `data/hipoteses.json`. Depois `python -m rvlocal validar`.
8. Rode manualmente em *Actions → rotina-diaria → Run workflow* (etapa `fechamento`, depois `numeros`) e confira o commit em `data/`.
9. **Tarefa agendada do Claude:** crie uma tarefa em dias úteis às 18:15 com o texto de `prompts/recap_1815.md`, com o repositório anexado.

## Uso diário

- Nova operação: acrescente uma linha em `operacoes.jsonl` (nunca edite o passado; corrija com nova linha). Compra/venda exige `tese_id`, `gatilho`, `horizonte`.
- Stop acionado ou alvo chegando: `python -m rvlocal decisao --data 2026-11-04 --tipo stop --ativo PETR4 --decisao manter --motivo "tese intacta"`.
- Nova hipótese: veja `prompts/hipotese_nova.md`.

## Limitações (leia antes de confiar)

1. **As APIs de preço NÃO foram testadas ao vivo.** O ambiente onde escrevi o código bloqueia rede externa. O parser foi escrito pela documentação e por conhecimento prévio e testado só contra respostas simuladas. O endpoint da brapi e a liberação de índices (`^BVSP`) estão marcados "a conferir". Rode `testar-fontes` antes de tudo; se falhar, ajuste `src/rvlocal/fontes.py`.
2. **`config/feriados.toml` foi montado de memória e não foi verificado** contra o calendário oficial da B3 (a consulta falhou). Confira e corrija antes do uso. Se o dia estiver errado, a coleta roda em feriado ou pula dia útil.
3. **Yahoo é endpoint não oficial**: pode mudar ou bloquear IP de nuvem sem aviso. Se acontecer, o sistema cai para "fonte única" e o fechamento **não grava** (lacuna), em vez de mentir.
4. **GitHub Actions agendado atrasa** alguns minutos e usa UTC (BRT = UTC−3, sem horário de verão). A vigilância consome ~50 execuções por dia útil; em repositório privado no plano gratuito (2.000 min/mês) isso fica perto de 1.100–1.400 min. Acompanhe o consumo.
5. **Alerta de movimento** usa sigma padrão de 1,8% até haver 20 fechamentos de histórico.
6. Fechamentos antigos não são retroativos: o histórico começa quando a coleta passa a rodar.
7. Dividendos/JCP e desdobramentos não são ajustados automaticamente: registre `provento` e corrija quantidades por nova operação.

## Testes

`PYTHONPATH=src python -m pytest -q` (38 testes, tudo com dados simulados).
