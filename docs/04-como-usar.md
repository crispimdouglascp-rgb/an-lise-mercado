# Como usar

> A plataforma **não envia ordens** a nenhuma corretora. Ela registra o que você decidiu, mede, cobra e avalia.
> Carteira pessoal; não constitui recomendação de investimento.

## 1. Instalação (uma vez)

```bash
git clone https://github.com/crispimdouglascp-rgb/an-lise-mercado.git
cd an-lise-mercado
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[painel,dev]"
python -m pytest -q                                      # 72 testes devem passar
```

O núcleo usa só a biblioteca padrão do Python (3.11+). O extra `painel` instala FastAPI, Uvicorn e Jinja2.

## 2. Explorar com a base DEMO (5 minutos)

```bash
python -m rvlocal demo --destino demo                    # gera uma carteira fictícia completa
RVLOCAL_HOME=demo python -m rvlocal painel               # abre http://127.0.0.1:8765
```

A demo usa **tickers fictícios** (EXPO3, BANK4, TECHX...) e preços sintéticos. Todo registro sai com
`natureza: demo` e o painel mostra o selo **DADOS DEMO**. Os fechamentos foram produzidos pelo mesmo
código de produção, pregão a pregão, com falhas roteirizadas para você ver o sistema reagir:

| Falha roteirizada | Onde aparece |
|---|---|
| Compra de VARE3 por impulso, sem tese | Auditoria (0/9), Qualidade das decisões = 0 na semana, cobrança "sem ficha" |
| Stop de OLEO3 ignorado por 2 pregões após um choque | Aderência = 0 e teto da nota em 2,0 (D+) na semana do choque |
| DARF de julho sem pagamento registrado | Execução, custos e fiscal −2 na semana do vencimento |
| Compra grande de INDX11 que estoura o teto de posição | Mesa: pendência aberta; Risco: barra vermelha acima do teto |

Outras formas de ver a demo:

```bash
RVLOCAL_HOME=demo python -m rvlocal mesa --data 2026-10-30       # pendências
RVLOCAL_HOME=demo python -m rvlocal hipotese                      # placar das hipóteses
RVLOCAL_HOME=demo python -m rvlocal boletim --tipo semanal --data 2026-10-30
RVLOCAL_HOME=demo python -m rvlocal painel --exportar painel-estatico   # HTML para o celular
```

## 3. Onde ficam os seus dados (antes de qualquer dado real)

O repositório do código é **público**. Os seus dados ficam numa pasta **separada e privada**:

```bash
python -m rvlocal iniciar --destino ~/rvlocal-dados
cd ~/rvlocal-dados && git init && git add . && git commit -m "base"   # e um repositório PRIVADO no GitHub
```

`iniciar` cria a pasta (config, livros vazios) e grava o caminho em `.rvlocal-home`, na pasta do código
e fora do git: a partir daí todo comando e o painel usam essa pasta. Para usar outra pontualmente:
`RVLOCAL_HOME=/outra/pasta python -m rvlocal ...`.

| O que | Onde | Público? |
|---|---|---|
| Código, documentação, vitrine | este repositório | sim |
| Sua carteira, clientes, analistas, preços | `~/rvlocal-dados` (repositório privado) | **não** |
| Painel com dados reais | `http://127.0.0.1:8765` no seu computador | **não** |

## 4. Várias carteiras: a sua, de clientes, de analistas e simulações

Cada carteira tem os próprios livros, mesa, fichas, hipóteses e boletins. Todas compartilham o
**universo de ativos** e o **banco de preços**, então são comparáveis pelo mesmo critério.

| Tipo | Para quê | Natureza dos dados |
|---|---|---|
| `propria` | a sua carteira (a `principal`) | real |
| `cliente` | carteira que você acompanha ou monta para um cliente | real (ou `--natureza simulada` para uma proposta) |
| `analista` | carteira recomendada de um analista ou casa | simulada |
| `simulacao` | um teste seu: alocação, ideia, paper trading | simulada |

```bash
python -m rvlocal carteira-nova --id analista-casa-x --nome "Recomendada Casa X" --tipo analista --fonte "Casa X"
python -m rvlocal carteira-nova --id cliente-017 --nome "Cliente 017 · moderado" --tipo cliente
python -m rvlocal carteira-nova --id teste-dividendos --nome "Teste dividendos" --tipo simulacao
python -m rvlocal carteiras                         # lista e compara (patrimônio, acumulado, nota)
python -m rvlocal --carteira cliente-017 mesa       # qualquer comando, em qualquer carteira
```

**Clientes e LGPD:** identifique o cliente só por um código. A plataforma recusa CPF, e-mail e afins no
nome da carteira de cliente. O vínculo código → pessoa fica fora da plataforma.

**Regras por carteira:** um cliente com outra política (ex.: até 35% num ETF de índice) ganha um
`carteiras/<id>/config/regras.toml` próprio; o que a carteira não definir vem da configuração geral.

