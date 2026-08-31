@echo off
setlocal EnableExtensions
cd /d D:\AI_Research\dsh-run

echo ==============================================================================
echo DSH FBAW ENGINEERING AGENT v1.0 SCORE

echo Runtime model expected: deepseek-official / deepseek-v4-flash

echo ==============================================================================

set "PY=C:\Python314\python.exe"
set "EVAL=D:\AI_Research\dsh-run\evaluate_v4_3c_autonomous_benchmark.py"
set "SUMMARY=D:\AI_Research\dsh-run\fbaw_3Rx4_native_dsh_output\V4_3c_AUTONOMOUS_DSH_SESSION_SUMMARY.json"

if not exist "%PY%" (
  echo [FAIL] Python not found: %PY%
  exit /b 2
)
if not exist "%EVAL%" (
  echo [FAIL] Evaluator not found: %EVAL%
  exit /b 2
)
if not exist "%SUMMARY%" (
  echo [FAIL] Session summary not found: %SUMMARY%
  echo Run run_v4_3c_autonomous_benchmark.bat first.
  exit /b 2
)

"%PY%" "%EVAL%" --summary "%SUMMARY%"
set RC=%ERRORLEVEL%

echo.
if %RC%==0 (
  echo MODEL EVIDENCE: check benchmark log for:
  echo   provider=deepseek-official
  echo   model=deepseek-v4-flash
  echo   model-attributed DSH tool calls
  echo   Python-authorized STOP
) else (
  echo [FAIL] Agent benchmark score did not pass.
)
exit /b %RC%
