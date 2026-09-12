@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python Launcher не найден. Установите Python 3.10+ и повторите запуск.
  pause
  exit /b 1
)

set "GIGACHAT_AUTHORIZATION_KEY="
set /p GIGACHAT_AUTHORIZATION_KEY=Вставьте Authorization Key GigaChat: 
if not defined GIGACHAT_AUTHORIZATION_KEY (
  echo Ключ не указан. Запуск отменен.
  pause
  exit /b 1
)

set "GIGACHAT_SCOPE=GIGACHAT_API_PERS"
set /p GIGACHAT_SCOPE=Scope ^(Enter = GIGACHAT_API_PERS; для бизнеса — GIGACHAT_API_B2B или GIGACHAT_API_CORP^): 

set "GIGACHAT_CA_BUNDLE=%~dp0russian_trusted_root_ca_pem.crt"
if not exist "%GIGACHAT_CA_BUNDLE%" (
  echo Загружаю официальный корневой сертификат НУЦ Минцифры...
  curl.exe -k --fail --silent --show-error "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" -o "%GIGACHAT_CA_BUNDLE%"
  if errorlevel 1 (
    echo Не удалось получить сертификат. Проверьте подключение к интернету и повторите запуск.
    pause
    exit /b 1
  )
)

start "Тула.Транспорт — сервер" cmd /k py "%~dp0gigachat-server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8771/tula-transport-assistant.html"
exit /b 0
