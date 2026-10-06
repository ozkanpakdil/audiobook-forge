<#
.SYNOPSIS
    Build every book's text and turn it into MP3 files on Windows.

.DESCRIPTION
    Windows counterpart of scripts/make_all_audio.sh. It checks (and, if you let
    it, installs) what the pipeline needs, rebuilds each book's text from its
    chapter files, and converts it with a speech engine found on the machine.

    Speech engines, in the order the converter prefers them:
      piper   neural voices, the default                 pip install piper-tts
      kokoro  very natural voices, no torch needed       pip install kokoro-onnx
      melotts accented English, including EN-INDIA       from GitHub, needs torch
      sapi    Windows System.Speech through PowerShell   nothing to install
      espeak  espeak-ng, robotic but light               install separately

    Models are downloaded on first use: piper about 60 MB per voice,
    kokoro about 340 MB once.

    The pipeline needs no third-party Python packages at all: it is standard
    library only, plus ffmpeg.

.PARAMETER Book
    it, tropical, equipment, diagnosis or all. Default: all. May be repeated.

.PARAMETER Engine
    sapi, espeak or piper. Default: the best available.

.EXAMPLE
    .\scripts\make_all_audio.ps1 -Book equipment
    .\scripts\make_all_audio.ps1 -DryRun
    .\scripts\make_all_audio.ps1 -Engine piper -PiperModel C:\voices\en_US-lessac-medium.onnx
    .\scripts\make_all_audio.ps1 -ListVoices
#>
[CmdletBinding()]
param(
    [ValidateSet('it', 'tropical', 'equipment', 'diagnosis', 'all')]
    [string[]]$Book = @('all'),

    [ValidateSet('', 'piper', 'kokoro', 'melotts', 'sapi', 'espeak')]
    [string]$Engine = '',

    [string]$PiperModel = '',
    [string]$PiperDir = '',

    [int]$Jobs = 0,
    [string]$Voice = '',
    [int]$Rate = 0,
    [string]$Bitrate = '',
    [string]$Out = '',
    [string]$Only = '',

    [switch]$Force,
    [switch]$NoSingle,
    [switch]$NoBuild,
    [switch]$DryRun,
    [switch]$PruneCache,
    [switch]$ListVoices,
    [switch]$PreviewVoices,
    [switch]$NoPrompt,
    [switch]$ResetVoice,
    [switch]$SkipInstall,
    [switch]$WithPip,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Acronyms each English book tolerates as spoken short forms (see their PLAN.md).
$TropicalAcronyms = 'CT,MRI,ECG,EEG'
$EquipmentAcronyms = 'CT,MRI,ECG,EEG,EMG,PET,DEXA,PACS,ICU,PPE,CPR,AED,CPAP,BIPAP,PICC,PCA,CRRT,CSSD,UPS,HVAC,EHR,ISO,IEC,FDA,MSF,VHF,UHF,USB,LED,LCD,PVC,PTFE,RFID,GPS,SIM,AI,DICOM,HL7,BF,CF,ENT'
$DiagnosisAcronyms = 'CT,MRI,ECG,ENT,ICU,CPR,PPE'

function Write-Info { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "  ok $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Warning $Message }
function Write-Die  { param([string]$Message) Write-Host "error: $Message" -ForegroundColor Red; exit 1 }

function Confirm-Action {
    param([string]$Question)
    if ($Yes) { return $true }
    $answer = Read-Host "$Question [y/N]"
    return ($answer -eq 'y' -or $answer -eq 'Y')
}

# --------------------------------------------------------------- environment
if (-not ($env:OS -eq 'Windows_NT')) {
    Write-Warn "this script targets Windows; on macOS or Linux use scripts/make_all_audio.sh"
}

$pythonExe = $null
$pythonPre = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = 'py'; $pythonPre = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = 'python'
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonExe = 'python3'
}
if (-not $pythonExe) {
    Write-Die @"
python3 not found. Install Python 3.8 or newer first, for example:
  winget install --id Python.Python.3.12 -e
"@
}

# Windows ships a stub "python" that opens the Microsoft Store: make sure the
# interpreter really runs before using it for anything else.
$version = & $pythonExe @pythonPre -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
if ($LASTEXITCODE -ne 0 -or -not $version) {
    Write-Die "the '$pythonExe' command did not run. Disable the Microsoft Store python stub, or install Python from python.org."
}
$major, $minor = $version.Split('.')[0..1]
if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 8)) {
    Write-Die "Python $version is too old: version 3.8 or newer is required."
}
Write-Ok "Python $version ($pythonExe)"

