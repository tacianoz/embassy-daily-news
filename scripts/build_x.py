#!/usr/bin/env python3
"""
EXPERIMENTO (branch experimento-x-twitter) — Monitor de contas indianas no X.

Gera uma página SEPARADA (public/x.html) com posts recentes das principais
contas indianas (política, parlamento, jornalistas, tech, diplomacia).

⚠️ Fonte de dados: o X/Twitter removeu o RSS e fechou a API de leitura
gratuita. A única via gratuita é o **Nitter** (RSS por conta), porém a maioria
das instâncias públicas está instável/fora do ar. Este script tenta uma lista
de instâncias com fallback; se nenhuma responder, a página sai vazia (sem
quebrar). Para uso sério, plugar uma fonte paga (X API v2, twitterapi.io,
rss.app) trocando apenas `fetch_account()`.

Reaproveita utilidades de build.py (fetch/parse/strip_html).
"""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timezone

import build  # mesmo diretório (scripts/) — reaproveita helpers

# --------------------------------------------------------------------------- #
# Contas monitoradas (handles reais), por categoria
# --------------------------------------------------------------------------- #
ACCOUNTS = {
    "Governo e política": [
        "narendramodi", "PMOIndia", "AmitShah", "RajnathSingh",
        "DrSJaishankar", "nsitharaman", "PiyushGoyal", "RahulGandhi",
        "ArvindKejriwal",
    ],
    "Diplomacia / MEA": [
        "MEAIndia", "IndianDiplomacy", "DrSJaishankar",
    ],
    "Parlamento / partidos": [
        "BJP4India", "INCIndia",
    ],
    "Jornalistas": [
        "sardesairajdeep", "bdutt", "ShekharGupta", "palkisu",
        "faye_dsouza", "svaradarajan",
    ],
    "Tech, economia e ciência": [
        "nandannilekani", "isro", "DRDO_India", "Inc42", "moneycontrolcom",
    ],
}

# Instâncias Nitter (RSS). Podem mudar/cair — sobrescreva via NITTER_INSTANCES.
NITTER_INSTANCES = os.environ.get(
    "NITTER_INSTANCES",
    "nitter.net,nitter.poast.org,nitter.privacydev.net,lightbrd.com",
).split(",")


def fetch_account(handle: str) -> list[dict]:
    """Tenta as instâncias Nitter até obter o RSS da conta. Retorna lista de
    posts (via build.parse_feed). Vazio se nada responder."""
    # Modo teste: ACCOUNT_SAMPLE aponta um arquivo RSS local para todas as contas
    sample = os.environ.get("ACCOUNT_SAMPLE")
    if sample:
        raw = build.fetch(sample)
        return build.parse_feed(raw, handle) if raw else []
    for inst in NITTER_INSTANCES:
        inst = inst.strip()
        if not inst:
            continue
        raw = build.fetch(f"https://{inst}/{handle}/rss", timeout=15)
        if raw:
            posts = build.parse_feed(raw, handle)
            if posts:
                return posts
    return []


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


