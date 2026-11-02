# data/: os seus dados

| Pasta | O que é | Versionado no git? |
|---|---|---|
| `livros/` | **Fonte da verdade.** Só por acréscimo: nunca edite nem apague uma linha; corrija com outra linha | Sim (trilha de auditoria) |
| `mercado.db` | Séries de mercado (SQLite): fechamentos com fonte, status e horário | Sim enquanto as rotinas rodam no GitHub Actions |
| `gerado/` | Vistas refeitas pelo código: diários, risco, recaps, coleta | Sim (o painel lê daqui), mas podem ser apagadas e refeitas |

Comece cadastrando os instrumentos em `livros/instrumentos.json` e registrando a carteira com
`python -m rvlocal operar ...`. Veja `docs/04-como-usar.md`.

Para explorar a plataforma sem os seus dados: `python -m rvlocal demo` (gera `demo/`, DADOS DEMO).