function Test-PythonModule {
    param([string]$Name)
    & $pythonExe @pythonPre -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$Name') else 1)" | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# The pipeline must run with no third-party packages at all. Running each entry
# point with --help proves every import resolves; that is the whole check.
foreach ($script in @('scripts/txt2mp3.py', 'scripts/build_book.py', 'scripts/build_book_en.py')) {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $pythonExe @pythonPre $script --help | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Die "$script does not run: fix the Python environment before continuing" }
}
Write-Ok "pipeline scripts run (standard library only, no pip packages needed)"

if ($WithPip) {
    if (Test-Path 'requirements.txt') {
        Write-Info 'pip install -r requirements.txt (documented no-op)'
        & $pythonExe @pythonPre -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Write-Warn 'the pip step failed, but it is not required' }
    } else {
        Write-Warn 'requirements.txt not found; skipping -WithPip'
    }
}

function Install-Component {
    param([string]$Component)
    if ($SkipInstall) { Write-Die "$Component is missing, and -SkipInstall was given" }
    $cmd = $null
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $cmd = @('winget', 'install', '--id', 'Gyan.FFmpeg', '-e', '--accept-source-agreements', '--accept-package-agreements')
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        $cmd = @('choco', 'install', 'ffmpeg', '-y')
    } elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
        $cmd = @('scoop', 'install', 'ffmpeg')
    }
    if (-not $cmd) {
        Write-Die @"
$Component is missing, and no installer was found.
Install it by hand and re-run:
  winget install --id Gyan.FFmpeg -e
"@
    }
    Write-Info "missing: $Component"
    if (Confirm-Action ("Run this now?  " + ($cmd -join ' '))) {
        & $cmd[0] $cmd[1..($cmd.Count - 1)]
        if ($LASTEXITCODE -ne 0) { Write-Die "$Component installation failed" }
    } else {
        Write-Die "$Component is missing"
    }
}

# Engine-specific checks.
$engineArgs = @()
if ($Engine) { $engineArgs += @('--engine', $Engine) }
if ($PiperModel) { $engineArgs += @('--piper-model', $PiperModel) }
if ($PiperDir) { $engineArgs += @('--piper-dir', $PiperDir) }

if ($ListVoices) {
    Write-Info 'speech engines on this machine'
    & $pythonExe @pythonPre 'scripts/txt2mp3.py' --list-engines
    Write-Host ''
    Write-Info 'Italian voices'
    & $pythonExe @pythonPre 'scripts/txt2mp3.py' --list-voices --lang it @engineArgs
    Write-Host ''
    Write-Info 'English voices'
    & $pythonExe @pythonPre 'scripts/txt2mp3.py' --list-voices --lang en @engineArgs
    exit 0
}

