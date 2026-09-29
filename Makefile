# Atalhos de desenvolvimento. No Windows sem make, use os comandos da
# seção "Desenvolvimento" do README — são os mesmos.

PY ?= python3
COV = --cov=lumen_ingestao --cov=lumen_canonico --cov=lumen_deteccao --cov=lint_vocabulario

.PHONY: ajuda instalar testes cobertura vocabulario verificar docs

ajuda:
	@echo "make instalar     dependencias de desenvolvimento"
	@echo "make testes       suite completa"
	@echo "make cobertura    suite com cobertura minima de 80%"
	@echo "make vocabulario  verificador de vocabulario controlado"
	@echo "make verificar    tudo o que a CI verifica"
	@echo "make docs         regenera os .docx da documentacao"

instalar:
	$(PY) -m pip install pytest pytest-cov

testes:
	$(PY) -m pytest -q

cobertura:
	$(PY) -m pytest -q $(COV) --cov-report=term-missing --cov-fail-under=80

vocabulario:
	$(PY) ferramentas/lint-vocabulario/lint_vocabulario.py

verificar: vocabulario cobertura

docs:
	cd docs-src && npm install --silent && npm run docs
