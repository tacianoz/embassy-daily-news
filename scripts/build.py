#!/usr/bin/env python3
"""
Embassy Daily News — coletor de notícias indianas relevantes para o Brasil.

Busca feeds RSS/Atom de grandes veículos indianos, classifica cada matéria
nos temas de interesse e gera um dashboard estático (public/index.html +
public/data.json).

Usa apenas a biblioteca padrão do Python (sem dependências externas).

Variáveis de ambiente úteis:
  FEEDS_OVERRIDE  JSON com lista de feeds [{"name","url","themes":[...]}] —
                  usado para testes locais (aceita caminhos de arquivo).
  OUTPUT_DIR      diretório de saída (padrão: public).
  MAX_AGE_DAYS    idade máxima das matérias em dias (padrão: 3).
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

# --------------------------------------------------------------------------- #
# Configuração de feeds
#
# Cada feed pode trazer "themes": uma dica de temas aplicada a TODAS as suas
# matérias (somada à classificação por palavras-chave). Útil para feeds de
# seção (ex.: caderno de economia, ciência etc.).
# --------------------------------------------------------------------------- #
FEEDS = [
    # Buscas dedicadas (Google News RSS) — varrem toda a imprensa indiana
    # procurando menções a Brasil e BRICS, que raramente aparecem nos feeds
    # de seção. O <source> de cada item traz o nome real do veículo.
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil+India&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"]},
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil+(Lula+OR+Mercosur+OR+trade+OR+BRICS)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"]},
    {"name": "Google News — BRICS", "url": "https://news.google.com/rss/search?q=BRICS&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brics"]},

    # The Hindu
    {"name": "The Hindu — Nacional", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "themes": ["politica_interna"]},
    {"name": "The Hindu — Internacional", "url": "https://www.thehindu.com/news/international/feeder/default.rss", "themes": ["politica_externa"]},
    {"name": "The Hindu — Economia", "url": "https://www.thehindu.com/business/Economy/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Negócios", "url": "https://www.thehindu.com/business/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Ciência", "url": "https://www.thehindu.com/sci-tech/science/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Tecnologia", "url": "https://www.thehindu.com/sci-tech/technology/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Energia e Meio Ambiente", "url": "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "themes": ["energia", "clima"]},

    # The Indian Express
    {"name": "Indian Express — Índia", "url": "https://indianexpress.com/section/india/feed/", "themes": ["politica_interna"]},
    {"name": "Indian Express — Mundo", "url": "https://indianexpress.com/section/world/feed/", "themes": ["politica_externa"]},
    {"name": "Indian Express — Economia", "url": "https://indianexpress.com/section/business/economy/feed/", "themes": ["economia"]},
    {"name": "Indian Express — Tecnologia", "url": "https://indianexpress.com/section/technology/feed/", "themes": ["cti"]},
    {"name": "Indian Express — Clima", "url": "https://indianexpress.com/section/india/climate-change/feed/", "themes": ["clima"]},

    # The Times of India
    {"name": "Times of India — Índia", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "themes": ["politica_interna"]},
    {"name": "Times of India — Mundo", "url": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "themes": ["politica_externa"]},
    {"name": "Times of India — Negócios", "url": "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms", "themes": ["economia"]},
    {"name": "Times of India — Ciência", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128672765.cms", "themes": ["cti"]},
    {"name": "Times of India — Meio Ambiente", "url": "https://timesofindia.indiatimes.com/rssfeeds/2647163.cms", "themes": ["clima"]},

    # Hindustan Times
    {"name": "Hindustan Times — Índia", "url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "themes": ["politica_interna"]},
    {"name": "Hindustan Times — Mundo", "url": "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml", "themes": ["politica_externa"]},
    {"name": "Hindustan Times — Negócios", "url": "https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml", "themes": ["economia"]},

    # The Economic Times
    {"name": "Economic Times — Economia", "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "themes": ["economia"]},
    {"name": "Economic Times — Energia", "url": "https://economictimes.indiatimes.com/industry/energy/power/rssfeeds/13357704.cms", "themes": ["energia"]},
    {"name": "Economic Times — Política Externa", "url": "https://economictimes.indiatimes.com/news/economy/foreign-trade/rssfeeds/1373380681.cms", "themes": ["politica_externa", "economia"]},

    # Livemint
    {"name": "Livemint — Economia", "url": "https://www.livemint.com/rss/economy", "themes": ["economia"]},
    {"name": "Livemint — Notícias", "url": "https://www.livemint.com/rss/news", "themes": []},

    # NDTV
    {"name": "NDTV — Índia", "url": "https://feeds.feedburner.com/ndtvnews-india-news", "themes": ["politica_interna"]},
    {"name": "NDTV — Mundo", "url": "https://feeds.feedburner.com/ndtvnews-world-news", "themes": ["politica_externa"]},

    # Mídia independente / análise
    {"name": "The Wire", "url": "https://thewire.in/rss", "themes": []},
    {"name": "Scroll.in", "url": "https://scroll.in/feeds/all.rss", "themes": []},
    {"name": "Down To Earth — Meio Ambiente", "url": "https://www.downtoearth.org.in/rss/environment", "themes": ["clima"]},
]

# --------------------------------------------------------------------------- #
# Temas de interesse (ordem definida pelo usuário)
# --------------------------------------------------------------------------- #
THEMES = {
    "brasil": {
        "label": "Brasil",
        "desc": "Menções ao Brasil",
        "color": "#009c3b",
        "icon": "🇧🇷",
        "keywords": [
            "brazil", "brazilian", "brasil", "brasilia", "lula", "mercosur",
            "mercosul", "itamaraty", "sao paulo", "rio de janeiro", "petrobras",
            "embraer", "bolsonaro", "planalto", "amazon basin",
        ],
    },
    "brics": {
        "label": "BRICS",
        "desc": "Menções ao BRICS",
        "color": "#b8860b",
        "icon": "🤝",
        "keywords": [
            "brics", "new development bank", "ndb", "brics plus",
            "expanded brics", "global south",
        ],
    },
    "politica_externa": {
        "label": "Política internacional",
        "desc": "Diplomacia e relações internacionais",
        "color": "#3d4eac",
        "icon": "🌐",
        "keywords": [
            "foreign policy", "external affairs", "diplomacy", "diplomatic",
            "jaishankar", "bilateral", "g20", "g 20", "quad", "indo pacific",
            "foreign minister", "ambassador", "embassy", "neighbourhood",
            "international relations", "summit", "treaty", "geopolitic",
            "india us", "india china", "india russia", "india pakistan",
            "united nations", "free trade agreement", "fta", "indo us",
            "sco summit", "modi visit",
        ],
    },
    "politica_interna": {
        "label": "Política interna",
        "desc": "Política doméstica e governo",
        "color": "#c0392b",
        "icon": "🏛️",
        "keywords": [
            "parliament", "lok sabha", "rajya sabha", "bjp", "congress party",
            "modi government", "pm modi", "election", "by election", "cabinet",
            "supreme court", "high court", "opposition", "rahul gandhi",
            "governance", "chief minister", "legislation", "no confidence",
            "coalition", "home ministry", "amit shah", "assembly polls",
        ],
    },
    "economia": {
        "label": "Economia",
        "desc": "Economia, mercados e comércio",
        "color": "#0f7b6c",
        "icon": "📈",
        "keywords": [
            "economy", "economic", "gdp", "inflation", "rupee", "rbi",
            "reserve bank", "fiscal", "budget", "trade", "exports", "imports",
            "manufacturing", "gst", "sensex", "nifty", "stock market", "fdi",
            "investment", "interest rate", "unemployment", "current account",
            "tariff", "supply chain", "startup funding", "ipo",
        ],
    },
    "energia": {
        "label": "Energia",
        "desc": "Petróleo, gás, renováveis e eletricidade",
        "color": "#e67e22",
        "icon": "⚡",
        "keywords": [
            "energy", "oil", "natural gas", "petroleum", "crude", "coal",
            "solar", "wind power", "renewable", "power sector", "electricity",
            "nuclear", "hydrogen", "refinery", "opec", "lng", "electric vehicle",
            "power grid", "biofuel", "ethanol", "thermal power",
        ],
    },
    "cti": {
        "label": "Ciência, tecnologia e inovação",
        "desc": "C&T, espaço e inovação",
        "color": "#6c5ce7",
        "icon": "🔬",
        "keywords": [
            "technology", "science", "isro", "space mission", "satellite",
            "artificial intelligence", "semiconductor", "innovation",
            "research", "quantum", "biotech", "5g", "6g", "drdo", "robotics",
            "deep tech", "chip", "digital india", "moon mission", "rocket",
        ],
    },
    "clima": {
        "label": "Mudanças climáticas e meio ambiente",
        "desc": "Clima, meio ambiente e sustentabilidade",
        "color": "#2e8b57",
        "icon": "🌱",
        "keywords": [
            "climate", "climate change", "environment", "environmental",
            "emission", "carbon", "pollution", "monsoon", "biodiversity",
            "forest", "wildlife", "cop29", "cop30", "sustainability",
            "net zero", "global warming", "deforestation", "air quality",
            "drought", "cyclone", "heatwave", "green energy", "renewable energy",
        ],
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; EmbassyDailyNews/1.0; +https://github.com/tacianoz/embassy-daily-news)"

# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
_norm_re = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Minúsculas + remoção de pontuação, mantendo espaços simples nas bordas."""
    text = html.unescape(text or "")
    text = text.lower()
    text = _norm_re.sub(" ", text)
    return " " + text.strip() + " "


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, timeout: int = 25) -> bytes | None:
    """Busca uma URL (ou lê um arquivo local, para testes)."""
    if not url.startswith(("http://", "https://")):
        try:
            with open(url, "rb") as fh:
                return fh.read()
        except OSError as exc:
            print(f"  ! erro ao ler arquivo {url}: {exc}", file=sys.stderr)
            return None

    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 — toleramos qualquer falha de rede
            last_err = exc
    print(f"  ! falhou ({last_err}): {url}", file=sys.stderr)
    return None


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_text(elem, names) -> str:
    for child in elem:
        if _localname(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
            # Atom: link como atributo href
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def _find_link(elem) -> str:
    # RSS: <link>texto</link>; Atom: <link href=... rel="alternate"/>
    fallback = ""
    for child in elem:
        if _localname(child.tag) != "link":
            continue
        rel = child.attrib.get("rel", "alternate")
        href = child.attrib.get("href")
        if href and rel == "alternate":
            return href.strip()
        if href and not fallback:
            fallback = href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return fallback


def parse_date(value: str):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, IndexError):
        pass
    try:
        iso = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def parse_feed(raw: bytes, source: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"  ! XML inválido em {source}: {exc}", file=sys.stderr)
        return items

    # Localiza entradas: RSS (<item>) ou Atom (<entry>)
    entries = [e for e in root.iter() if _localname(e.tag) in ("item", "entry")]
    for entry in entries:
        title = _find_text(entry, ("title",))
        link = _find_link(entry)
        summary = _find_text(entry, ("description", "summary", "content", "encoded"))
        date_raw = _find_text(entry, ("pubDate", "published", "updated", "date"))
        # Google News inclui <source>Veículo</source> em cada item
        item_source = _find_text(entry, ("source",))
        if not title or not link:
            continue
        items.append({
            "title": strip_html(title),
            "link": link,
            "summary": strip_html(summary),
            "published": parse_date(date_raw),
            "source": source,
            "outlet": strip_html(item_source) if item_source else "",
        })
    return items