if (-not $DryRun) {
    switch ($Engine) {
        'sapi' {
            if (-not (Get-Command powershell -ErrorAction SilentlyContinue)) {
                Write-Die 'PowerShell not found: System.Speech needs it'
            }
        }
        'piper' {
            # piper is the default engine; the converter downloads the model.
            if (-not (Get-Command piper -ErrorAction SilentlyContinue) -and
                -not (Test-PythonModule 'piper')) {
                Write-Info 'installing piper through pip'
                & $pythonExe @pythonPre -m pip install --user piper-tts
                if ($LASTEXITCODE -ne 0) { Write-Die 'piper installation failed' }
            }
        }
        'kokoro' {
            if (-not (Test-PythonModule 'kokoro_onnx') -and -not (Test-PythonModule 'kokoro')) {
                Write-Info 'installing kokoro-onnx through pip (models are about 340 MB, downloaded on first use)'
                & $pythonExe @pythonPre -m pip install --user kokoro-onnx
                if ($LASTEXITCODE -ne 0) { Write-Die 'kokoro installation failed' }
            }
        }
        'melotts' {
            if (-not (Test-PythonModule 'melo')) {
                Write-Die @'
MeloTTS is missing. It must come from GitHub, not PyPI:
  python3 -m pip install git+https://github.com/myshell-ai/MeloTTS.git
  python3 -m unidic download
It pulls in torch, several gigabytes. It is also the only engine with an
Indian English accent:  -Engine melotts -Voice EN-INDIA
'@
            }
        }
        'espeak' {
            if (-not (Get-Command espeak-ng -ErrorAction SilentlyContinue) -and
                -not (Get-Command espeak -ErrorAction SilentlyContinue)) {
                Write-Die @'
espeak-ng is missing and winget has no package for it. Install it by hand
(https://github.com/espeak-ng/espeak-ng/releases), or use -Engine sapi, which
needs nothing extra on Windows.
'@
            }
        }
        default {
            if (-not $Engine) {
                Write-Info 'speech engines found on this machine'
                & $pythonExe @pythonPre 'scripts/txt2mp3.py' --list-engines
            }
        }
    }
}

if ($PreviewVoices) {
    Write-Info 'voice list: pick one to hear the sample phrase (it / en switch language)'
    $prevArgs = @('scripts/txt2mp3.py', '--preview-voices') + $engineArgs
    & $pythonExe @pythonPre @prevArgs
    exit 0
}

# ffmpeg and ffprobe.
$missingFfmpeg = $false
foreach ($exe in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { $missingFfmpeg = $true }
}
if ($missingFfmpeg) {
    if ($DryRun) {
        Write-Warn 'ffmpeg/ffprobe missing, but -DryRun needs neither'
    } else {
        Install-Component 'ffmpeg'
        if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Die 'ffmpeg is not on PATH yet: open a new PowerShell window and re-run'
        }
        Write-Ok 'ffmpeg installed'
    }
} else {
    Write-Ok 'ffmpeg ready'
}

# Parallel jobs.
if ($Jobs -le 0) {
    $cores = $env:NUMBER_OF_PROCESSORS
    if (-not $cores) { $cores = 4 }
    $Jobs = [Math]::Min([int]$cores, 8)
}

# Free space: the synthesis cache is the big consumer (several GB per book).
$neededGb = 0
foreach ($b in ($Book | ForEach-Object { $_ -split ',' })) {
    switch ($b.Trim()) {
        'equipment' { $neededGb += 7 }
        'diagnosis' { $neededGb += 7 }
        default     { $neededGb += 6 }
    }
}
if ($Book -contains 'all' -or $Book.Count -eq 0) { $neededGb = 26 }
try {
    $qualifier = (Split-Path -Qualifier $Root).TrimEnd(':')
    $freeGb = [Math]::Round((Get-PSDrive $qualifier).Free / 1GB)
    Write-Info "disk: $freeGb GB free, about $neededGb GB needed for the synthesis cache"
    if ($freeGb -lt $neededGb) {
        if ($Yes) {
            Write-Warn 'proceeding anyway because -Yes was given; a full disk will abort the run'
        } else {
            Write-Die "not enough free space. Free some, or use -PruneCache, or pass -Yes to try anyway."
        }
    }
} catch {
    Write-Warn "could not read the free space of $Root; skipping the disk check"
}

# ------------------------------------------------------------------- per book
$doSingle = -not $NoSingle

