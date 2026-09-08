param(
    [ValidateRange(0, 65535)][int]$Port = 0,
    [AllowEmptyString()][string]$Text
)
$ErrorActionPreference = 'Stop'
function Read-ConfiguredPort([string]$Path) {
    $settings = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($null -eq $settings -or $settings.GetType().FullName -ne 'System.Management.Automation.PSCustomObject') {
        throw 'Settings must be a JSON object.'
    }
    # Older valid settings can omit the port, just as the app permits.
    $configuredPort = 47210
    if ($null -ne $settings.socket_port) { $configuredPort = [int]$settings.socket_port }
    if ($configuredPort -lt 1 -or $configuredPort -gt 65535) { throw 'Invalid socket_port.' }
    return $configuredPort
}
if (-not $PSBoundParameters.ContainsKey('Text')) { $Text = Get-Clipboard -Raw }
if ([string]::IsNullOrEmpty($Text)) { return }
if ($Port -eq 0) {
    $dataDirectory = $env:SCROLLY_POLLY_NOTELY_DATA_DIR
    if (-not $dataDirectory) { $dataDirectory = Join-Path $env:APPDATA 'ScrollyPollyNotely' }
    $configPath = Join-Path $dataDirectory 'notes-and-settings.json'
    $Port = 47210
    if ((Test-Path -LiteralPath $configPath) -or (Test-Path -LiteralPath ($configPath + '.bak'))) {
        try {
            $Port = Read-ConfiguredPort $configPath
        } catch {
            try {
                $Port = Read-ConfiguredPort ($configPath + '.bak')
            } catch {
                throw 'Cannot read settings or backup. Restore the settings file or pass -Port with the app port.'
            }
        }
    }
}
if ($Port -lt 1 -or $Port -gt 65535) { throw 'socket_port must be between 1 and 65535.' }
$payload = [System.Text.Encoding]::UTF8.GetBytes($Text)
if ($payload.Length -gt 1048576) { throw 'Clipboard text exceeds the 1 MiB limit.' }
$client = New-Object System.Net.Sockets.TcpClient
try {
    if (-not $client.ConnectAsync('127.0.0.1', $Port).Wait(2000)) {
        throw 'Cannot connect to Scrolly Polly Notely. Start the app and check socket_port.'
    }
    $client.SendTimeout = 2000
    $stream = $client.GetStream()
    $stream.Write($payload, 0, $payload.Length)
    $stream.Flush()
    $client.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
} finally {
    $client.Close()
}
