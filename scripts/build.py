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
       "shades": ["#4a5e3a", "#5f754a", "#7a8f5f", "#93a676"]}

INVENTORY = [("JAVA", "java"), ("SPRING", "spring"), ("PGSQL", "postgres"), ("ORACLE", "oracle"),
             ("DOCKER", "docker"), ("JS", "js"), ("TS", "ts"), ("ANGULAR", "angular"),
             ("REACT", "react"), ("HTML", "html"), ("CSS", "css"), ("GIT", "git")]
PERIODS = {"1": "2025 - HOJE", "2": "2023 - 2025", "3": "2022 - 2023"}
CARTRIDGES = {"prancha": "PRANCHA KIDS", "lume": "LUME"}
SECTIONS = {"sobre": "SOBRE MIM", "inventario": "INVENTÁRIO", "cartuchos": "CARTUCHOS", "historico": "HISTÓRICO"}

LOOP = 14        # segundos por volta da cobrinha
MAX_COLS = 12    # blocos por linha de linguagem
MAX_SNAKE = 8    # tamanho máximo da cobrinha


def fetch(url, accept="application/vnd.github+json", data=None):
    headers = {"User-Agent": "readme-build", "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def contributions():
    """Soma as contribuições do calendário público dos últimos 12 meses."""
    html = fetch(f"https://github.com/users/{USER}/contributions", accept="text/html")
    ids = dict(re.findall(r'data-date="(\d{4}-\d\d-\d\d)"[^>]*id="([^"]+)"', html))
    tips = dict(re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]+)</tool-tip>', html))
    if not ids:
        raise SystemExit("calendário de contribuições vazio; o formato da página pode ter mudado")
    total = 0
    for cell in ids.values():
        m = re.match(r"\s*(\d+)\s+contribution", tips.get(cell, ""))
        total += int(m.group(1)) if m else 0
    return total


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
    def __init__(self, width, height, title, vb=None, scale=1):
        self.w, self.h, self.title = width, height, title
        self.scale = scale  # fator do tamanho exibido; o desenho (viewBox) não muda
        self.vb = vb or (0, 0, width, height)  # janela do desenho que aparece (x, y, largura, altura)
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
        vx, vy, vw, vh = self.vb
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w * self.scale:g}" height="{self.h * self.scale:g}" '
                f'viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" role="img"><title>{self.title}</title>'
                f'<defs>{defs}</defs>' + "".join(self.parts) + "</svg>\n")


