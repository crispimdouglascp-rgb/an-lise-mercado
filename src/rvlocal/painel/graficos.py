"""Gráficos em SVG gerados no servidor (sem JavaScript, funcionam no HTML estático e no celular).

Cores vêm de variáveis CSS (--s1..--s4, --tinta-3, --linha) para respeitar o tema claro/escuro.
"""
from __future__ import annotations

from html import escape


def num(v: float, casas: int = 1) -> str:
    """Número no formato brasileiro (1.234,5)."""
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d: str) -> str:
    return f"{d[8:10]}/{d[5:7]}"


def linhas(series: list[dict], altura: int = 220, largura: int = 680, base: float | None = 100.0) -> str:
    """series: [{"nome", "pontos": [(data, valor)], "cor": "var(--s1)", "grossa": bool}]"""
    pts_all = [v for s in series for _, v in s["pontos"] if v is not None]
    datas = sorted({d for s in series for d, _ in s["pontos"]})
    if len(datas) < 2 or not pts_all:
        return '<p class="vazio">Sem pontos suficientes para o gráfico.</p>'
    lo, hi = min(pts_all + ([base] if base else [])), max(pts_all + ([base] if base else []))
    if hi - lo < 1e-9:
        hi, lo = hi + 1, lo - 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    ml, mr, mt, mb = 44, 12, 10, 26
    w, h = largura - ml - mr, altura - mt - mb
    idx = {d: i for i, d in enumerate(datas)}

    def x(d):
        return ml + idx[d] / (len(datas) - 1) * w

    def y(v):
        return mt + (hi - v) / (hi - lo) * h

    out = [f'<svg viewBox="0 0 {largura} {altura}" class="grafico" role="img" '
           f'aria-label="{escape(", ".join(s["nome"] for s in series))}">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line x1="{ml}" x2="{largura - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grade"/>'
                   f'<text x="{ml - 6}" y="{y(v) + 4:.1f}" class="eixo" text-anchor="end">{num(v)}</text>')
    if base is not None and lo < base < hi:
        out.append(f'<line x1="{ml}" x2="{largura - mr}" y1="{y(base):.1f}" y2="{y(base):.1f}" class="base"/>')
    for i in sorted({0, len(datas) // 3, 2 * len(datas) // 3, len(datas) - 1}):
        out.append(f'<text x="{x(datas[i]):.1f}" y="{altura - 6}" class="eixo" text-anchor="middle">'
                   f'{_fmt_data(datas[i])}</text>')
    for s in series:
        p = [(d, v) for d, v in s["pontos"] if v is not None]
        if len(p) < 2:
            continue
        caminho = " ".join(f"{'M' if i == 0 else 'L'}{x(d):.1f},{y(v):.1f}" for i, (d, v) in enumerate(p))
        out.append(f'<path d="{caminho}" fill="none" stroke="{s["cor"]}" '
                   f'stroke-width="{3 if s.get("grossa") else 1.6}" stroke-linejoin="round"/>')
        d, v = p[-1]
        out.append(f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="3.5" fill="{s["cor"]}"/>')
    out.append("</svg>")
    leg = "".join(f'<span class="leg"><i style="background:{s["cor"]}"></i>{escape(s["nome"])}</span>' for s in series)
    return "".join(out) + f'<div class="legenda">{leg}</div>'


def barras(itens: list[tuple[str, float]], maximo: float | None = None, sufixo: str = "%",
           limite: float | None = None) -> str:
    """Barras horizontais (exposição, pesos). `limite` desenha a marca do teto."""
    if not itens:
        return '<p class="vazio">Sem dados.</p>'
    m = maximo or max(abs(v) for _, v in itens) or 1
    if limite:
        m = max(m, limite * 1.1)
    linhas_ = []
    for nome, v in itens:
        larg = abs(v) / m * 100
        cls = "neg" if v < 0 else ("estoura" if limite and v > limite else "")
        marca = f'<span class="teto" style="left:{limite / m * 100:.1f}%"></span>' if limite else ""
        linhas_.append(f'<div class="barra"><span class="rot">{escape(str(nome))}</span>'
                       f'<span class="trilho">{marca}<span class="cheio {cls}" style="width:{larg:.1f}%"></span></span>'
                       f'<span class="val num">{num(v)}{sufixo}</span></div>')
    return '<div class="barras">' + "".join(linhas_) + "</div>"


def barra_100(itens: list[tuple[str, float]]) -> str:
    """Barra 100% empilhada (composição), como na capa da referência."""
    tot = sum(v for _, v in itens if v > 0) or 1
    cores = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--tinta-3)"]
    segs, leg = [], []
    for i, (n, v) in enumerate(i for i in itens if i[1] > 0):
        c = cores[min(i, len(cores) - 1)]
        segs.append(f'<span style="width:{v / tot * 100:.2f}%;background:{c}" title="{escape(n)} {num(v)}%"></span>')
        leg.append(f'<span class="leg"><i style="background:{c}"></i>{escape(n)} {num(v)}%</span>')
    return f'<div class="b100">{"".join(segs)}</div><div class="legenda">{"".join(leg)}</div>'


def notas(historico: list[dict], largura: int = 680, altura: int = 160) -> str:
    """Evolução da nota final (0 a 5) por edição."""
    pts = [(b["fim"], b["nota_final"]) for b in historico]
    if len(pts) < 2:
        return '<p class="vazio">A evolução aparece a partir da 2ª edição.</p>'
    return linhas([{"nome": "nota do boletim (0 a 5)", "pontos": pts, "cor": "var(--s1)", "grossa": True}],
                  altura=altura, largura=largura, base=None)
