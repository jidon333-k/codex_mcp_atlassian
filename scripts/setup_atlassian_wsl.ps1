param()

$scriptsDirWin = $PSScriptRoot
$projectDirWin = Split-Path -Parent $scriptsDirWin
$projectDirWsl = (wsl.exe wslpath -a "$projectDirWin").Trim()

if (-not $projectDirWsl) {
  throw "WSL 경로 변환에 실패했습니다: $projectDirWin"
}

$bashCmd = "cd '$projectDirWsl' && chmod +x scripts/setup_atlassian_wsl.sh && ./scripts/setup_atlassian_wsl.sh"
wsl.exe bash -lc $bashCmd
