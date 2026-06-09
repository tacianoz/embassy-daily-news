# 🇮🇳→🇧🇷 Índia em Foco — Monitor de Notícias para o Brasil

Dashboard estático, atualizado **automaticamente todas as manhãs**, com notícias
indianas relevantes para o Brasil. As matérias são coletadas via **RSS** de
grandes veículos da Índia, classificadas por tema e exibidas em um painel
interativo com manchetes, resumos e link de acesso.

## Temas de interesse

| Tema | Descrição |
|------|-----------|
| 🇧🇷 **Brasil** | Menções ao Brasil |
| 🤝 **BRICS** | Menções ao BRICS |
| 🌐 **Política internacional** | Diplomacia e relações internacionais |
| 🏛️ **Política interna** | Política doméstica e governo |
| 📈 **Economia** | Economia, mercados e comércio |
| ⚡ **Energia** | Petróleo, gás, renováveis e eletricidade |
| 🔬 **Ciência, tecnologia e inovação** | C&T, espaço e inovação |
| 🌱 **Mudanças climáticas e meio ambiente** | Clima, meio ambiente e sustentabilidade |

## Como funciona

```
 GitHub Actions (cron diário, 07h Brasília)
        │
        ├── scripts/build.py
        │     ├── busca os feeds RSS/Atom (lista em FEEDS)
        │     ├── classifica cada matéria por palavras-chave + dica de seção
        │     ├── filtra para os últimos N dias e remove duplicatas
        │     └── gera public/index.html + public/data.json
        │
        └── publica em GitHub Pages
```

- **Sem dependências externas**: o `build.py` usa apenas a biblioteca padrão do
  Python (parser de RSS/Atom próprio). Não precisa de `pip install`.
- **Gratuito**: GitHub Actions + GitHub Pages, sem servidor.
- As manchetes e resumos são mantidos **no idioma original (inglês)**; a
  interface é em português.

## Ativando o GitHub Pages (uma única vez)

1. Faça o merge deste branch na `main`.
2. No repositório: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. O workflow roda diariamente às 10:00 UTC (07:00 Brasília). Para rodar na
   hora, vá em **Actions → "Atualização diária do dashboard" → Run workflow**.
4. A página ficará disponível em
   `https://tacianoz.github.io/embassy-daily-news/`.

## Rodando localmente

```bash
# Gera o dashboard a partir dos feeds reais (requer internet)
python3 scripts/build.py
# Saída em public/index.html

# Teste rápido com um feed de exemplo (offline)
FEEDS_OVERRIDE='[{"name":"Sample","url":"tests/sample_feed.xml","themes":[]}]' \
MAX_AGE_DAYS=3650 python3 scripts/build.py
```

## Personalização

- **Fontes**: edite a lista `FEEDS` em `scripts/build.py`.
- **Palavras-chave dos temas**: edite o dicionário `THEMES` no mesmo arquivo.
- **Horário**: ajuste o `cron` em `.github/workflows/daily.yml`.
- **Janela de notícias**: variável `MAX_AGE_DAYS` (padrão: 3 dias).
- **Apenas imprensa indiana**: as buscas agregadas (Google News) só aceitam
  veículos da lista `INDIAN_OUTLETS`; fontes estrangeiras são descartadas.
- **Jornais em destaque**: os veículos em `PRIORITY_OUTLETS` (Economic Times,
  The Hindu, Mint, Hindustan Times, Times of India) aparecem primeiro e com
  marcação ★.

> **Nota sobre os temas:** as seções gerais "Nacional/Índia" não recebem mais
> rótulo automático de *Política interna* — a classificação é feita por
> palavras-chave, evitando que matérias de crime/regionais entrem no tema.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OUTPUT_DIR` | `public` | Diretório de saída |
| `MAX_AGE_DAYS` | `3` | Idade máxima das matérias (dias) |
| `FEEDS_OVERRIDE` | — | JSON de feeds para teste local |
