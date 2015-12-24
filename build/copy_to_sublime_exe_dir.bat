
echo SUBLIME_PLUGIN_DIR=%SUBLIME_PLUGIN_DIR%
echo 1: %1
echo 2: %2
ROBOCOPY %1\src %2 /MIR
ROBOCOPY %1\data %2\data /MIR
dir