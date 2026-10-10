"""Gera os SVGs do README (aparelho, inventário, títulos e selos) a partir de dados públicos do GitHub.

Uso: python scripts/build.py
Só usa a biblioteca padrão. Com GITHUB_TOKEN no ambiente, as chamadas à API usam o token.

O GitHub não carrega fontes dentro de SVG, então o texto é desenhado com os contornos da fonte
Silkscreen (licença OFL, ver OFL-Silkscreen.txt), guardados em glyphs.json. Os ícones, em
icons.json, vêm do Simple Icons (CC0). A fonte tem pixel de 1/8 do corpo: use corpos múltiplos de 8
(16, 24, 32) para as bordas ficarem nítidas.
"""
import datetime
import json
import os
import re
import urllib.request
from collections import defaultdict

USER = "Joaopredondo"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "media")
GLYPHS = json.load(open(os.path.join(HERE, "glyphs.json"), encoding="utf-8"))
ICONS = json.load(open(os.path.join(HERE, "icons.json"), encoding="utf-8"))

WIDTH = 560  # largura única de todos os blocos do README

THEMES = {
    "dark": {
        "shell": "#d9d3c4", "edge": "#b9b3a3", "shell_ink": "#5a564b", "bezel": "#2b2d34", "btn": "#c9473e",
        "accent": "#58a6ff", "on_accent": "#0d1117", "card": "#151a21", "card_edge": "#30363d", "ink": "#f0f6fc",
    },
    "light": {
        "shell": "#ebe6d8", "edge": "#cdc7b4", "shell_ink": "#6a665b", "bezel": "#2b2d34", "btn": "#c9473e",
        "accent": "#0b5fd0", "on_accent": "#ffffff", "card": "#f6f8fa", "card_edge": "#d0d7de", "ink": "#1f2328",
    },
}
LCD = {"bg": "#b9c99c", "dim": "#9fb182", "edge": "#8a9c70", "ink": "#222c1b",
       "ramp": ["#aebf90", "#93a676", "#70865a", "#4a5e3a", "#222c1b"]}

INVENTORY = [("JAVA", "java"), ("SPRING", "spring"), ("PGSQL", "postgres"), ("ORACLE", "oracle"),
             ("DOCKER", "docker"), ("JS", "js"), ("TS", "ts"), ("ANGULAR", "angular"),
             ("REACT", "react"), ("HTML", "html"), ("CSS", "css"), ("GIT", "git")]
PERIODS = {"1": "2025 - HOJE", "2": "2023 - 2025", "3": "2022 - 2023"}
CARTRIDGES = {"prancha": "PRANCHA KIDS", "lume": "LUME"}
SECTIONS = {"sobre": "SOBRE MIM", "inventario": "INVENTÁRIO", "cartuchos": "CARTUCHOS", "historico": "HISTÓRICO"}


