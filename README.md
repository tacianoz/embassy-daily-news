# 🇮🇳→🇧🇷 Índia em Foco — Monitor de Notícias para o Brasil

Dashboard estático, atualizado **automaticamente todas as manhãs**, com notícias
indianas relevantes para o Brasil. As matérias são coletadas via **RSS** de
grandes veículos da Índia, classificadas por tema e exibidas em um painel
interativo com manchetes, resumos e link de acesso.

## Temas de interesse

| Tema | Descrição |
|------|-----------|
| 🇧🇷 **Brasil e América Latina** | Menções ao Brasil e à América Latina |
| 🤝 **BRICS** | Menções ao BRICS |
| 🌐 **Política internacional** | Diplomacia e relações internacionais |
| 🏛️ **Política interna** | Política doméstica e governo |
| 📈 **Economia** | Economia, mercados e comércio |
| ⚡ **Energia** | Petróleo, gás, renováveis e eletricidade |
| 🔬 **Ciência, tecnologia e inovação** | C&T, espaço e inovação |
| 🌱 **Clima e meio ambiente** | Mudanças climáticas, meio ambiente e sustentabilidade |

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

## Ranking e curadoria por IA

As matérias são ordenadas por um **ranking heurístico de relevância**
(determinístico, sem custo): peso por tema (Brasil ≫ BRICS > política
internacional > demais), veículo de grande circulação, origem indiana,
recência e cruzamento de temas.

Opcionalmente, uma **camada de IA (Gemini)** gera os **Destaques do dia**,
**resumos de 1 frase em português** e as **🧭 Narrativas do dia** — uma
síntese analítica no topo da página Início, com o quadro geral do dia e as
principais narrativas da imprensa indiana (os Destaques vêm logo abaixo).
Cada narrativa passa por um **aprofundamento**: a IA identifica o fio
condutor, faz uma **pesquisa adicional específica** no Google News Índia e
entrega um relatório sucinto — síntese, fatos-chave em bullets, chave de
leitura, implicação para o Brasil e fontes. É totalmente
opcional e com *fallback* automático: sem a chave (ou se a cota/rede
falhar), o painel funciona 100% com o ranking heurístico (e o bloco de
narrativas simplesmente não aparece).

**Ativar o Gemini (gratuito):**
1. Crie uma API key em <https://aistudio.google.com/apikey> (free tier).
2. No repositório: **Settings → Secrets and variables → Actions → New
   repository secret**, nome `GEMINI_API_KEY`, valor = sua chave.
3. Rode o workflow. Modelo padrão: `gemini-3.6-flash` (ajustável via
   variável `GEMINI_MODEL`).

## Personalização

- **Fontes**: edite a lista `FEEDS` em `scripts/build.py`.
- **Palavras-chave dos temas**: edite o dicionário `THEMES` no mesmo arquivo.
- **Horário**: ajuste o `cron` em `.github/workflows/daily.yml`.
- **Janela de notícias**: por padrão mostra apenas as **últimas 24 horas**
  (janela rolante). `MAX_AGE_DAYS` força uma janela maior (uso em testes).
- **Logo**: recriada em SVG no cabeçalho de `scripts/build.py`. Para usar o PNG
  oficial, substitua o bloco `<svg class="logo-svg">` por `<img src="logo.png">`
  e faça o script copiar o arquivo para `OUTPUT_DIR`.
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
| `MAX_AGE_DAYS` | — | Janela rolante em dias (testes); sem ela, valem as últimas 24 horas |
| `FEEDS_OVERRIDE` | — | JSON de feeds para teste local |
| `MIN_ARTICLES` | `30` (`0` em teste) | Piso de matérias: abaixo disso o build aborta sem publicar, preservando a edição anterior |
| `HISTORY_DIR` | `history` | Pasta versionada com os snapshots diários (menu Hoje/Ontem/Anteontem) |
| `GEMINI_API_KEY` | — | Ativa a camada de IA (ranqueamento/destaques/resumos) |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Modelo da camada de IA (pontuação/curadoria) |
| `GEMINI_MODEL_NARRATIVES` | `gemini-3.5-pro` | Modelo de ponta usado só nas Narrativas do dia (com raciocínio profundo; *fallback* para o `GEMINI_MODEL`) |

## Histórico de 3 dias (Hoje / Ontem / Anteontem)

O cabeçalho traz um menuzinho com as edições dos **últimos 3 dias**. Cada dia é
uma página estática autocontida (`index.html` = hoje; `h-AAAA-MM-DD.html` = dias
anteriores) e o menu são apenas links entre elas. A cada execução o build:

1. salva o snapshot do dia em `history/data-AAAA-MM-DD.json` (versionado);
2. mantém só os **3 snapshots mais recentes** (poda os demais);
3. renderiza uma página por dia e o menu correspondente.

O passo *"Persistir histórico"* do workflow faz commit da pasta `history/` para
que os snapshots sobrevivam entre execuções (exige `permissions: contents: write`).
