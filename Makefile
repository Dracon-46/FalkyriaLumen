# Atalhos de desenvolvimento. No Windows sem make, use os comandos da
# seção "Desenvolvimento" do README — são os mesmos.

PY ?= python3
COV = --cov=lumen_ingestao --cov=lumen_canonico --cov=lumen_deteccao --cov=lint_vocabulario \
      --cov=lumen_normalizacao --cov=lumen_conformidade --cov=lumen_orquestracao --cov=lumen_eleicoes --cov=referencia

.PHONY: ajuda instalar testes cobertura vocabulario estilo verificar docs ambiente banco contrato portal

ajuda:
	@echo "make instalar     dependencias de desenvolvimento"
	@echo "make testes       suite completa"
	@echo "make cobertura    suite com cobertura minima de 80%"
	@echo "make vocabulario  verificador de vocabulario controlado"
	@echo "make verificar    tudo o que a CI verifica"
	@echo "make estilo       analise estatica (ruff)"
	@echo "make docs         regenera os .docx da documentacao"
	@echo "make ambiente     sobe PostgreSQL e MinIO (docker compose)"
	@echo "make banco        testes da migracao no PostgreSQL do ambiente"
	@echo "make contrato     testes de contrato contra as fontes reais"
	@echo "make portal       instala, verifica e gera o portal (Next.js)"

instalar:
	$(PY) -m pip install -e ".[dev,analitico]"

testes:
	$(PY) -m pytest -q

cobertura:
	$(PY) -m pytest -q $(COV) --cov-report=term-missing --cov-fail-under=80

vocabulario:
	$(PY) ferramentas/lint-vocabulario/lint_vocabulario.py

estilo:
	$(PY) -m ruff check packages ferramentas testes

verificar: vocabulario estilo cobertura

docs:
	$(PY) ferramentas/referencia/referencia.py --json docs-src/referencia.json
	cd docs-src && npm install --silent && npm run docs

ambiente:
	docker compose -f infra/docker-compose.yml up -d

banco:
	LUMEN_TESTE_PG=postgresql://lumen:lumen-dev-local@localhost:5432/lumen $(PY) -m pytest -m postgres -q

contrato:
	LUMEN_TESTE_CONTRATO=1 $(PY) -m pytest -m contrato -q

portal:
	cd packages/portal && npm ci && npm run verificar && npm run build
