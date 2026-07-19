@echo off
rem VODCutter entry point. Models cache inside the install dir; the nvidia
rem PATH prepend only fires when the GPU component was installed.
set "HF_HOME=%~dp0models"
if exist "%~dp0python\Lib\site-packages\nvidia\cudnn\bin" (
  set "PATH=%~dp0python\Lib\site-packages\nvidia\cudnn\bin;%~dp0python\Lib\site-packages\nvidia\cublas\bin;%PATH%"
)
"%~dp0python\python.exe" -m cutter %*
