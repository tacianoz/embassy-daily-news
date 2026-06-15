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
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
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
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"]},
    {"name": "Google News — Brasil", "url": "https://news.google.com/rss/search?q=Brazil+(Lula+OR+Mercosur+OR+Petrobras+OR+Embraer+OR+ethanol+OR+trade+OR+Amazon)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"]},
    {"name": "Google News — BRICS", "url": "https://news.google.com/rss/search?q=BRICS&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brics"]},
    # Cobertura indiana do Brasil e do entorno latino-americano.
    {"name": "Google News — Brasil/América Latina", "url": "https://news.google.com/rss/search?q=India+(Brazil+OR+%22Latin+America%22+OR+Mercosur+OR+%22South+America%22+OR+CELAC)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["brasil"]},

    # Buscas dedicadas por tema (Google News) — garantem recall de assuntos
    # que os feeds de seção não cobrem (ex.: biocombustíveis). Só imprensa
    # indiana. O tema já vem carimbado via "themes".
    {"name": "Google News — Energia", "url": "https://news.google.com/rss/search?q=India+(ethanol+OR+biofuel+OR+%22flex+fuel%22+OR+biogas+OR+biodiesel+OR+bioenergy+OR+%22ethanol+blending%22+OR+E20+OR+E85+OR+E100)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["energia"], "scope_india": True},
    {"name": "Google News — Energia", "url": "https://news.google.com/rss/search?q=India+(%22renewable+energy%22+OR+%22green+hydrogen%22+OR+%22solar+power%22+OR+%22wind+energy%22+OR+%22nuclear+power%22+OR+%22clean+energy%22+OR+%22energy+transition%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["energia"], "scope_india": True},
    {"name": "Google News — C&T", "url": "https://news.google.com/rss/search?q=India+(ISRO+OR+semiconductor+OR+%22artificial+intelligence%22+OR+%22space+mission%22+OR+startup+OR+innovation+OR+DRDO)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["cti"], "scope_india": True},
    {"name": "Google News — C&T", "url": "https://news.google.com/rss/search?q=India+(%22digital+public+infrastructure%22+OR+%22quantum+computing%22+OR+supercomputer+OR+agritech+OR+healthtech+OR+biotechnology+OR+%22deep+tech%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["cti"], "scope_india": True},
    {"name": "Google News — Mineração", "url": "https://news.google.com/rss/search?q=India+(%22critical+minerals%22+OR+%22rare+earths%22+OR+%22rare+earth%22+OR+lithium+OR+cobalt+OR+%22mineral+exploration%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["energia"], "scope_india": True},
    {"name": "Google News — Clima", "url": "https://news.google.com/rss/search?q=India+(%22climate+change%22+OR+emissions+OR+pollution+OR+%22water+dispute%22+OR+%22National+Green+Tribunal%22+OR+groundwater+OR+deforestation+OR+%22environment+ministry%22+OR+monsoon+OR+flood)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["clima"], "scope_india": True},
    # Análise / reflexão estratégica (geopolítica e geoeconômica)
    {"name": "Google News — Análise estratégica", "url": "https://news.google.com/rss/search?q=India+(geopolitics+OR+geoeconomic+OR+geo-economic+OR+%22strategic+autonomy%22+OR+%22world+order%22+OR+%22great+power%22+OR+doctrine)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["opiniao"], "scope_india": True},
    {"name": "Google News — Defesa", "url": "https://news.google.com/rss/search?q=India+(defence+OR+military+OR+%22fighter+jet%22+OR+DRDO+OR+missile+OR+%22armed+forces%22+OR+warship+OR+%22air+force%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["defesa"], "scope_india": True},
    {"name": "Google News — Defesa/Brasil", "url": "https://news.google.com/rss/search?q=India+(Embraer+OR+%22C-390%22+OR+%22KC-390%22+OR+Gripen+OR+%22Taurus+Armas%22+OR+%22Brazilian+defence%22+OR+%22defence+export%22)&hl=en-IN&gl=IN&ceid=IN:en", "themes": ["defesa", "brasil"], "scope_india": True},

    # The Hindu
    {"name": "The Hindu — Nacional", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "themes": []},
    {"name": "The Hindu — Internacional", "url": "https://www.thehindu.com/news/international/feeder/default.rss", "themes": ["politica_externa"]},
    {"name": "The Hindu — Economia", "url": "https://www.thehindu.com/business/Economy/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Negócios", "url": "https://www.thehindu.com/business/feeder/default.rss", "themes": ["economia"]},
    {"name": "The Hindu — Ciência", "url": "https://www.thehindu.com/sci-tech/science/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Tecnologia", "url": "https://www.thehindu.com/sci-tech/technology/feeder/default.rss", "themes": ["cti"]},
    {"name": "The Hindu — Energia e Meio Ambiente", "url": "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "themes": ["energia", "clima"]},
    {"name": "The Hindu — Opinião (Lead)", "url": "https://www.thehindu.com/opinion/lead/feeder/default.rss", "themes": ["opiniao"]},
    {"name": "The Hindu — Opinião (Op-Ed)", "url": "https://www.thehindu.com/opinion/op-ed/feeder/default.rss", "themes": ["opiniao"]},
    {"name": "Indian Express — Opinião", "url": "https://indianexpress.com/section/opinion/feed/", "themes": ["opiniao"]},

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

    # --- Publicações especializadas indianas (RSS direto) ---
    # Defesa
    {"name": "Livefist", "url": "https://www.livefistdefence.com/feed/", "themes": ["defesa"]},
    {"name": "IDRW", "url": "https://idrw.org/feed/", "themes": ["defesa"]},
    {"name": "Raksha Anirveda", "url": "https://raksha-anirveda.com/feed/", "themes": ["defesa"]},
    {"name": "Indian Defence Review", "url": "https://www.indiandefencereview.com/feed/", "themes": ["defesa"]},
    {"name": "Bharat Shakti", "url": "https://bharatshakti.in/feed/", "themes": ["defesa"]},
    {"name": "The EurAsian Times", "url": "https://www.eurasiantimes.com/feed/", "themes": ["defesa", "politica_externa"]},
    # Tecnologia / startups
    {"name": "Inc42", "url": "https://inc42.com/feed/", "themes": ["cti", "economia"]},
    {"name": "Entrackr", "url": "https://entrackr.com/feed/", "themes": ["cti", "economia"]},
    {"name": "MediaNama", "url": "https://www.medianama.com/feed/", "themes": ["cti"]},
    {"name": "Analytics India Magazine", "url": "https://analyticsindiamag.com/feed/", "themes": ["cti"]},
    {"name": "YourStory", "url": "https://yourstory.com/feed", "themes": ["cti", "economia"]},
    {"name": "ET Tech", "url": "https://tech.economictimes.indiatimes.com/rss/topstories", "themes": ["cti"]},
    # Energia / mineração / agro
    {"name": "Mercom India", "url": "https://www.mercomindia.com/feed/", "themes": ["energia"]},
    {"name": "Saur Energy", "url": "https://www.saurenergy.com/feed/", "themes": ["energia"]},
    {"name": "PV Magazine India", "url": "https://www.pv-magazine-india.com/feed/", "themes": ["energia"]},
    {"name": "ChiniMandi", "url": "https://www.chinimandi.com/feed/", "themes": ["energia"]},
    {"name": "ETEnergyWorld", "url": "https://energy.economictimes.indiatimes.com/rss/topstories", "themes": ["energia"]},
    # Clima / meio ambiente
    {"name": "Mongabay India", "url": "https://india.mongabay.com/feed/", "themes": ["clima"]},
    # Economia
    {"name": "Moneycontrol", "url": "https://www.moneycontrol.com/rss/latestnews.xml", "themes": ["economia"]},
]

# --------------------------------------------------------------------------- #
# Temas de interesse (ordem definida pelo usuário)
# --------------------------------------------------------------------------- #
THEMES = {
    "brasil": {
        "label": "Brasil e América Latina",
        "desc": "Menções ao Brasil e à América Latina",
        "color": "#009c3b",
        "icon": "🇧🇷",
        "keywords": [
            "brazil", "brazilian", "brasil", "brasilia", "lula", "mercosur",
            "mercosul", "itamaraty", "sao paulo", "rio de janeiro",
            "bolsonaro", "planalto", "amazon basin",
            # grandes empresas brasileiras
            "embraer", "petrobras", "weg", "gerdau", "jbs", "marfrig",
            "suzano", "braskem", "ambev", "itau", "bradesco", "nubank",
            "stefanini", "eletrobras", "banco do brasil", "bndes",
            "taurus armas", "marcopolo", "vale", "cbc",
            # interesse muito próximo do Brasil
            "latin america", "latin american", "south america", "celac",
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
    "defesa": {
        "label": "Defesa",
        "desc": "Defesa, indústria bélica e cooperação militar",
        "color": "#475569",
        "icon": "🛡️",
        "keywords": [
            # geral / forças armadas
            "defence", "defense", "military", "armed forces", "indian army",
            "indian navy", "indian air force", "defence ministry",
            "defence minister", "rajnath singh", "drdo", "defence deal",
            "arms deal", "defence export", "defence procurement",
            "military exercise", "air defence",
            # aeronaves e plataformas
            "fighter jet", "fighter aircraft", "warship", "submarine",
            "aircraft carrier", "tejas", "rafale", "c 390", "kc 390",
            "gripen", "transport aircraft", "helicopter",
            # mísseis e munições
            "missile", "missile system", "brahmos", "akash missile",
            "s 400", "artillery", "ammunition", "munitions",
            # empresas (Brasil + concorrentes da Embraer)
            "embraer", "taurus armas", "lockheed", "lockheed martin",
            "airbus defence", "boeing defense", "dassault", "saab",
            "leonardo", "northrop",
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
        "label": "Energia e mineração",
        "desc": "Energia, minerais críticos e terras raras",
        "color": "#e67e22",
        "icon": "⚡",
        "keywords": [
            "energy", "energy transition", "natural gas", "petroleum", "coal",
            # petróleo — termos específicos (evita falsos positivos como "hot oil")
            "crude oil", "oil price", "oil prices", "oil and gas", "oilfield",
            "oil import", "oil imports", "oil output", "oil production",
            "oil demand", "fuel price", "refinery", "opec", "lng",
            # renováveis
            "solar power", "rooftop solar", "solar energy", "wind power",
            "wind energy", "wind farm", "offshore wind", "renewable",
            "renewables", "clean energy", "hydrogen", "green hydrogen",
            "hydropower", "geothermal",
            # eletricidade / nuclear (energia, não armas)
            "power sector", "power plant", "power grid", "electricity",
            "thermal power", "nuclear power", "nuclear reactor",
            "nuclear plant", "nuclear energy", "electric vehicle",
            # bioenergia
            "biofuel", "ethanol", "ethanol blending", "ethanol blend",
            "e10", "e20", "e27", "e85", "e100", "biogas",
            "compressed biogas", "bioenergy", "biodiesel", "biomass",
            "flex fuel", "flex fuel vehicle",
            # mineração / minerais críticos
            "critical mineral", "critical minerals", "rare earth",
            "rare earths", "lithium", "cobalt", "graphite", "nickel ore",
            "mining sector", "mineral resources", "mineral exploration",
            "strategic minerals", "coal mining", "kabil",
        ],
    },
    "cti": {
        "label": "Ciência, tecnologia e inovação",
        "desc": "C&T, espaço e inovação",
        "color": "#6c5ce7",
        "icon": "🔬",
        "keywords": [
            "technology", "science", "isro", "space mission", "satellite",
            "artificial intelligence", "semiconductor", "semiconductors",
            "innovation", "research", "quantum", "quantum computing",
            "supercomputer", "supercomputing", "biotech", "biotechnology",
            "agritech", "agri tech", "healthtech", "health tech",
            "digital public infrastructure", "digital india", "deep tech",
            "5g", "6g", "drdo", "robotics", "chip", "chip plant", "fab",
            "moon mission", "rocket", "spacetech", "data centre", "data center",
        ],
    },
    "clima": {
        "label": "Mudanças climáticas e meio ambiente",
        "desc": "Clima, meio ambiente, recursos naturais e políticas/disputas ambientais",
        "color": "#0891b2",
        "icon": "🌱",
        "keywords": [
            # clima e eventos
            "climate", "climate change", "global warming", "monsoon",
            "rainfall", "extreme weather", "ocean temperature", "sea level",
            "glacier", "flood", "floods", "drought", "cyclone", "heatwave",
            "el nino", "la nina", "air quality", "emission", "carbon",
            "net zero", "cop29", "cop30",
            # meio ambiente e recursos naturais
            "environment", "environmental", "pollution", "biodiversity",
            "forest", "deforestation", "wildlife", "wetland", "mangrove",
            "groundwater", "water scarcity", "water crisis", "river water",
            "water dispute", "river pollution", "ganga", "cauvery",
            "sustainability", "conservation",
            # políticas e disputas jurídicas ambientais
            "environment ministry", "environmental policy",
            "environmental clearance", "national green tribunal",
            "green tribunal", "environmental law",
        ],
    },
    "opiniao": {
        "label": "Opiniões & Análises",
        "desc": "Artigos de opinião, análise e reflexão estratégica",
        "color": "#8d6e63",
        "icon": "📝",
        "keywords": [],  # vem das fontes de opinião/análise (hint), não de keyword
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; EmbassyDailyNews/1.0; +https://github.com/tacianoz/embassy-daily-news)"

# Veículos indianos reconhecidos. Resultados de buscas agregadas (Google News)
# só entram se a fonte estiver nesta lista — garante apenas imprensa indiana.
INDIAN_OUTLETS = [
    # Grandes jornais / agências
    "the hindu", "businessline", "times of india", "hindustan times",
    "indian express", "economic times", "mint", "livemint", "ndtv",
    "ndtv profit", "business standard", "the wire", "scroll", "firstpost",
    "news18", "india today", "the print", "theprint", "deccan herald",
    "deccan chronicle", "the tribune", "tribune india", "outlook",
    "moneycontrol", "financial express", "wion", "zee news", "zee business",
    "republic world", "business today", "cnbc tv18", "cnbctv18", "frontline",
    "the quint", "swarajya", "the federal", "dna india", "free press journal",
    "national herald", "the statesman", "the new indian express",
    "telangana today", "rediff", "oneindia", "ani", "pti",
    "press trust of india", "fortune india", "the hindu businessline",
    # Tecnologia / startups
    "inc42", "entrackr", "medianama", "yourstory", "analytics india",
    "the ken", "techcircle", "gadgets 360", "gadgets360", "trak.in",
    "ettech", "et tech",
    # Energia / mineração / agro / químico
    "etenergyworld", "et energyworld", "mercom", "saur energy", "pv magazine",
    "chinimandi", "energetica india", "power line", "steelmint", "bigmint",
    "indian chemical news", "krishak jagat", "rural voice", "etauto",
    "et auto", "autocar",
    # Clima / meio ambiente / saúde
    "down to earth", "mongabay", "carbon copy", "the third pole",
    "ethealthworld", "et healthworld", "medical dialogues", "pharmabiz",
    # Agro / mainstream adicionais
    "krishi jagran", "krishijagran", "newslaundry", "the caravan", "india tv",
    "india briefing", "ibef", "observer research foundation", "orf online",
    # Defesa
    "livefist", "idrw", "indian defence", "indian defense", "stratpost",
    "force magazine", "indian defence review", "raksha anirveda",
    "india strategic", "sp s aviation", "sp s naval forces", "sp guide",
    "vayu aerospace", "defence and security alert", "defence monitor",
    "idsa", "manohar parrikar", "bharat shakti", "the eurasian times",
]

# Jornais de grande circulação — recebem prioridade na ordenação e destaque.
PRIORITY_OUTLETS = [
    "economic times", "the hindu", "businessline", "mint", "livemint",
    "hindustan times", "times of india",
]

def matches_outlet(source: str, tokens: list[str]) -> bool:
    blob = normalize(source)
    return any((" " + t + " ") in blob for t in tokens)


def is_indian(source: str) -> bool:
    return matches_outlet(source, INDIAN_OUTLETS)


# Unifica variações do nome do mesmo veículo (ex.: "Economic Times" e "The
# Economic Times") — para o filtro de jornais e a exibição nos cards.
# Ordem importa: tokens mais específicos primeiro.
CANONICAL_SOURCES = [
    ("The Hindu BusinessLine", "businessline"),
    ("The Economic Times", "economic times"),
    ("The Times of India", "times of india"),
    ("The Indian Express", "indian express"),
    ("The New Indian Express", "new indian express"),
    ("Hindustan Times", "hindustan times"),
    ("The Hindu", "the hindu"),
    ("NDTV Profit", "ndtv profit"),
    ("NDTV", "ndtv"),
    ("Mint", "livemint"),
    ("Mint", "mint"),
    ("Business Standard", "business standard"),
    ("Business Today", "business today"),
    ("The Wire", "the wire"),
    ("Scroll.in", "scroll"),
    ("Moneycontrol", "moneycontrol"),
    ("ThePrint", "theprint"),
    ("ThePrint", "the print"),
    ("News18", "news18"),
    ("India Today", "india today"),
    ("Firstpost", "firstpost"),
    ("Deccan Herald", "deccan herald"),
    ("Financial Express", "financial express"),
    ("Outlook", "outlook"),
    ("The Tribune", "tribune"),
    ("Press Trust of India", "press trust of india"),
    ("Press Trust of India", "pti"),
    ("ANI", "ani"),
    ("The Quint", "the quint"),
    ("The Federal", "the federal"),
    ("Frontline", "frontline"),
    ("Down To Earth", "down to earth"),
    ("Mongabay India", "mongabay"),
]


def canonical_source(name: str) -> str:
    blob = normalize(name)
    for display, token in CANONICAL_SOURCES:
        if (" " + token + " ") in blob:
            return display
    return name.strip()


def is_priority(source: str) -> bool:
    return matches_outlet(source, PRIORITY_OUTLETS)


# Grandes empresas brasileiras: ao serem citadas, a matéria SEMPRE recebe a
# tag "brasil" (mesmo que a IA não a inclua na recategorização).
BRAZIL_COMPANIES = [
    "embraer", "petrobras", "weg", "gerdau", "jbs", "marfrig", "suzano",
    "braskem", "ambev", "itau", "bradesco", "nubank", "stefanini",
    "eletrobras", "banco do brasil", "bndes", "taurus armas", "marcopolo",
    # formas inequívocas de Vale e CBC (bare 'vale'/'cbc' são ambíguos:
    # vale=vale do Caxemira, CBC=exame de sangue/emissora — ficam só como
    # palavra-chave soft, confirmada pela IA)
    "vale sa", "vale mining", "cbc global", "companhia brasileira de cartuchos",
]


def mentions_brazil_company(text: str) -> bool:
    return matches_outlet(text, BRAZIL_COMPANIES)


# Boletins/roundups recorrentes e tickers — ruído. Matérias com esses padrões
# no título são DESCARTADAS (não entram na seleção).
JUNK_TITLE = [
    "market update", "market wrap", "market roundup", "market round up",
    "closing bell", "opening bell", "share market live", "stock market live",
    "sensex today", "nifty today", "gold rate today", "silver rate today",
    "petrol and diesel price", "fuel price today", "price today",
    "rate today", "horoscope", "rashifal", "daily briefing",
]


def is_junk_title(title: str) -> bool:
    blob = normalize(title)
    return any(p in blob for p in JUNK_TITLE)


def is_english(text: str) -> bool:
    """Descarta títulos em scripts índicos (hindi/devanagari, bengali, tâmil,
    telugu, etc.). O monitor exibe só matérias em inglês."""
    indic = sum(1 for ch in (text or "") if 0x0900 <= ord(ch) <= 0x0DFF)
    return indic < 4

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


def fetch(url: str, timeout: int = 20) -> bytes | None:
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
        except urllib.error.HTTPError as exc:
            # 4xx (404/403/410): erro de cliente — não adianta repetir.
            if 400 <= exc.code < 500:
                print(f"  ! {exc.code} {url}", file=sys.stderr)
                return None
            last_err = exc
        except Exception as exc:  # noqa: BLE001 — toleramos falhas de rede
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


_TITLE_STOP = {
    "the", "and", "for", "with", "says", "after", "over", "amid", "into",
    "from", "that", "this", "are", "was", "will", "has", "have", "its", "new",
    "out", "how", "why", "what", "who", "his", "her", "their", "more", "than",
    "first", "second", "third", "report", "amid", "ahead", "year", "day",
}


def title_tokens(title: str) -> set:
    """Conjunto de palavras significativas do título (para detectar quase-dups)."""
    return {t for t in normalize(title).split()
            if len(t) >= 3 and t not in _TITLE_STOP}


def titles_similar(a: set, b: set) -> bool:
    """True se dois títulos provavelmente são a MESMA notícia (veículos
    diferentes, manchetes diferentes)."""
    if len(a) < 4 or len(b) < 4:
        return False
    inter = len(a & b)
    jaccard = inter / len(a | b)
    containment = inter / min(len(a), len(b))
    return jaccard >= 0.6 or containment >= 0.8


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

  /* ---- Mobile: cabeçalho e filtros mais compactos ---- */
  @media (max-width: 640px) {
    .top-inner { padding: 14px 16px 12px; }
    .brandline { gap: 12px; }
    .logo-svg { height: 54px; }
    h1 { font-size: 20px; }
    .subtitle { font-size: 11.5px; margin-top: 3px; }
    .stats { gap: 12px; margin-top: 9px; font-size: 11.5px; }
    .controls { padding: 8px 0; }
    .controls-inner { gap: 8px; }
    .search { flex: 1 1 100%; order: 1; padding: 8px 14px; }
    .srcpick { flex: 1 1 100%; order: 2; padding: 7px 12px; }
    .srcpick select { max-width: 100%; width: 100%; }
    /* chips numa única linha, com rolagem horizontal (não quebram a tela) */
    .chips { order: 3; width: 100%; flex-wrap: nowrap; overflow-x: auto;
      -webkit-overflow-scrolling: touch; scrollbar-width: none; padding-bottom: 2px; }
    .chips::-webkit-scrollbar { display: none; }
    .chip { flex: 0 0 auto; }
    .grid { grid-template-columns: 1fr; }
  }
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
  let inicio = HL.length > 0;            // página inicial = Destaques
  const activeThemes = new Set();        // temas selecionados (cumulativos)
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

  // Chips de filtro (Início e Todos são exclusivos; temas são cumulativos)
  function updateChips() {
    document.querySelectorAll('.chip').forEach(c => {
      const k = c.dataset.key;
      const on = k === 'inicio' ? inicio
        : k === 'all' ? (!inicio && activeThemes.size === 0)
        : (!inicio && activeThemes.has(k));
      c.classList.toggle('active', on);
    });
  }
  function makeChip(key, label, color, count) {
    const el = document.createElement('button');
    el.className = 'chip';
    el.dataset.key = key;
    if (color) el.style.setProperty('--cc', color);
    el.innerHTML =
      (color ? '<span class="dot" style="background:' + color + '"></span>' : '') +
      '<span>' + label + '</span><span class="count">' + count + '</span>';
    el.addEventListener('click', () => {
      if (key === 'inicio') { inicio = true; activeThemes.clear(); }
      else if (key === 'all') { inicio = false; activeThemes.clear(); }
      else {
        inicio = false;
        if (activeThemes.has(key)) activeThemes.delete(key); else activeThemes.add(key);
      }
      updateChips();
      render();
    });
    return el;
  }
  if (HL.length) chipsEl.appendChild(makeChip('inicio', '🏠 Início', '#c2185b', HL.length));
  chipsEl.appendChild(makeChip('all', 'Todos', '', counts.all));
  for (const k in THEMES) {
    chipsEl.appendChild(makeChip(k, THEMES[k].icon + ' ' + THEMES[k].label, THEMES[k].color, counts[k] || 0));
  }
  updateChips();

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
    const badges = a.themes.slice(0, 3).map(t =>
      '<span class="badge" style="--bc:' + THEMES[t].color + '">' + THEMES[t].icon + ' ' + esc(THEMES[t].label) + '</span>'
    ).join('');
    const hl = hlLinks.has(a.link) && !inicio;  // marquinha roxa nos filtros
    return '<article class="card t-' + primary + (hl ? ' is-hl' : '') + '">' +
      '<div class="bar"></div>' +
      '<div class="body">' +
        '<div class="meta">' +
          (hl ? '<span class="hl-mark" title="Destaque do dia">✦</span>' : '') +
          '<span class="source' + (a.priority ? ' pri' : '') + '">' + esc(a.source) + '</span>' +
          (a.time_ago ? '<span>•</span><span>' + esc(a.time_ago) + '</span>' : '') + '</div>' +
        '<h3><a href="' + esc(a.link) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></h3>' +
        (function () {
          // Resumo em PT (✨) só na página Início; nas seções, o resumo original.
          const useAi = inicio && a.ai_summary_text;
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
    const okQuery = !q ||
      a.title.toLowerCase().includes(q) ||
      (a.summary || '').toLowerCase().includes(q) ||
      a.source.toLowerCase().includes(q);
    return okSource && okQuery;
  }

  // Contadores dos chips acompanham os filtros ativos (origem/jornal/busca):
  // mostram quantas matérias cada tema tem NA VISÃO atual, não no total bruto.
  function updateCounts() {
    const base = articles.filter(matchFilters);
    const c = { all: base.length };
    for (const k in THEMES) c[k] = 0;
    for (const a of base) for (const t of a.themes) c[t] = (c[t] || 0) + 1;
    document.querySelectorAll('.chip').forEach(ch => {
      const k = ch.dataset.key;
      const span = ch.querySelector('.count');
      if (!span) return;
      span.textContent = k === 'inicio' ? HL.length : (k === 'all' ? c.all : (c[k] || 0));
    });
  }

  function render() {
    updateCounts();
    let list;
    if (inicio) {
      // Página inicial: somente os Destaques do dia (sem misturar o resto)
      list = HL.filter(matchFilters);
      const tag = DATA.meta.ai_curated ? 'curadoria por IA' : 'mais relevantes';
      viewTitle.innerHTML = '✨ Destaques do dia <span class="sec-tag">' + tag + '</span>';
      viewTitle.hidden = false;
    } else {
      // Temas cumulativos (E/interseção): artigo só entra se tiver TODOS os
      // temas selecionados. Combina com origem/jornal/busca.
      list = articles.filter(a =>
        [...activeThemes].every(t => a.themes.includes(t)) && matchFilters(a));
      // Ordem em cada seção (sort estável; base = relevância):
      //  0) Brasil em 1º lugar E o tema da seção em 2º;
      //  1) tema da seção em 1º lugar;
      //  2) o resto. Destaque é desempate interno.
      list.sort((x, y) => (hlLinks.has(y.link) ? 1 : 0) - (hlLinks.has(x.link) ? 1 : 0));
      if (activeThemes.size) {
        const srank = a =>
          (a.themes[0] === 'brasil' && activeThemes.has(a.themes[1])) ? 0
          : activeThemes.has(a.themes[0]) ? 1 : 2;
        list.sort((x, y) => srank(x) - srank(y));
      } else {
        // "Todos": matérias com a tag Brasil primeiro
        list.sort((x, y) => (y.themes.includes('brasil') ? 1 : 0) - (x.themes.includes('brasil') ? 1 : 0));
      }
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
DIPLOMAT_PERSONA = (
    "Você é uma DIPLOMATA BRASILEIRA lotada na Embaixada do Brasil em Nova "
    "Délhi. Sua função é monitorar a imprensa indiana e selecionar o que "
    "interessa ao Brasil e à relação Brasil–Índia. Pense e selecione COMO "
    "diplomata, priorizando:\n"
    "- a agenda bilateral Brasil–Índia e o BRICS;\n"
    "- os grandes eixos de cooperação entre os dois países: comércio e "
    "investimentos, agronegócio, energia e biocombustíveis (etanol/flex fuel), "
    "defesa, ciência e tecnologia, economia digital e DPI, saúde, minerais "
    "críticos e terras raras, e clima;\n"
    "- e SEMPRE as grandes linhas POLÍTICAS e ECONÔMICAS da Índia, que ajudam "
    "a ler o cenário estratégico e podem afetar a relação bilateral.\n"
    "Analise o SENTIDO de cada manchete (não palavras isoladas)."
)


SCORE_RUBRIC = (
    "Dê uma nota 0-100 de RELEVÂNCIA EDITORIAL para um diplomata brasileiro "
    "que acompanha a Índia. LEIA o conteúdo e pergunte-se quanto aquilo de fato "
    "INFORMA esse diplomata — julgue por importância e substância, NÃO por "
    "fórmula nem por simples menção.\n"
    "ALTA (75-100): relação Índia–Brasil e cooperação/empresas bilaterais; "
    "BRICS; grandes decisões e movimentos da POLÍTICA, ECONOMIA e POLÍTICA "
    "EXTERNA indianas com peso estratégico (acordos, política comercial, "
    "Índia–China e outras potências, defesa, energia, tecnologia/DPI, agro); "
    "e grandes ANÁLISES / artigos de REFLEXÃO estratégica (geopolítica ou "
    "geoeconômica) sobre a Índia e sua inserção no mundo — peças que ajudam a "
    "entender tendências e doutrina (ex.: 'From minerals to might: India's "
    "next geo-economic imperative').\n"
    "MÉDIA (40-74): notícia setorial, econômica ou política indiana de "
    "interesse, porém mais rotineira ou de menor alcance.\n"
    "BAIXA (0-39): episódios isolados ou repetitivos, acidentes/crimes locais, "
    "resultados esportivos de rotina, curiosidades, boletins de mercado e "
    "tickers — INCLUSIVE quando citam o Brasil. Uma MENÇÃO ao Brasil NÃO "
    "garante nota alta: pese a importância real (um acordo da Embraer vale "
    "muito mais que uma queda de helicóptero ou um jogo da Copa; estes só "
    "sobem se forem de real destaque nacional).\n"
    "EQUILÍBRIO POR TEMA: em ENERGIA, distribua a importância entre petróleo/"
    "gás, eletricidade, renováveis, nuclear, minerais críticos e "
    "biocombustíveis conforme o peso da NOTÍCIA específica — NÃO privilegie "
    "etanol/biocombustível automaticamente. Em ECONOMIA, foque a economia "
    "indiana (interna e internacional: acordos comerciais, relação com China e "
    "outros países, política do RBI/orçamento), sem deixar de pontuar outras "
    "notícias econômicas relevantes.\n"
    "Notícia estrangeira/curiosidade sem ligação com Índia ou Brasil é "
    "irrelevante (0-15). Use notas DISTINTAS para refletir a ordem."
)


EDITOR_PROMPT = (
    DIPLOMAT_PERSONA + "\n\n"
    "Abaixo está uma lista pré-selecionada de matérias indianas do dia. Atue "
    "como o EDITOR de clipping da Embaixada e escolha de 6 a 9 DESTAQUES — os "
    "itens mais IMPORTANTES e INFORMATIVOS do dia para um diplomata brasileiro "
    "na Índia. É uma seleção criteriosa e cautelosa, lendo cada matéria.\n"
    "Critérios:\n"
    "- IMPORTÂNCIA acima de menção: um episódio trivial ou repetitivo "
    "(acidente, crime local, resultado esportivo) ou uma simples menção ao "
    "Brasil NÃO entra só por isso — entra se for de real destaque. Ex.: um "
    "acordo da Embraer importa muito mais que uma queda de helicóptero ou um "
    "jogo da Copa (embora a queda ou a Copa POSSAM entrar se forem mesmo "
    "relevantes).\n"
    "- COBERTURA do que mais informa: grandes fatos da política, economia e "
    "política externa indianas (Índia–China e outras potências, acordos, "
    "comércio), relação Índia–Brasil e BRICS, cooperação setorial (defesa, "
    "energia, tecnologia, agro).\n"
    "- DIVERSIDADE: não encha de um só tema nem repita o mesmo fato/assunto; "
    "varie. Não selecione vários itens quase idênticos.\n"
    "- VALORIZE grandes ANÁLISES e artigos de REFLEXÃO estratégica "
    "(geopolítica/geoeconômica) sobre a Índia — não só notícia factual; essas "
    "peças costumam informar muito o diplomata sobre tendências e estratégia.\n\n"
    "Responda APENAS em JSON, em ordem editorial (mais relevante primeiro): "
    '{"destaques": [{"i": <índice>, "resumo": "<1 frase factual em PT, máx. 160>"}]}.\n\n'
    "Matérias:\n"
)


def _gemini_call(prompt: str, api_key: str, model: str, max_tokens: int,
                 retries: int = 2):
    """Chama o Gemini e devolve o JSON da resposta. Tenta de novo com backoff
    em falhas transitórias (429/5xx/rede/JSON truncado); esgotado, relança."""
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "maxOutputTokens": max_tokens,
            # Desliga o "thinking" do 2.5-flash (senão consome tokens e trunca).
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": api_key,
                         "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = json.loads(resp.read())
            return json.loads(raw["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last_err


def gemini_enrich(articles: list[dict], now: datetime) -> list[dict]:
    """A IA comanda o ranqueamento e a curadoria. Duas chamadas ao Gemini:
      1) lê e pontua um conjunto amplo por relevância editorial + recategoriza
         os temas (ordena cada seção);
      2) CURADORIA editorial dos Destaques — seleciona, com juízo de
         importância e diversidade, lendo as matérias (não top-N mecânico).
    Define a["ai_score"], a["themes"] e (nos destaques) a["ai_summary_text"];
    retorna os destaques. Falha graciosamente para o ranking heurístico.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not articles:
        if not api_key:
            print("  (Gemini desativado: sem GEMINI_API_KEY — usando ranking heurístico)")
        return []
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # Cobertura ampla: topo global + até 40 por tema => a IA pontua (e ordena)
    # cada seção, não só os destaques. O heurístico fica só como desempate.
    candidates: list[dict] = []
    seen_ids: set[int] = set()

    def _add(a: dict) -> None:
        if id(a) not in seen_ids:
            seen_ids.add(id(a))
            candidates.append(a)

    for a in articles[:90]:
        _add(a)
    for theme in THEMES:
        c = 0
        for a in articles:
            if theme in a["themes"]:
                _add(a)
                c += 1
                if c >= 60:
                    break
    candidates = candidates[:420]

    # ---- Chamada 1: NOTA + TEMAS (a IA entende o texto e recategoriza) ----
    # Em LOTES: respostas menores não truncam, e a falha de um lote não
    # derruba a avaliação dos demais.
    prompt_header = (
        DIPLOMAT_PERSONA + "\n\n"
        "Temas válidos (use estas CHAVES exatas):\n"
        "  brasil = menções ao Brasil OU a temas muito próximos do Brasil "
        "(América Latina, Mercosul, América do Sul, CELAC); brics = BRICS; "
        "politica_externa = política externa/relações internacionais da Índia; "
        "defesa = defesa, forças armadas, indústria bélica, aeronaves e navios "
        "militares, mísseis, exportações/negócios de defesa (Embraer, Taurus, "
        "CBC, Gripen, Rafale, BrahMos, etc.); "
        "politica_interna = política doméstica indiana; economia = economia/"
        "mercados/comércio; energia = petróleo, gás, eletricidade, renováveis, "
        "nuclear (energia), biocombustíveis, mineração, minerais críticos e "
        "terras raras; cti = ciência, tecnologia, espaço, inovação, IA, "
        "semicondutores, quântica, supercomputação, DPI, biotech, agritech, "
        "healthtech; clima = mudanças climáticas e eventos (monção, temperatura "
        "do oceano, enchentes, seca), meio ambiente, recursos naturais (água, "
        "rios, florestas) e políticas/disputas jurídicas ambientais (ex.: "
        "Tribunal Verde Nacional/NGT); "
        "opiniao = artigo de OPINIÃO, análise, editorial, coluna ou reflexão "
        "estratégica (use EM ADIÇÃO ao(s) tema(s) factual(is), quando o texto "
        "for analítico/opinativo, não uma notícia factual).\n\n"
        "Para CADA item, devolva:\n"
        "- \"temas\": lista das CHAVES que REALMENTE se aplicam ao conteúdo. "
        "Entenda o contexto: 'óleo quente de cozinha' NÃO é energia; 'armas/"
        "arsenal nuclear' é politica_externa, NÃO energia; 'drone militar' não "
        "é energia; 'balsa turística que aproveita a energia da água' NÃO é "
        "energia (é curiosidade). Se não se encaixar em nenhum tema de "
        "interesse da Embaixada, use []. ORDENE os temas do MAIS CENTRAL (o "
        "que melhor define o assunto principal da notícia) para o menos "
        "central.\n"
        "- \"score\": " + SCORE_RUBRIC + "\n\n"
        'Responda APENAS em JSON, sem texto fora dele: '
        '{"itens": {"<i>": {"temas": ["..."], "score": <0-100>}}}.\n\n'
        'Cada item vem como `i: "título" — fonte :: resumo`. CONSIDERE também '
        'o resumo (ex.: o Brasil pode ser citado só no resumo, não no título).\n\n'
    )
    BATCH = 80
    itens: dict = {}
    for start in range(0, len(candidates), BATCH):
        batch = candidates[start:start + BATCH]
        listing = "\n".join(
            f'{i}: "{a["title"]}" — {a["source"]}'
            + (f' :: {a["summary"][:200]}' if a["summary"] else "")
            for i, a in enumerate(batch, start=start)
        )
        try:
            result = _gemini_call(prompt_header + f"Itens:\n{listing}",
                                  api_key, model, 32768)
            itens.update(result.get("itens", {}) or {})
        except Exception as exc:  # noqa: BLE001 — lote perdido, segue o jogo
            print(f"  ! Gemini (lote {start}-{start + len(batch) - 1}) falhou "
                  f"({str(exc)[:60]})")
    if not itens:
        print("  ! Gemini indisponível — usando ranking heurístico")
        return []

    n_scored = 0
    for k, v in itens.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(candidates)) or not isinstance(v, dict):
            continue
        try:
            candidates[idx]["ai_score"] = max(0, min(100, int(v.get("score"))))
            n_scored += 1
        except (TypeError, ValueError):
            pass
        # Recategorização inteligente: a IA decide os temas reais da matéria,
        # ordenados do MAIS CENTRAL para o menos (preserva a ordem da IA).
        temas = v.get("temas")
        if isinstance(temas, list):
            candidates[idx]["themes"] = [t for t in dict.fromkeys(temas) if t in THEMES]

    # Só imprensa indiana RECONHECIDA (não "presumida") com tema válido.
    scored = [a for a in candidates
              if "ai_score" in a and a["themes"] and is_indian(a["source"])]
    scored.sort(key=lambda a: (a["ai_score"], a["priority"]), reverse=True)

    # ---- Chamada 2: CURADORIA EDITORIAL dos Destaques ----
    # Em vez de pegar mecanicamente o top-N por nota (o que faria toda matéria
    # de Brasil dominar), a IA atua como editor e SELECIONA, com diversidade e
    # juízo de importância. Pool diverso: top global + alguns de cada tema.
    pool: list[dict] = []
    pool_ids: set[int] = set()

    def _pool(a: dict) -> None:
        if id(a) not in pool_ids:
            pool_ids.add(id(a))
            pool.append(a)

    for a in scored[:28]:
        _pool(a)
    for theme in THEMES:
        c = 0
        for a in scored:
            if theme in a["themes"]:
                _pool(a)
                c += 1
                if c >= 9:
                    break
    pool = pool[:70]

    highlights: list[dict] = []
    if pool:
        listing = "\n".join(
            f'{i}: "{a["title"]}" — {a["source"]} [{", ".join(a["themes"])}]'
            + (f' :: {a["summary"][:180]}' if a["summary"] else "")
            for i, a in enumerate(pool)
        )
        try:
            res = _gemini_call(EDITOR_PROMPT + listing, api_key, model, 4096)
            chosen: set[int] = set()
            for d in (res.get("destaques", []) or [])[:9]:
                try:
                    i = int(d.get("i"))
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(pool) and i not in chosen:
                    chosen.add(i)
                    art = pool[i]
                    resumo = d.get("resumo")
                    if isinstance(resumo, str) and resumo.strip():
                        art["ai_summary_text"] = resumo.strip()
                    highlights.append(art)
        except Exception as exc:  # noqa: BLE001 — fallback: top por nota
            print(f"  ! Gemini (curadoria) falhou ({str(exc)[:60]}) — top por nota")
    if not highlights:
        highlights = scored[:8]

    print(f"  ✓ Gemini: {n_scored} matérias pontuadas, {len(highlights)} destaques curados")
    return highlights


# --------------------------------------------------------------------------- #
# Pipeline principal
# --------------------------------------------------------------------------- #
def main() -> int:
    out_dir = os.environ.get("OUTPUT_DIR", "public")
    override = os.environ.get("FEEDS_OVERRIDE")
    feeds = json.loads(override) if override else FEEDS

    now = datetime.now(timezone.utc)

    # Janela de notícias: últimas 24h — mas 48h às SEGUNDAS (para cobrir o fim
    # de semana), considerando o dia em Nova Délhi (IST), quando o build roda.
    # MAX_AGE_DAYS continua disponível só para testes locais (janela maior).
    IST = timezone(timedelta(hours=5, minutes=30))
    max_age_env = os.environ.get("MAX_AGE_DAYS")
    if max_age_env:
        cutoff = now - timedelta(days=int(max_age_env))
        require_date = False
        window_h = int(max_age_env) * 24
    else:
        window_h = 48 if now.astimezone(IST).weekday() == 0 else 24
        cutoff = now - timedelta(hours=window_h)
        require_date = True

    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    seen_clusters: list[dict] = []  # {"tokens": set, "article": dict} p/ quase-dups
    articles: list[dict] = []
    ok_sources: set[str] = set()

    # Busca todos os feeds em paralelo (preservando a ordem da lista) — com
    # ~50 feeds, em série ficaria lento; o ThreadPoolExecutor reduz para ~o
    # tempo do feed mais lento.
    with ThreadPoolExecutor(max_workers=12) as ex:
        raws = list(ex.map(lambda f: fetch(f["url"]), feeds))

    for feed, raw in zip(feeds, raws):
        name = feed["name"]
        hint = feed.get("themes", [])
        outlet_default = name.split(" — ")[0]  # ex.: "The Hindu", "Google News"
        print(f"- {name}")
        if not raw:
            continue
        parsed = parse_feed(raw, name)
        for item in parsed:
            # Nome do veículo: usa o <source> (Google News) quando houver,
            # senão o nome-base do feed.
            outlet = canonical_source(item.get("outlet") or outlet_default)

            # Limpa o título ANTES de gerar a chave de dedupe: o Google News
            # acrescenta " - Veículo" ao fim, o que impediria a deduplicação
            # contra o feed próprio do veículo.
            title = item["title"]
            if item.get("outlet") and title.endswith(" - " + item["outlet"]):
                title = title[: -(len(item["outlet"]) + 3)].strip()

            # Descarta boletins/tickers recorrentes e matérias não-inglês
            if is_junk_title(title) or not is_english(title):
                continue

            link_key = item["link"].split("?")[0].strip().lower()
            title_key = normalize(title).strip()
            if link_key in seen_links or (title_key and title_key in seen_titles):
                continue
            # filtro por data: só últimas 24 horas
            if item["published"] is None:
                if require_date:
                    continue
            elif item["published"] < cutoff:
                continue

            # Buscas agregadas (Google News): SÓ imprensa indiana reputada
            # (lista INDIAN_OUTLETS). Agências internacionais e sites
            # aleatórios/desconhecidos são descartados — este é um monitor
            # da imprensa indiana.
            if item.get("outlet") and not is_indian(outlet):
                continue

            themes = classify(item, hint)
            if not themes:
                continue  # só interessa o que cai em algum tema

            article = {
                "title": title,
                "link": item["link"],
                "summary": (item["summary"][:320] + "…") if len(item["summary"]) > 320 else item["summary"],
                "source": outlet,
                "published": item["published"].isoformat() if item["published"] else None,
                "themes": themes,
                "priority": is_priority(outlet),
                "opinion": "opiniao" in hint,  # veio de fonte de opinião/análise
            }

            # Quase-duplicata (mesma notícia, veículos/manchetes diferentes):
            # mantém a versão do veículo de MAIOR porte; senão, a primeira.
            tok = title_tokens(title)
            dup = next((c for c in seen_clusters if titles_similar(tok, c["tokens"])), None)
            if dup is not None:
                kept = dup["article"]
                if article["priority"] and not kept["priority"]:
                    kept.update(article)   # promove a versão do veículo grande
                    dup["tokens"] = tok
                continue

            seen_links.add(link_key)
            if title_key:
                seen_titles.add(title_key)
            ok_sources.add(outlet)
            articles.append(article)
            seen_clusters.append({"tokens": tok, "article": article})

    # Ranking heurístico de relevância (determinístico, sem IA). Pondera tema
    # (foco da Embaixada: Brasil ≫ BRICS > política internacional > demais),
    # veículo de peso, origem indiana, recência e cruzamento de temas.
    THEME_WEIGHT = {
        "brasil": 6, "brics": 5, "politica_externa": 3, "defesa": 3,
        "politica_interna": 2, "economia": 2, "energia": 2, "cti": 2,
        "clima": 2, "opiniao": 3,
    }

    def relevance(a: dict) -> float:
        s = float(sum(THEME_WEIGHT.get(t, 1) for t in a["themes"]))
        if len(a["themes"]) > 1:
            s += 1.5  # bônus por cruzar temas
        if a["priority"]:
            s += 3
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

    # Garantia: matérias vindas de fontes de opinião/análise mantêm a tag
    # 'opiniao' (a IA pode tê-la descartado na recategorização).
    for a in articles:
        if a.get("opinion") and "opiniao" not in a["themes"]:
            a["themes"].append("opiniao")

    # A IA pode ter recategorizado matérias como irrelevantes (temas = []):
    # removê-las limpa os falsos positivos (ex.: "óleo quente" em Energia).
    before = len(articles)
    articles = [a for a in articles if a["themes"]]
    if before != len(articles):
        print(f"  [diag] removidas por recategorização da IA: {before - len(articles)}")

    # Garantia: matéria que cita grande empresa brasileira SEMPRE tem tag
    # 'brasil' (e em destaque, como tema principal) — mesmo que a IA não inclua.
    for a in articles:
        if "brasil" not in a["themes"] and mentions_brazil_company(a["title"] + " " + a["summary"]):
            a["themes"] = ["brasil"] + a["themes"]

    # Se a IA pontuou os itens, ela passa a comandar a ordenação: notas da IA
    # primeiro (desc); itens não avaliados seguem pelo ranking heurístico.
    if any("ai_score" in a for a in articles):
        articles.sort(key=lambda a: (
            1 if "ai_score" in a else 0,
            a.get("ai_score", 0),
            1 if a["priority"] else 0,   # desempate: veículo grande primeiro
            a["score"],
            a["published"] or "",
        ), reverse=True)

    # Destaques sempre presentes na página principal: curadoria da IA quando
    # disponível; senão, os mais relevantes pelo heurístico. Em ambos os casos,
    # PREFERÊNCIA ABSOLUTA por imprensa indiana (sem internacionais).
    highlights = ai_highlights if ai_curated else [a for a in articles if is_indian(a["source"])][:8]

    # Diagnóstico (aparece no log do Actions): mostra a realidade do dia.
    _bio_kw = ("ethanol", "biofuel", "flex fuel", "biogas", "biodiesel",
               "e10", "e20", "e27", "e85", "e100", "bioenergy")
    bio = [a for a in articles if any(" " + k + " " in normalize(a["title"] + " " + a["summary"]) for k in _bio_kw)]
    print(f"  [diag] biocombustível no período (últimas {window_h}h): {len(bio)}")
    for a in bio[:6]:
        print(f"         score={a.get('ai_score', '-')} | {a['source']} | {a['title'][:64]}")
    en = [a for a in articles if "energia" in a["themes"]]
    print(f"  [diag] Energia: {len(en)} matérias — topo:")
    for a in en[:6]:
        print(f"         score={a.get('ai_score', '-')} | {a['source']} | {a['title'][:64]}")

    # Rótulo de atualização no horário de Nova Délhi (IST, UTC+5:30)
    generated_label = now.astimezone(IST).strftime("%d/%m/%Y às %H:%M (Nova Délhi)")

    # Guarda de edição vazia: se a coleta falhou em massa (rede, feeds fora do
    # ar), aborta SEM publicar — o GitHub Pages mantém a edição anterior.
    # Em testes locais (FEEDS_OVERRIDE) o piso é 0, salvo MIN_ARTICLES.
    default_min = "0" if override else "30"
    min_articles = int(os.environ.get("MIN_ARTICLES", default_min))
    if len(articles) < min_articles:
        print(f"\n✖ Apenas {len(articles)} matérias (mínimo {min_articles}) — "
              "abortando para preservar a edição anterior", file=sys.stderr)
        return 1

    payload = {
        "meta": {
            "generated_utc": now.isoformat(),
            "generated_label": generated_label,
            "window": f"últimas {window_h} horas",
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
