<#
.SYNOPSIS
    GitHub Private Repo Auto-Setup & Project Manager (Windows PowerShell)
    Usage:
      .\Run_Setup.bat
      powershell -ExecutionPolicy Bypass -File .\github_auto_setup.ps1

.DESCRIPTION
    1. Checks and installs Git & GitHub CLI (gh) automatically.
    2. Checks GitHub login status; supports Browser Device Code & Token login.
    3. Mode 1: Create a brand new Private GitHub Repo & auto-push local files/project to GitHub.
    4. Mode 2: Clone/update any existing private/public repo (with 1-click repo list or URL).
    5. Auto-detects project type (Node.js, Python, PHP, Go, Rust, .NET) and installs dependencies.
#>

param(
    [Parameter(Mandatory=$false, HelpMessage="Action to perform: 'create' or 'clone'")]
    [ValidateSet("create", "clone", "")]
    [string]$Action = "",

    [Parameter(Mandatory=$false, HelpMessage="Enter your GitHub Repository URL or owner/repo for clone")]
    [string]$RepoUrl = "",

    [Parameter(Mandatory=$false, HelpMessage="Target directory to clone into or source directory to push")]
    [string]$TargetDir = "",

    [Parameter(Mandatory=$false, HelpMessage="Name for the new private repository (for create mode)")]
    [string]$NewRepoName = ""
)

$ErrorActionPreference = "Continue"

function Write-Step {
    param([string]$Message)
    Write-Host "`n========================================================" -ForegroundColor Cyan
    Write-Host ">>> $Message" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK]   $Message" -ForegroundColor Green
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERR]  $Message" -ForegroundColor Red
}

function Refresh-SessionPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path    = "$machinePath;$userPath"
}

function Test-CommandExists {
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Install-GitWindows {
    Write-Info "Git install nahi hai. Windows par Git automatically install kiya ja raha hai..."
    $hasWinget = Test-CommandExists "winget"
    if ($hasWinget) {
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "winget nahi mila. GitHub se direct installer download ho raha hai..."
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest"
            $asset = $release.assets | Where-Object { $_.name -match "Git-.*-64-bit\.exe$" } | Select-Object -First 1
            if (-not $asset) { throw "Git 64-bit installer nahi mila." }
            $installerPath = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath
            Write-Info "Running silent Git installer..."
            Start-Process -FilePath $installerPath -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP-" -Wait
            Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Err "Git download/install me issue: $($_.Exception.Message)"
        }
    }
    Refresh-SessionPath
    if (-not (Test-CommandExists "git")) {
        $fallbackPaths = @(
            "$env:ProgramFiles\Git\cmd",
            "${env:ProgramFiles(x86)}\Git\cmd",
            "$env:LOCALAPPDATA\Programs\Git\cmd"
        )
        foreach ($p in $fallbackPaths) {
            if (Test-Path "$p\git.exe") {
                $env:Path += ";$p"
                break
            }
        }
    }
    if (Test-CommandExists "git") {
        Write-Success "Git successfully install ho gaya: $(git --version)"
    } else {
        Write-Err "Git install hone ke baad bhi PATH me nahi mila. Setup restart karein."
    }
}

