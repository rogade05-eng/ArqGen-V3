# Ejecuta un comando de compilación/QA y, si falla, publica su salida como
# anotaciones `::error::` para que la causa sea legible por la API de
# comprobaciones incluso cuando el registro del runner no es descargable.
# Publica tres cortes: encabezado (primeras líneas), líneas que parecen errores
# y cola. No oculta el fallo: termina con el mismo código de salida.
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [Parameter(Mandatory = $true)][string]$Command,
  [int]$TailLines = 30,
  [int]$MaxChars = 3500
)

function Format-Annotation([string[]]$Lines, [int]$Limit, [switch]$KeepStart) {
  $text = ($Lines | ForEach-Object { $_.TrimEnd() }) -join "`n"
  $text = $text -replace '%', '%25' -replace "`r", '' -replace "`n", '%0A'
  if ($text.Length -gt $Limit) {
    $text = if ($KeepStart) { $text.Substring(0, $Limit) } else { $text.Substring($text.Length - $Limit) }
  }
  return $text
}

$log = Join-Path $env:RUNNER_TEMP ("$Name-" + [Guid]::NewGuid().ToString('N') + '.log')
Invoke-Expression $Command 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if ($code -ne 0) {
  $lines = @(Get-Content -LiteralPath $log)
  $head = Format-Annotation ($lines | Select-Object -First 12) $MaxChars -KeepStart
  Write-Host "::error title=$Name head ($($lines.Count) log lines)::$head"
  $hits = @($lines | Select-String -Pattern 'error|failed|fall|cannot|denied|not found|no se pudo|panic' -CaseSensitive:$false |
    Select-Object -First 25 | ForEach-Object { $_.Line })
  if ($hits.Count -gt 0) {
    $match = Format-Annotation $hits $MaxChars
    Write-Host "::error title=$Name error-like lines ($($hits.Count))::$match"
  }
  $tail = Format-Annotation ($lines | Select-Object -Last $TailLines) $MaxChars
  Write-Host "::error title=$Name failed (exit $code)::$tail"
  exit $code
}
Write-Host "$Name OK"