### Universo de ativos e histórico

```bash
python -m rvlocal ativo WEGE3 --nome WEG --classe acao --setor industria --fatores exportadora --receita-usd-pct 50 --monitorar
python -m rvlocal ativo VOO --classe etf_ext --moeda USD --pais US --setor indice_eua
python -m rvlocal historico --periodo 2y            # fechamentos históricos do Yahoo (fonte única, marcados)
```

`--monitorar` faz a coleta acompanhar o ativo mesmo sem posição em nenhuma carteira. A tela **Ativos** do
painel mostra cada ativo, os retornos de 1 dia a 12 meses, a volatilidade e em quais carteiras ele está.

### Montar e testar uma carteira (recomendada de analista, proposta de cliente, ideia sua)

```bash
# monta a carteira com os pesos-alvo no fechamento da data (o que sobra fica em caixa)
python -m rvlocal --carteira analista-casa-x rebalancear --data 2026-06-01 --capital 100000 \
  --pesos "WEGE3=20, ITUB4=20, BOVA11=30, VOO=20" --fonte "Casa X" --justificativa "carteira de junho"
# cada mês, a nova recomendação (o que sai da lista é vendido)
python -m rvlocal --carteira analista-casa-x rebalancear --data 2026-07-01 --pesos "WEGE3=25, ITUB4=25, BOVA11=40"
# roda os fechamentos do período: TWR, risco, mesa, boletins (o mesmo código da rotina diária)
python -m rvlocal --carteira analista-casa-x reprocessar --desde 2026-06-01
```

`rebalancear` mostra o plano (atual → alvo, peso efetivo) e pede confirmação. Ele recusa se faltar preço
na data (nunca estima), converte câmbio quando precisa e grava uma decisão de rebalanceamento com os
pesos. Uma carteira de analista não tem stop nem alvo por ativo, então o boletim mostra isso na
qualidade das decisões, o que também diz algo sobre a recomendação.

## 5. Começar com os seus dados

### 5.1 Cadastrar os instrumentos

Use `python -m rvlocal ativo ...` (seção 4) ou edite `data/livros/instrumentos.json` na sua pasta de dados (modelo em `exemplos/instrumentos.json`). Campos:
`classe` (acao, fii, etf, bdr, acao_ext, etf_ext, opcao, rf, fundo, cripto), `moeda`, `pais`, `setor`,
`fatores` (ex.: `juro_longo`, `exportadora`: entram no limite por fator), `receita_usd_pct` (exposição
econômica ao dólar).

### 5.2 Escrever as fichas de tese ANTES de operar

```bash
python -m rvlocal tese --arquivo exemplos/ficha_tese.json
# mudar algo depois = nova versão, com motivo:
python -m rvlocal tese --arquivo ficha_wege_v2.json --motivo "resultado do 3T abaixo do esperado"
```

A ficha guarda tese, preço justo, cenários com probabilidade, "muda de ideia se", **nível de compra, alvo e
stop**. Alvo e stop da ficha vigente são os que a vigilância e as regras usam. Nenhuma versão é apagada.

### 5.3 Registrar a carteira e cada operação, com o checklist

```bash
# aporte (fluxo externo, sempre em R$)
echo '{"id":"op-001","data":"2026-11-03","tipo":"aporte","valor":100000}' >> data/livros/operacoes.jsonl

# compra COM decisão e checklist de 9 itens (recusa se faltar item, a menos que você aceite pontuar menos)
python -m rvlocal operar --tipo compra --ativo WEGE3 --qtd 300 --preco 42.10 --custos 4.90 \
  --tese T-WEGE3 --justificativa "nível de compra atingido; dólar acima de 5,60" --horizonte "24 meses" \
  --tamanho-pct 12 --risco-max-pct 1.0 --stop 36 --alvo 55
```

`operar` mostra o checklist, calcula o risco-retorno, **recusa** se o caixa ficar negativo ou se o
instrumento não estiver cadastrado, e pede confirmação antes de gravar a decisão e a operação.
Para o exterior: cadastre o ativo com `moeda: "USD"`, registre a remessa como operação `cambio`
(`{"tipo":"cambio","de":"BRL","para":"USD","valor_de":5600,"valor_para":1000}`) e use `--cambio` no `operar`.

Já tem o histórico no formato antigo (`data/operacoes.jsonl`, `ativos.json`, `hipoteses.json`)?
Rode `python -m rvlocal migrar`: converte para os livros e renomeia os antigos para `*.migrado`.

### 5.4 Registrar hipóteses testáveis

```bash
python -m rvlocal hipotese --arquivo exemplos/hipotese.json
python -m rvlocal hipotese                          # placar
python -m rvlocal hipotese --ativar H-IA-01 --motivo "concordo"   # o seu "sim" para uma hipótese da IA
```

### 5.5 Conferir tudo

```bash
python -m rvlocal validar      # razão, fichas, hipóteses, natureza dos dados, imutabilidade, calendário
```