function Install-GhCliWindows {
    Write-Info "GitHub CLI (gh) install nahi hai. Installing GitHub CLI..."
    $hasWinget = Test-CommandExists "winget"
    if ($hasWinget) {
        winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "winget nahi mila. Direct GitHub CLI MSI installer download ho raha hai..."
        try {
            $release = Invoke-RestMethod -Uri "https://api.github.com/repos/cli/cli/releases/latest"
            $asset = $release.assets | Where-Object { $_.name -match "gh_.*_windows_amd64\.msi$" } | Select-Object -First 1
            if (-not $asset) { throw "GitHub CLI MSI asset nahi mila." }
            $msiPath = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $msiPath
            Write-Info "Running GitHub CLI MSI installer..."
            Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$msiPath`" /qn /norestart" -Wait
            Remove-Item $msiPath -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Err "GitHub CLI download/install me issue: $($_.Exception.Message)"
        }
    }
    Refresh-SessionPath
    if (-not (Test-CommandExists "gh")) {
        $fallbackPaths = @(
            "$env:ProgramFiles\GitHub CLI",
            "${env:ProgramFiles(x86)}\GitHub CLI",
            "$env:LOCALAPPDATA\Programs\GitHub CLI"
        )
        foreach ($p in $fallbackPaths) {
            if (Test-Path "$p\gh.exe") {
                $env:Path += ";$p"
                break
            }
        }
    }
    if (Test-CommandExists "gh") {
        Write-Success "GitHub CLI successfully install ho gaya: $(gh --version | Select-Object -First 1)"
    } else {
        Write-Err "GitHub CLI install hone ke baad bhi PATH me nahi mila. Setup restart karein."
    }
}

function Ensure-SmartGitIgnore {
    param([string]$FolderPath)
    $ignorePath = Join-Path $FolderPath ".gitignore"
    $rules = @(
        "# Environment & Secrets",
        ".env",
        ".env.local",
        "*.env",
        "",
        "# Node.js dependencies",
        "node_modules/",
        "npm-debug.log*",
        "yarn-debug.log*",
        "yarn-error.log*",
        "dist/",
        "build/",
        "",
        "# Python virtual env & cache",
        "__pycache__/",
        "*.py[cod]",
        "*$py.class",
        ".venv/",
        "venv/",
        "env/",
        "*.egg-info/",
        "",
        "# PHP / Composer",
        "vendor/",
        "",
        "# OS & Editor temp files",
        ".DS_Store",
        "Thumbs.db",
        ".vscode/",
        ".idea/"
    )

    if (-not (Test-Path $ignorePath)) {
        Write-Info "Standard .gitignore file nahi mili. Auto-generating smart .gitignore..."
        $rules -join "`r`n" | Out-File -FilePath $ignorePath -Encoding utf8
        Write-Success "Created .gitignore (protected .env, node_modules, .venv from accidental push)"
    } else {
        $existing = Get-Content $ignorePath -Raw
        $needsAppend = @()
        if ($existing -notmatch "\.env") { $needsAppend += ".env" }
        if ($existing -notmatch "node_modules") { $needsAppend += "node_modules/" }
        if ($existing -notmatch "\.venv") { $needsAppend += ".venv/" }
        if ($needsAppend.Count -gt 0) {
            "`r`n# Auto-added safeguards`r`n" + ($needsAppend -join "`r`n") | Out-File -FilePath $ignorePath -Append -Encoding utf8
            Write-Success "Updated .gitignore with security safeguards (.env, .venv, node_modules)"
        }
    }
}

function Invoke-ManageDependencies {
    param([string]$ProjectDir)
    Write-Step "Auto-Managing Project Environment & Dependencies"
    Push-Location $ProjectDir

    # 1. Environment file setup (.env.example -> .env)
    if (-not (Test-Path ".env")) {
        foreach ($envTemplate in @(".env.example", ".env.sample", ".env.template")) {
            if (Test-Path $envTemplate) {
                Copy-Item $envTemplate ".env" -Force
                Write-Success "Created .env automatically from $envTemplate"
                break
            }
        }
    }

    $managedAny = $false

    # 2. Node.js Project
    if (Test-Path "package.json") {
        $managedAny = $true
        Write-Info "Node.js project detected (package.json found)."
        if (-not (Test-CommandExists "node")) {
            Write-Info "Node.js installed nahi hai. Installing Node.js LTS via winget..."
            if (Test-CommandExists "winget") {
                winget install --id OpenJS.NodeJS.LTS -e --source winget --accept-package-agreements --accept-source-agreements
                Refresh-SessionPath
            }
        }
        if (Test-CommandExists "node") {
            if ((Test-Path "pnpm-lock.yaml") -and (Test-CommandExists "pnpm")) {
                Write-Info "Running 'pnpm install'..."
                pnpm install
            } elseif ((Test-Path "yarn.lock") -and (Test-CommandExists "yarn")) {
                Write-Info "Running 'yarn install'..."
                yarn install
            } elseif ((Test-Path "bun.lockb") -and (Test-CommandExists "bun")) {
                Write-Info "Running 'bun install'..."
                bun install
            } else {
                Write-Info "Running 'npm install'..."
                npm install
            }
            Write-Success "Node.js dependencies installed!"
        }
    }

    # 3. Python Project
    if ((Test-Path "requirements.txt") -or (Test-Path "pyproject.toml") -or (Test-Path "Pipfile")) {
        $managedAny = $true
        Write-Info "Python project detected."
        if (-not (Test-CommandExists "python")) {
            Write-Info "Python installed nahi hai. Installing Python 3 via winget..."
            if (Test-CommandExists "winget") {
                winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
                Refresh-SessionPath
            }
        }
        if (Test-CommandExists "python") {
            if (-not (Test-Path ".venv")) {
                Write-Info "Creating Python virtual environment (.venv)..."
                python -m venv .venv
            }
            $venvPip = ".\.venv\Scripts\pip.exe"
            $venvPy  = ".\.venv\Scripts\python.exe"
            if (Test-Path $venvPy) {
                Write-Info "Virtual environment ready. Installing packages..."
                if (Test-Path "requirements.txt") {
                    & $venvPip install -r requirements.txt
                } elseif (Test-Path "pyproject.toml") {
                    & $venvPip install -e .
                }
                Write-Success "Python virtual environment (.venv) and dependencies are ready!"
            }
        }
    }

    # 4. PHP / Composer
    if (Test-Path "composer.json") {
        $managedAny = $true
        Write-Info "PHP Composer project detected."
        if (Test-CommandExists "composer") {
            composer install --no-interaction
            Write-Success "Composer dependencies installed!"
        }
    }

    # 5. Go Project
    if (Test-Path "go.mod") {
        $managedAny = $true
        Write-Info "Go project detected."
        if (Test-CommandExists "go") {
            go mod download
            go mod tidy
            Write-Success "Go modules downloaded and tidied!"
        }
    }

    # 6. Rust Project
    if (Test-Path "Cargo.toml") {
        $managedAny = $true
        Write-Info "Rust project detected."
        if (Test-CommandExists "cargo") {
            cargo fetch
            Write-Success "Rust crates fetched!"
        }
    }

    # 7. .NET Project
    $dotnetFiles = Get-ChildItem -Path . -Filter "*.sln" -File -ErrorAction SilentlyContinue
    if (-not $dotnetFiles) {
        $dotnetFiles = Get-ChildItem -Path . -Filter "*.csproj" -File -ErrorAction SilentlyContinue
    }
    if ($dotnetFiles) {
        $managedAny = $true
        Write-Info ".NET project detected."
        if (Test-CommandExists "dotnet") {
            dotnet restore
            Write-Success ".NET packages restored!"
        }
    }

    # 8. Git Submodules
    if (Test-Path ".gitmodules") {
        $managedAny = $true
        Write-Info "Initializing Git submodules..."
        git submodule update --init --recursive
        Write-Success "Git submodules updated!"
    }

    if (-not $managedAny) {
        Write-Info "Koi extra dependency file nahi mili. Project tayyar hai."
    }

    Pop-Location
}

# ==============================================================================
# FUNCTION: Create New Private Repo & Push Local Code
# ==============================================================================
function Invoke-CreateAndPushRepo {
    param(
        [string]$SourceFolder = "",
        [string]$RepoName = ""
    )

    Write-Step "Nayi Private Repository Banayein & Code Push Karein"

    # 1. Source Folder Selection
    if ([string]::IsNullOrWhiteSpace($SourceFolder)) {
        $defaultSource = (Get-Location).Path
        Write-Host "Kaunsa local project folder GitHub par push karna chahte hain?" -ForegroundColor Cyan
        Write-Host "  [Default Folder]: $defaultSource" -ForegroundColor Green
        $inputFolder = Read-Host "Folder path dalein (Enter dabayein default folder ke liye)"
        if ([string]::IsNullOrWhiteSpace($inputFolder)) {
            $SourceFolder = $defaultSource
        } else {
            $SourceFolder = $inputFolder.Trim(" '`"`t`r`n")
        }
    }

    if (-not (Test-Path $SourceFolder)) {
        Write-Err "Folder '$SourceFolder' nahi mila! Kripya path check karein."
        return
    }

    Push-Location $SourceFolder
    Write-Success "Source folder set: $SourceFolder"

    # 2. Suggested Repo Name
    if ([string]::IsNullOrWhiteSpace($RepoName)) {
        $folderLeaf = Split-Path $SourceFolder -Leaf
        $sanitizedDefault = ($folderLeaf -replace "[^a-zA-Z0-9_\-\.]", "-").ToLower()
        Write-Host ""
        Write-Host "Nayi GitHub Repository ka naam dalein:" -ForegroundColor Cyan
        Write-Host "  [Default Name]: $sanitizedDefault" -ForegroundColor Green
        $inputRepo = Read-Host "Repo name (Enter dabayein '$sanitizedDefault' ke liye)"
        if ([string]::IsNullOrWhiteSpace($inputRepo)) {
            $RepoName = $sanitizedDefault
        } else {
            $RepoName = ($inputRepo.Trim(" '`"`t`r`n") -replace "[^a-zA-Z0-9_\-\.]", "-")
        }
    }

    # 3. Visibility (Default = Private)
    Write-Host ""
    Write-Host "Repository Visibility chunein:" -ForegroundColor Cyan
    Write-Host "  [1] Private (Sirf aapke liye, bilkul mehfooz) [DEFAULT]" -ForegroundColor Green
    Write-Host "  [2] Public (Koi bhi dekh sakta hai)" -ForegroundColor Yellow
    $visChoice = Read-Host "Option select karein (1 ya 2, default = 1)"
    $visibilityFlag = if ($visChoice -eq "2") { "--public" } else { "--private" }

    # 4. Description (Optional)
    $repoDesc = Read-Host "Repository Description (Optional, press Enter to skip)"

    # 5. Smart .gitignore Safeguard
    Ensure-SmartGitIgnore -FolderPath $SourceFolder

    # 6. Initialize Git if needed
    if (-not (Test-Path ".git")) {
        Write-Info "Git repository initialize ki ja rahi hai..."
        git init -b main 2>$null
        if ($LASTEXITCODE -ne 0) {
            git init
            git branch -M main
        }
        Write-Success "Git initialized with branch 'main'."
    } else {
        git branch -M main 2>$null
    }

    # 7. Stage & Commit
    Write-Info "Staging files (git add .)..."
    git add -A

    $gitStatus = (git status --porcelain 2>$null)
    $hasCommits = (git rev-parse HEAD 2>$null)

    if ($gitStatus) {
        $commitMsg = Read-Host "Commit message dalein (default = 'Initial commit')"
        if ([string]::IsNullOrWhiteSpace($commitMsg)) {
            $commitMsg = "Initial commit"
        }
        git commit -m "$commitMsg"
        Write-Success "Local commit ready: '$commitMsg'"
    } elseif (-not $hasCommits) {
        if (-not (Test-Path "README.md")) {
            "# $RepoName`n`nCreated with GitHub Auto-Setup." | Out-File "README.md" -Encoding utf8
            git add "README.md"
        }
        git commit -m "Initial commit"
        Write-Success "Initial commit created."
    } else {
        Write-Info "Koi naye uncommitted changes nahi hain. Existing commit push kiya jayega."
    }

    # 8. Check GitHub User & Existing Remote
    $ghUser = (gh api user --jq .login 2>$null)
    if ([string]::IsNullOrWhiteSpace($ghUser)) {
        $ghUser = "current-user"
    }

    Write-Info "GitHub par '$RepoName' repository banayi ja rahi hai..."

    # Check if remote 'origin' already exists
    $existingRemote = (git remote get-url origin 2>$null)
    $createArgs = @("repo", "create", $RepoName, $visibilityFlag)
    if (-not [string]::IsNullOrWhiteSpace($repoDesc)) {
        $createArgs += @("--description", $repoDesc)
    }

    if ([string]::IsNullOrWhiteSpace($existingRemote)) {
        # Can use direct --source and --push
        $createArgs += @("--source", ".", "--remote", "origin", "--push")
        & gh @createArgs
    } else {
        # Remote already configured in local folder; create repo on GH then update remote
        & gh @createArgs
        git remote set-url origin "https://github.com/$ghUser/$RepoName.git"
        Write-Info "Pushing data to GitHub (git push -u origin main)..."
        git push -u origin main
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host ">>> KAMIYABI! Nayi Private Repository Ban Gayi!" -ForegroundColor Green
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host "Repository URL : https://github.com/$ghUser/$RepoName" -ForegroundColor Cyan
        Write-Host "Clone URL      : https://github.com/$ghUser/$RepoName.git" -ForegroundColor Cyan
        Write-Host "Visibility     : $(if ($visibilityFlag -eq '--public') { 'Public' } else { 'Private' })" -ForegroundColor Green
        Write-Host "Branch         : main" -ForegroundColor Green
        Write-Host "Local Folder   : $SourceFolder" -ForegroundColor Green
        Write-Host ""

        $openBrowser = Read-Host "Kya aap is repo ko Web Browser me kholna chahte hain? (Y/N, default = Y)"
        if ([string]::IsNullOrWhiteSpace($openBrowser) -or $openBrowser -match "^[Yy]$") {
            Start-Process "https://github.com/$ghUser/$RepoName"
        }

        $openCode = Read-Host "Kya aap is project ko VS Code me kholna chahte hain? (Y/N, default = Y)"
        if (([string]::IsNullOrWhiteSpace($openCode) -or $openCode -match "^[Yy]$") -and (Test-CommandExists "code")) {
            code $SourceFolder
        }
    } else {
        Write-Err "Repository create ya push me masla aaya. Check karein ki repo name '$RepoName' pehle se maujood to nahi hai."
    }

    Pop-Location
}

# ==============================================================================
# FUNCTION: Clone or Download Existing Repository
# ==============================================================================
function Invoke-CloneAndSetupRepo {
    param(
        [string]$CloneUrl = "",
        [string]$DestinationDir = ""
    )

    Write-Step "Existing Repository Clone / Update Karein"

    if ([string]::IsNullOrWhiteSpace($CloneUrl)) {
        # Fetch user's recent repositories
        $userRepos = @()
        try {
            $reposJson = gh repo list --limit 15 --json nameWithOwner,isPrivate,description 2>$null
            if ($reposJson) {
                $userRepos = $reposJson | ConvertFrom-Json
            }
        } catch {
            $userRepos = @()
        }

        if ($userRepos -and $userRepos.Count -gt 0) {
            Write-Host "Aapke GitHub account ke recent repositories:" -ForegroundColor Green
            for ($i = 0; $i -lt $userRepos.Count; $i++) {
                $r = $userRepos[$i]
                $typeTag = if ($r.isPrivate) { "[Private]" } else { "[Public]" }
                $desc = if ($r.description) { " - $($r.description)" } else { "" }
                if ($desc.Length -gt 45) { $desc = $desc.Substring(0, 42) + "..." }
                $color = if ($r.isPrivate) { "Cyan" } else { "Gray" }
                Write-Host ("  [{0,2}] {1,-10} {2}{3}" -f ($i + 1), $typeTag, $r.nameWithOwner, $desc) -ForegroundColor $color
            }
            Write-Host "  [ 0] Manually enter URL / repo name" -ForegroundColor Yellow
            Write-Host ""
            $selection = Read-Host "Select repo number (1-$($userRepos.Count)) ya URL paste karein (default = 1)"

            if ([string]::IsNullOrWhiteSpace($selection)) {
                $CloneUrl = $userRepos[0].nameWithOwner
            } elseif ($selection -match "^\d+$" -and [int]$selection -ge 1 -and [int]$selection -le $userRepos.Count) {
                $CloneUrl = $userRepos[[int]$selection - 1].nameWithOwner
            } elseif ($selection -eq "0") {
                $CloneUrl = Read-Host "Apna GitHub Repository URL ya owner/repo dalein"
            } else {
                $CloneUrl = $selection
            }
        } else {
            $CloneUrl = Read-Host "Apna GitHub Repository URL ya owner/repo dalein (e.g. username/repo ya https://github.com/username/repo.git)"
        }
    }

    # Sanitize input
    $CloneUrl = $CloneUrl.Trim(" '`"`t`r`n")
    while ([string]::IsNullOrWhiteSpace($CloneUrl)) {
        $CloneUrl = Read-Host "Repository URL khali nahi ho sakta. Dobara dalein"
        $CloneUrl = $CloneUrl.Trim(" '`"`t`r`n")
    }

    Write-Success "Target Repository: $CloneUrl"

    # Extract repo name safely
    $cleanUrl = $CloneUrl -replace "\.git$", ""
    $cleanUrl = $cleanUrl.TrimEnd("/")
    $repoName = ($cleanUrl -split "[/:]")[-1]

    if ([string]::IsNullOrWhiteSpace($DestinationDir)) {
        $defaultDir = Join-Path (Get-Location).Path $repoName
        Write-Host "Project folder path: $defaultDir" -ForegroundColor Cyan
        $customDir = Read-Host "Kisi aur folder me clone karna hai? (Enter dabayein default ke liye, ya folder path dalein)"
        if ([string]::IsNullOrWhiteSpace($customDir)) {
            $DestinationDir = $defaultDir
        } else {
            $DestinationDir = $customDir.Trim(" '`"`t`r`n")
        }
    }

    # If folder already exists
    if (Test-Path (Join-Path $DestinationDir ".git")) {
        Write-Info "Folder '$DestinationDir' pehle se maujood hai."
        Write-Host "  [1] Pull latest changes (git pull) [DEFAULT]" -ForegroundColor Green
        Write-Host "  [2] Naye folder me clone karein" -ForegroundColor Yellow
        $existChoice = Read-Host "Option chunein (1 ya 2, default = 1)"
        if ($existChoice -eq "2") {
            $newFolder = Read-Host "Naye folder ka naam ya path dalein"
            if (-not [string]::IsNullOrWhiteSpace($newFolder)) {
                $DestinationDir = $newFolder.Trim(" '`"`t`r`n")
            }
        }
    }

    if (Test-Path (Join-Path $DestinationDir ".git")) {
        Write-Info "Pulling latest changes in '$DestinationDir'..."
        Push-Location $DestinationDir
        git fetch --all
        git pull
    } else {
        Write-Info "Cloning repository into '$DestinationDir'..."
        gh repo clone $CloneUrl $DestinationDir
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Clone fail hua. Checking direct git clone fallback..."
            git clone $CloneUrl $DestinationDir
            if ($LASTEXITCODE -ne 0) {
                Write-Err "Repository download nahi ho payi. Check karein ki URL sahi hai aur aapke account ko access hai."
                return
            }
        }
        Push-Location $DestinationDir
    }

    Write-Success "Repository ready at: $DestinationDir"

    # Auto-detect dependencies
    Invoke-ManageDependencies -ProjectDir $DestinationDir

    Pop-Location

    Write-Step "All Done! Project Setup Complete"
    Write-Host "Project Location: $DestinationDir" -ForegroundColor Green
    Write-Host ""

    if (Test-CommandExists "code") {
        $openCode = Read-Host "Kya aap is project ko VS Code me kholna chahte hain? (Y/N, default = Y)"
        if ([string]::IsNullOrWhiteSpace($openCode) -or $openCode -match "^[Yy]$") {
            Write-Info "Opening in VS Code..."
            code $DestinationDir
        }
    }

    $openExplorer = Read-Host "Folder ko Windows Explorer me kholna hai? (Y/N, default = N)"
    if ($openExplorer -match "^[Yy]$") {
        Start-Process "explorer.exe" -ArgumentList "`"$DestinationDir`""
    }
}

# ==============================================================================
# MAIN EXECUTION FLOW
# ==============================================================================

# STEP 1: Requirements Check (Git + GitHub CLI)
Write-Step "1. Checking Windows Requirements (Git & GitHub CLI)"
Refresh-SessionPath

if (Test-CommandExists "git") {
    Write-Success "Git already installed: $(git --version)"
} else {
    Install-GitWindows
}

if (Test-CommandExists "gh") {
    Write-Success "GitHub CLI already installed: $(gh --version | Select-Object -First 1)"
} else {
    Install-GhCliWindows
}

# STEP 2: Authentication Check
Write-Step "2. Checking GitHub Authentication Status"

$isLoggedIn = $false
try {
    $null = gh auth status 2>&1
    if ($LASTEXITCODE -eq 0) {
        $isLoggedIn = $true
    }
} catch {
    $isLoggedIn = $false
}

if ($isLoggedIn) {
    Write-Success "Aap pehle se GitHub par logged in hain!"
    gh auth status
} else {
    Write-Info "Aapka GitHub abhi logged in nahi hai."
    Write-Host ""
    Write-Host "Login karne ka tareeqa chunein:" -ForegroundColor Cyan
    Write-Host "  [1] Browser Login (Quick Code) - Terminal par 8-digit code aayega, Browser me enter karein [DEFAULT]" -ForegroundColor Green
    Write-Host "  [2] Personal Access Token (PAT) - Token paste karke login karein" -ForegroundColor Yellow
    Write-Host ""
    $loginChoice = Read-Host "Option select karein (1 ya 2, default = 1)"

    if ($loginChoice -eq "2") {
        Write-Info "Token Login mode..."
        $pat = Read-Host "Apna GitHub Personal Access Token (repo scope ke sath) paste karein"
        if (-not [string]::IsNullOrWhiteSpace($pat)) {
            $pat.Trim() | gh auth login --hostname github.com --with-token
        }
    } else {
        Write-Info "Browser Login shuru ho raha hai..."
        Write-Host "1. Neeche 8-digit One-Time Code aayega, use copy karein." -ForegroundColor Magenta
        Write-Host "2. Enter dabayein, Browser open hoga: https://github.com/login/device" -ForegroundColor Magenta
        Write-Host "3. Code enter karke Authorize karein." -ForegroundColor Magenta
        gh auth login --hostname github.com --git-protocol https --web --scopes "repo,read:org,workflow"
    }

    # Verify login succeeded
    $null = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "GitHub login pura nahi hua. Kripya dobara koshish karein."
        Read-Host "Press Enter to exit..."
        exit 1
    }
    Write-Success "GitHub Login successful!"
}

# Configure Git credential helper automatically
Write-Info "Configuring Git to use GitHub CLI credentials automatically..."
gh auth setup-git 2>$null

# Auto-configure git user.name & email if not set
$gitUser = (git config --global user.name 2>$null)
if ([string]::IsNullOrWhiteSpace($gitUser)) {
    try {
        $ghUserRaw = gh api user 2>$null
        if ($ghUserRaw) {
            $ghUserJson = $ghUserRaw | ConvertFrom-Json
            if ($ghUserJson.login) {
                git config --global user.name $ghUserJson.login
                $emailToSet = if ($ghUserJson.email) { $ghUserJson.email } else { "$($ghUserJson.id)+$($ghUserJson.login)@users.noreply.github.com" }
                git config --global user.email $emailToSet
                Write-Success "Git user.name ($($ghUserJson.login)) and user.email configured."
            }
        }
    } catch {
        # Non-fatal
    }
}

# STEP 3: Main Action Selection (Create & Push OR Clone)
if ([string]::IsNullOrWhiteSpace($Action)) {
    if (-not [string]::IsNullOrWhiteSpace($RepoUrl)) {
        $Action = "clone"
    } else {
        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Magenta
        Write-Host ">>> Main Menu - Aap kya karna chahte hain?" -ForegroundColor Magenta
        Write-Host "========================================================" -ForegroundColor Magenta
        Write-Host "  [1] Nayi Private Repo banayein & apna Project/Data Push karein [CREATE & PUSH]" -ForegroundColor Green
        Write-Host "  [2] Maujooda Repo clone / download karein (1-Click List ya URL) [CLONE]" -ForegroundColor Cyan
        Write-Host ""
        $userAction = Read-Host "Option chunein (1 ya 2, default = 1)"
        if ($userAction -eq "2") {
            $Action = "clone"
        } else {
            $Action = "create"
        }
    }
}

if ($Action -eq "create") {
    Invoke-CreateAndPushRepo -SourceFolder $TargetDir -RepoName $NewRepoName
} else {
    Invoke-CloneAndSetupRepo -CloneUrl $RepoUrl -DestinationDir $TargetDir
}

Write-Host "`nAll operations finished!" -ForegroundColor Green
Read-Host "Press Enter to exit..."
