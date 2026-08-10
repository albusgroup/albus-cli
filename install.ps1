# Install the Albus CLI (albus) from PyPI.
# Prefers uv, then pip --user, then pip inside a conda env.
# Usage:
#   irm https://raw.githubusercontent.com/albusgroup/albus-cli/main/install.ps1 | iex
# Optional:
#   $env:ALBUS_CLI_VERSION = "0.1.0"

$ErrorActionPreference = "Stop"

$Package = "albus-cli"
$Version = $env:ALBUS_CLI_VERSION
if ([string]::IsNullOrEmpty($Version)) {
    $Spec = $Package
} else {
    $Spec = "$Package==$Version"
}

function Test-Command($Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PipCommand {
    if (Test-Command "py") {
        try {
            & py -m pip --version | Out-Null
            if ($LASTEXITCODE -eq 0) { return @("py", "-m", "pip") }
        } catch {}
    }
    if (Test-Command "python") {
        try {
            & python -m pip --version | Out-Null
            if ($LASTEXITCODE -eq 0) { return @("python", "-m", "pip") }
        } catch {}
    }
    if (Test-Command "python3") {
        try {
            & python3 -m pip --version | Out-Null
            if ($LASTEXITCODE -eq 0) { return @("python3", "-m", "pip") }
        } catch {}
    }
    return $null
}

function Install-WithUv {
    Write-Host "Installing $Spec with uv tool install..."
    & uv tool install $Spec
    if ($LASTEXITCODE -ne 0) { throw "uv tool install failed" }
    Write-Host "Installed with uv. Ensure the uv tool bin directory is on PATH."
}

function Install-WithPip {
    $pip = Get-PipCommand
    if ($null -eq $pip) { return $false }
    Write-Host "Installing $Spec with $($pip -join ' ') --user..."
    & $pip[0] $pip[1..($pip.Length - 1)] install --user $Spec
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Write-Host "Installed with pip --user. Ensure your user Scripts directory is on PATH."
    return $true
}

function Install-WithConda {
    if (-not (Test-Command "conda")) { return $false }

    if (-not [string]::IsNullOrEmpty($env:CONDA_PREFIX)) {
        $envPython = Join-Path $env:CONDA_PREFIX "python.exe"
        $envLabel = $env:CONDA_PREFIX
    } else {
        $base = (& conda info --base).Trim()
        $envPython = Join-Path $base "python.exe"
        $envLabel = $base
    }

    if (-not (Test-Path $envPython)) {
        throw "conda found but Python is missing at $envPython"
    }

    try {
        & $envPython -m pip --version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pip missing" }
    } catch {
        Write-Host "pip missing in conda env; installing pip via conda..."
        & conda install -y pip
        if ($LASTEXITCODE -ne 0) { throw "conda install pip failed" }
    }

    Write-Host "Installing $Spec with pip into conda env ($envLabel)..."
    & $envPython -m pip install $Spec
    if ($LASTEXITCODE -ne 0) { throw "conda env pip install failed" }
    Write-Host "Installed into the conda env. Activate that env to run albus."
    return $true
}

if (Test-Command "uv") {
    Install-WithUv
} elseif (Install-WithPip) {
    # done
} elseif (Install-WithConda) {
    # done
} else {
    throw "need uv, pip, or conda on PATH. Install one of them, then re-run."
}

if (Test-Command "albus") {
    Write-Host "Running: albus --help"
    & albus --help
} else {
    Write-Host "albus is installed but not on PATH yet. Open a new shell or add the scripts directory to PATH, then run: albus --help"
}

Write-Host "Set ALBUS_API_KEY before calling the API."
