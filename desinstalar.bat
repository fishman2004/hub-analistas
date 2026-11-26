@echo off
rem Desinstala o Hub deste PC (par do instalar.bat). Nao precisa de administrador.
rem Fecha o Hub, tira do "abrir com o Windows", cuida dos dados (manter, copiar ou apagar)
rem e apaga os arquivos do programa desta pasta.
setlocal
cd /d "%~dp0"
set "HUBDIR=%~dp0"
echo.
echo  ==========================================
echo   Desinstalar o Hub dos Analistas
echo  ==========================================
echo.
echo  Isto vai:
echo    - fechar o Hub, se estiver aberto;
echo    - tirar o Hub do "abrir junto com o Windows";
echo    - apagar os arquivos do programa desta pasta:
echo      %HUBDIR%
echo  Antes, voce escolhe o que fazer com os dados (equipe, demandas, rotinas...).
echo.
choice /c SN /m "  Quer continuar"
if errorlevel 2 goto cancelado

rem --- qual Python usar (so para os dados; o do proprio Hub, se existir) ---
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"

rem --- 1. fechar o Hub: o processo na porta 8800 que roda "-m hub" e o que estiver rodando desta pasta ---
echo.
echo  Fechando o Hub...
powershell -NoProfile -Command "$d = $env:HUBDIR + '.venv\'; $ids = @(); try { $own = (Get-NetTCPConnection -LocalPort 8800 -State Listen -ErrorAction Stop).OwningProcess; $ids += (Get-CimInstance Win32_Process | Where-Object { ($own -contains $_.ProcessId) -and ($_.CommandLine -like '*-m hub*') }).ProcessId } catch {}; $ids += (Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) }).ProcessId; $ids | Where-Object { $_ } | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

rem --- 2. dados ---
echo.
if not defined PY (
  echo  Nao encontrei o Python, entao os dados ficam como estao, em %LOCALAPPDATA%\Hub
  goto programa
)
%PY% -m hub.desinstalar info
echo.
echo  O que fazer com os dados do Hub?
echo    1 - Manter os dados neste PC (recomendado: se instalar de novo, volta tudo como estava)
echo    2 - Guardar uma copia na Area de Trabalho e depois apagar os dados
echo    3 - Apagar os dados sem copia (nao tem volta)
echo.
choice /c 123 /n /m "  Digite 1, 2 ou 3: "
if errorlevel 3 goto apagar_sem_copia
if errorlevel 2 goto copia_e_apagar
echo  Os dados foram mantidos.
goto programa

:copia_e_apagar
echo.
echo  Guardando a copia...
%PY% -m hub.desinstalar copia
if errorlevel 1 (
  echo  A copia falhou, entao NAO apaguei os dados.
  goto programa
)
%PY% -m hub.desinstalar apagar-dados
goto programa

:apagar_sem_copia
echo.
set "CONF="
set /p "CONF=  Para apagar os dados sem copia, digite APAGAR e Enter (outra coisa mantem os dados): "
if /i not "%CONF%"=="APAGAR" (
  echo  Os dados foram mantidos.
  goto programa
)
%PY% -m hub.desinstalar apagar-dados

rem --- 3. abrir com o Windows e arquivos do programa ---
:programa
echo.
echo  Tirando do "abrir junto com o Windows"...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Hub.cmd" >nul 2>nul

echo  Apagando os arquivos do programa...
for %%D in (.venv hub tests tools docs .pytest_cache __pycache__) do if exist "%%D\" rmdir /s /q "%%D"
for %%F in (iniciar.bat instalar.bat README.md LICENSE pyproject.toml requirements.txt requirements-dev.txt .gitattributes .gitignore) do if exist "%%F" del /f /q "%%F"
if exist ".venv\" echo  Nao consegui apagar a pasta .venv (algo ainda esta usando). Reinicie o PC e apague esta pasta a mao.

echo.
echo  Pronto! O Hub foi desinstalado.
echo  Se a TV ainda estiver aberta no Edge, feche com Alt+F4.
echo.
pause
rem por ultimo, o proprio desinstalar.bat e a pasta (so se ficou vazia; nada que nao seja do Hub e apagado)
cd /d "%TEMP%"
(goto) 2>nul & del /f /q "%HUBDIR%desinstalar.bat" & rmdir "%HUBDIR:~0,-1%" 2>nul

:cancelado
echo  Nada foi alterado.
pause
exit /b 0
