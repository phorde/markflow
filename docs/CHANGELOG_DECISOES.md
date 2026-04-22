# Changelog e Justificativas de Decisoes

## Objetivo

Este documento registra, com racional tecnico, as decisoes estruturais e operacionais mais relevantes para que outros agentes (Codex, Claude Code, Gemini CLI, GitHub Copilot e similares) consigam continuar o trabalho sem perda de contexto.

## Resumo Executivo (2026-04-20)

- O projeto deixou de ser apenas CLI/core e passou a operar com arquitetura de servicos (`frontend`, `api`, `worker`).
- O estado canonico foi centralizado no `services/api` com processamento orientado a eventos via Redis Streams.
- A governanca GSD foi reforcada com rastreabilidade completa entre requisitos, implementacao e testes.
- O processo de release foi endurecido com gates de CI para fronteiras de servico, build frontend, tipagem, lint e cobertura.

## Registro por Agente

### GitHub Copilot

- Decisao: estruturar o monorepo com `services/frontend`, `services/api` e `services/worker`.
- Justificativa: separar ownership de runtime/build/deploy por dominio operacional.
- Impacto: base para isolamento de servicos, contratos formais e evolucao independente de componentes.
- Decisao: formalizar continuidade operacional Copilot<->Codex com artefatos canônicos de instrucoes, checkpoint, handoff e runbook.
- Justificativa: reduzir perda de contexto entre agentes e tornar a transicao auditavel/deterministica.
- Impacto: adicionados `.github/copilot-instructions.md`, `.planning/COPILOT_HANDOFF_PROTOCOL.md`, `.planning/copilot-state.md`, `.planning/SKILLS_FOR_COPILOT.md`, `.planning/CONTEXT_FOR_AGENTS.md`, `.planning/AGENT_ROLES.md`, `docs/INTEGRATION_COPILOT_CODEX.md` e gate de validacao em CI.
- Decisao: endurecer runtime de seguranca apos auditoria (guards explicitos no broker, defaults mais seguros de bind e controle deterministico de subprocessos com timeout).
- Justificativa: reduzir superficie de risco em operacao local/CI sem quebrar contratos de servico e mantendo comportamento deterministico.
- Impacto: `services/api/broker.py` e `services/worker/broker.py` migraram de `assert` para guardas de runtime; `services/worker/entrypoint.py` passou a bind padrao em `127.0.0.1`; `scripts/run_with_timeout.py` ganhou resolucao de executavel e terminacao robusta de arvore de processos; varredura Bandit ficou sem achados.

### Carver (subagente)

- Decisao: auditar o frontend e identificar riscos de build/runtime e UX de estados terminais.
- Justificativa: o frontend era ponto critico para fluxo fim-a-fim de jobs e precisava de garantias de terminalidade.
- Impacto: ajustes em polling/SSE, validacoes de entrada e melhoria no fluxo de revisao de paginas com baixa confianca.

### Averroes (subagente)

- Decisao: endurecer semantica de ACK e idempotencia no pipeline de eventos da API.
- Justificativa: evitar corrupcao de estado em entregas at-least-once.
- Impacto: ACK condicionado ao commit do reducer e reducao de risco de inconsistencias em reprocessamento.

### Herschel (subagente)

- Decisao: corrigir adaptacao multimodal no cliente Anthropic.
- Justificativa: preservar suporte real a entrada de imagem em fluxos OCR remotos.
- Impacto: tratamento correto de blocos `image_url` (data URI) e maior paridade entre provedores.

### Pascal (subagente)

- Decisao: corrigir e ampliar o verificador de fronteiras de servico.
- Justificativa: regex e varredura anterior deixavam falsos negativos/positivos.
- Impacto: script mais confiavel com exclusao de diretorios de build/cache e cobertura de regras proibidas.

### Locke (subagente)

- Decisao: revisar seguranca de dependencias e conflitos de versao.
- Justificativa: resolver vulnerabilidades e conflitos de resolvedor sem quebrar os gates.
- Impacto: pins atualizados (`fastapi`, `starlette`, `pytest-*`) e auditorias limpas por manifesto.

### Rawls (subagente)

