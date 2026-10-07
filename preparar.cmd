@echo off
rem Falkyria Lumen - aba Eleicoes pronta num clique: mapa, eleicoes de 1933 a 2026
rem e o portal aberto no navegador. Pode fechar e abrir de novo a qualquer momento:
rem o que ja foi baixado e processado nao e refeito.
rem
rem Precisa de: Python 3.11+ (https://www.python.org/downloads/) e, para o portal,
rem Node.js 20.9+ (https://nodejs.org). Opcoes extras vao direto para o comando,
rem por exemplo: preparar.cmd --anos 2024,2022  ou  preparar.cmd --sem-ao-vivo
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"

if not exist lumen.toml (
  echo Falta o lumen.toml. Copie lumen.toml.exemplo para lumen.toml e preencha o contato em [coleta].
  goto fim
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.11 ou mais novo nao encontrado. Instale em https://www.python.org/downloads/
  goto fim
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando o ambiente Python em .venv ...
  %PY% -m venv .venv || goto erro
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -e . || goto erro

where npm >nul 2>nul || echo Aviso: Node.js nao encontrado; os dados serao carregados, mas o portal nao sera gerado.

".venv\Scripts\python.exe" -m lumen_eleicoes preparar --servir %*
goto fim

:erro
echo.
echo Algo deu errado acima. A mensagem de erro diz o que faltou.

:fim
echo.
pause
