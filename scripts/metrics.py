"""Gera os gráficos do README (contribuições e linguagens) a partir de dados públicos do GitHub.

Uso: python scripts/metrics.py
Só usa a biblioteca padrão. Com GITHUB_TOKEN no ambiente, as chamadas à API usam o token.
"""
import datetime
import json
import os
import re
import urllib.request
from collections import defaultdict
from xml.sax.saxutils import escape

USER = "Joaopredondo"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")
WIDTH = 840
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
EASE = "cubic-bezier(.23, 1, .32, 1)"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
THEMES = {
    "light": {"ink": "#1f2328", "muted": "#59636e", "track": "#d8dee4", "accent": "#d9532b",
              "steps": ["#1f2328", "#57606a", "#8c959f", "#afb8c1"]},
    "dark": {"ink": "#f0f6fc", "muted": "#9198a1", "track": "#30363d", "accent": "#ff8a65",
             "steps": ["#f0f6fc", "#b1bac4", "#7d8590", "#545d68"]},
}


def fetch(url, accept="application/vnd.github+json"):
    headers = {"User-Agent": "readme-metrics", "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
        return resp.read().decode("utf-8")


def contributions():
    """Lê o calendário público de contribuições e devolve [(data, quantidade)] em ordem."""
    html = fetch(f"https://github.com/users/{USER}/contributions", accept="text/html")
    ids = dict(re.findall(r'data-date="(\d{4}-\d\d-\d\d)"[^>]*id="([^"]+)"', html))
    tips = dict(re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]+)</tool-tip>', html))
    days = []
    for date, cell in ids.items():
        m = re.match(r"\s*(\d+)\s+contribution", tips.get(cell, ""))
        days.append((datetime.date.fromisoformat(date), int(m.group(1)) if m else 0))
    days.sort()
    if not days:
        raise SystemExit("calendário de contribuições vazio; o formato da página pode ter mudado")
    return days


def languages():
    """Conta a linguagem principal de cada repositório público próprio (sem forks).

    A soma por bytes distorce o resultado quando um único repositório traz arquivos grandes,
    então o gráfico usa a contagem de repositórios.
    """
    repos = json.loads(fetch(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    totals = defaultdict(int)
    for repo in repos:
        if not repo["fork"] and repo["language"]:
            totals[repo["language"]] += 1
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def activity_svg(days, t):
    weeks = defaultdict(int)
    first = {}
    for date, count in days:
        key = date - datetime.timedelta(days=(date.weekday() + 1) % 7)  # domingo da semana
        weeks[key] += count
        first.setdefault((date.year, date.month), key)
    keys = sorted(weeks)
    total = sum(weeks.values())
    peak = max(weeks.values()) or 1
    top, base = 86, 176
    step = WIDTH / len(keys)
    bar = round(step * 0.62, 2)
    bars, labels = [], []
    for i, key in enumerate(keys):
        x = round(i * step + (step - bar) / 2, 2)
        n = weeks[key]
        if n:
            h = max(4, round((base - top) * n / peak, 2))
            bars.append(f'<rect class="bar" style="animation-delay:{i * 14}ms" x="{x}" y="{round(base - h, 2)}" '
                        f'width="{bar}" height="{h}" rx="2" fill="{t["accent"]}"><title>{n} na semana de '
                        f'{key.day} de {MESES[key.month - 1]}</title></rect>')
        else:
            bars.append(f'<rect x="{x}" y="{base - 2}" width="{bar}" height="2" rx="1" fill="{t["track"]}"/>')
    seen = set()
    for (year, month), key in sorted(first.items()):
        i = keys.index(key)
        if i in seen or i * step > WIDTH - 24:
            continue
        seen.add(i)
        labels.append(f'<text x="{round(i * step, 2)}" y="200" fill="{t["muted"]}" font-size="11.5">{MESES[month - 1]}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} 208" width="{WIDTH}" height="208" role="img" aria-label="{total} contribuições nos últimos 12 meses, por semana">
  <style>
    text {{ font-family: {SANS}; }}
    .bar {{ transform-box: fill-box; transform-origin: 50% 100%; animation: rise .7s {EASE} backwards; }}
    .num {{ animation: fade .6s {EASE} backwards; }}
    @keyframes rise {{ from {{ transform: scaleY(.08); opacity: 0; }} }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(6px); }} }}
    @media (prefers-reduced-motion: reduce) {{ .bar, .num {{ animation: none; }} }}
  </style>
  <text x="0" y="14" fill="{t["muted"]}" font-size="11.5" font-weight="600" letter-spacing="1.2">CONTRIBUIÇÕES · ÚLTIMOS 12 MESES</text>
  <g class="num">
    <text x="0" y="58" fill="{t["ink"]}" font-size="38" font-weight="600" letter-spacing="-1">{total}</text>
    <text x="{14 + 23 * len(str(total))}" y="58" fill="{t["muted"]}" font-size="15">contribuições, somadas por semana</text>
  </g>
  {"".join(bars)}
  {"".join(labels)}
