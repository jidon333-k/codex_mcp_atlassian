param()

$scriptsDirWin = $PSScriptRoot
$codexDirWin = Split-Path -Parent $scriptsDirWin
$projectDirWin = Split-Path -Parent $codexDirWin
$projectDirWsl = (wsl.exe wslpath -a "$projectDirWin").Trim()

if (-not $projectDirWsl) {
  throw "WSL 경로 변환에 실패했습니다: $projectDirWin"
}

$bashCmd = "cd '$projectDirWsl' && chmod +x scripts/codex/install_skill.sh && ./scripts/codex/install_skill.sh"
wsl.exe bash -lc $bashCmd
