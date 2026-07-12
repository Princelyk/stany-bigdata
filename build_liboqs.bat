@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

set CL_PATH=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64
set PATH=%CL_PATH%;%PATH%
set CMAKE_C_COMPILER=%CL_PATH%\cl.exe
set CMAKE_ASM_COMPILER=%CL_PATH%\ml64.exe

set PYOQS_VENV=c:\Users\princ\Documents\Stany\hybrid_secure_bigdata\venv_win
set PYOQS_CMAKE=%PYOQS_VENV%\Scripts\cmake.exe
set OQS_INSTALL=%USERPROFILE%\_oqs
set OQS_INSTALL_PATH=%OQS_INSTALL%

echo === Checking cl.exe ===
cl.exe 2>&1 | findstr "Microsoft"

echo === Building liboqs manually ===
set TMPBUILD=%TEMP%\liboqs_build

if exist "%TMPBUILD%" rmdir /s /q "%TMPBUILD%"
mkdir "%TMPBUILD%"

cd /d "%TMPBUILD%"
git clone --depth 1 --branch 0.15.0 https://github.com/open-quantum-safe/liboqs
"%PYOQS_CMAKE%" -S liboqs -B liboqs/build ^
    -DBUILD_SHARED_LIBS=ON ^
    -DOQS_BUILD_ONLY_LIB=ON ^
    -DOQS_ENABLE_SIG_STFL_LMS=ON ^
    -DOQS_ENABLE_SIG_STFL_XMSS=ON ^
    -DOQS_HAZARDOUS_EXPERIMENTAL_ENABLE_SIG_STFL_KEY_SIG_GEN=ON ^
    -DCMAKE_INSTALL_PREFIX="%OQS_INSTALL%" ^
    -DCMAKE_WINDOWS_EXPORT_ALL_SYMBOLS=TRUE ^
    -DCMAKE_C_COMPILER="%CL_PATH%\cl.exe" ^
    -G "NMake Makefiles"

if errorlevel 1 (
    echo cmake configure failed
    exit /b 1
)

"%PYOQS_CMAKE%" --build liboqs/build --parallel 4
if errorlevel 1 (
    echo cmake build failed
    exit /b 1
)

"%PYOQS_CMAKE%" --build liboqs/build --target install
if errorlevel 1 (
    echo cmake install failed
    exit /b 1
)

echo === liboqs built and installed to %OQS_INSTALL% ===
dir "%OQS_INSTALL%\bin\*.dll"
dir "%OQS_INSTALL%\lib\*.lib"

echo === Testing oqs import ===
set PATH=%PYOQS_VENV%\Scripts;%PATH%
python -c "import oqs; print('SUCCESS: oqs version =', oqs.get_version())"
