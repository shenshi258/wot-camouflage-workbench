# Run outside the game. Completed cache resources are immutable; a rebuild uses
# a new generation directory. Equal files can therefore share NTFS data safely.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$GameRoot,
    [switch]$Apply,
    [string]$ReportPath
)
$ErrorActionPreference = 'Stop'
$gameDirectory = [IO.Path]::GetFullPath($GameRoot).TrimEnd('\','/')

function Assert-PlainPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if ([IO.File]::Exists($current) -or [IO.Directory]::Exists($current)) {
            $attributes = [IO.File]::GetAttributes($current)
            if ($attributes -band [IO.FileAttributes]::ReparsePoint) { throw "链接目录不支持优化：$current" }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
function Assert-Within([string]$Path, [string]$Boundary) {
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($Boundary.TrimEnd('\','/') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw '缓存路径超出本插件目录'
    }
    Assert-PlainPath $resolved
    return $resolved
}
function Assert-GameClosed {
    foreach ($process in @(Get-Process -Name WorldOfTanks -ErrorAction SilentlyContinue)) {
        $executable = $process.Path
        if (-not $executable) { throw '无法确认游戏状态，请先退出所有坦克世界客户端。' }
        if ($executable.StartsWith($gameDirectory+'\', [StringComparison]::OrdinalIgnoreCase)) {
            throw '请先退出这个区服的游戏，再优化缓存。'
        }
    }
}
function Get-ResourceHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path); $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

Assert-PlainPath $gameDirectory
if (-not (Test-Path -LiteralPath (Join-Path $gameDirectory 'version.xml'))) { throw '请选择游戏根目录（包含 version.xml）。' }
$pathsFile = Join-Path $gameDirectory 'paths.xml'
[xml]$paths = Get-Content -LiteralPath $pathsFile -Raw
$branch = @($paths.SelectNodes('//Path') | ForEach-Object { $_.InnerText.Trim().Replace('\','/') } |
    Where-Object { $_ -match '^\./res_mods/([0-9.]+)/?$' } | ForEach-Object { [regex]::Match($_,'[0-9]+(?:\.[0-9]+)+').Value })
if ($branch.Count -ne 1) { throw '无法识别当前游戏的 res_mods 版本目录。' }
$cacheRoot = Join-Path $gameDirectory ('res_mods\'+$branch[0]+'\vehicles\_lsf2')
Assert-PlainPath $cacheRoot
if (-not (Test-Path -LiteralPath $cacheRoot -PathType Container)) { throw '尚未生成本插件缓存，无需优化。' }
if ($Apply) { Assert-GameClosed }

if (-not ('SkinFilterFileIdentity' -as [type])) {
    # Filesystem handles only: no process handles, injection or game interfaces.
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class SkinFilterFileIdentity {
    [StructLayout(LayoutKind.Sequential)] struct Info {
        public uint Attr, C1, C2, A1, A2, W1, W2, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
    public static string[] Read(string path) {
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) {
            Info value;
            if (!GetFileInformationByHandle(stream.SafeFileHandle, out value)) throw new IOException("Cannot read file identity");
            return new string[] { value.Volume.ToString("x8")+":"+value.IndexHigh.ToString("x8")+value.IndexLow.ToString("x8"), value.Links.ToString() };
        }
    }
}
'@
}

$lockPath = Assert-Within (Join-Path $cacheRoot '_storage.lock') $cacheRoot
$lock = [IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    $seen = @{}; $groups = @{}; $skipped = New-Object 'System.Collections.Generic.List[string]'
    # Walk only the known fingerprint / car / generation structure. Check every
    # component before enumeration so a junction can never redirect traversal.
    foreach ($fingerprint in @(Get-ChildItem -LiteralPath $cacheRoot -Directory)) {
        if ($fingerprint.Name -notmatch '^[a-f0-9]{12}$') { continue }
        try { [void](Assert-Within $fingerprint.FullName $cacheRoot) } catch { $skipped.Add($_.Exception.Message); continue }
        foreach ($car in @(Get-ChildItem -LiteralPath $fingerprint.FullName -Directory)) {
            if ($car.Name -notmatch '^[a-f0-9]{12}$') { continue }
            try { [void](Assert-Within $car.FullName $cacheRoot) } catch { $skipped.Add($_.Exception.Message); continue }
            foreach ($generation in @(Get-ChildItem -LiteralPath $car.FullName -Directory)) {
                if ($generation.Name -notmatch '^[a-f0-9]{12}$') { continue }
                try {
                    [void](Assert-Within $generation.FullName $cacheRoot)
                    $marker = Assert-Within (Join-Path $generation.FullName 'ready.json') $cacheRoot
                    if (-not (Test-Path -LiteralPath $marker) -or (Get-Item -LiteralPath $marker).Length -gt 16MB) { continue }
                    $record = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
                    $relativeBase = 'vehicles/_lsf2/'+$fingerprint.Name+'/'+$car.Name+'/'+$generation.Name+'/'
                    if ($record.schema -notin @(2,3) -or $record.base -cne $relativeBase -or
                        $record.fingerprint -cnotmatch '^[a-f0-9]{64}$' -or
                        $record.fingerprint.Substring(0,12) -cne $fingerprint.Name -or @($record.resources).Count -gt 10000) { throw '缓存清单格式不匹配' }
                    foreach ($row in $record.resources) {
                        try {
                            $relative = [string]$row.destination
                            if (-not $relative.StartsWith($relativeBase,[StringComparison]::Ordinal) -or
                                $relative.Contains('..') -or $relative.Contains(':') -or $relative.Contains('\') -or
                                $row.sha256 -cnotmatch '^[a-f0-9]{64}$' -or [long]$row.bytes -lt 0) { throw '跳过无效缓存路径或校验值' }
                            $file = Assert-Within (Join-Path $gameDirectory ('res_mods/'+$branch[0]+'/'+$relative)) $cacheRoot
                            if ($seen.ContainsKey($file)) { continue }; $seen[$file] = $true
                            if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item -LiteralPath $file).Length -ne [long]$row.bytes) { throw '缓存大小不符，跳过' }
                            $groupKey = [string]$row.sha256+':'+[string]$row.bytes
                            if (-not $groups.ContainsKey($groupKey)) { $groups[$groupKey] = New-Object 'System.Collections.Generic.List[object]' }
                            $groups[$groupKey].Add(@{ path=$file; hash=[string]$row.sha256; bytes=[long]$row.bytes })
                        } catch { $skipped.Add($_.Exception.Message) }
                    }
                } catch { $skipped.Add($_.Exception.Message) }
            }
        }
    }
    [long]$logical = 0; [long]$physical = 0; [long]$potential = 0; [long]$released = 0
    $linked = 0; $alreadyShared = 0; $checked = 0
    foreach ($group in $groups.Values) {
        $identities = @{}; $valid = New-Object 'System.Collections.Generic.List[object]'
        foreach ($row in $group) {
            $logical += $row.bytes
            try {
                $identity = [SkinFilterFileIdentity]::Read($row.path)
                if (-not $identities.ContainsKey($identity[0])) { $physical += $row.bytes; $identities[$identity[0]]=$true }
                if ($group.Count -lt 2) { continue }
                if ((Get-ResourceHash $row.path) -cne $row.hash) { throw '缓存内容校验不符，跳过' }
                $checked++; $valid.Add($row)
            } catch { $skipped.Add($_.Exception.Message) }
        }
        if ($valid.Count -lt 2) { continue }
        $canonical = $valid[0]; $canonicalID = [SkinFilterFileIdentity]::Read($canonical.path)
        $remaining = @{}
        for ($index=1; $index -lt $valid.Count; $index++) {
            $row = $valid[$index]; $identity = [SkinFilterFileIdentity]::Read($row.path)
            if ($identity[0] -eq $canonicalID[0]) { $alreadyShared++; continue }
            if (-not $remaining.ContainsKey($identity[0])) { $remaining[$identity[0]]=[int]$identity[1] }
            $remaining[$identity[0]]--
            if ($remaining[$identity[0]] -eq 0) { $potential += $row.bytes }
            if (-not $Apply) { continue }
            $temporary = $null; $backup = $null
            try {
                Assert-GameClosed
                [void](Assert-Within $row.path $cacheRoot); [void](Assert-Within $canonical.path $cacheRoot)
                $stem = Join-Path ([IO.Path]::GetDirectoryName($row.path)) ('.lsf_link_'+[guid]::NewGuid().ToString('N'))
                $temporary = Assert-Within ($stem+'.tmp') $cacheRoot; $backup = Assert-Within ($stem+'.bak') $cacheRoot
                [void](New-Item -ItemType HardLink -Path $temporary -Target $canonical.path)
                [IO.File]::Replace($temporary,$row.path,$backup)
                if ((Get-ResourceHash $row.path) -cne $row.hash) {
                    [IO.File]::Replace($backup,$row.path,$null); throw '共享后校验失败，已恢复原文件'
                }
                $oldIdentity = [SkinFilterFileIdentity]::Read($backup)
                Remove-Item -LiteralPath (Assert-Within $backup $cacheRoot) -Force
                if ([int]$oldIdentity[1] -eq 1) { $released += $row.bytes }
                $linked++
            } catch { $skipped.Add($_.Exception.Message) }
            finally {
                if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath (Assert-Within $temporary $cacheRoot) -Force }
                # Preserve any recovery backup if replacement/verification failed.
            }
        }
    }
    $result = [ordered]@{ schema=1; applied=[bool]$Apply; game_root=$gameDirectory; cache_root=$cacheRoot;
        logical_bytes=$logical; unique_file_bytes_before=$physical; estimated_releasable_bytes=$potential;
        released_file_bytes=$released; linked_files=$linked; already_shared_files=$alreadyShared;
        checked_duplicate_files=$checked; listed_files=$seen.Count; skipped=@($skipped.ToArray());
        method='NTFS hardlinks; unchanged paths and bytes'; game_rendering='not_tested' }
    if (-not $ReportPath) { $ReportPath = Join-Path $cacheRoot '_storage_report.json' }
    $reportFile = [IO.Path]::GetFullPath($ReportPath); Assert-PlainPath $reportFile
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    $prefix = if ($Apply) { '已优化' } else { '仅统计' }
    Write-Output ('{0}：缓存逻辑大小 {1:N2} GiB，可释放约 {2:N2} GiB，本次释放 {3:N2} GiB。' -f $prefix,($logical/1GB),($potential/1GB),($released/1GB))
    Write-Output ('共享文件 {0}，此前已共享 {1}；报告：{2}' -f $linked,$alreadyShared,$reportFile)
    if ($skipped.Count) { Write-Output ('跳过 {0} 项，详见报告；原模型和高清资源均未删减。' -f $skipped.Count) }
} finally { $lock.Dispose() }