# --------------------------------------------------------------------------- #
# Coleta + montagem
# --------------------------------------------------------------------------- #
def collect() -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - 36 * 3600  # últimas 36h
    seen: set[str] = set()
    posts: list[dict] = []
    for category, handles in ACCOUNTS.items():
        for handle in handles:
            print(f"- @{handle} ({category})")
            for item in fetch_account(handle):
                link = item["link"]
                if link in seen:
                    continue
                dt = item["published"]
                if dt and dt.timestamp() < cutoff:
                    continue
                seen.add(link)
                posts.append({
                    "handle": handle,
                    "category": category,
                    "text": item["title"],
                    "link": link,
                    "published": dt.isoformat() if dt else None,
                    "ts": dt.timestamp() if dt else 0,
                })
    posts.sort(key=lambda p: p["ts"], reverse=True)
    return posts


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vozes indianas no X — Embaixada do Brasil em Nova Délhi</title>
<style>
  :root { --bg:#f4f6fb; --card:#fff; --ink:#1a1f36; --muted:#6b7280; --line:#e6e9f0; --x:#1d9bf0; }
  @media (prefers-color-scheme: dark){ :root{ --bg:#0e1117; --card:#161b22; --ink:#e6edf3; --muted:#9aa4b2; --line:#232a35; } }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
  .wrap{max-width:1100px;margin:0 auto;padding:0 20px}
  header{background:#15224c;border-bottom:4px solid;border-image:linear-gradient(90deg,#1e9e3e 0 33%,#ffd200 33% 66%,#2b3a8f 66% 100%) 1;padding:20px 0}
  h1{margin:0;color:#fff;font-size:22px;font-weight:800}
  .sub{color:rgba(255,255,255,.8);font-size:13px;margin-top:4px}
  .controls{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 0;z-index:5}
  .chips{display:flex;gap:8px;flex-wrap:wrap}
  .chip{cursor:pointer;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:600}
  .chip.active{background:var(--x);color:#fff;border-color:transparent}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;padding:20px 0 60px}
  .post{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--x);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
  .meta{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--muted)}
  .h{font-weight:700;color:var(--ink)}
  .post p{margin:0;font-size:14px}
  .empty{color:var(--muted);text-align:center;padding:60px 20px}
  a.read{font-size:12.5px;font-weight:700;color:var(--x);text-decoration:none}
  footer{border-top:1px solid var(--line);color:var(--muted);font-size:12px;padding:18px 0 40px}
</style></head><body>
<header><div class="wrap"><h1>🐦 Vozes indianas no X</h1>
<div class="sub">Experimento · contas de governo, parlamento, imprensa e tech · Embaixada do Brasil em Nova Délhi</div></div></header>
<div class="controls"><div class="wrap chips" id="chips"></div></div>
<main class="wrap"><div class="grid" id="grid"></div>
<div class="empty" id="empty" hidden>Nenhum post coletado (as instâncias do Nitter podem estar fora do ar).</div></main>
<footer><div class="wrap" id="ft"></div></footer>
<script id="data" type="application/json">/*DATA*/</script>
<script>
(function(){
 const D=JSON.parse(document.getElementById('data').textContent);
 const posts=D.posts, cats=D.categories; let active='Todas';
 const grid=document.getElementById('grid'), chipsEl=document.getElementById('chips');
 document.getElementById('ft').textContent='Atualizado em '+D.generated+' · '+posts.length+' posts · fonte: Nitter (experimental)';
 function chip(c){const e=document.createElement('button');e.className='chip'+(c===active?' active':'');e.textContent=c+(c==='Todas'?' ('+posts.length+')':'');
  e.onclick=()=>{active=c;document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===e));render()};return e;}
 chipsEl.appendChild(chip('Todas')); cats.forEach(c=>chipsEl.appendChild(chip(c)));
 function ago(iso){if(!iso)return'';const m=Math.round((Date.now()-new Date(iso))/60000);if(m<60)return'há '+Math.max(m,1)+' min';const h=Math.round(m/60);if(h<24)return'há '+h+'h';return'há '+Math.round(h/24)+'d';}
 function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
 function render(){const l=posts.filter(p=>active==='Todas'||p.category===active);
  grid.innerHTML=l.map(p=>'<article class="post"><div class="meta"><span class="h">@'+esc(p.handle)+'</span><span>•</span><span>'+esc(p.category)+'</span>'+(p.published?'<span>•</span><span>'+ago(p.published)+'</span>':'')+'</div><p>'+esc(p.text)+'</p><a class="read" href="'+esc(p.link)+'" target="_blank" rel="noopener">Ver no X →</a></article>').join('');
  document.getElementById('empty').hidden=l.length!==0;}
 render();
})();
</script></body></html>
"""


def main() -> int:
    out_dir = os.environ.get("OUTPUT_DIR", "public")
    posts = collect()
    ist = timezone(__import__("datetime").timedelta(hours=5, minutes=30))
    payload = {
        "generated": datetime.now(ist).strftime("%d/%m/%Y às %H:%M (Nova Délhi)"),
        "categories": list(ACCOUNTS.keys()),
        "posts": posts,
    }
    out = TEMPLATE.replace("/*DATA*/", json.dumps(payload, ensure_ascii=False))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "x.html"), "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"\n✔ {len(posts)} posts → {out_dir}/x.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
