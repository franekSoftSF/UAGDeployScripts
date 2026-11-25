# Requires the original Omnissa module from the same UAG release.
param([Parameter(Mandatory)][string]$IniFile,[Parameter(Mandatory)][string]$VendorModule,[Parameter(Mandatory)][string]$OutputFile)
$ErrorActionPreference='Stop'
Import-Module (Resolve-Path $VendorModule).Path -Force
$s=ImportIni (Resolve-Path $IniFile).Path
$g=$s.General
if (!$g.name -or $g.name -notmatch '^[a-zA-Z0-9][a-zA-Z0-9-]{0,31}$') { throw 'Invalid VM name' }
$option=GetDeploymentSettingOption $s
if ($option -notmatch '^(one|two|three)nic(?:-(standard|large|xl))?$') { throw 'Unsupported deploymentOption' }
$count=@{one=1;two=2;three=3}[$Matches[1]]
if ($count -ne 1) { throw 'This release supports one NIC only' }
$lines=[System.Collections.Generic.List[string]]::new()
function Add-Property($key,$value) {
 if ([string]::IsNullOrEmpty([string]$value)) { return }
 if ([string]$value -match '[\r\n\x00]') { throw "Multiline property not supported: $key" }
 $lines.Add("$key=$value")
}
foreach($key in @('DNS','defaultGateway','routes0','routes1','routes2','policyRouteGateway0','policyRouteGateway1','policyRouteGateway2','adminPasswordPolicyMinLen','gatewaySpec','sshEnabled','sshPasswordAccessEnabled')) { Add-Property $key $g[$key] }
for($i=0;$i -lt $count;$i++) {
 $ip=$g["ip$i"]; $mask=$g["netmask$i"]; $mode=$g["ipMode$i"]
 if (!$mode) { $mode=if($ip){'STATICV4'}else{'DHCPV4'} }
 if ($mode -notin @('STATICV4','DHCPV4')) { throw 'MVP supports IPv4 only' }
 if ($mode -eq 'STATICV4') {
  foreach($v in @($ip,$mask)) { if (!$v -or $v -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw "Invalid IPv4 settings for NIC $i" }; [void][ipaddress]::Parse($v) }
  Add-Property "ip$i" $ip; Add-Property "netmask$i" $mask
 }
 Add-Property "ipMode$i" $mode
}
$json=GetJSONSettings $s ''
if (!$json -or $json -is [array]) { throw 'Vendor module did not return a single settingsJSON string' }
# Preserve vendor escaping exactly, as in the successful lab run.
# Do not print or normalize settingsJSON; it may contain secrets.
Write-Host 'Omnissa settingsJSON generated successfully.'
foreach($key in @('rootPassword','adminPassword')) {
 $secret=Read-Host "Enter $key (at least 14 characters)" -AsSecureString
 $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
 try { $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr); if($plain.Length -lt 14){throw 'Password too short'}; Add-Property $key $plain } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $plain=$null }
}
Add-Property 'settingsJSON' $json
$path='/var/lib/cloud/instances/user-data.txt'
$yaml="#cloud-config`nwrite_files:`n  - path: $path`n    content: |`n" + (($lines | ForEach-Object { '      '+$_ }) -join "`n") + "`n    permissions: '0600'`n"
if(Test-Path $OutputFile){throw 'Output already exists; refusing overwrite'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputFile),$yaml,[Text.UTF8Encoding]::new($false))
Write-Host 'Payload written. Contains plaintext secrets; protect and transfer securely.'
