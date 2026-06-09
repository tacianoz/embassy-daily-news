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
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil+-football+-soccer+-match+-cricket&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"], "allow_intl": True},
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil+(Lula+OR+Mercosur+OR+Petrobras+OR+Embraer+OR+ethanol+OR+trade+OR+Amazon)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"], "allow_intl": True},
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brasil+India&hl=pt-BR&gl=IN&ceid=IN:pt-419", "themes": ["brasil"], "allow_intl": True},
    {"name": "Google News — BRICS", "url": "https://news.google.com/rss/search?q=BRICS&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brics"], "allow_intl": True},

    # Buscas dedicadas por tema (Google News) — garantem recall de assuntos
    # que os feeds de seção não cobrem (ex.: biocombustíveis). Só imprensa
    # indiana (sem allow_intl). O tema já vem carimbado via "themes".
    {"name": "Google News — Energia", "url": "https://news.google.com/rss/search?q=India+(ethanol+OR+biofuel+OR+%22flex+fuel%22+OR+biogas+OR+biodiesel+OR+bioenergy+OR+%22ethanol+blending%22+OR+E20+OR+E85+OR+E100)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["energia"], "scope_india": True},
    {"name": "Google News — Energia", "url": "https://news.google.com/rss/search?q=India+(%22renewable+energy%22+OR+%22green+hydrogen%22+OR+%22solar+power%22+OR+%22wind+energy%22+OR+%22nuclear+power%22+OR+%22clean+energy%22+OR+%22energy+transition%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["energia"], "scope_india": True},
    {"name": "Google News — C&T", "url": "https://news.google.com/rss/search?q=India+(ISRO+OR+semiconductor+OR+%22artificial+intelligence%22+OR+%22space+mission%22+OR+startup+OR+innovation+OR+DRDO)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["cti"], "scope_india": True},
    {"name": "Google News — Clima", "url": "https://news.google.com/rss/search?q=India+(%22climate+change%22+OR+emissions+OR+%22net+zero%22+OR+pollution+OR+biodiversity+OR+%22COP30%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["clima"], "scope_india": True},

    # The Hindu
    {"name": "The Hindu — Nacional", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "themes": []},
    {"name": "The Hindu — Internacional", "url": "https://www.thehindu.com/news/international/feeder/default.rss", "themes": ["politica_externa"]},
    {"name": "The Hindu — Economia", "url": "https://www.thehindu.com/business/Economy/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Negócios", "url": "https://www.thehindu.com/business/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Ciência", "url": "https://www.thehindu.com/sci-tech/science/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Tecnologia", "url": "https://www.thehindu.com/sci-tech/technology/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Energia e Meio Ambiente", "url": "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "themes": ["energia", "clima"]},

    # The Indian Express
    {"name": "Indian Express — Índia", "url": "https://indianexpress.com/section/india/feed/", "themes": []},
    {"name": "Indian Express — Política", "url": "https://indianexpress.com/section/political-pulse/feed/", "themes": ["politica_interna"]},
    {"name": "Indian Express — Mundo", "url": "https://indianexpress.com/section/world/feed/", "themes": ["politica_externa"]},
    {"name": "Indian Express — Economia", "url": "https://indianexpress.com/section/business/economy/feed/", "themes": ["economia"]},
    {"name": "Indian Express — Tecnologia", "url": "https://indianexpress.com/section/technology/feed/", "themes": ["cti"]},
    {"name": "Indian Express — Clima", "url": "https://indianexpress.com/section/india/climate-change/feed/", "themes": ["clima"]},

    # The Times of India
    {"name": "Times of India — Índia", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "themes": []},
    {"name": "Times of India — Política Interna", "url": "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms", "themes": ["politica_interna"]},
    {"name": "Times of India — Mundo", "url": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "themes": ["politica_externa"]},
    {"name": "Times of India — Negócios", "url": "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms", "themes": ["economia"]},
    {"name": "Times of India — Ciência", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128672765.cms", "themes": ["cti"]},
    {"name": "Times of India — Meio Ambiente", "url": "https://timesofindia.indiatimes.com/rssfeeds/2647163.cms", "themes": ["clima"]},

    # Hindustan Times
    {"name": "Hindustan Times — Índia", "url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "themes": []},
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
    {"name": "NDTV — Índia", "url": "https://feeds.feedburner.com/ndtvnews-india-news", "themes": []},
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
            "narendra modi", "central government", "state government",
            "union minister", "aam aadmi party", "electoral", "ruling party",
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
            "solar", "solar power", "rooftop solar", "wind", "wind power",
            "wind energy", "wind farm", "offshore wind", "renewable",
            "renewables", "clean energy", "power sector", "electricity",
            "nuclear", "nuclear power", "hydrogen", "green hydrogen",
            "refinery", "opec", "lng", "electric vehicle", "power grid",
            "thermal power", "hydropower", "geothermal",
            # bioenergia
            "biofuel", "ethanol", "ethanol blending", "ethanol blend",
            "e10", "e20", "e27", "e85", "e100", "biogas",
            "compressed biogas", "bioenergy", "biodiesel", "biomass",
            "flex fuel", "flex fuel vehicle",
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
        "color": "#0891b2",
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

# Veículos indianos reconhecidos. Resultados de buscas agregadas (Google News)
# só entram se a fonte estiver nesta lista — garante apenas imprensa indiana.
INDIAN_OUTLETS = [
    "the hindu", "businessline", "times of india", "hindustan times",
    "indian express", "economic times", "mint", "livemint", "ndtv",
    "business standard", "the wire", "scroll", "down to earth", "firstpost",
    "news18", "india today", "the print", "theprint", "deccan herald",
    "deccan chronicle", "the tribune", "tribune india", "outlook",
    "moneycontrol", "financial express", "wion", "zee news", "zee business",
    "republic world", "business today", "cnbc tv18", "cnbctv18", "frontline",
    "the quint", "swarajya", "the federal", "dna india", "free press journal",
    "national herald", "the statesman", "etenergyworld", "mercom india",
    "the new indian express", "telangana today", "rediff", "oneindia",
    "ani", "pti", "chinimandi", "saur energy", "pv magazine", "mongabay",
    "autocar", "ndtv profit", "the print",
]

# Jornais de grande circulação — recebem prioridade na ordenação e destaque.
PRIORITY_OUTLETS = [
    "economic times", "the hindu", "businessline", "mint", "livemint",
    "hindustan times", "times of india",
]

# Grandes agências e imprensa internacional — aceitas (sobretudo em Brasil/BRICS),
# marcadas como internacionais e exibidas depois da imprensa indiana.
INTERNATIONAL_OUTLETS = [
    "reuters", "associated press", "ap news", "afp", "agence france presse",
    "bloomberg", "efe", "financial times", "the guardian", "guardian",
    "bbc", "cnn", "al jazeera", "mercopress", "nikkei", "wall street journal",
    "the new york times", "new york times", "washington post", "anadolu",
    "xinhua", "tass", "deutsche welle", "dw news", "the economist", "politico",
    "south china morning post", "rfi", "sputnik", "cnbc", "forbes",
]


def is_international(source: str) -> bool:
    return matches_outlet(source, INTERNATIONAL_OUTLETS)


def matches_outlet(source: str, tokens: list[str]) -> bool:
    blob = normalize(source)
    return any((" " + t + " ") in blob for t in tokens)


def is_indian(source: str) -> bool:
    return matches_outlet(source, INDIAN_OUTLETS)


def is_priority(source: str) -> bool:
    return matches_outlet(source, PRIORITY_OUTLETS)

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
        {"meta": payload["meta"], "themes": theme_meta,
         "articles": payload["articles"], "highlights": payload.get("highlights", [])},
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
<title>Notícias do dia — Embaixada do Brasil em Nova Délhi</title>
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
    background: #15224c;
    border-bottom: 4px solid transparent;
    border-image: linear-gradient(90deg, #1e9e3e 0 33.33%, #ffd200 33.33% 66.66%, #2b3a8f 66.66% 100%) 1;
  }
  .top-inner { padding: 22px 20px 20px; }
  .brandline { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
  .logo-svg { height: 92px; width: auto; display: block; flex: 0 0 auto; overflow: visible; }
  h1 { margin: 0; font-size: clamp(22px, 3.4vw, 32px); font-weight: 800; color: #fff; letter-spacing: .3px; }
  .subtitle { margin: 5px 0 0; color: rgba(255,255,255,.82); font-weight: 500; }
  .stats { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 16px; font-size: 13px; color: rgba(255,255,255,.78); }
  .stats b { color: #fff; }

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
  .chip.active { background: var(--cc, var(--accent)); border-color: transparent; color: #fff; }
  .chip.active .dot { box-shadow: 0 0 0 2px rgba(255,255,255,.6); }
  .chip.active .count { color: rgba(255,255,255,.85); }

  main { padding: 22px 0 60px; }
  .sec-title { font-size: 17px; font-weight: 800; margin: 8px 0 16px; display: flex; align-items: center; gap: 10px; }
  .sec-title[hidden] { display: none; }
  .sec-tag { font-size: 11px; font-weight: 700; color: #fff; background: #c2185b;
    padding: 3px 9px; border-radius: 999px; text-transform: uppercase; letter-spacing: .3px; }
  .ai-mark { font-size: 10.5px; font-weight: 700; color: #c2185b; }
  .hl-mark { font-size: 12px; color: #c2185b; }
  img.emoji { height: 1em; width: 1em; margin: 0 .05em 0 .1em; vertical-align: -0.1em; }
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
  .source.pri::before { content: "★ "; color: #f5b301; }
  .intl-tag { font-size: 10.5px; font-weight: 800; letter-spacing: .3px;
    padding: 2px 7px; border-radius: 999px; color: #fff; background: #5b6472;
    text-transform: uppercase; }
  .card.is-intl { border-style: dashed; }
  .card.is-intl .bar { background: repeating-linear-gradient(45deg, #8a93a3 0 8px, #b6bdc9 8px 16px); }
  .card.is-hl { border-left: 3px solid #c2185b; }
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
      <svg class="logo-svg" viewBox="0 0 440 300" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Embaixada do Brasil em Nova Délhi">
        <text x="220" y="74" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="600" letter-spacing="2">EMBAIXADA DO</text>
        <text x="220" y="166" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="86" font-weight="800" letter-spacing="1">BRASIL</text>
        <rect x="74" y="188" width="97" height="11" fill="#1e9e3e"/>
        <rect x="171" y="188" width="97" height="11" fill="#ffd200"/>
        <rect x="268" y="188" width="98" height="11" fill="#2b3a8f"/>
        <text x="220" y="252" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="36" font-weight="600" letter-spacing="5">NOVA DÉLHI</text>
      </svg>
      <div class="titles">
        <h1>Notícias do dia</h1>
        <p class="subtitle">Monitor diário da imprensa indiana · Embaixada do Brasil em Nova Délhi</p>
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
      <span aria-hidden="true">🌍</span>
      <select id="origin">
        <option value="all">Todas as origens</option>
        <option value="in">Imprensa indiana</option>
        <option value="intl">Agências internacionais</option>
      </select>
    </label>
    <label class="srcpick">
      <span aria-hidden="true">📰</span>
      <select id="src"><option value="all">Todos os jornais</option></select>
    </label>
    <div class="chips" id="chips"></div>
  </div>
</div>

<main class="wrap">
  <h2 class="sec-title" id="view-title" hidden></h2>
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
<script src="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/dist/twemoji.min.js" crossorigin="anonymous"></script>
<script>
(function () {
  // Renderiza emojis (inclusive bandeiras 🇧🇷/🇮🇳, que o Windows não desenha)
  // como imagens via Twemoji. Degrada para emoji nativo se o CDN falhar.
  function parseEmoji(el) {
    try { if (window.twemoji) twemoji.parse(el, { folder: 'svg', ext: '.svg' }); } catch (e) {}
  }
  const DATA = JSON.parse(document.getElementById('payload').textContent);
  const THEMES = DATA.themes;
  const articles = DATA.articles;
  const HL = DATA.highlights || [];
  const hlLinks = new Set(HL.map(a => a.link));
  let activeTheme = HL.length ? 'inicio' : 'all';  // página inicial = Destaques
  let activeSource = 'all';
  let activeOrigin = 'all';
  let query = '';

  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  const chipsEl = document.getElementById('chips');
  const srcEl = document.getElementById('src');
  const originEl = document.getElementById('origin');
  originEl.addEventListener('change', e => { activeOrigin = e.target.value; render(); });

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
    el.className = 'chip' + (key === activeTheme ? ' active' : '');
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
  if (HL.length) chipsEl.appendChild(makeChip('inicio', '🏠 Início', '#c2185b', HL.length));
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
    const intl = a.origin === 'intl';
    const hl = hlLinks.has(a.link) && activeTheme !== 'inicio';  // marquinha roxa nos filtros
    return '<article class="card t-' + primary + (intl ? ' is-intl' : '') + (hl ? ' is-hl' : '') + '">' +
      '<div class="bar"></div>' +
      '<div class="body">' +
        '<div class="meta">' +
          (hl ? '<span class="hl-mark" title="Destaque do dia">✦</span>' : '') +
          '<span class="source' + (a.priority ? ' pri' : '') + '">' + esc(a.source) + '</span>' +
          (intl ? '<span class="intl-tag">🌐 Internacional</span>' : '') +
          (a.time_ago ? '<span>•</span><span>' + esc(a.time_ago) + '</span>' : '') + '</div>' +
        '<h3><a href="' + esc(a.link) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></h3>' +
        (function () {
          // Resumo em PT (✨) só na página Início; nas seções, o resumo original.
          const useAi = activeTheme === 'inicio' && a.ai_summary_text;
          const text = useAi ? a.ai_summary_text : a.summary;
          return text ? '<p class="sum">' + (useAi ? '<span class="ai-mark">✨ </span>' : '') + esc(text) + '</p>' : '';
        })() +
        '<div class="badges">' + badges + '</div>' +
        '<a class="read" href="' + esc(a.link) + '" target="_blank" rel="noopener">Ler matéria →</a>' +
      '</div></article>';
  }

  const viewTitle = document.getElementById('view-title');

  function matchFilters(a) {
    const q = query.trim().toLowerCase();
    const okSource = activeSource === 'all' || a.source === activeSource;
    const okOrigin = activeOrigin === 'all' || a.origin === activeOrigin;
    const okQuery = !q ||
      a.title.toLowerCase().includes(q) ||
      (a.summary || '').toLowerCase().includes(q) ||
      a.source.toLowerCase().includes(q);
    return okSource && okOrigin && okQuery;
  }

  function render() {
    let list;
    if (activeTheme === 'inicio') {
      // Página inicial: somente os Destaques do dia (sem misturar o resto)
      list = HL.filter(matchFilters);
      const tag = DATA.meta.ai_curated ? 'curadoria por IA' : 'mais relevantes';
      viewTitle.innerHTML = '✨ Destaques do dia <span class="sec-tag">' + tag + '</span>';
      viewTitle.hidden = false;
    } else {
      list = articles.filter(a => (activeTheme === 'all' || a.themes.includes(activeTheme)) && matchFilters(a));
      // matérias destacadas aparecem em primeiro lugar (com marquinha roxa)
      list.sort((x, y) => (hlLinks.has(y.link) ? 1 : 0) - (hlLinks.has(x.link) ? 1 : 0));
      viewTitle.hidden = true;
    }
    grid.innerHTML = list.map(cardHTML).join('');
    empty.hidden = list.length !== 0;
    parseEmoji(grid);
  }

  // recomputa o "tempo atrás" no cliente (mais preciso que no build)
  for (const a of articles) a.time_ago = a.published ? timeAgo(a.published) : '';
  for (const a of HL) a.time_ago = a.published ? timeAgo(a.published) : '';

  document.getElementById('q').addEventListener('input', e => { query = e.target.value; render(); });
  render();
  parseEmoji(document.body);
  // Re-parseia quando o Twemoji terminar de carregar (CDN assíncrono)
  window.addEventListener('load', () => parseEmoji(document.body));
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Camada de IA (Gemini) — opcional, com fallback
# --------------------------------------------------------------------------- #
def gemini_enrich(articles: list[dict], now: datetime) -> list[dict]:
    """Usa o Gemini para (1) gerar resumos de 1 frase em PT e (2) selecionar os
    Destaques do dia. Retorna a lista de destaques (ou [] se indisponível).

    Nunca lança exceção: qualquer falha (sem chave, cota, rede, JSON inválido)
    resulta em fallback silencioso para o ranking heurístico.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not articles:
        if not api_key:
            print("  (Gemini desativado: sem GEMINI_API_KEY — usando ranking heurístico)")
        return []

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # Seleção de candidatos com COBERTURA TEMÁTICA: além do topo global,
    # inclui os melhores de cada tema. Sem isso, assuntos de baixo peso
    # heurístico (energia/biocombustível, C&T, clima) não chegariam ao modelo
    # e nunca seriam pontuados/destacados.
    candidates: list[dict] = []
    seen_ids: set[int] = set()

    def _add(a: dict) -> None:
        if id(a) not in seen_ids:
            seen_ids.add(id(a))
            candidates.append(a)

    for a in articles[:40]:           # topo global
        _add(a)
    for theme in THEMES:              # até 30 por tema => cada seção é ranqueada pela IA
        c = 0
        for a in articles:
            if theme in a["themes"]:
                _add(a)
                c += 1
                if c >= 30:
                    break
    candidates = candidates[:160]
    listing = "\n".join(
        f'{i}: "{a["title"]}" — {a["source"]} [{", ".join(a["themes"])}]'
        for i, a in enumerate(candidates)
    )
    prompt = (
        "Você é analista de imprensa da Embaixada do Brasil em Nova Délhi. "
        "Recebe manchetes da imprensa indiana (em inglês).\n\n"
        "Para CADA item, forneça:\n"
        "- \"resumo\": 1 frase em português (máx. 160 caracteres), factual.\n"
        "- \"score\": inteiro 0-100 de relevância para a Embaixada. Use estas "
        "FAIXAS (não estoure a faixa do Brasil para temas setoriais):\n"
        "   90-100: menções diretas ao Brasil e relações bilaterais Índia-Brasil.\n"
        "   80-89: BRICS e cúpulas/foros com participação do Brasil.\n"
        "   65-79: política externa DA ÍNDIA (relações da Índia com outros "
        "países; Índia em foros internacionais) e comércio exterior indiano.\n"
        "   50-64: temas SETORIAIS prioritários — altos DENTRO do seu tema, mas "
        "ABAIXO do Brasil: biocombustíveis (etanol, flex fuel, E20/E85/E100); IA, DPI"
        "(infraestrutura pública digital) e soberania digital; conferências do "
        "clima (COP) e ONU.\n"
        "   30-49: política/economia/energia/ciência/clima da Índia em geral; E "
        "notícias internacionais que NÃO envolvem a Índia nem o Brasil (ex.: "
        "relações entre terceiros países, como China e Coreia do Norte).\n"
        "   0-29: notícia local/factual sem interesse diplomático.\n"
        "Use scores DISTINTOS para refletir a ordem dentro de cada tema (evite "
        "empates). O score ordena tanto os Destaques quanto cada seção.\n\n"
        'Responda APENAS em JSON, sem texto fora dele, no formato: '
        '{"itens": {"<i>": {"resumo": "<resumo>", "score": <0-100>}}}.\n\n'
        f"Itens:\n{listing}"
    )

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json",
            "maxOutputTokens": 16384,
            # Desliga o "thinking" do gemini-2.5-flash: sem isso, o raciocínio
            # consome o orçamento de tokens e o JSON volta truncado.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")

    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read())
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except Exception as exc:  # noqa: BLE001 — fallback para o heurístico
        print(f"  ! Gemini indisponível ({str(exc)[:80]}) — usando ranking heurístico")
        return []

    # Aplica resumo em PT e nota de relevância (ai_score) a cada item
    itens = result.get("itens", {}) or {}
    n_resumos = 0
    for k, v in itens.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(candidates)) or not isinstance(v, dict):
            continue
        resumo = v.get("resumo")
        if isinstance(resumo, str) and resumo.strip():
            # Resumo em PT exibido APENAS nos Destaques (não nas seções).
            candidates[idx]["ai_summary_text"] = resumo.strip()
            n_resumos += 1
        try:
            candidates[idx]["ai_score"] = max(0, min(100, int(v.get("score"))))
        except (TypeError, ValueError):
            pass

    # Destaques: PREFERÊNCIA ABSOLUTA por imprensa indiana. Ignora itens
    # internacionais e ordena por nota da IA (desc).
    indian_scored = [a for a in candidates if a.get("origin") == "in" and "ai_score" in a]
    indian_scored.sort(key=lambda a: a["ai_score"], reverse=True)
    highlights = indian_scored[:8]
    print(f"  ✓ Gemini: {len(highlights)} destaques (indianos), {n_resumos} resumos/notas geradas")
    return highlights


# --------------------------------------------------------------------------- #
# Pipeline principal
# --------------------------------------------------------------------------- #
def main() -> int:
    out_dir = os.environ.get("OUTPUT_DIR", "public")
    override = os.environ.get("FEEDS_OVERRIDE")
    feeds = json.loads(override) if override else FEEDS

    now = datetime.now(timezone.utc)

    # Janela de notícias: apenas HOJE e ONTEM (calendário de Nova Délhi, IST).
    # MAX_AGE_DAYS continua disponível só para testes locais (janela rolante).
    IST = timezone(timedelta(hours=5, minutes=30))
    max_age_env = os.environ.get("MAX_AGE_DAYS")
    if max_age_env:
        cutoff = now - timedelta(days=int(max_age_env))
        require_date = False
    else:
        today_ist = now.astimezone(IST).date()
        yesterday = today_ist - timedelta(days=1)
        cutoff = datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=IST)
        require_date = True

    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    articles: list[dict] = []
    ok_sources: set[str] = set()

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        hint = feed.get("themes", [])
        allow_intl = feed.get("allow_intl", False)
        scope_india = feed.get("scope_india", False)
        outlet_default = name.split(" — ")[0]  # ex.: "The Hindu", "Google News"
        print(f"- {name}")
        raw = fetch(url)
        if not raw:
            continue
        parsed = parse_feed(raw, name)
        for item in parsed:
            # Nome do veículo: usa o <source> (Google News) quando houver,
            # senão o nome-base do feed.
            outlet = item.get("outlet") or outlet_default

            # Limpa o título ANTES de gerar a chave de dedupe: o Google News
            # acrescenta " - Veículo" ao fim, o que impediria a deduplicação
            # contra o feed próprio do veículo.
            title = item["title"]
            if item.get("outlet") and title.endswith(" - " + item["outlet"]):
                title = title[: -(len(item["outlet"]) + 3)].strip()

            link_key = item["link"].split("?")[0].strip().lower()
            title_key = normalize(title).strip()
            if link_key in seen_links or (title_key and title_key in seen_titles):
                continue
            # filtro por data: só hoje e ontem
            if item["published"] is None:
                if require_date:
                    continue
            elif item["published"] < cutoff:
                continue

            indian = is_indian(outlet)
            known_intl = is_international(outlet)
            intl = known_intl and not indian
            # Filtragem de fontes em buscas agregadas (Google News):
            if item.get("outlet"):
                if scope_india:
                    # Busca "India + tema": resultado já é indiano. Só descarta
                    # agências estrangeiras conhecidas; fontes desconhecidas
                    # (veículos/portais especializados indianos) são mantidas.
                    if intl:
                        continue
                    intl = False  # trata desconhecidas como imprensa indiana
                elif not indian and not (allow_intl and intl):
                    # Busca de Brasil/BRICS: só indianas conhecidas (ou grandes
                    # agências, quando allow_intl).
                    continue

            themes = classify(item, hint)
            if not themes:
                continue  # só interessa o que cai em algum tema

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
                "priority": is_priority(outlet),
                "origin": "intl" if intl else "in",
            })

    # Ranking heurístico de relevância (determinístico, sem IA). Pondera tema
    # (foco da Embaixada: Brasil ≫ BRICS > política internacional > demais),
    # veículo de peso, origem indiana, recência e cruzamento de temas.
    THEME_WEIGHT = {
        "brasil": 6, "brics": 5, "politica_externa": 3, "politica_interna": 2,
        "economia": 2, "energia": 2, "cti": 2, "clima": 2,
    }

    def relevance(a: dict) -> float:
        s = float(sum(THEME_WEIGHT.get(t, 1) for t in a["themes"]))
        if len(a["themes"]) > 1:
            s += 1.5  # bônus por cruzar temas
        if a["priority"]:
            s += 3
        s += 2 if a["origin"] == "in" else -1
        if a["published"]:
            age_h = (now - datetime.fromisoformat(a["published"])).total_seconds() / 3600
            s += 3 if age_h <= 24 else (1 if age_h <= 48 else 0)
        a["score"] = round(s, 1)
        return s

    articles.sort(key=lambda a: (relevance(a), a["published"] or ""), reverse=True)

    # Camada de IA (opcional): nota de relevância p/ a Embaixada + resumos em
    # português + Destaques. Falha graciosamente para o ranking heurístico se a
    # chave/cota do Gemini não estiver disponível.
    ai_highlights = gemini_enrich(articles, now)
    ai_curated = bool(ai_highlights)

    # Se a IA pontuou os itens, ela passa a comandar a ordenação: notas da IA
    # primeiro (desc); itens não avaliados seguem pelo ranking heurístico.
    if any("ai_score" in a for a in articles):
        articles.sort(key=lambda a: (
            1 if "ai_score" in a else 0,
            a.get("ai_score", 0),
            a["score"],
            a["published"] or "",
        ), reverse=True)

    # Destaques sempre presentes na página principal: curadoria da IA quando
    # disponível; senão, os mais relevantes pelo heurístico. Em ambos os casos,
    # PREFERÊNCIA ABSOLUTA por imprensa indiana (sem internacionais).
    highlights = ai_highlights if ai_curated else [a for a in articles if a["origin"] == "in"][:8]

    # Diagnóstico (aparece no log do Actions): mostra a realidade do dia.
    _bio_kw = ("ethanol", "biofuel", "flex fuel", "biogas", "biodiesel",
               "e10", "e20", "e27", "e85", "e100", "bioenergy")
    bio = [a for a in articles if any(" " + k + " " in normalize(a["title"] + " " + a["summary"]) for k in _bio_kw)]
    print(f"  [diag] biocombustível no período (hoje/ontem): {len(bio)}")
    for a in bio[:6]:
        print(f"         score={a.get('ai_score', '-')} | {a['source']} | {a['title'][:64]}")
    en = [a for a in articles if "energia" in a["themes"]]
    print(f"  [diag] Energia: {len(en)} matérias — topo:")
    for a in en[:6]:
        print(f"         score={a.get('ai_score', '-')} | {a['source']} | {a['title'][:64]}")

    # Rótulo de atualização no horário de Nova Délhi (IST, UTC+5:30)
    generated_label = now.astimezone(IST).strftime("%d/%m/%Y às %H:%M (Nova Délhi)")

    payload = {
        "meta": {
            "generated_utc": now.isoformat(),
            "generated_label": generated_label,
            "window": "hoje e ontem",
            "feeds": sorted(ok_sources, key=str.lower),
            "ai_curated": ai_curated,
        },
        "articles": articles,
        "highlights": highlights,
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
