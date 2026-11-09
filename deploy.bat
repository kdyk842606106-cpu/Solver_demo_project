@echo off
setlocal DisableDelayedExpansion
set "PLANNER_FROM_DEPLOY=1"
"%~dp0start-workbench.cmd" %*
