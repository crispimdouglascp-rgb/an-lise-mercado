# RV Local · cola rápida (Windows)

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Programa (código) | `C:\Users\<você>\an-lise-mercado` |
| **Seus dados** (carteiras, preços, decisões) | `C:\Users\<você>\RVLocal-dados` |
| Esta cola | `RVLocal-dados\COLA.md` |
| Log das rotinas automáticas | `RVLocal-dados\data\gerado\rotinas.log` |
| Painel | http://127.0.0.1:8765 (só no seu computador) |

Para confirmar a qualquer momento: `python -m rvlocal onde`

## Primeira vez (uma vez só)

Na pasta `an-lise-mercado\windows`, dê dois cliques em **`configurar.bat`**. Ele:
1. instala o programa;
2. **apaga os dados de teste** (a base DEMO);
3. cria a sua pasta de dados `RVLocal-dados`, vazia;
4. testa as fontes de preço;
5. agenda as rotinas automáticas (sem administrador);
6. cria o atalho **RV Local** na área de trabalho.

## Dia a dia

| Quero... | Faço |
|---|---|
| Abrir o painel | dois cliques em **RV Local** na área de trabalho |
| Fechar o painel | `windows\parar-painel.bat` |
| Ver o que precisa de mim | painel → **Mesa e monitoramento** |
| Rodar uma rotina agora | `windows\rodar-agora.bat fechar --todas` |
| Desligar a automação | `windows\remover-rotina.bat` (não apaga dados) |

O painel abre sozinho quando você entra no Windows. As rotinas rodam com o computador **ligado e você logado**.

| Horário | Rotina automática |
|---|---|
| 07:45 | cobrança: pendências e rotinas que falharam |
| 08:20 · 09:40 | coleta da manhã e pré-abertura |
| 09:45–18:15, a cada 10 min | vigilância: stop, alvo, movimento fora do padrão |
| 18:00 · 18:05 · 18:10 | coleta do fechamento, números do dia, boletim diário |
| sexta 19:00 | boletim semanal |
| dia 1º 08:10 | boletim mensal |

## Comandos (PowerShell, dentro de `an-lise-mercado`)

```
python -m rvlocal ativo WEGE3 --nome WEG --classe acao --setor industria --monitorar   # cadastrar ativo
python -m rvlocal historico --periodo 2y                                               # baixar histórico
python -m rvlocal carteira-nova --id teste-1 --nome "Meu teste" --tipo simulacao      # nova carteira
python -m rvlocal --carteira teste-1 rebalancear --data 2026-06-01 --capital 100000 --pesos "WEGE3=50"
python -m rvlocal --carteira teste-1 reprocessar --desde 2026-06-01                    # rodar o período
python -m rvlocal carteiras                                                            # comparar carteiras
python -m rvlocal mesa                                                                 # pendências
python -m rvlocal operar --tipo compra --ativo WEGE3 --qtd 100 --preco 42 ...          # registrar compra real
```

Tipos de carteira: `propria` (sua), `cliente` (só código, sem nome/CPF), `analista` (recomendada), `simulacao` (teste).

## Se algo der errado

- **Painel não abre:** rode `windows\rodar-agora.bat painel` e leia a mensagem.
- **Sem preços:** `python -m rvlocal testar-fontes`. A rede da empresa pode bloquear Yahoo, brapi ou BCB.
- **Rotina não rodou:** veja `RVLocal-dados\data\gerado\rotinas.log`; a cobrança das 07:45 também avisa.
- **Atualizar o programa:** `git pull` dentro de `an-lise-mercado`, depois `windows\configurar.bat` de novo (não apaga seus dados).

O programa nunca envia ordens à corretora. Carteira pessoal; não é recomendação de investimento.
