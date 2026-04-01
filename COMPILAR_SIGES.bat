@echo off
chcp 65001 > nul
echo.
echo ===================================================
echo   SIGES - Sistema de Gestion de Eventos en Salud
echo   Compilador PyInstaller  ^|  Arranque rapido
echo ===================================================
echo.

:: ─────────────────────────────────────────────────────
:: MODO: --onedir  (arranque inmediato, recomendado)
::   Resultado: dist\SIGES\SIGES.exe
::   Para distribuir: copiar toda la carpeta dist\SIGES\
::
:: Para generar un solo .exe (arranque ~5-10s mas lento):
::   Cambiar --onedir por --onefile
:: ─────────────────────────────────────────────────────

echo [1/1] Compilando SIGES ...
echo.

python -m PyInstaller ^
  --onedir ^
  --noconsole ^
  --clean ^
  --noconfirm ^
  --name="SIGES" ^
  --icon="logo.ico" ^
  ^
  --hidden-import=PySide6.QtCore ^
  --hidden-import=PySide6.QtGui ^
  --hidden-import=PySide6.QtWidgets ^
  --hidden-import=PySide6.QtSvg ^
  --hidden-import=PySide6.QtPrintSupport ^
  ^
  --hidden-import=psycopg2 ^
  --hidden-import=psycopg2._psycopg ^
  --hidden-import=psycopg2.extensions ^
  --hidden-import=psycopg2.extras ^
  ^
  --hidden-import=bcrypt ^
  ^
  --hidden-import=reportlab ^
  --hidden-import=reportlab.platypus ^
  --hidden-import=reportlab.lib ^
  --hidden-import=reportlab.lib.pagesizes ^
  --hidden-import=reportlab.lib.styles ^
  --hidden-import=reportlab.lib.units ^
  --hidden-import=reportlab.lib.colors ^
  --hidden-import=reportlab.lib.enums ^
  ^
  --hidden-import=openpyxl ^
  --hidden-import=openpyxl.cell._writer ^
  --hidden-import=openpyxl.styles ^
  --hidden-import=openpyxl.utils ^
  ^
  --hidden-import=conexion ^
  --hidden-import=config_conexion_backend ^
  --hidden-import=config_conexion_ui ^
  --hidden-import=login_backend ^
  --hidden-import=login_ui ^
  --hidden-import=entidad_backend ^
  --hidden-import=entidad_ui ^
  --hidden-import=ops_backend ^
  --hidden-import=ops_ui ^
  --hidden-import=gestion_eps_backend ^
  --hidden-import=gestion_eps_ui ^
  --hidden-import=gestion_eps_ops_backend ^
  --hidden-import=gestion_eps_ops_ui ^
  --hidden-import=gestion_afiliacion_backend ^
  --hidden-import=gestion_afiliacion_ui ^
  --hidden-import=pacientes_backend ^
  --hidden-import=pacientes_ui ^
  --hidden-import=gestion_eventos_backend ^
  --hidden-import=gestion_eventos_ui ^
  --hidden-import=gestion_reportes_backend ^
  --hidden-import=gestion_reportes_ui ^
  --hidden-import=maestro_backend ^
  ^
  --collect-submodules=PySide6.QtCore ^
  --collect-submodules=PySide6.QtGui ^
  --collect-submodules=PySide6.QtWidgets ^
  --collect-all=psycopg2 ^
  --collect-all=reportlab ^
  --collect-all=openpyxl ^
  --collect-all=bcrypt ^
  ^
  --exclude-module=PySide6.Qt3DCore ^
  --exclude-module=PySide6.Qt3DRender ^
  --exclude-module=PySide6.Qt3DInput ^
  --exclude-module=PySide6.Qt3DLogic ^
  --exclude-module=PySide6.Qt3DAnimation ^
  --exclude-module=PySide6.Qt3DExtras ^
  --exclude-module=PySide6.QtCharts ^
  --exclude-module=PySide6.QtDataVisualization ^
  --exclude-module=PySide6.QtMultimedia ^
  --exclude-module=PySide6.QtMultimediaWidgets ^
  --exclude-module=PySide6.QtWebEngineCore ^
  --exclude-module=PySide6.QtWebEngineWidgets ^
  --exclude-module=PySide6.QtWebEngineQuick ^
  --exclude-module=PySide6.QtWebChannel ^
  --exclude-module=PySide6.QtBluetooth ^
  --exclude-module=PySide6.QtNfc ^
  --exclude-module=PySide6.QtPositioning ^
  --exclude-module=PySide6.QtSensors ^
  --exclude-module=PySide6.QtRemoteObjects ^
  --exclude-module=PySide6.QtScxml ^
  --exclude-module=PySide6.QtQuick ^
  --exclude-module=PySide6.QtQuickWidgets ^
  --exclude-module=PySide6.QtQml ^
  --exclude-module=PySide6.QtDesigner ^
  --exclude-module=matplotlib ^
  --exclude-module=numpy ^
  --exclude-module=scipy ^
  --exclude-module=pandas ^
  --exclude-module=PIL ^
  --exclude-module=tkinter ^
  ^
  --add-data="logo.ico;." ^
  ^
  main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Fallo la compilacion.
    echo Revisa los mensajes anteriores.
    pause
    exit /b 1
)

:: Copiar gestion_eventos_db.cfg si existe
if exist "gestion_eventos_db.cfg" (
    copy /Y "gestion_eventos_db.cfg" "dist\SIGES\gestion_eventos_db.cfg" > nul
    echo [OK] Configuracion de BD copiada.
)

echo.
echo ===================================================
echo  COMPILACION EXITOSA
echo.
echo  Ejecutable: dist\SIGES\SIGES.exe
echo.
echo  Para distribuir copiar la carpeta dist\SIGES\
echo  completa al equipo destino.
echo.
echo  Modulos del sistema incluidos:
echo    Back: conexion, config, login, entidad, ops
echo          eps, eps_ops, afiliacion, pacientes
echo          eventos, reportes, maestro
echo    Front: todos los *_ui.py correspondientes
echo ===================================================
pause
