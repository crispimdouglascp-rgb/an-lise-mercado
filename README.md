# RV Local: plataforma pessoal de gestão e análise de renda variável

Coleta, vigilância, síntese e placar para uma carteira pessoal (Brasil e exterior).
**O código calcula; a IA interpreta. Nenhuma ordem é enviada pela plataforma.**
Carteira pessoal; não constitui recomendação de investimento.

```bash
pip install -e ".[painel,dev]"
python -m rvlocal demo --destino demo                 # 3 carteiras fictícias (DADOS DEMO)
RVLOCAL_HOME=demo python -m rvlocal painel            # http://127.0.0.1:8765
python -m rvlocal iniciar --destino ~/rvlocal-dados   # seus dados reais: pasta PRIVADA, fora deste repositório
```

**Vitrine (só DEMO):** https://crispimdouglascp-rgb.github.io/an-lise-mercado/ (após ativar o GitHub Pages).

**Várias carteiras:** a sua, as de clientes (identificados por código) e as recomendadas por analistas,
cada uma com os próprios livros e boletim, todas comparadas pelo mesmo critério nas telas Carteiras e Ativos.

## As quatro camadas

| Camada | O que faz | Motor | Onde |
|---|---|---|---|
| 01 Coleta | Preço em duas fontes comparadas; divergência vira lacuna, nunca média; dólar conferido com o BCB | Código | `fontes.py`, `coleta.py`, `series.py` (SQLite) |
| 02 Vigilância e risco | Regras, monitor de risco (exposição, HHI, vol, beta, VaR/CVaR com 250 pregões, drawdown, stress pré-registrado), mesa de pendências com prazo | Código | `regras.py`, `risco.py`, `mesa.py`, `vigilancia.py` |
| 03 Síntese | Briefing, recap, auditoria escrita | IA (lê, não calcula) | `prompts/` · agentes completos no Ciclo 3 |
| 04 Placar | Placar de hipóteses (limiar, 8 gates, Wilson) e boletim do gestor 0 a 5 com evidência | Código | `hipoteses.py`, `boletim.py` |

Base de tudo: **livros só por acréscimo** em `data/livros/` (operações, decisões, fichas de tese versionadas,
hipóteses, pontos do placar, eventos, pendências, boletins, heartbeat), verificados contra o git.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/04-como-usar.md`](docs/04-como-usar.md) | **Instalação, demo, primeiros passos, rotina diária, parâmetros** |
| [`docs/01-diagnostico.md`](docs/01-diagnostico.md) | Auditoria do projeto original e defeitos D1 a D14 |
| [`docs/02-arquitetura.md`](docs/02-arquitetura.md) | Arquitetura: livros, camadas, agentes, placar, risco, interface |
| [`docs/03-plano.md`](docs/03-plano.md) | Plano por ciclos, status e próximos passos |
| [`docs/rv-local-fase1-README.md`](docs/rv-local-fase1-README.md) | README original da fase 1 |

## Estado

- **Ciclo 1** (diagnóstico e arquitetura): concluído.
- **Ciclo 2** (carteira, teses, decisões, risco, placar, painel, fiscal): concluído.
- **Ciclo 2.1** (várias carteiras, universo de ativos, rebalanceamento por pesos-alvo, histórico, dados privados, vitrine): concluído, 83 testes.
- **Ciclo 3** (agentes de IA, coleta ampliada, valuation, quant, backtest, opções): próximo.

Os agendamentos do GitHub Actions estão **desligados** até as fontes de preço passarem no teste ao vivo
(`python -m rvlocal testar-fontes`). Veja a seção "Automatizar" do guia.
