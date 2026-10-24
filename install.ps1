# free-agent-setup bootstrap for Windows.
# Usage: irm https://raw.githubusercontent.com/Jaimedsf/free-agent-setup/main/install.ps1 | iex
# Pass options with:  $env:FREEAGENT_ARGS = "--dry-run"   (use a local clone: $env:FREEAGENT_SRC = <folder>)
# Runs in a script block so `irm | iex` neither closes the window nor leaks settings into the session.
& {
    $ErrorActionPreference = 'Stop'
    $repo = 'https://github.com/Jaimedsf/free-agent-setup/archive/refs/heads/main.zip'

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Installing uv (https://astral.sh/uv) ...'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }

    $here = if ($env:FREEAGENT_SRC) { $env:FREEAGENT_SRC } else { $PSScriptRoot }
    $toml = if ($here) { Join-Path $here 'pyproject.toml' } else { $null }
    if ($toml -and (Select-String -Path $toml -Pattern 'name = "freeagent"' -Quiet -ErrorAction SilentlyContinue)) {
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
    $global:LASTEXITCODE = $LASTEXITCODE
}
if ($PSScriptRoot -and $MyInvocation.InvocationName -ne '&') { exit $global:LASTEXITCODE }
