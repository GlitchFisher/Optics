@echo off
chcp 65001 >nul
title Building Driver Manager

echo [1/3] Сборка исполняемого файла...

PyInstaller manager.spec --noconfirm >nul 2>&1

if errorlevel 1 (
    echo Сборка не удалась!
    exit /b 1
)

echo [OK] Сборка завершена!

echo [2/3] Копирование в корень...

copy /y "dist\DriverManager.exe" "..\build\DriverManager.exe" >nul 2>&1

echo [OK] Файл скопирован!

echo [3/3] Удаление временных папок...

timeout /t 1 /nobreak >nul

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo [OK] Очистка завершена!