def blink(dur="1.1s"):
    return (f'<animate attributeName="opacity" values="1;0" keyTimes="0;0.5" dur="{dur}" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


def visibility(intervals):
    """<animate> discreto que deixa o elemento visível dentro dos intervalos (frações da volta) e oculto fora."""
    intervals = [(a, b) for a, b in intervals if a < b]
    cuts = sorted({0.0} | {t for a, b in intervals for t in (a, b) if 0 < t < 1})
    on = lambda t: any(a <= t < b for a, b in intervals)
    values = ";".join("1" if on(t) else "0" for t in cuts)
    keys = ";".join(f"{t:.4f}" for t in cuts)
    return (f'<animate attributeName="opacity" values="{values}" keyTimes="{keys}" dur="{LOOP}s" '
            f'calcMode="discrete" repeatCount="indefinite"/>')


def snake_screen(svg, langs, left, top, right):
    """Uma linha por linguagem, um bloco por repositório. A cobrinha percorre as linhas em serpentina,
    come os blocos, cresce a cada um e conta os pontos. Tudo volta ao começo no fim da volta."""
    langs = [(name, count, min(count, MAX_COLS)) for name, count in langs[:4]]
    ncols = max(shown for _, _, shown in langs)
    cell, px, py, x0 = 16, 22, 28, 200
    path = []
    for r in range(len(langs)):
        cols = range(ncols) if r % 2 == 0 else range(ncols - 1, -1, -1)
        path += [(r, c) for c in cols]
    n = len(path)
    step = {rc: i for i, rc in enumerate(path)}
    reset = (n - 0.5) / n

    eaten = []
    for r, (name, count, shown) in enumerate(langs):
        y = top + r * py
        svg.text(left, y, name.upper(), 16, LCD["ink"])
        svg.text(right, y, str(count), 16, LCD["ink"], anchor="end")
        for c in range(shown):
            t = step[(r, c)] / n
            eaten.append(t)
            svg.add(f'<rect x="{x0 + c * px}" y="{y - 13}" width="{cell}" height="{cell}" '
                    f'fill="{LCD["shades"][r % 4]}">{visibility([(0, t), (reset, 1)])}</rect>')
    eaten.sort()
    total = len(eaten)

    # a cobrinha: o segmento k aparece quando o k-ésimo bloco é comido
    for k in range(min(MAX_SNAKE, total + 1)):
        values = []
        for i in range(n):
            j = i - k
            if j < 0:
                values.append("-40 0")
            else:
                r, c = path[j]
                values.append(f"{x0 + c * px} {top + r * py - 13}")
        keys = ";".join(f"{i / n:.4f}" for i in range(n))
        grow = "" if k == 0 else visibility([(eaten[k - 1], reset)])
        svg.add(f'<rect width="{cell}" height="{cell}" fill="{LCD["ink"]}" stroke="{LCD["bg"]}" stroke-width="1">'
                f'<animateTransform attributeName="transform" type="translate" values="{";".join(values)}" '
                f'keyTimes="{keys}" dur="{LOOP}s" calcMode="discrete" repeatCount="indefinite"/>{grow}</rect>')

    # placar: COMIDOS 00/25, com um par de dígitos por valor, mostrado só no seu intervalo
    head_y = top - 34
    label, tail = "COMIDOS ", f"/{total}"
    start = right - svg.measure(label + "00" + tail, 16)
    num_x = start + svg.measure(label, 16)
    svg.text(start, head_y, label, 16, LCD["ink"])
    svg.text(num_x + svg.measure("00", 16), head_y, tail, 16, LCD["ink"])
    for k in range(total + 1):
        if k == 0:
            spans = [(0, eaten[0]), (reset, 1)]
        elif k == total:
            spans = [(eaten[-1], reset)]
        else:
            spans = [(eaten[k - 1], eaten[k])]
        if not any(a < b for a, b in spans):
            continue
        svg.add(f'<g>{visibility(spans)}')
        svg.text(num_x, head_y, f"{k:02d}", 16, LCD["ink"])
        svg.add("</g>")
    return total


def layout(nrows):
    """Medidas da tela de baixo: altura do LCD, da moldura, quanto os comandos sobem e altura total."""
    lcd_h = 168 if nrows == 4 else 168 - (4 - nrows) * 28
    bezel_h = lcd_h + 32
    shift = 252 - bezel_h  # quanto os comandos sobem em relação ao desenho de 252 px de tela
    return lcd_h, bezel_h, shift, 670 - shift


def shell(svg, t, shift):
    """Carcaça do aparelho, com sombra embaixo."""
    for dy, fill in ((6, t["edge"]), (0, t["shell"])):
        svg.add(f'<path d="M24 {dy}H536a24 24 0 0 1 24 24V{616 - shift + dy}a48 48 0 0 1-48 48H24a24 24 0 0 1-24-24V{24 + dy}A24 24 0 0 1 24 {dy}Z" '
                f'fill="{fill}"/>')


def controls(svg, t, s, which):
    """Cruz, pílulas, botões redondos e grade de som. s é o deslocamento vertical da faixa de comandos."""
    if "dpad" in which:
        svg.add(f'<rect x="56" y="{547 + s}" width="28" height="78" rx="5" fill="{t["bezel"]}"/>')
        svg.add(f'<rect x="31" y="{572 + s}" width="78" height="28" rx="5" fill="{t["bezel"]}"/>')
    if "pills" in which:
        for cx in (262, 326):
            svg.add(f'<rect x="{cx - 24}" y="{591 + s}" width="48" height="12" rx="6" fill="{t["edge"]}" '
                    f'transform="rotate(-20 {cx} {597 + s})"/>')
    for key, cx, cy, label in (("email", 399, 600 + s, "E-MAIL"), ("linkedin", 494, 574 + s, "LINKEDIN")):
        if key in which:
            svg.add(f'<circle cx="{cx}" cy="{cy + 3}" r="22" fill="#000" opacity=".22"/>')
            svg.add(f'<circle cx="{cx}" cy="{cy}" r="22" fill="{t["btn"]}"/>')
            svg.text(cx, cy + 42, label, 16, t["shell_ink"], anchor="middle")
    if "grille" in which:
        for i in range(4):
            x = 410 + i * 24
            svg.add(f'<rect x="{x}" y="{545 + s}" width="8" height="60" rx="4" fill="{t["edge"]}" '
                    f'transform="rotate(-20 {x + 4} {575 + s})"/>')


# A base do console é cortada em quatro imagens para os botões virarem links. Os cortes ficam em
# múltiplos de 20 px para que, no celular (escala 0,45), todas as peças tenham largura inteira.
# No celular o README tem só ~293 px úteis em telas de 375 px e ~278 px em telas de 360 px, então o
# console inteiro (560 x 0,45 = 252 px) precisa caber nisso para as peças não quebrarem de linha.
STRIP = {"p1": (0, 160, {"dpad"}), "p2": (160, 360, {"pills"}), "p3": (360, 440, {"email"}),
         "p4": (440, 560, {"linkedin"})}
MOBILE = 0.45  # escala do console no celular: 560 px viram 252 px


def strip(theme, piece, nrows=4, scale=1):
    """Um pedaço da faixa de baixo do console, para virar uma imagem com link."""
    t = THEMES[theme]
    x0, x1, which = STRIP[piece]
    _, bezel_h, shift, H = layout(nrows)
    top = 273 + bezel_h
    svg = Svg(x1 - x0, H - top, "Faixa de comandos do console", vb=(x0, top, x1 - x0, H - top), scale=scale)
    shell(svg, t, shift)
    controls(svg, t, -shift, which)
    return svg.render()


def device(theme, data, buttons=True, body_only=False, scale=1):
    t = THEMES[theme]
    nrows = len(data["langs"][:4])
    lcd_h, bezel_h, shift, H = layout(nrows)
    W = WIDTH
    title_ = "Console portátil: números do perfil em cima e, embaixo, uma cobrinha comendo os repositórios, uma linha por linguagem"
    if body_only:
        cut = 273 + bezel_h
        svg = Svg(W, cut, title_, vb=(0, 0, W, cut), scale=scale)
    else:
        svg = Svg(W, H, title_, scale=scale)
    shell(svg, t, shift)
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

    # tela de baixo: a cobrinha e os repositórios
    svg.rect(28, 273, 504, bezel_h, t["bezel"], 12)
    svg.rect(44, 289, 472, lcd_h, LCD["bg"], extra=f'stroke="{LCD["edge"]}" stroke-width="2"')
    svg.text(64, 317, "SNAKE · REPOS", 16, LCD["ink"])
    snake_screen(svg, data["langs"], left=64, top=351, right=496)

    # comandos
    which = {"dpad", "pills"} | ({"email", "linkedin"} if buttons else {"grille"})
    controls(svg, t, -shift, which)
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
    extra = totals()
    data = {"contrib": contributions(), "commits": extra["commits"], "prs": extra["prs"],
            "repos": extra["repos"], "langs": languages()}
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        files = {f"inventory-{theme}.svg": inventory(theme)}
        for suffix, scale in (("", 1), ("-m", MOBILE)):
            files[f"console-{theme}{suffix}.svg"] = device(theme, data, body_only=True, scale=scale)
            for piece in STRIP:
                files[f"{piece}-{theme}{suffix}.svg"] = strip(theme, piece, len(data["langs"][:4]), scale)
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
          "| repositórios:", data["repos"], "| linguagens:", data["langs"][:4])


if __name__ == "__main__":
    main()
