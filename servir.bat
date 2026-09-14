@echo off
REM Sobe o site do A MILLION KEYS em http://localhost:8440
REM Feche esta janela para derrubar o servidor.
cd /d "%~dp0site"
echo.
echo   A MILLION KEYS  ->  http://localhost:8440
echo   (feche esta janela para parar)
echo.
python -m http.server 8440
