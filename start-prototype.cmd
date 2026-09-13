@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PROTOTYPE_PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8771 .*LISTENING"') do set "PROTOTYPE_PORT_PID=%%P"
if defined PROTOTYPE_PORT_PID (
  echo Порт 8771 занят старым сервером ^(PID %PROTOTYPE_PORT_PID%^).
  choice /m "Закрыть его и запустить обновлённый прототип"
  if errorlevel 2 exit /b 0
  taskkill /PID %PROTOTYPE_PORT_PID% /F >nul
  if errorlevel 1 (
    echo Не удалось закрыть старый сервер. Закройте окно Python вручную и повторите запуск.
    pause
    exit /b 1
  )
  timeout /t 1 /nobreak >nul
)

where py >nul 2>&1
if errorlevel 1 (
  echo Python Launcher не найден. Установите Python 3.10+ и повторите запуск.
  pause
  exit /b 1
)

set "GIGACHAT_AUTHORIZATION_KEY="
set /p GIGACHAT_AUTHORIZATION_KEY=Вставьте Authorization Key GigaChat: 
if not defined GIGACHAT_AUTHORIZATION_KEY (
  echo Ключ не указан. Чат запустится в офлайн-режиме; карта 2ГИС будет доступна.
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

set "GIGACHAT_SUB_CA_BUNDLE=%~dp0russian_trusted_sub_ca_pem.crt"
if not exist "%GIGACHAT_SUB_CA_BUNDLE%" (
  echo Загружаю выпускающий сертификат НУЦ Минцифры...
  curl.exe -k --fail --silent --show-error "https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt" -o "%GIGACHAT_SUB_CA_BUNDLE%"
  if errorlevel 1 (
    echo Не удалось получить выпускающий сертификат. Проверьте подключение к интернету и повторите запуск.
    pause
    exit /b 1
  )
)

set "GIGACHAT_EXTRA_CA_BUNDLE="
set /p GIGACHAT_EXTRA_CA_BUNDLE=Путь к PEM корпоративного сертификата ^(Enter, если нет^): 
if defined GIGACHAT_EXTRA_CA_BUNDLE if not exist "%GIGACHAT_EXTRA_CA_BUNDLE%" (
  echo Указанный PEM-файл не найден. Запуск отменен.
  pause
  exit /b 1
)

set "TWOGIS_API_KEY="
set /p TWOGIS_API_KEY=Вставьте API Key 2ГИС ^(нужен для карты; Enter — запустить без карты^): 

start "Тула.Транспорт — сервер" cmd /k py "%~dp0gigachat-server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8771/tula-transport-assistant.html"
exit /b 0
