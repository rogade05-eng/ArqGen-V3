# Ejecuta un comando de compilación/QA y, si falla, publica su salida final como
# anotación `::error::` para que la causa sea legible por la API de comprobaciones
# incluso cuando el registro del runner no es descargable. No oculta el fallo:
# termina con el mismo código de salida.
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [Parameter(Mandatory = $true)][string]$Command,
  [int]$TailLines = 30,
  [int]$MaxChars = 3500
)

$log = Join-Path $env:RUNNER_TEMP ("$Name-" + [Guid]::NewGuid().ToString('N') + '.log')
Invoke-Expression $Command 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if ($code -ne 0) {
  $tail = (Get-Content -LiteralPath $log -Tail $TailLines) -join "`n"
  $tail = $tail -replace '%', '%25' -replace "`r", '' -replace "`n", '%0A'
  if ($tail.Length -gt $MaxChars) { $tail = $tail.Substring($tail.Length - $MaxChars) }
  Write-Host "::error title=$Name failed (exit $code)::$tail"
  exit $code
}
Write-Host "$Name OK"
