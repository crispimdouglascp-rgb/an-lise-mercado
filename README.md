# Plataforma pessoal de análise e gestão de renda variável

Evolução do projeto **RV Local** para uma plataforma completa de coleta, vigilância, síntese e placar, no modelo das apresentações de referência.

**O código calcula; a IA interpreta. Nenhuma ordem é executada pela plataforma.** Carteira pessoal; não constitui recomendação de investimento.

## Onde está cada coisa

| Caminho | Conteúdo |
|---|---|
| `rv-local/` | Projeto atual, **importado sem alterações** do ZIP (fase 1, só Brasil). Veja `rv-local/README.md` |
| `docs/01-diagnostico.md` | Fase 1: auditoria, comparação com a referência, defeitos comprovados |
| `docs/02-arquitetura.md` | Fase 2: camadas, livros (modelo de dados), agentes, placar, risco, opções, interface, rotina |
| `docs/03-plano.md` | Fase 3: plano por ciclos, dependências, critérios de pronto e **decisões pendentes** |

## Estado

- Ciclo 1 (diagnóstico e arquitetura): **concluído**.
- Ciclo 2 (construção): aguardando as decisões D-1 a D-8 de `docs/03-plano.md`.

Os workflows em `rv-local/.github/` estão **inativos de propósito**: o GitHub só lê `.github/` na raiz. Movê-los ativaria a vigilância a cada 10 minutos (decisão D-2).

## Testes do projeto atual

```bash
cd rv-local
pip install pytest
PYTHONPATH=src python -m pytest -q   # 38 testes, dados simulados
```
