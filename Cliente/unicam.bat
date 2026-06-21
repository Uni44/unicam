@echo off
:REINTENTAR
echo.
echo ===============================
echo Iniciando cam
echo ===============================
mpv.exe mpv --fs --hwdec=auto --rtsp-transport=tcp --demuxer-lavf-o="buffer_size=20480,max_delay=300000" --no-cache --no-input-default-bindings --input-vo-keyboard=no --untimed --framedrop=vo --profile=low-latency --vd-lavc-threads=1 rtsp://localhost:8554/cam
echo.
echo Stream caído o cerrado. Reintentando en 3 segundos...
timeout /t 3 /nobreak >nul
goto REINTENTAR