- Decisao: consolidar governanca operacional em CI.
- Justificativa: transformar politicas de arquitetura em verificacoes automatizadas.
- Impacto: jobs de CI para boundaries, runtime checks, build frontend e gates de qualidade.

### Codex (orquestracao final)

- Decisao: consolidar empacotamento, governanca documental e rastreabilidade de decisoes.
- Justificativa: garantir continuidade entre sessoes/agentes e reduzir risco de regressao de arquitetura.
- Impacto:
- `CHANGELOG.md` criado.
- `.planning/decisions/DECISION_LOG.md` criado.
- Skill `gsd-decision-ledger` criada.
- Specs GSD atualizadas com requisitos de servico/operacao/governanca.
- Runner `scripts/run_with_timeout.py` criado para comandos que podem travar.
- CI ajustado para executar Black com `--no-cache` e timeout.

### Codex (depuracao do travamento)

- Decisao: executar Black no CI via `scripts/run_with_timeout.py 120 -- python -m black --check --no-cache .`.
- Justificativa: `black 26.3.1` travou no Windows ao usar cache neste workspace; `--no-cache` passou imediatamente.
- Impacto: travamentos passam a falhar com codigo `124` e mensagem clara, sem deixar processos Python filhos vivos.

### Codex (correcao CI mypy Linux)

- Decisao: acessar atributos especificos de plataforma via `getattr` em branches Windows/POSIX.
- Justificativa: o CI falhava no step `Mypy` nos jobs Python 3.10, 3.11 e 3.12 porque os stubs Linux nao expunham `subprocess.CREATE_NEW_PROCESS_GROUP` nem `ctypes.windll`, embora esses acessos estivessem protegidos por `os.name == "nt"`.
- Impacto: `python -m mypy --platform linux markflow services scripts` passa localmente e o runner de timeout preserva comportamento robusto em Windows e POSIX.

### Codex (deploy Render)

- Decisao: preparar deploy via Render Blueprint com API, frontend e worker como servicos isolados e Redis Streams em Render Key Value.
- Justificativa: o Render Blueprint mapeia diretamente os Dockerfiles existentes do monorepo e evita colapsar os limites `services/frontend`, `services/api` e `services/worker`.
- Ajuste operacional: como a instancia Free do Render nao esta disponivel para background workers, o deploy gratuito inicial executa o worker como Web Service Docker com endpoint `/health`; o upgrade natural para producao e mudar esse servico para `type: worker` em plano pago.
- Impacto: `render.yaml` passa a descrever `app.phorde.com.br`, `api.phorde.com.br`, worker isolado e Key Value Redis-compatible, com CORS configuravel via ambiente.

## Decisoes Estruturais

1. API como autoridade de estado canonico.
2. Worker publica observacoes e resultados, sem mutacao direta de estado canonico.
3. Frontend apenas envia comandos e consome estado/eventos.
4. Contratos Redis versionados (`v1`) como limite formal de compatibilidade.
5. Check de fronteiras de servico como gate obrigatorio de CI.
6. Comandos de qualidade propensos a travamento devem rodar com timeout explicito.
7. Deploy gratuito inicial no Render usa worker como Web Service isolado; background worker nativo exige plano pago.

## Decisoes de Processo (GSD)

1. Requisitos v1 devem permanecer 100% mapeados em `.planning/specs/features.json`.
2. Cada requisito v1 deve ter secao de aceitacao em `.planning/specs/feature_acceptance_matrix.md`.
3. Mudancas arquiteturais devem entrar no ledger de decisoes e no changelog.
4. Nova skill dedicada para manter historico por agente e justificativas auditaveis.

## Evidencias Tecnicas

- Tests: `tests/spec/test_gsd_spec_traceability.py`, `tests/spec/test_decision_context_governance.py`, `tests/unit/test_web_foundation.py`, `tests/unit/test_event_contract_schemas.py`, `tests/unit/test_service_boundary_checker.py`.
- CI: `.github/workflows/ci.yml`.
- Politicas: `docs/architecture/service-isolation-policy.md`, `docs/architecture/event-contracts.md`.
- Ledger: `.planning/decisions/DECISION_LOG.md`.
- Timeout runner: `scripts/run_with_timeout.py`.
