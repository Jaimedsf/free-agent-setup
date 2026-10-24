# free-agent-setup bootstrap for Windows.
# Usage: irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
# Pass options with:  $env:FREEAGENT_ARGS = "--dry-run"
$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/Jaimedsf/free-agent-setup/archive/refs/heads/main.zip'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv (https://astral.sh/uv) ...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

$here = if ($PSScriptRoot) { $PSScriptRoot } else { $null }
if ($here -and (Select-String -Path (Join-Path $here 'pyproject.toml') -Pattern 'name = "freeagent"' -Quiet -ErrorAction SilentlyContinue)) {
    $project = $here
} else {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("freeagent-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'src.zip'
    Invoke-WebRequest -Uri $repo -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp
    $project = (Get-ChildItem -Path $tmp -Directory | Select-Object -First 1).FullName
}

$extra = if ($env:FREEAGENT_ARGS) { $env:FREEAGENT_ARGS -split '\s+' | Where-Object { $_ } } else { @() }
& uv run --quiet --project $project python -m freeagent @extra
exit $LASTEXITCODE
