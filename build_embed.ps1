# Virtual KR IME - Windows Embeddable Python 배포 패키지 빌드 스크립트
# 사용법: .\build_embed.ps1 [-Version "3.12.3"]
# 결과: build\Virtual_KR_IME\ 에 실행 가능한 폴더가 생성됨. 압축해서 배포하면 됨.

param(
    [string]$Version = "3.12.3"
)
# 터미널 한글 출력: 출력 인코딩 UTF-8 + 콘솔 코드페이지 65001
$null = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch { }

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $BuildDir "Virtual_KR_IME"
$AppDir = Join-Path $DistDir "app"

# 버전에서 _pth 파일명 추출 (3.12.3 -> python312._pth)
$VersionParts = $Version.Split(".")
$ShortVer = $VersionParts[0] + $VersionParts[1]
$PthName = "python$ShortVer._pth"

$EmbedZip = "python-$Version-embed-amd64.zip"
$EmbedUrl = "https://www.python.org/ftp/python/$Version/$EmbedZip"

Write-Host "=== Virtual KR IME Embeddable 빌드 ===" -ForegroundColor Cyan
Write-Host "Python embed 버전: $Version"
Write-Host "출력 폴더: $DistDir"
Write-Host "실행 파일 폴더: $AppDir"
Write-Host ""

# 1) build 폴더 정리 후 생성
if (Test-Path $DistDir) {
    Write-Host "기존 배포 폴더 삭제 중..."
    Remove-Item -Recurse -Force $DistDir
}
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# 2) Embeddable ZIP 다운로드 (없으면)
$ZipPath = Join-Path $BuildDir $EmbedZip
if (-not (Test-Path $ZipPath)) {
    Write-Host "Embeddable Python 다운로드 중: $EmbedUrl"
    try {
        Invoke-WebRequest -Uri $EmbedUrl -OutFile $ZipPath -UseBasicParsing
    } catch {
        Write-Host "오류: 다운로드 실패. 아래에서 수동으로 받아 build\ 에 넣어주세요:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/windows/ (Windows embeddable package (64-bit))"
        Write-Host "  파일명: $EmbedZip"
        exit 1
    }
} else {
    Write-Host "기존 Embed ZIP 사용: $ZipPath"
}

# 3) 압축 해제 (app 하위에 구성 파일 모으기)
Write-Host "압축 해제 중..."
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
Expand-Archive -Path $ZipPath -DestinationPath $AppDir -Force

# 4) _pth 수정: Lib, Lib\site-packages 추가 (site-packages 인식)
$PthPath = Join-Path $AppDir $PthName
if (-not (Test-Path $PthPath)) {
    Write-Host "오류: $PthName 을 찾을 수 없습니다. Embed 버전을 확인하세요." -ForegroundColor Red
    exit 1
}
$pthContent = Get-Content $PthPath -Raw
if ($pthContent -notmatch "Lib\\site-packages") {
    $pthContent = $pthContent.TrimEnd() + "`r`nLib`r`nLib\site-packages`r`n"
    Set-Content -Path $PthPath -Value $pthContent -NoNewline
    Write-Host "_pth 수정 완료: Lib, Lib\site-packages 추가"
} else {
    Write-Host "_pth 에 이미 site-packages 경로가 있습니다."
}

# 5) Lib\site-packages 생성 후 pip install --target
$SitePackages = Join-Path $AppDir "Lib\site-packages"
New-Item -ItemType Directory -Path $SitePackages -Force | Out-Null

$Requirements = Join-Path $ProjectRoot "requirements.txt"
Write-Host "의존성 설치 중 (pip install --target)..."
Write-Host "  참고: PC에 설치된 Python 버전이 Embed($Version)과 같거나 호환되는 것이 좋습니다." -ForegroundColor Gray
& python -m pip install -r $Requirements --target $SitePackages --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "오류: pip install 실패. Python이 설치되어 있고 PATH에 있는지 확인하세요." -ForegroundColor Red
    exit 1
}

# 6) 프로젝트 소스 복사 (src)
$SrcSrc = Join-Path $ProjectRoot "src"
$SrcDst = Join-Path $AppDir "src"
Copy-Item -Path $SrcSrc -Destination $SrcDst -Recurse -Force
Write-Host "src 폴더 복사 완료"

# 7) run.bat 생성 (배포 폴더에서 실행용)
$RunBat = @"
@echo off
cd /d "%~dp0app"
set PYTHONNOUSERSITE=1
"python.exe" -m src.main
pause
"@
Set-Content -Path (Join-Path $DistDir "run.bat") -Value $RunBat -Encoding ASCII
Write-Host "run.bat 생성 완료"

# 8) 사용자용 간단 안내
$ReadmeDist = @"
가상 한글 입력기 (Virtual KR IME) - 배포용

[실행 방법]
  run.bat 더블클릭

[설정]
  app\src\config.py 를 메모장 등으로 열어서 수정할 수 있습니다.
  (대상 게임 창 제목 키워드, IME 켜기/끄기 키 등)

[주의]
  - 관리자 권한이 필요할 수 있습니다 (키보드 후킹 사용 시).
  - 일부 게임/안티치트는 입력 도구 사용을 제한할 수 있습니다.
"@
$ReadmePath = Join-Path $DistDir "README.txt"
# BOM 있음($true): Windows 메모장 등에서 UTF-8로 인식해 한글이 깨지지 않음
[System.IO.File]::WriteAllText($ReadmePath, $ReadmeDist, [System.Text.UTF8Encoding]::new($true))
Write-Host "README.txt 생성 완료"

# 9) 라이선스/서드파티 고지 복사
$ProjectLicenseSrc = Join-Path $ProjectRoot "LICENSE"
$ProjectLicenseDst = Join-Path $DistDir "LICENSE.txt"
if (Test-Path $ProjectLicenseSrc) {
    Copy-Item -Path $ProjectLicenseSrc -Destination $ProjectLicenseDst -Force
    Write-Host "LICENSE.txt 복사 완료"
} else {
    Write-Host "경고: LICENSE 파일을 찾지 못했습니다." -ForegroundColor Yellow
}

$ThirdPartySrc = Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.txt"
$ThirdPartyDst = Join-Path $DistDir "THIRD_PARTY_NOTICES.txt"
if (Test-Path $ThirdPartySrc) {
    Copy-Item -Path $ThirdPartySrc -Destination $ThirdPartyDst -Force
    Write-Host "THIRD_PARTY_NOTICES.txt 복사 완료"
} else {
    Write-Host "경고: THIRD_PARTY_NOTICES.txt 파일을 찾지 못했습니다." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "빌드 완료: $DistDir" -ForegroundColor Green
Write-Host "이 폴더를 ZIP으로 압축해 배포하면 됩니다. 사용자는 압축 해제 후 run.bat 실행." -ForegroundColor Gray
