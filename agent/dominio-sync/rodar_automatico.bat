@echo off
REM ===================================================================
REM  Dominio-Sync AUTOMATICO  (chamado pelo Agendador de Tarefas)
REM
REM  Baixa os XMLs do PAC e salva nas pastas do Dominio, SEM precisar
REM  editar a competencia todo mes: "--competencia recente" cobre o mes
REM  ATUAL + o mes PASSADO numa execucao so (janela rolante).
REM
REM  Por que a janela rolante e nao alternar auto/anterior: a janela vai
REM  como filtro pro servidor e o cursor (estado.json) e GLOBAL, entao
REM  rodar um mes avanca o cursor e o outro PULARIA notas. Uma janela
REM  unica + um cursor unico nao tem esse furo.
REM
REM  IMPORTANTE: usa o Python312 pelo caminho COMPLETO. O "python" do
REM  PATH resolve pro venv do hermes, que NAO tem as dependencias.
REM ===================================================================

cd /d C:\dominio-sync

set "PY=C:\Users\pacpa\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "logs" mkdir "logs"

echo. >> "logs\agendado.log"
echo ======== INICIO %DATE% %TIME% ======== >> "logs\agendado.log"

"%PY%" dominio_sync.py --competencia recente >> "logs\agendado.log" 2>&1
set "CODIGO=%ERRORLEVEL%"

echo ======== FIM %DATE% %TIME% (codigo=%CODIGO%) ======== >> "logs\agendado.log"

exit /b %CODIGO%
