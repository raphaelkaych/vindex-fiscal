# Exemplo cliente externo: Windows PowerShell 5.1+; somente dados locais/autorizados.
# VINDEX_API_TOKEN deve vir do ambiente/gerenciador de segredos; não grave o segredo neste arquivo.
param(
    [Parameter(Mandatory=$true)][string]$XmlPath,
    [string]$BaseUrl = 'http://127.0.0.1:8000/api/v1/'
)
$ErrorActionPreference = 'Stop'
if (-not $env:VINDEX_API_TOKEN) { throw 'Configure VINDEX_API_TOKEN no ambiente do processo com a credencial gerada em Integrações e API.' }
$vindexBase = [Uri]($BaseUrl.TrimEnd('/') + '/')
if ($vindexBase.Scheme -ne 'https' -and $vindexBase.Host -notin @('localhost','127.0.0.1','::1')) { throw 'Use HTTPS fora do desenvolvimento local.' }
$vindexXml = Get-Item -LiteralPath $XmlPath
if ($vindexXml.Extension -ne '.xml' -or $vindexXml.Length -gt 2MB) { throw 'Escolha um XML NF-e modelo 55 de até 2 MB.' }
$vindexHeaders = @{Authorization = 'Bearer ' + $env:VINDEX_API_TOKEN; Accept = 'application/json'}

# A credencial individual autentica cada requisição; não existe login por senha nesta API.
$vindexCompanies = Invoke-RestMethod -Uri ($vindexBase.AbsoluteUri + 'empresas/') -Headers $vindexHeaders -Method Get
Write-Output $vindexCompanies
if ($vindexCompanies.results.Count -eq 0) { throw 'Nenhuma empresa autorizada. Revise a seleção da credencial na aplicação.' }
$vindexCompanyId = $vindexCompanies.results[0].id
$vindexNotes = Invoke-RestMethod -Uri ($vindexBase.AbsoluteUri + 'notas/?company=' + $vindexCompanyId + '&ordering=-issued_on') -Headers $vindexHeaders -Method Get
Write-Output $vindexNotes

# Multipart compatível com Windows PowerShell 5.1 (Invoke-RestMethod -Form exige PowerShell mais recente).
Add-Type -AssemblyName System.Net.Http
$vindexClient = New-Object System.Net.Http.HttpClient
$vindexMultipart = New-Object System.Net.Http.MultipartFormDataContent
$vindexStream = [System.IO.File]::OpenRead($vindexXml.FullName)
try {
    $vindexClient.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $env:VINDEX_API_TOKEN)
    $vindexContent = New-Object System.Net.Http.StreamContent($vindexStream)
    $vindexContent.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue('application/xml')
    $vindexMultipart.Add($vindexContent, 'file', $vindexXml.Name)
    $vindexResult = $vindexClient.PostAsync(($vindexBase.AbsoluteUri + 'notas/importar/'), $vindexMultipart).GetAwaiter().GetResult()
    $vindexResultText = $vindexResult.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $vindexResult.IsSuccessStatusCode) { throw ('A importação foi recusada (HTTP ' + [int]$vindexResult.StatusCode + '): ' + $vindexResultText) }
    Write-Output ($vindexResultText | ConvertFrom-Json)
} finally {
    $vindexMultipart.Dispose()
    $vindexStream.Dispose()
    $vindexClient.Dispose()
}
