@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d D:\AI_Research\dsh-run
echo ==============================================================================
echo V4.3c AUTONOMOUS NATIVE DSH FBAW BENCHMARK - MODEL-ID VERIFIED
echo ==============================================================================
if not exist "D:\AI_Research\dsh-run\node_modules\.bin\dsh.cmd" (
  echo [FAIL] Local DSH launcher not found: D:\AI_Research\dsh-run\node_modules\.bin\dsh.cmd
  exit /b 2
)
set "FBAW_DSH_PYTHON=C:\Python314\python.exe"
set "FBAW_DSH_BRIDGE=D:\AI_Research\dsh-run\fbaw_dsh_native_bridge_v4_3c.py"
set "FBAW_DSH_WORKDIR=D:\AI_Research\dsh-run"
set "FBAW_DSH_OUTDIR=fbaw_3Rx4_native_dsh_output"
set "FBAW_CHECKPOINT_CACHE=D:\AI_Research\dsh-run\fbaw_3Rx4_native_dsh_output\v4_2_5_preserved_50db_checkpoint.json"
set "FBAW_GOAL_NOMINAL=0.55"
set "FBAW_GOAL_Q80=0.63"
set "FBAW_GOAL_Q60=0.75"
set "FBAW_GOAL_REJECTION=45"
set "FBAW_DSH_STRESS=1"

echo.
echo DSH MODEL IDENTITY
set "MODEL_TMP=%TEMP%\dsh_model_v4_3c_%RANDOM%.txt"
"%FBAW_DSH_PYTHON%" "D:\AI_Research\dsh-run\detect_dsh_model_v4_3c.py" > "%MODEL_TMP%"
if errorlevel 1 (
  type "%MODEL_TMP%" 2>nul
  del "%MODEL_TMP%" 2>nul
  echo [FAIL] DSH model identity could not be resolved; benchmark not started.
  exit /b 3
)
for /f "usebackq tokens=1,* delims==" %%A in ("%MODEL_TMP%") do (
  if /i "%%A"=="DSH_PROVIDER" set "FBAW_DSH_RESOLVED_PROVIDER=%%B"
  if /i "%%A"=="DSH_MODEL" set "FBAW_DSH_RESOLVED_MODEL=%%B"
  if /i "%%A"=="DSH_MODEL_SOURCE" set "FBAW_DSH_MODEL_SOURCE=%%B"
  if /i "%%A"=="DSH_MODEL_CONFIG" set "FBAW_DSH_MODEL_CONFIG=%%B"
)
del "%MODEL_TMP%" 2>nul
echo   profile      = headless
echo   provider     = !FBAW_DSH_RESOLVED_PROVIDER!
echo   model        = !FBAW_DSH_RESOLVED_MODEL!
echo   source       = !FBAW_DSH_MODEL_SOURCE!
if defined FBAW_DSH_MODEL_CONFIG echo   config       = !FBAW_DSH_MODEL_CONFIG!
echo   NOTE         = resolved configured model; DSH user settings can override defaults.
echo.

call "D:\AI_Research\dsh-run\node_modules\.bin\dsh.cmd" --profile headless --patch "D:\AI_Research\dsh-run\fbaw_native_v4_3c.patch.yml" "You are evaluating an autonomous FBAW engineering agent. The launcher resolved the DSH configured provider/model as !FBAW_DSH_RESOLVED_PROVIDER!/!FBAW_DSH_RESOLVED_MODEL!. Hard goals are: nominal passband ripple <=0.55 dB, Q80_Cp40 ripple <=0.63 dB, Q60_Cp60 ripple <=0.75 dB, and worst far-stop rejection >=45 dB. Use only the registered FBAW engineering tools for engineering actions. Python tool results are authoritative for numerical state, acceptance, rollback, and STOP. Choose the tool sequence autonomously from the verified state returned by the tools. Do not invent S-parameters, component values, margins, or success. If an attempted engineering action is rejected or rolled back, re-plan from the returned verified state. Finish with exactly NATIVE_DSH_FBAW_OK only after Python authorizes engineering STOP. If the task cannot be completed, close the engineering session before giving the failure reason."
set RC=%ERRORLEVEL%
echo.
echo DSH MODEL IDENTITY USED BY LAUNCHER
echo   provider=!FBAW_DSH_RESOLVED_PROVIDER!
echo   model=!FBAW_DSH_RESOLVED_MODEL!
echo EXITCODE=%RC%
exit /b %RC%