def fetch(url, accept="application/vnd.github+json", data=None):
    headers = {"User-Agent": "readme-build", "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
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
    """Conta a linguagem principal de cada repositório público próprio (sem forks)."""
    repos = json.loads(fetch(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    totals = defaultdict(int)
    for repo in repos:
        if not repo["fork"] and repo["language"]:
            totals[repo["language"]] += 1
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def totals():
    """Commits e pull requests dos últimos 12 meses, e repositórios públicos. None se faltar o dado."""
    out = {"commits": None, "prs": None, "repos": None}
    try:
        out["repos"] = json.loads(fetch(f"https://api.github.com/users/{USER}"))["public_repos"]
    except Exception:
        pass
    if os.environ.get("GITHUB_TOKEN"):
        query = ('query{user(login:"%s"){contributionsCollection{totalCommitContributions '
                 'totalPullRequestContributions}}}' % USER)
        try:
            body = json.dumps({"query": query}).encode()
            res = json.loads(fetch("https://api.github.com/graphql", data=body))
            c = res["data"]["user"]["contributionsCollection"]
            out["commits"], out["prs"] = c["totalCommitContributions"], c["totalPullRequestContributions"]
        except Exception:
            pass
    return out


class Svg:
    def __init__(self, width, height, title):
        self.w, self.h, self.title = width, height, title
        self.defs = {}
        self.parts = []

    def add(self, markup):
        self.parts.append(markup)

    def rect(self, x, y, w, h, fill, rx=0, extra=""):
        self.add(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" fill="{fill}" {extra}/>')

    def measure(self, s, size, weight="R", track=0):
        adv = sum(GLYPHS[weight].get(str(ord(c)), GLYPHS[weight]["32"])[0] for c in s)
        return adv * size / 1000 + track * max(len(s) - 1, 0)

    def text(self, x, y, s, size, fill, weight="R", anchor="start", track=0, extra=""):
        """Escreve s com os contornos da Silkscreen. size é o corpo em px; 8 px de corpo = 1 px de pixel."""
        width = self.measure(s, size, weight, track)
        cx = x - (width if anchor == "end" else width / 2 if anchor == "middle" else 0)
        scale = size / 1000
        uses = []
        for ch in s:
            code = str(ord(ch))
            glyph = GLYPHS[weight].get(code) or GLYPHS[weight]["32"]
            if glyph[1]:
                gid = f"{weight}{code}"
                self.defs[gid] = glyph[1]
                uses.append(f'<use href="#{gid}" transform="translate({cx:.2f} {y:g}) scale({scale:g} {-scale:g})"/>')
            cx += glyph[0] * scale + track
        self.add(f'<g fill="{fill}" {extra}>' + "".join(uses) + "</g>")

    def render(self):
        defs = "".join(f'<path id="{k}" d="{v}"/>' for k, v in sorted(self.defs.items()))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:g}" height="{self.h:g}" '
                f'viewBox="0 0 {self.w:g} {self.h:g}" role="img"><title>{self.title}</title>'
                f'<defs>{defs}</defs>' + "".join(self.parts) + "</svg>\n")


def calendar_columns(days):
    """Agrupa os dias em colunas de domingo a sábado, com nível 0 a 4 por dia."""
    peak = max(n for _, n in days) or 1

    def level(n):
        if n == 0:
            return 0
        q = n / peak
        return 1 if q <= .25 else 2 if q <= .5 else 3 if q <= .75 else 4

    cols, col = [], [0] * ((days[0][0].weekday() + 1) % 7)
    for date, n in days:
        col.append(level(n))
        if len(col) == 7:
            cols.append(col)
            col = []
    if col:
        cols.append(col + [0] * (7 - len(col)))
    return cols[-53:]


def blink(dur="1.1s"):
    return (f'<animate attributeName="opacity" values="1;0" keyTimes="0;0.5" dur="{dur}" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


def snake(svg, ncols, left, top, pitch=8, size=6, length=4, dur=14):
    """Cobrinha em passos discretos, em zigue-zague, atravessando a grade da esquerda para a direita."""
    def pos(i):
        r = i % 12
        return i * pitch, (r if r <= 6 else 12 - r) * pitch
    clip = f"clip{left}"
    svg.add(f'<clipPath id="{clip}"><rect x="{left}" y="{top}" width="{ncols * pitch - 2}" height="{7 * pitch - 2}"/></clipPath>')
    svg.add(f'<g clip-path="url(#{clip})">')
    for k in range(length):
        values = []
        for i in range(ncols):
            j = i - k
            x, y = pos(j) if j >= 0 else (-pitch * 2, 0)
            values.append(f"{left + x:g} {top + y:g}")
        key = ";".join(f"{i / ncols:.4f}" for i in range(ncols))
        svg.add(f'<rect width="{size}" height="{size}" fill="{LCD["ink"]}" stroke="{LCD["bg"]}" stroke-width="1">'
                f'<animateTransform attributeName="transform" type="translate" values="{";".join(values)}" '
                f'keyTimes="{key}" dur="{dur}s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    svg.add("</g>")


def device(theme, data):
    t = THEMES[theme]
    W, H = WIDTH, 670
    svg = Svg(W, H, "Console portátil com os números do perfil, a cobrinha sobre o calendário e as linguagens")
    # carcaça com sombra embaixo
    for dy, fill in ((6, t["edge"]), (0, t["shell"])):
        svg.add(f'<path d="M24 {dy}H536a24 24 0 0 1 24 24V{616 + dy}a48 48 0 0 1-48 48H24a24 24 0 0 1-24-24V{24 + dy}A24 24 0 0 1 24 {dy}Z" '
                f'fill="{fill}"/>')
    svg.text(28, 40, "JPR-1 · DEV HANDHELD", 16, t["shell_ink"])
    svg.text(532, 40, "MARINGÁ · PR", 16, t["shell_ink"], anchor="end")

    # tela de cima
    svg.rect(28, 56, 504, 192, t["bezel"], 12)
    svg.rect(44, 72, 472, 160, LCD["bg"], extra=f'stroke="{LCD["edge"]}" stroke-width="2"')
    svg.text(64, 98, "JOGADOR 1", 16, LCD["ink"], extra='opacity=".7"')
    svg.text(64, 128, "JOÃO PEDRO", 24, LCD["ink"], "B")
    svg.text(64, 156, "REDONDO", 24, LCD["ink"], "B")
    svg.text(64, 180, "CLASSE · DEV JAVA", 16, LCD["ink"])
    svg.text(64, 198, "SUB · FULL STACK", 16, LCD["ink"])
    svg.add(f'<g>{blink()}<path d="M64 208h3v3h3v3h3v3h-3v3h-3v3h-3z" fill="{LCD["ink"]}"/>')
    svg.text(80, 222, "PRESS START", 16, LCD["ink"], "B")
    svg.add("</g>")
    stats = [("CONTRIB.", data["contrib"]), ("COMMITS", data["commits"]),
             ("PULL REQ.", data["prs"]), ("REPOS", data["repos"])]
    stats = [(label, v) for label, v in stats if v is not None]
    peak = max(v for _, v in stats) or 1
    bx, bw = 336, 160
    for i, (label, value) in enumerate(stats):
        y = 98 + i * 34
        svg.text(bx, y, label, 16, LCD["ink"])
        svg.text(bx + bw, y, str(value), 16, LCD["ink"], anchor="end")
        svg.rect(bx, y + 7, bw, 8, LCD["dim"])
        w = max(round(bw * value / peak), 4 if value else 0)
        vals = ";".join(f"{round(w * s / 12)}" for s in range(13))
        keys = ";".join(f"{s / 12:.4f}" for s in range(13))
        svg.add(f'<rect x="{bx}" y="{y + 7}" width="{w}" height="8" fill="{LCD["ink"]}">'
                f'<animate attributeName="width" values="{vals}" keyTimes="{keys}" dur="1.4s" '
                f'calcMode="discrete" begin="{i * 0.15:g}s" fill="freeze"/></rect>')

    svg.rect(28, 258, 504, 5, t["edge"], 2)

    # tela de baixo
    svg.rect(28, 273, 504, 252, t["bezel"], 12)
    svg.rect(44, 289, 472, 220, LCD["bg"], extra=f'stroke="{LCD["edge"]}" stroke-width="2"')
    svg.text(64, 317, "SNAKE · 12 MESES", 16, LCD["ink"])
    svg.text(496, 317, f"PONTOS {data['contrib']}", 16, LCD["ink"], anchor="end")
    cols = data["cols"]
    gx, gy = 64, 329
    for ci, col in enumerate(cols):
        for ri, lv in enumerate(col):
            svg.rect(gx + ci * 8, gy + ri * 8, 6, 6, LCD["ramp"][lv])
    snake(svg, len(cols), gx, gy)
    svg.rect(64, 397, 432, 2, LCD["ink"])
    for i, (name, count) in enumerate(data["langs"][:4]):
        y = 425 + i * 22
        svg.text(64, y, name.upper(), 16, LCD["ink"])
        n = min(count, 14)
        for b in range(n):
            svg.rect(196 + b * 9, y - 12, 6, 12, LCD["ink"])
        svg.text(196 + n * 9 + 6, y, str(count), 16, LCD["ink"])

    # comandos
    svg.add(f'<rect x="56" y="547" width="28" height="78" rx="5" fill="{t["bezel"]}"/>')
    svg.add(f'<rect x="31" y="572" width="78" height="28" rx="5" fill="{t["bezel"]}"/>')
    for cx in (262, 326):
        svg.add(f'<rect x="{cx - 24}" y="591" width="48" height="12" rx="6" fill="{t["edge"]}" transform="rotate(-20 {cx} 597)"/>')
    for cx, cy, label in ((418, 600, "E-MAIL"), (494, 574, "LINKEDIN")):
        svg.add(f'<circle cx="{cx}" cy="{cy + 3}" r="22" fill="#000" opacity=".22"/>')
        svg.add(f'<circle cx="{cx}" cy="{cy}" r="22" fill="{t["btn"]}"/>')
        svg.text(cx, cy + 42, label, 16, t["shell_ink"], anchor="middle")
    return svg.render()


def inventory(theme):
    t = THEMES[theme]
    slot, gap = 90, 4
    rows = (len(INVENTORY) + 5) // 6
    svg = Svg(WIDTH, rows * slot + (rows - 1) * gap, "Tecnologias com as quais trabalho")
    for i, (label, key) in enumerate(INVENTORY):
        x = (i % 6) * (slot + gap)
        y = (i // 6) * (slot + gap)
        assert svg.measure(label, 16) <= slot - 4, label
        svg.add(f'<rect x="{x + 1}" y="{y + 1}" width="{slot - 2}" height="{slot - 2}" fill="{t["card"]}" '
                f'stroke="{t["card_edge"]}" stroke-width="2"/>')
        svg.add(f'<path transform="translate({x + slot / 2 - 16:g} {y + 14}) scale({32 / 24:.4f})" '
                f'fill="{t["ink"]}" d="{ICONS[key]}"/>')
        svg.text(x + slot / 2, y + 70, label, 16, t["ink"], anchor="middle")
    return svg.render()


def title(theme, label, size=24, width=WIDTH):
    """Título em pixel, na cor de destaque, seguido de uma linha tracejada até a borda."""
    t = THEMES[theme]
    svg = Svg(width, size + 8, label)
    end = svg.measure(label, size, "B")
    svg.text(0, size, label, size, t["accent"], "B")
    cap = size * 0.625
    x = end + 16
    while x + 6 <= width:
        svg.rect(round(x), round(size - cap / 2 - 1), 6, 2, t["accent"], extra='opacity=".45"')
        x += 10
    return svg.render()


def badge(theme, label):
    """Selo de período, com borda azul."""
    t = THEMES[theme]
    w = round(Svg(0, 0, "").measure(label, 16)) + 28
    svg = Svg(w, 30, label)
    svg.add(f'<rect x="1" y="1" width="{w - 2}" height="28" fill="none" stroke="{t["accent"]}" stroke-width="2"/>')
    svg.text(w / 2, 20, label, 16, t["ink"], anchor="middle")
    return svg.render()


def main():
    days = contributions()
    langs = languages()
    extra = totals()
    data = {"contrib": sum(n for _, n in days), "commits": extra["commits"], "prs": extra["prs"],
            "repos": extra["repos"], "cols": calendar_columns(days), "langs": langs}
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        files = {f"device-{theme}.svg": device(theme, data), f"inventory-{theme}.svg": inventory(theme)}
        for key, label in SECTIONS.items():
            files[f"h-{key}-{theme}.svg"] = title(theme, label)
        for key, label in CARTRIDGES.items():
            files[f"c-{key}-{theme}.svg"] = title(theme, label, size=16, width=400)
        for key, label in PERIODS.items():
            files[f"b-{key}-{theme}.svg"] = badge(theme, label)
        for name, content in files.items():
            with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
    print("contribuições:", data["contrib"], "| commits:", data["commits"], "| PRs:", data["prs"],
          "| repositórios:", data["repos"], "| linguagens:", langs[:4])


if __name__ == "__main__":
    main()
