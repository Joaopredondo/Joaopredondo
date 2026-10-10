"""Gera os SVGs do README (aparelho, inventário e títulos) a partir de dados públicos do GitHub.

Uso: python scripts/build.py
Só usa a biblioteca padrão. Com GITHUB_TOKEN no ambiente, as chamadas à API usam o token.

O GitHub não carrega fontes dentro de SVG, então o texto é desenhado com os contornos da fonte
Silkscreen (licença OFL, ver OFL-Silkscreen.txt), guardados em glyphs.json. Os ícones, em
icons.json, vêm do Simple Icons (CC0).
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

THEMES = {
    "dark": {
        "shell": "#d9d3c4", "edge": "#b9b3a3", "shell_ink": "#5a564b", "bezel": "#2b2d34", "btn": "#c9473e",
        "accent": "#e8734a", "card": "#151a21", "card_edge": "#30363d", "ink": "#f0f6fc",
    },
    "light": {
        "shell": "#ebe6d8", "edge": "#cdc7b4", "shell_ink": "#6a665b", "bezel": "#2b2d34", "btn": "#c9473e",
        "accent": "#b8461f", "card": "#f6f8fa", "card_edge": "#d0d7de", "ink": "#1f2328",
    },
}
LCD = {"bg": "#b9c99c", "dim": "#9fb182", "edge": "#8a9c70", "ink": "#222c1b",
       "ramp": ["#aebf90", "#93a676", "#70865a", "#4a5e3a", "#222c1b"]}

INVENTORY = [("JAVA", "java"), ("SPRING", "spring"), ("POSTGRES", "postgres"), ("ORACLE", "oracle"),
             ("DOCKER", "docker"), ("JS", "js"), ("TS", "ts"), ("ANGULAR", "angular"),
             ("REACT", "react"), ("HTML", "html"), ("CSS", "css"), ("GIT", "git")]


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


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join("%02x" % round(x + (y - x) * t) for x, y in zip(pa, pb))


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


def blink(opacity_values="1;0", dur="1.1s"):
    return (f'<animate attributeName="opacity" values="{opacity_values}" keyTimes="0;0.5" dur="{dur}" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


def snake(svg, ncols, lcd, left, top, pitch=11, size=9, length=4, dur=14):
    """Cobrinha em passos discretos, em zigue-zague, atravessando a grade da esquerda para a direita."""
    def pos(i):
        r = i % 12
        return i * pitch, (r if r <= 6 else 12 - r) * pitch
    steps = ncols
    clip = f"clip{left}"
    svg.add(f'<clipPath id="{clip}"><rect x="{left}" y="{top}" width="{ncols * pitch - 2}" height="{7 * pitch - 2}"/></clipPath>')
    svg.add(f'<g clip-path="url(#{clip})">')
    for k in range(length):
        values = []
        for i in range(steps):
            j = i - k
            x, y = pos(j) if j >= 0 else (-pitch * 2, 0)
            values.append(f"{left + x:g} {top + y:g}")
        key = ";".join(f"{i / steps:.4f}" for i in range(steps))
        svg.add(f'<rect width="{size}" height="{size}" fill="{lcd["ink"]}" stroke="{lcd["bg"]}" stroke-width="1">'
                f'<animateTransform attributeName="transform" type="translate" values="{";".join(values)}" '
                f'keyTimes="{key}" dur="{dur}s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    svg.add("</g>")


def device(theme, data):
    t = THEMES[theme]
    W, H = 760, 866
    svg = Svg(W, H, "Console portátil com os números do perfil, a cobrinha sobre o calendário e as linguagens")
    # carcaça com sombra embaixo
    for dy, fill in ((6, t["edge"]), (0, t["shell"])):
        svg.add(f'<path d="M28 {dy}H732a28 28 0 0 1 28 28V{796 + dy}a64 64 0 0 1-64 64H28a28 28 0 0 1-28-28V{28 + dy}A28 28 0 0 1 28 {dy}Z" '
                f'fill="{fill}"/>')
    svg.text(40, 52, "JPR-1 · DEV HANDHELD", 16, t["shell_ink"], track=1)
    svg.text(720, 52, "MARINGÁ · PR", 16, t["shell_ink"], anchor="end", track=1)

    # tela de cima
    svg.rect(40, 72, 680, 284, t["bezel"], 14)
    svg.rect(62, 94, 636, 240, LCD["bg"], extra=f'stroke="{LCD["edge"]}" stroke-width="2"')
    svg.text(86, 128, "JOGADOR 1", 16, LCD["ink"], extra='opacity=".7"')
    svg.text(86, 176, "JOÃO PEDRO", 32, LCD["ink"], "B")
    svg.text(86, 220, "REDONDO", 32, LCD["ink"], "B")
    svg.text(86, 268, "CLASSE · DESENVOLVEDOR JAVA", 16, LCD["ink"])
    svg.text(86, 292, "SUBCLASSE · FULL STACK", 16, LCD["ink"])
    svg.add(f'<g>{blink()}<path d="M86 306h4v4h4v4h4v4h-4v4h-4v4h-4z" fill="{LCD["ink"]}"/></g>')
    svg.add(f'<g>{blink()}')
    svg.text(106, 320, "PRESS START", 16, LCD["ink"], "B")
    svg.add("</g>")
    stats = [("CONTRIB.", data["contrib"]), ("COMMITS", data["commits"]),
             ("PULL REQ.", data["prs"]), ("REPOS", data["repos"])]
    stats = [(label, v) for label, v in stats if v is not None]
    peak = max(v for _, v in stats) or 1
    for i, (label, value) in enumerate(stats):
        y = 124 + i * 52
        svg.text(470, y, label, 16, LCD["ink"])
        svg.text(674, y, str(value), 16, LCD["ink"], anchor="end")
        svg.rect(470, y + 12, 204, 10, LCD["dim"])
        w = max(round(204 * value / peak), 4 if value else 0)
        vals = ";".join(f"{round(w * s / 12)}" for s in range(13))
        keys = ";".join(f"{s / 12:.4f}" for s in range(13))
        svg.add(f'<rect x="470" y="{y + 12}" width="{w}" height="10" fill="{LCD["ink"]}">'
                f'<animate attributeName="width" values="{vals}" keyTimes="{keys}" dur="1.4s" '
                f'calcMode="discrete" begin="{i * 0.15:g}s" fill="freeze"/></rect>')

    svg.rect(40, 366, 680, 6, t["edge"], 3)

    # tela de baixo
    svg.rect(40, 384, 680, 328, t["bezel"], 14)
    svg.rect(62, 406, 636, 284, LCD["bg"], extra=f'stroke="{LCD["edge"]}" stroke-width="2"')
    svg.text(86, 442, "SNAKE · 12 MESES", 16, LCD["ink"])
    svg.text(674, 442, f"PONTOS {data['contrib']}", 16, LCD["ink"], anchor="end")
    cols = data["cols"]
    gx, gy = 86, 458
    for ci, col in enumerate(cols):
        for ri, lv in enumerate(col):
            svg.rect(gx + ci * 11, gy + ri * 11, 9, 9, LCD["ramp"][lv])
    snake(svg, len(cols), LCD, gx, gy)
    svg.rect(86, 554, 588, 2, LCD["ink"])
    for i, (name, count) in enumerate(data["langs"][:4]):
        y = 584 + i * 26
        svg.text(86, y, name.upper(), 16, LCD["ink"])
        n = min(count, 16)
        for b in range(n):
            svg.rect(214 + b * 12, y - 14, 8, 14, LCD["ink"])
        svg.text(214 + n * 12 + 8, y, str(count), 16, LCD["ink"])

    # comandos
    svg.add(f'<rect x="72" y="742" width="32" height="96" rx="6" fill="{t["bezel"]}"/>')
    svg.add(f'<rect x="40" y="774" width="96" height="32" rx="6" fill="{t["bezel"]}"/>')
    for cx in (350, 420):
        svg.add(f'<rect x="{cx - 28}" y="793" width="56" height="14" rx="7" fill="{t["edge"]}" transform="rotate(-20 {cx} 800)"/>')
    for cx, cy, label in ((604, 800, "E-MAIL"), (690, 770, "LINKEDIN")):
        svg.add(f'<circle cx="{cx}" cy="{cy + 3}" r="26" fill="#000" opacity=".22"/>')
        svg.add(f'<circle cx="{cx}" cy="{cy}" r="26" fill="{t["btn"]}"/>')
        svg.text(cx, cy + 48, label, 16, t["shell_ink"], anchor="middle", track=1)
    return svg.render()


def inventory(theme):
    t = THEMES[theme]
    svg = Svg(760, 242, "Tecnologias com as quais trabalho")
    slot, gap = 112, 17.6
    for i, (label, key) in enumerate(INVENTORY):
        x = (i % 6) * (slot + gap)
        y = (i // 6) * (slot + gap)
        svg.add(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{slot - 2}" height="{slot - 2}" fill="{t["card"]}" '
                f'stroke="{t["card_edge"]}" stroke-width="2"/>')
        svg.add(f'<path transform="translate({x + slot / 2 - 20:.1f} {y + 24:.1f}) scale({40 / 24:.4f})" '
                f'fill="{t["ink"]}" d="{ICONS[key]}"/>')
        svg.text(x + slot / 2, y + 96, label, 16, t["ink"], anchor="middle")
    return svg.render()


def title(theme, label):
    t = THEMES[theme]
    probe = Svg(0, 0, "")
    width = round(probe.measure(label, 24, "B", 2)) + 2
    svg = Svg(width, 28, label)
    svg.text(0, 22, label, 24, t["accent"], "B", track=2)
    return svg.render()


def main():
    days = contributions()
    langs = languages()
    extra = totals()
    data = {"contrib": sum(n for _, n in days), "commits": extra["commits"], "prs": extra["prs"],
            "repos": extra["repos"], "cols": calendar_columns(days), "langs": langs}
    os.makedirs(OUT, exist_ok=True)
    titles = {"sobre": "SOBRE MIM", "inventario": "INVENTÁRIO", "cartuchos": "CARTUCHOS", "historico": "HISTÓRICO"}
    for theme in THEMES:
        files = {f"device-{theme}.svg": device(theme, data), f"inventory-{theme}.svg": inventory(theme)}
        for key, label in titles.items():
            files[f"h-{key}-{theme}.svg"] = title(theme, label)
        for name, content in files.items():
            with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
    print("contribuições:", data["contrib"], "| commits:", data["commits"], "| PRs:", data["prs"],
          "| repositórios:", data["repos"], "| linguagens:", langs[:4])


if __name__ == "__main__":
    main()