def classify(item: dict, hint_themes: list[str]) -> list[str]:
    blob = normalize(item["title"] + " " + item["summary"])
    matched = set(hint_themes)
    for key, cfg in THEMES.items():
        for kw in cfg["keywords"]:
            needle = " " + normalize(kw).strip() + " "
            if needle in blob:
                matched.add(key)
                break
    # mantém a ordem canônica dos temas
    return [k for k in THEMES if k in matched]


# --------------------------------------------------------------------------- #
# Geração do HTML
# --------------------------------------------------------------------------- #
def render_html(payload: dict) -> str:
    theme_meta = {k: {"label": v["label"], "desc": v["desc"],
                      "color": v["color"], "icon": v["icon"]}
                  for k, v in THEMES.items()}
    data_json = json.dumps(
        {"meta": payload["meta"], "themes": theme_meta, "articles": payload["articles"]},
        ensure_ascii=False,
    )

    # CSS para as faixas coloridas de cada tema
    theme_css = "\n".join(
        f'    .t-{k} {{ --tc: {v["color"]}; }}' for k, v in THEMES.items()
    )

    return TEMPLATE.replace("/*THEME_CSS*/", theme_css).replace(
        "/*DATA_JSON*/", data_json
    )


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Índia em Foco — Monitor de Notícias para o Brasil</title>
<style>
  :root {
    --bg: #f4f6fb; --card: #ffffff; --ink: #1a1f36; --muted: #6b7280;
    --line: #e6e9f0; --brand: #ff9933; --brand2: #138808; --accent: #1f3a93;
    --shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06);
    --radius: 16px;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0e1117; --card: #161b22; --ink: #e6edf3; --muted: #9aa4b2;
      --line: #232a35; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.3);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
  }
  a { color: inherit; }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 0 20px; }

  header.top {
    background: linear-gradient(120deg, #ff9933 0%, #ffffff 50%, #138808 100%);
    border-bottom: 1px solid var(--line);
  }
  @media (prefers-color-scheme: dark) {
    header.top { background: linear-gradient(120deg, #5a3a12 0%, #161b22 50%, #123a14 100%); }
  }
  .top-inner { padding: 26px 20px 22px; }
  .brandline { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .brandline .flags { font-size: 26px; letter-spacing: 2px; }
  h1 { margin: 0; font-size: clamp(22px, 3.2vw, 30px); font-weight: 800; color: #1a1f36; }
  @media (prefers-color-scheme: dark) { h1 { color: var(--ink); } }
  .subtitle { margin: 4px 0 0; color: #33415c; font-weight: 500; }
  @media (prefers-color-scheme: dark) { .subtitle { color: var(--muted); } }
  .stats { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 14px; font-size: 13px; color: #33415c; }
  @media (prefers-color-scheme: dark) { .stats { color: var(--muted); } }
  .stats b { color: #1a1f36; }
  @media (prefers-color-scheme: dark) { .stats b { color: var(--ink); } }

  .controls { position: sticky; top: 0; z-index: 20; background: var(--bg);
    border-bottom: 1px solid var(--line); padding: 12px 0; backdrop-filter: blur(6px); }
  .controls-inner { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .search {
    flex: 1 1 240px; min-width: 200px; display: flex; align-items: center; gap: 8px;
    background: var(--card); border: 1px solid var(--line); border-radius: 999px;
    padding: 9px 16px; box-shadow: var(--shadow);
  }
  .search input { border: 0; outline: 0; background: transparent; color: var(--ink);
    width: 100%; font-size: 14px; }
  .srcpick {
    display: flex; align-items: center; gap: 8px; background: var(--card);
    border: 1px solid var(--line); border-radius: 999px; padding: 8px 14px;
    box-shadow: var(--shadow); flex: 0 1 auto;
  }
  .srcpick select { border: 0; outline: 0; background: transparent; color: var(--ink);
    font-size: 14px; font-weight: 600; max-width: 200px; cursor: pointer; }

  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    display: inline-flex; align-items: center; gap: 7px; cursor: pointer; user-select: none;
    border: 1px solid var(--line); background: var(--card); color: var(--ink);
    padding: 7px 13px; border-radius: 999px; font-size: 13px; font-weight: 600;
    box-shadow: var(--shadow); transition: transform .08s ease, border-color .15s ease;
  }
  .chip:hover { transform: translateY(-1px); }
  .chip .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--cc, #999); }
  .chip .count { color: var(--muted); font-weight: 600; font-size: 12px; }
  .chip.active { border-color: var(--cc, var(--accent)); box-shadow: 0 0 0 2px color-mix(in srgb, var(--cc, var(--accent)) 35%, transparent); }

  main { padding: 22px 0 60px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
    box-shadow: var(--shadow); padding: 0; overflow: hidden; display: flex; flex-direction: column;
    transition: transform .1s ease, box-shadow .15s ease;
  }
  .card:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(16,24,40,.12); }
  .card .bar { height: 4px; background: var(--tc, var(--accent)); }
  .card .body { padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 10px; height: 100%; }
  .card .meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
  .source { font-weight: 700; color: var(--ink); }
  .card h3 { margin: 0; font-size: 16px; line-height: 1.35; font-weight: 700; }
  .card h3 a { text-decoration: none; }
  .card h3 a:hover { text-decoration: underline; }
  .card p.sum { margin: 0; color: var(--muted); font-size: 13.5px;
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; padding-top: 6px; }
  .badge { font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 999px;
    color: #fff; background: var(--bc, #555); white-space: nowrap; }
  .read { margin-top: 4px; font-size: 13px; font-weight: 700; color: var(--tc, var(--accent)); text-decoration: none; }
  .read:hover { text-decoration: underline; }

  .empty { text-align: center; color: var(--muted); padding: 60px 20px; }
  footer { border-top: 1px solid var(--line); color: var(--muted); font-size: 12.5px; padding: 24px 0 50px; }
  footer .wrap { display: flex; flex-direction: column; gap: 6px; }
/*THEME_CSS*/
</style>
</head>
<body>
<header class="top">
  <div class="wrap top-inner">
    <div class="brandline">
      <span class="flags">🇮🇳→🇧🇷</span>
      <div>
        <h1>Índia em Foco</h1>
        <p class="subtitle">Monitor diário de notícias indianas relevantes para o Brasil</p>
      </div>
    </div>
    <div class="stats">
      <span><b id="stat-total">0</b> matérias</span>
      <span><b id="stat-sources">0</b> fontes</span>
      <span>Atualizado em <b id="stat-updated">—</b></span>
    </div>
  </div>
</header>

<div class="controls">
  <div class="wrap controls-inner">
    <label class="search">
      <span aria-hidden="true">🔎</span>
      <input id="q" type="search" placeholder="Buscar por palavra-chave, assunto…" autocomplete="off">
    </label>
    <label class="srcpick">
      <span aria-hidden="true">📰</span>
      <select id="src"><option value="all">Todos os jornais</option></select>
    </label>
    <div class="chips" id="chips"></div>
  </div>
</div>

<main class="wrap">
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" hidden>Nenhuma matéria encontrada para este filtro.</div>
</main>

<footer>
  <div class="wrap">
    <div>Gerado automaticamente via GitHub Actions • As manchetes e resumos são exibidos no idioma original (inglês).</div>
    <div id="sources-list"></div>
  </div>
</footer>

<script id="payload" type="application/json">/*DATA_JSON*/</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('payload').textContent);
  const THEMES = DATA.themes;
  const articles = DATA.articles;
  let activeTheme = 'all';
  let activeSource = 'all';
  let query = '';

  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  const chipsEl = document.getElementById('chips');
  const srcEl = document.getElementById('src');

  // Estatísticas do cabeçalho
  document.getElementById('stat-total').textContent = articles.length;
  const sources = [...new Set(articles.map(a => a.source))].sort((a, b) => a.localeCompare(b));
  document.getElementById('stat-sources').textContent = sources.length;

  // Seletor de jornal (com contagem por fonte)
  const srcCounts = {};
  for (const a of articles) srcCounts[a.source] = (srcCounts[a.source] || 0) + 1;
  for (const s of sources) {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s + ' (' + srcCounts[s] + ')';
    srcEl.appendChild(opt);
  }
  srcEl.addEventListener('change', e => { activeSource = e.target.value; render(); });
  document.getElementById('stat-updated').textContent = DATA.meta.generated_label;
  document.getElementById('sources-list').textContent =
    'Veículos nesta edição (' + (DATA.meta.feeds || []).length + '): ' + (DATA.meta.feeds || []).join(' · ');

  // Contagem por tema
  const counts = { all: articles.length };
  for (const k in THEMES) counts[k] = 0;
  for (const a of articles) for (const t of a.themes) counts[t] = (counts[t] || 0) + 1;

  // Chips de filtro
  function makeChip(key, label, color, count) {
    const el = document.createElement('button');
    el.className = 'chip' + (key === 'all' ? ' active' : '');
    el.dataset.key = key;
    if (color) el.style.setProperty('--cc', color);
    el.innerHTML =
      (color ? '<span class="dot" style="background:' + color + '"></span>' : '') +
      '<span>' + label + '</span><span class="count">' + count + '</span>';
    el.addEventListener('click', () => {
      activeTheme = key;
      document.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c === el));
      render();
    });
    return el;
  }
  chipsEl.appendChild(makeChip('all', 'Todos', '', counts.all));
  for (const k in THEMES) {
    chipsEl.appendChild(makeChip(k, THEMES[k].icon + ' ' + THEMES[k].label, THEMES[k].color, counts[k] || 0));
  }

  function timeAgo(iso) {
    if (!iso) return '';
    const d = new Date(iso), now = new Date();
    const mins = Math.round((now - d) / 60000);
    if (mins < 60) return 'há ' + Math.max(mins, 1) + ' min';
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return 'há ' + hrs + 'h';
    const days = Math.round(hrs / 24);
    return 'há ' + days + (days === 1 ? ' dia' : ' dias');
  }

  function esc(s) {
    return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function cardHTML(a) {
    const primary = a.themes[0] || 'all';
    const badges = a.themes.map(t =>
      '<span class="badge" style="--bc:' + THEMES[t].color + '">' + THEMES[t].icon + ' ' + esc(THEMES[t].label) + '</span>'
    ).join('');
    return '<article class="card t-' + primary + '">' +
      '<div class="bar"></div>' +
      '<div class="body">' +
        '<div class="meta"><span class="source">' + esc(a.source) + '</span>' +
          (a.time_ago ? '<span>•</span><span>' + esc(a.time_ago) + '</span>' : '') + '</div>' +
        '<h3><a href="' + esc(a.link) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></h3>' +
        (a.summary ? '<p class="sum">' + esc(a.summary) + '</p>' : '') +
        '<div class="badges">' + badges + '</div>' +
        '<a class="read" href="' + esc(a.link) + '" target="_blank" rel="noopener">Ler matéria →</a>' +
      '</div></article>';
  }

  function render() {
    const q = query.trim().toLowerCase();
    const list = articles.filter(a => {
      const okTheme = activeTheme === 'all' || a.themes.includes(activeTheme);
      const okSource = activeSource === 'all' || a.source === activeSource;
      const okQuery = !q ||
        a.title.toLowerCase().includes(q) ||
        (a.summary || '').toLowerCase().includes(q) ||
        a.source.toLowerCase().includes(q);
      return okTheme && okSource && okQuery;
    });
    grid.innerHTML = list.map(cardHTML).join('');
    empty.hidden = list.length !== 0;
  }

  // recomputa o "tempo atrás" no cliente (mais preciso que no build)
  for (const a of articles) a.time_ago = a.published ? timeAgo(a.published) : '';

  document.getElementById('q').addEventListener('input', e => { query = e.target.value; render(); });
  render();
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Pipeline principal
# --------------------------------------------------------------------------- #
def main() -> int:
    out_dir = os.environ.get("OUTPUT_DIR", "public")
    max_age = int(os.environ.get("MAX_AGE_DAYS", "3"))
    override = os.environ.get("FEEDS_OVERRIDE")
    feeds = json.loads(override) if override else FEEDS

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age)

    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    articles: list[dict] = []
    ok_sources: set[str] = set()

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        hint = feed.get("themes", [])
        outlet_default = name.split(" — ")[0]  # ex.: "The Hindu", "Google News"
        print(f"- {name}")
        raw = fetch(url)
        if not raw:
            continue
        parsed = parse_feed(raw, name)
        for item in parsed:
            link_key = item["link"].split("?")[0].strip().lower()
            title_key = normalize(item["title"]).strip()
            if link_key in seen_links or (title_key and title_key in seen_titles):
                continue
            # filtro por data (mantém itens sem data — alguns feeds omitem)
            if item["published"] and item["published"] < cutoff:
                continue
            themes = classify(item, hint)
            if not themes:
                continue  # só interessa o que cai em algum tema

            # Nome do veículo: usa o <source> (Google News) quando houver,
            # senão o nome-base do feed.
            outlet = item.get("outlet") or outlet_default
            title = item["title"]
            # Google News acrescenta " - Veículo" ao fim do título; remove.
            if item.get("outlet") and title.endswith(" - " + item["outlet"]):
                title = title[: -(len(item["outlet"]) + 3)].strip()

            seen_links.add(link_key)
            if title_key:
                seen_titles.add(title_key)
            ok_sources.add(outlet)
            articles.append({
                "title": title,
                "link": item["link"],
                "summary": (item["summary"][:320] + "…") if len(item["summary"]) > 320 else item["summary"],
                "source": outlet,
                "published": item["published"].isoformat() if item["published"] else None,
                "themes": themes,
            })

    # ordena: com data primeiro (mais recente), depois sem data
    articles.sort(key=lambda a: a["published"] or "", reverse=True)

    # Rótulo de atualização em horário de Brasília (UTC-3)
    brt = now.astimezone(timezone(timedelta(hours=-3)))
    generated_label = brt.strftime("%d/%m/%Y às %H:%M (Brasília)")

    payload = {
        "meta": {
            "generated_utc": now.isoformat(),
            "generated_label": generated_label,
            "max_age_days": max_age,
            "feeds": sorted(ok_sources, key=str.lower),
        },
        "articles": articles,
    }

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render_html(payload))
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"\n✔ {len(articles)} matérias de {len(ok_sources)} fontes → {out_dir}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
