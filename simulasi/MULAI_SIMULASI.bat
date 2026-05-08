@echo off
TITLE SIMU JR - Judicial Review Simulator
COLOR 0B
cls

echo.
echo  ------------------------------------------
echo    SIMU JR - JUDICIAL REVIEW SIMULATOR
echo  ------------------------------------------
echo.
echo  [S] [I] [M] [U]   [J] [R]
echo.
echo ==========================================
echo    JUDICIAL REVIEW SIMULATOR - ACTIVE
echo ==========================================
echo.
echo [1/2] Memeriksa lingkungan...

:: Cek Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan dalam PATH! 
    echo Harap instal Python atau tambahkan ke environment variables.
    pause
    exit
)

:: Cek apakah ada virtual environment (venv)
if exist venv\Scripts\activate (
    echo [OK] Mengaktifkan virtual environment...
    call venv\Scripts\activate
) else (
    echo [INFO] Berjalan menggunakan sistem Python langsung...
)

echo [2/2] Menyalakan server dan browser...
echo.
echo ------------------------------------------
echo STATUS: JANGAN TUTUP JENDELA INI.
echo URL: http://localhost:8080
echo ------------------------------------------
echo.

:: Menjalankan browser otomatis (tanpa delay agar lebih responsif)
start http://localhost:8080

:: Jalankan server Python
python server.py

:: Jika server crash/stop, jangan langsung tutup jendela
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server berhenti dengan kode: %errorlevel%
    pause
) else (
    echo.
    echo [INFO] Server telah dimatikan secara normal.
    pause
)