## 6. A rotina diária

| Horário (BRT) | Comando | O que faz |
|---|---|---|
| 07:45 | `python -m rvlocal cobranca --todas` | O que o sistema precisa de você: rotina que falhou, pendência vencida, ficha sem revisão, hipótese aguardando o seu sim |
| 08:20 · 09:40 | `python -m rvlocal coletar --modo manha` / `flash` | Coleta e conferência do dólar contra o BCB |
| 09:45–18:15 | `python -m rvlocal vigiar` (a cada 10 min) | Stop, alvo, movimento fora do padrão, fonte congelada; stop tocado vira pendência |
| 18:00 | `python -m rvlocal coletar --modo fechamento` | Grava só preço conferido e do dia |
| 18:05 | `python -m rvlocal fechar --todas` | Patrimônio, TWR, sleeves, regras, risco, mesa, placar de hipóteses, em cada carteira |
| 18:05 | `python -m rvlocal boletim --tipo diario` | Nota do dia |
| Sexta | `python -m rvlocal boletim --tipo semanal --todas` | Boletim semanal de cada carteira |
| Dia 1º | `boletim --tipo mensal`, `--tipo trimestral`, `fiscal` | Consolidação e apuração |

Respondendo a uma pendência (pelo painel, na tela Mesa, ou pela linha de comando):

```bash
python -m rvlocal mesa
python -m rvlocal decisao --data 2026-11-04 --tipo stop --ativo WEGE3 --decisao manter \
  --motivo "queda setorial, tese intacta" --nova-invalidacao "fechamento abaixo de 34" --alerta AL-2026-11-04-001
```

Repescagem de um dia que não rodou: `python -m rvlocal fechar --data 2026-11-04` (refaz as vistas; os livros não mudam).
DARF pago: `python -m rvlocal darf-pago --mes 2026-10 --valor 288.53`.

### Automatizar no GitHub Actions

Os workflows estão em `.github/workflows/` com os **agendamentos desligados** (decisão D-2). Para ligar:

1. Rode `python -m rvlocal testar-fontes` na sua máquina: as 5 fontes devem responder.
2. Confira os feriados da B3 do ano e registre em `config/feriados.toml` (`anos_conferidos`).
3. Crie os segredos `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BRAPI_TOKEN` (Settings → Secrets → Actions).
4. Descomente os blocos `schedule:` de `rotina-diaria.yml` e `vigilancia.yml`.

O workflow `testes.yml` já roda a suíte a cada push e PR.

### O recap das 18:15 (IA)

Crie uma tarefa agendada do Claude (dias úteis, 18:15) com o texto de `prompts/recap_1815.md` e o
repositório anexado. O prompt manda a IA **ler** o diário e o risco, sem recalcular nada.

## 7. Onde mexer nos parâmetros (`config/`)

| Arquivo | O que define |
|---|---|
| `regras.toml` | Teto/piso de posição, teto de setor, caixa mínimo, gatilho de realização, validade das decisões, prazos da mesa, limites da vigilância |
| `risco.toml` | Teto por fator, exposição ao dólar, drawdown máximo, VaR, stress, HHI, bandas do nível 1 |
| `stress.toml` | Cenários de stress pré-registrados |
| `placar.toml` | Pesos do boletim, escala de cada critério, tetos, escala de letras, limiar das hipóteses |
| `fiscal.toml` | Alíquotas, isenção, compensação (a validar com o contador) |
| `rotina.toml` | Horários e rotinas esperadas (o alarme de falha usa este arquivo) |
| `feriados.toml` | Ajustes ao calendário calculado da B3 e anos conferidos |

## 8. Vitrine (GitHub Pages) e, mais adiante, Vercel

**Vitrine:** o workflow `.github/workflows/vitrine.yml` gera a base DEMO a partir do código e publica o
painel estático no GitHub Pages a cada envio ao `main`. Ele nunca lê a sua pasta de dados, e falha se
alguma página sair sem o selo DADOS DEMO. Ativação, uma vez: *Settings → Pages → Source: GitHub Actions*.
Endereço: `https://crispimdouglascp-rgb.github.io/an-lise-mercado/`.

**Vercel (mais adiante):** para ver os seus dados reais fora de casa, a ideia é publicar a exportação
estática (`python -m rvlocal painel --exportar site`) da sua pasta PRIVADA, com proteção de acesso da Vercel.
É só leitura: decisões continuam sendo registradas no painel local. Fica para quando a carteira existir.

## 9. Regras que a plataforma impõe a si mesma

- O código calcula; a IA só interpreta. A nota do boletim não passa por modelo de linguagem.
- Preço faltante é lacuna, nunca estimativa; duas fontes divergentes = lacuna, nunca média.
- Livros só por acréscimo: o `validar` falha se uma linha já commitada mudar.
- Todo registro tem `natureza` (real, demo, estimativa, hipótese).
- Nenhuma operação é executada; nenhuma posição é alterada automaticamente.
