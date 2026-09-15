# Instale sua própria cópia em 4 passos

O painel roda **de graça** no seu GitHub (GitHub Actions + GitHub Pages),
sem servidor e sem instalar nada no computador. Cada cópia é independente:
usa a **sua** chave de API e publica no **seu** endereço.

> Tempo total: uns 5 minutos. Só precisa de uma conta no GitHub.

## 1. Crie a cópia (1 clique)

Abra o link abaixo e clique em **Create repository**:

**https://github.com/tacianoz/embassy-daily-news/generate**

- Escolha um nome (ex.: `india-em-foco`).
- Deixe o repositório como **Public** (o GitHub Pages gratuito exige isso).

## 2. Ative o GitHub Pages (1 clique)

No repositório recém-criado, abra
`Settings → Pages` (endereço: `https://github.com/SEU-USUARIO/NOME-DO-REPO/settings/pages`)
e, em **Build and deployment → Source**, escolha **GitHub Actions**.
Não precisa salvar nada além disso.

## 3. Cadastre sua chave de API (opcional, mas recomendado)

A chave ativa a camada de IA (Destaques, resumos em português e Narrativas do dia).
Sem ela, o painel funciona do mesmo jeito, só com o ranking automático.

1. Gere uma chave gratuita em <https://aistudio.google.com/apikey>.
2. No repositório, abra
   `Settings → Secrets and variables → Actions → New repository secret`
   (endereço: `https://github.com/SEU-USUARIO/NOME-DO-REPO/settings/secrets/actions/new`).
3. **Name:** `GEMINI_API_KEY` — **Secret:** cole a chave — **Add secret**.

## 4. Rode a primeira edição

Abra a aba **Actions**, clique em **"Atualização diária do dashboard"** →
**Run workflow** → **Run workflow**. Em 2 a 5 minutos o painel estará em:

**`https://SEU-USUARIO.github.io/NOME-DO-REPO/`**

(o endereço exato aparece no fim da execução, no job *deploy*).

Daí em diante ele se atualiza **sozinho todo dia**, por volta das 06:30 em
Nova Délhi (22:00 em Brasília). O menu Hoje / Ontem / Anteontem vai se
preenchendo ao longo dos primeiros 3 dias.

---

## Se algo der errado

| Sintoma | O que fazer |
|---------|-------------|
| A execução falha no passo *"Verificar se o GitHub Pages está ativado"* | Faça o passo 2 e rode de novo. |
| A aba Actions pede para habilitar workflows | Clique em **"I understand my workflows, go ahead and enable them"** (acontece em cópias feitas por *fork*; usando o link do passo 1 não acontece). |
| O painel saiu sem "Destaques" nem "Narrativas" | A secret `GEMINI_API_KEY` não foi cadastrada, está com o nome errado ou a cota gratuita do dia acabou. O painel continua funcionando sem IA. |
| Parou de atualizar sozinho depois de meses | O GitHub desliga agendamentos em repositórios sem atividade por 60 dias; abra Actions e rode manualmente uma vez. |

## Personalizar

- **Fontes e temas:** edite `FEEDS` e `THEMES` em `scripts/build.py`
  (qualquer alteração em `scripts/` já dispara uma nova edição).
- **Horário:** ajuste o `cron` em `.github/workflows/daily.yml` (em UTC).
- **Modelos de IA pagos (opcional):** cadastre `ANTHROPIC_API_KEY` ou
  `OPENAI_API_KEY` como secret; veja a tabela de variáveis no `README.md`.