function Invoke-Book {
    param([string]$Name)

    switch ($Name) {
        'it' {
            $text = 'out/anatomia.txt'; $audio = 'audio'; $lang = 'it'
            $build = @('scripts/build_book.py', '--strict')
        }
        'tropical' {
            $text = 'tropical/out/tropical-medicine.txt'; $audio = 'tropical/audio'; $lang = 'en'
            $build = @('scripts/build_book_en.py', '--strict', '--acronyms-ok', $TropicalAcronyms)
        }
        'equipment' {
            $text = 'equipment/out/hospital-equipment.txt'; $audio = 'equipment/audio'; $lang = 'en'
            $build = @(
                'scripts/build_book_en.py',
                '--capitoli', 'equipment/content/capitoli',
                '--out', 'equipment/out/hospital-equipment.txt',
                '--indice', 'equipment/out/index.txt',
                '--front-matter', 'equipment/content/FRONT_MATTER.md',
                '--acronyms-ok', $EquipmentAcronyms,
                '--toc-noun', 'guide',
                '--strict'
            )
        }
        'diagnosis' {
            $text = 'diagnosis/out/clinical-diagnosis.txt'; $audio = 'diagnosis/audio'; $lang = 'en'
            $build = @(
                'scripts/build_book_en.py',
                '--capitoli', 'diagnosis/content/capitoli',
                '--out', 'diagnosis/out/clinical-diagnosis.txt',
                '--indice', 'diagnosis/out/index.txt',
                '--front-matter', 'diagnosis/content/FRONT_MATTER.md',
                '--acronyms-ok', $DiagnosisAcronyms,
                '--toc-noun', 'manual',
                '--strict'
            )
        }
        default { Write-Die "unknown book: $Name" }
    }

    if ($Out) { $audio = $Out }

    Write-Host ''
    Write-Info "book: $Name  ($lang)  ->  $audio"

    if ($NoBuild) {
        Write-Info 'skipping the rebuild (-NoBuild)'
        if (-not (Test-Path $text)) { Write-Die "$text does not exist; drop -NoBuild" }
    } elseif ($DryRun -and (Test-Path $text)) {
        Write-Info "keeping the existing $text (-DryRun does not rebuild it)"
    } else {
        Write-Info "building $text"
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & $pythonExe @pythonPre @build
        if ($LASTEXITCODE -ne 0) { Write-Die "building $text failed" }
        Write-Ok 'text rebuilt'
    }

    $manifest = Join-Path $audio '.manifest.json'
    if ((Test-Path $manifest) -and -not $Force -and -not $DryRun) {
        if ((Get-Item $text).LastWriteTime -gt (Get-Item $manifest).LastWriteTime) {
            Write-Warn 'the text is newer than the audio manifest: existing MP3s may be stale'
            Write-Warn 'add -Force to re-encode everything from the cached chunks'
        }
    }

    $convArgs = @('scripts/txt2mp3.py', $text, '--lang', $lang, '-o', $audio, '--jobs', $Jobs)
    if ($doSingle)  { $convArgs += '--single' }
    if ($Force)     { $convArgs += '--force' }
    if ($DryRun)    { $convArgs += '--dry-run' }
    if ($Rate)      { $convArgs += @('--rate', $Rate) }
    if ($Bitrate)   { $convArgs += @('--bitrate', $Bitrate) }
    if ($Voice)     { $convArgs += @('--voice', $Voice) }
    if ($Only)      { $convArgs += @('--only', $Only) }
    if ($NoPrompt)  { $convArgs += '--no-prompt' }
    if ($ResetVoice) { $convArgs += '--reset-voice' }
    $convArgs += $engineArgs

    Write-Info ("converting: " + ($convArgs -join ' '))
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $pythonExe @pythonPre @convArgs
    if ($LASTEXITCODE -ne 0) { Write-Die "conversion failed for $Name" }

    if ($PruneCache -and -not $DryRun) {
        $cache = Join-Path $audio '.cache'
        if (Test-Path $cache) {
            Remove-Item $cache -Recurse -Force
            Write-Ok "pruned $cache"
        }
    }

    if (-not $DryRun -and (Test-Path $audio)) {
        $mp3s = Get-ChildItem -Path $audio -Filter '*.mp3' -File
        $size = [Math]::Round((($mp3s | Measure-Object -Property Length -Sum).Sum) / 1MB)
        Write-Ok "$($mp3s.Count) MP3 files, $size MB total in $audio"
        $single = $mp3s | Where-Object { $_.Name -like '*-integrale.mp3' } | Select-Object -First 1
        if ($single) {
            Write-Ok "single file: $($single.Name) ($([Math]::Round($single.Length / 1MB)) MB)"
        }
    }
}

$selected = @()
foreach ($b in $Book) {
    foreach ($piece in ($b -split ',')) {
        $name = $piece.Trim()
        if ($name -eq 'all' -or $name -eq '') {
            $selected = @('it', 'tropical', 'equipment', 'diagnosis')
        } elseif ($name -in @('it', 'tropical', 'equipment', 'diagnosis')) {
            $selected += $name
        } else {
            Write-Die "unknown book: $name (use it, tropical, equipment, diagnosis or all)"
        }
    }
}
$selected = $selected | Select-Object -Unique

if ($Out -and $selected.Count -ne 1) {
    Write-Die '-Out needs exactly one -Book (the books have different output folders)'
}
if ($Only -and $selected.Count -ne 1) {
    Write-Die '-Only needs exactly one -Book'
}

foreach ($name in $selected) { Invoke-Book $name }

Write-Host ''
Write-Info 'done. Playlists (.m3u) and .manifest.json sit next to the MP3s.'
if (-not $DryRun -and -not $PruneCache) {
    Write-Info 'the .cache/ directories hold intermediate WAVs and can be deleted at any time.'
}
