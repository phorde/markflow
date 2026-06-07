# MarkFlow — Auditoria de Projeto

## 1. INTENÇÃO

Pipeline de extração PDF → Markdown com OCR-first, roteamento inteligente de modelos LLM, e output auditável. Projetado para qualidade de produção em documentos médicos e regulados.

**Problema que resolve:** Extração confiável de PDFs de qualidade variada com rastreabilidade e validação.

## 2. ESTADO ATUAL

- **Status:** Funcional, v1.0.0 lançado
- **Stack:** Python 3.10+, EasyOCR, aiohttp, Pillow, questionary (TUI)
- **Maturidade:** Alta — tem CLI, TUI, Docker, testes, CI, changelog, documentação extensa
- **Último commit:** Ativo (já teve deploy no Render)
- **Commits:** Projeto maduro com histórico consistente
- **Já tem .planning/ GSD completo** — provavelmente o projeto mais estruturado do portfólio

## 3. STACK

- **Linguagem:** Python 3.10+
- **Framework:** CLI/TUI (Click + Questionary)
- **OCR:** EasyOCR, RapidOCR, Tesseract
- **LLM:** OpenAI, Anthropic, Gemini, OpenRouter, Z.AI (provider-agnostic)
- **Deploy:** Render (docker-compose.yml existente)
- **Build:** Makefile, pyproject.toml

## 4. ESTRUTURA

```
markflow/
├── app.py                    # Entry point (Render deployment)
├── markflow/
│   ├── cli.py                # CLI interface
│   ├── tui.py                # Terminal UI interativa
│   ├── pipeline.py           # Pipeline principal de extração
│   ├── llm_client.py         # Cliente LLM provider-agnostic
│   ├── routing.py            # Roteamento inteligente de modelos
│   ├── model_selection.py    # Benchmark-driven model selection
│   ├── security.py           # Validação e segurança
│   └── benchmark_ingestion.py # Benchmarks de qualidade
├── tests/                    # Testes
├── docs/                     # Documentação
└── docker-compose.yml        # Deploy config
```

## 5. CÓDIGO MORTO

- Nenhum óbvio — projeto bem mantido
- `.codex/` e `.github/copilot-instructions.md` são configs de AI assistant — podem ser removidos ou unificados
- `EXECUTION_MODES.md` pode estar desatualizado

## 6. PADRONIZAÇÃO

**Divergências do padrão (Next.js + Bun + TypeScript):**
- Python, não TypeScript — **NÃO recomendado migrar**. Python é a stack correta para ML/OCR.
- Tem Makefile em vez de scripts npm — adequado para Python
- Tem pyproject.toml em vez de package.json — adequado para Python

**Avaliação:** Manter Python. A stack é correta para o domínio (OCR/ML).

## 7. QUALIDADE

- ✅ README profissional e extenso
- ✅ CHANGELOG
- ✅ CONTRIBUTING guide
- ✅ Testes
- ✅ Docker support
- ✅ CI/CD
- ✅ .planning/ GSD completo
- ✅ AGENTS.md
- ⚠️ `.env.example` existe — bom
- ⚠️ Deploy no Render configurado

## 8. CLASSIFICAÇÃO

- **Categoria:** App (CLI/TUI)
- **Escopo:** Utilitário / ML / Document processing
- **Tipo de deploy:** Web service (app.py no Render) ou CLI standalone

## 9. DEPLOY

- **Atual:** Render (docker-compose)
- **Dokploy:** Pode ser deployado via Dockerfile
- **Subdomínio:** markflow.phorde.com.br → web interface ou landing page
- **Tipo:** Web service com API + landing page

## 10. ROADMAP PARA PUBLICAÇÃO

1. Criar Dockerfile (referência: docker-compose.yml existente)
2. Deploy no Dokploy via Docker
3. Configurar markflow.phorde.com.br no Cloudflare Tunnel
4. Adicionar web interface ao app.py (atualmente pode ser CLI-only)
5. Se não houver web UI, servir landing page com README renderizado
6. Limpar configs de AI assistant (.codex/, copilot-instructions.md) ou unificar
7. Revisar e atualizar .planning/ GSD existente

---

## Resumo

**MarkFlow é o projeto mais maduro do portfólio.** Já tem documentação profissional, GSD, Docker, testes e CI/CD. Precisa apenas de um Dockerfile adequado para Dokploy e um subdomínio apontando pra ele. Se não tiver web UI, pode servir uma landing page.
