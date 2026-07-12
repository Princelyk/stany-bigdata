param(
    [string]$D1Dir = "data/user_data/D1",
    [string]$D2Dir = "data/user_data/D2",
    [string]$D3Dir = "data/user_data/D3",
    [string]$OutDir = "results/data/protocol",
    [int]$Repetitions = 3,
    [int[]]$Threads = @(1,2,4,8,16),
    [int]$CorrectnessSamples = 100,
    [int]$MaxFiles = 0,
    [int]$MaxBytesPerFile = 0,
    [switch]$RunStrongScaling,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Run-WeakScalingDataset {
    param(
        [string]$DatasetId,
        [string]$DataDir
    )

    if (-not (Test-Path -Path $DataDir -PathType Container)) {
        Write-Warning "Skipping ${DatasetId}: data dir not found -> $DataDir"
        return
    }

    for ($rep = 1; $rep -le $Repetitions; $rep++) {
        $runId = "{0}_r{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), $rep
        $cmd = @(
            "-m", "src.benchmarks.scalability_protocol_run",
            "--dataset-id", $DatasetId,
            "--data-dir", $DataDir,
            "--out", $OutDir,
            "--run-id", $runId,
            "--correctness-samples", $CorrectnessSamples,
            "--max-files", $MaxFiles,
            "--max-bytes-per-file", $MaxBytesPerFile
        )

        if ($DryRun) {
            Write-Host "[DRY-RUN] python $($cmd -join ' ')"
        } else {
            Write-Host "Running weak scaling: $DatasetId rep=$rep"
            python @cmd
        }
    }
}

Write-Host "=== Weak scaling protocol ==="
Run-WeakScalingDataset -DatasetId "D1" -DataDir $D1Dir
Run-WeakScalingDataset -DatasetId "D2" -DataDir $D2Dir
Run-WeakScalingDataset -DatasetId "D3" -DataDir $D3Dir

if ($RunStrongScaling) {
    if (-not (Test-Path -Path $D2Dir -PathType Container)) {
        Write-Warning "Skipping strong scaling: D2 dir not found -> $D2Dir"
    } else {
        $threadCsv = ($Threads | ForEach-Object { $_.ToString() }) -join ","
        $runId = "{0}_strong" -f (Get-Date -Format "yyyyMMdd_HHmmss")
        $cmd = @(
            "-m", "src.benchmarks.scalability_protocol_strong",
            "--dataset-id", "D2",
            "--data-dir", $D2Dir,
            "--out", $OutDir,
            "--run-id", $runId,
            "--threads", $threadCsv,
            "--repetitions", $Repetitions,
            "--max-files", $MaxFiles,
            "--max-bytes-per-file", $MaxBytesPerFile
        )

        if ($DryRun) {
            Write-Host "[DRY-RUN] python $($cmd -join ' ')"
        } else {
            Write-Host "=== Strong scaling protocol (D2) ==="
            python @cmd
        }
    }
}

$analyzeCmd = @("-m", "src.benchmarks.scalability_protocol_analyze", "--out", $OutDir, "--baseline-dataset", "D1")
if ($DryRun) {
    Write-Host "[DRY-RUN] python $($analyzeCmd -join ' ')"
} else {
    Write-Host "=== Protocol analysis ==="
    python @analyzeCmd
}

Write-Host "Done. Outputs in: $OutDir"