</svg>
"""


def languages_svg(langs, t):
    total = sum(size for _, size in langs) or 1
    main = langs[:5]
    rest = total - sum(size for _, size in main)
    parts = main + ([("Outras", rest)] if rest > 0 else [])
    colors = [t["accent"]] + t["steps"] + [t["track"]]
    segs, legend, x = [], [], 0.0
    lx = 0
    for i, (name, size) in enumerate(parts):
        w = WIDTH * size / total
        color = t["track"] if name == "Outras" else colors[min(i, len(colors) - 2)]
        segs.append(f'<rect x="{round(x, 2)}" y="34" width="{round(max(w - 2, 1), 2)}" height="12" fill="{color}"/>')
        x += w
        label = f"{name} {size}"
        legend.append(f'<g class="leg" style="animation-delay:{500 + i * 70}ms"><rect x="{lx}" y="67" width="10" height="10" rx="2" fill="{color}"/>'
                      f'<text x="{lx + 17}" y="76.5" fill="{t["ink"]}" font-size="13.5">{escape(name)} '
                      f'<tspan fill="{t["muted"]}">{size}</tspan></text></g>')
        lx += 34 + round(len(label) * 7.6)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} 90" width="{WIDTH}" height="90" role="img" aria-label="Linguagem principal por repositório público: {escape(', '.join(f'{n} {s}' for n, s in parts))}">
  <defs><clipPath id="pill"><rect x="0" y="34" width="{WIDTH}" height="12" rx="6"/></clipPath></defs>
  <style>
    text {{ font-family: {SANS}; }}
    .fill {{ transform-origin: 0 0; animation: grow 1s {EASE} backwards; }}
    .leg {{ animation: fade .5s {EASE} backwards; }}
    @keyframes grow {{ from {{ transform: scaleX(.04); }} }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(4px); }} }}
    @media (prefers-reduced-motion: reduce) {{ .fill, .leg {{ animation: none; }} }}
  </style>
  <text x="0" y="14" fill="{t["muted"]}" font-size="11.5" font-weight="600" letter-spacing="1.2">LINGUAGEM PRINCIPAL · POR REPOSITÓRIO PÚBLICO</text>
  <g clip-path="url(#pill)"><g class="fill">{"".join(segs)}</g></g>
  {"".join(legend)}
</svg>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    days = contributions()
    langs = languages()
    for name, t in THEMES.items():
        for kind, svg in (("activity", activity_svg(days, t)), ("languages", languages_svg(langs, t))):
            with open(os.path.join(OUT, f"{kind}-{name}.svg"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(svg)
    print("contribuições:", sum(c for _, c in days), "| linguagens:", [n for n, _ in langs[:6]])


if __name__ == "__main__":
    main()
