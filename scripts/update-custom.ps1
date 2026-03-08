[CmdletBinding()]
param(
    [string]$CustomBranch = "justin-custom",
    [string]$UpstreamRemote = "upstream",
    [string]$UpstreamBranch = "main",
    [switch]$Autostash,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Git {
    param([string[]]$GitArgs)
    Write-Host ">> git $($GitArgs -join ' ')"
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $($GitArgs -join ' ')"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git was not found on PATH."
}

$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    throw "This script must run inside a git repository."
}
$repoRoot = $repoRoot.Trim()
Set-Location $repoRoot

$remoteNames = @(& git remote)
if (-not ($remoteNames -contains $UpstreamRemote)) {
    $originUrl = (& git remote get-url origin 2>$null)
    if (-not $originUrl) {
        throw "Missing '$UpstreamRemote' remote and could not infer URL from origin."
    }
    $originUrl = $originUrl.Trim()
    Invoke-Git -GitArgs @("remote", "add", $UpstreamRemote, $originUrl)
    Write-Host "Added '$UpstreamRemote' remote -> $originUrl"
}

$status = @(& git status --porcelain)
if ($status.Count -gt 0 -and -not $Autostash) {
    throw "Working tree has uncommitted changes. Commit/stash first, or rerun with -Autostash."
}

$currentBranch = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($currentBranch -ne $CustomBranch) {
    & git show-ref --verify --quiet "refs/heads/$CustomBranch"
    $branchExists = ($LASTEXITCODE -eq 0)
    if ($branchExists) {
        Invoke-Git -GitArgs @("checkout", $CustomBranch)
    } else {
        Invoke-Git -GitArgs @("checkout", "-b", $CustomBranch)
    }
}

Invoke-Git -GitArgs @("fetch", $UpstreamRemote)

$rebaseArgs = @("rebase", "$UpstreamRemote/$UpstreamBranch")
if ($Autostash) {
    $rebaseArgs += "--autostash"
}
Invoke-Git -GitArgs $rebaseArgs

if (-not $SkipInstall) {
    Write-Host ">> pip install -e ."
    & pip install -e .
    if ($LASTEXITCODE -ne 0) {
        throw "pip install -e . failed."
    }
}

Write-Host "Update complete on branch '$CustomBranch' from '$UpstreamRemote/$UpstreamBranch'."
