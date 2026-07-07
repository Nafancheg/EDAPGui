<#
.SYNOPSIS
    Creates fake Elite Dangerous data files so EDAPGui can start on a machine
    where the game is NOT installed (e.g. a dev laptop).

.DESCRIPTION
    EDAP's startup (EDAutopilot.__init__) hard-requires several ED files and
    raises if they are missing:
      - EDGraphicsSettings -> Options\Graphics\DisplaySettings.xml + Settings.xml (must be Borderless)
      - EDPlayerSettings   -> Options\Player\*.misc
      - EDJournal          -> Saved Games\...\Journal.*.log  (dir must exist)
      - EDKeys             -> Options\Bindings\*.binds  (root <Root> required)
      - CargoParser/Status/NavRoute etc -> Saved Games\...\*.json live files

    This script writes minimal-but-valid versions of all of them. It is
    idempotent: re-running overwrites the mocks with the same content.

    These files live OUTSIDE the repo (in %LOCALAPPDATA% and Saved Games),
    so they never touch git and don't affect the real game on a gaming PC.

    NOTE: The GUI still logs two harmless ERRORs ("Could not find window
    'Elite - Dangerous (CLIENT)'" / "could not be located on any monitor")
    because the game window isn't running. Those do NOT stop startup.

.NOTES
    Full autopilot verification (real FSD runs) still requires a machine with
    Elite Dangerous actually installed and running. This mock only unblocks
    launching the GUI for visual/refactor checks.
#>

$ErrorActionPreference = 'Stop'
$ts = '2026-07-06T14:00:00Z'

$local   = $env:LOCALAPPDATA
$gfxDir  = Join-Path $local 'Frontier Developments\Elite Dangerous\Options\Graphics'
$plyDir  = Join-Path $local 'Frontier Developments\Elite Dangerous\Options\Player'
$bndDir  = Join-Path $local 'Frontier Developments\Elite Dangerous\Options\Bindings'
$saved   = Join-Path ([Environment]::GetFolderPath('MyDocuments') | Split-Path) 'Saved Games'
# GetFolderPath has no SavedGames enum on all runtimes; build it from the user profile instead:
$saved   = Join-Path $env:USERPROFILE 'Saved Games'
$jrnDir  = Join-Path $saved 'Frontier Developments\Elite Dangerous'

foreach ($d in @($gfxDir, $plyDir, $bndDir, $jrnDir)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

function Write-File($path, $content) {
    # Write BOM-less UTF-8 explicitly. Note: `Set-Content -Encoding UTF8`
    # emits a BOM under Windows PowerShell 5.1 (it is BOM-less only in
    # PowerShell 7+), and a leading BOM makes both expat/xmltodict and
    # json.loads reject the file. WriteAllText with UTF8Encoding($false)
    # is BOM-less on every PowerShell edition.
    [System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "  wrote $path"
}

Write-Host 'Creating mock ED graphics settings...'
Write-File (Join-Path $gfxDir 'DisplaySettings.xml') @'
<?xml version="1.0" encoding="UTF-8"?>
<DisplayConfig>
	<Version>1</Version>
	<ScreenWidth>1920</ScreenWidth>
	<ScreenHeight>1080</ScreenHeight>
	<FullScreen>2</FullScreen>
	<Monitor>0</Monitor>
	<RefreshRateNumerator>60000</RefreshRateNumerator>
	<RefreshRateDenominator>1000</RefreshRateDenominator>
</DisplayConfig>
'@

Write-File (Join-Path $gfxDir 'Settings.xml') @'
<?xml version="1.0" encoding="UTF-8"?>
<GraphicsOptions>
	<Version>1</Version>
	<FOV>56.000000</FOV>
</GraphicsOptions>
'@

Write-Host 'Creating mock ED player settings (.misc)...'
Write-File (Join-Path $plyDir 'Custom.4.3.misc') @'
<?xml version="1.0" encoding="UTF-8"?>
<Root>
	<DashboardGUIBrightness Value="1.0" />
	<HideLocationIcons Value="0" />
	<Language Value="English" />
	<LanguageOverrideActive Value="0" />
</Root>
'@

Write-Host 'Creating mock ED key bindings (.binds)...'
Write-File (Join-Path $bndDir 'Custom.4.0.binds') @'
<?xml version="1.0" encoding="UTF-8"?>
<Root PresetName="Custom" MajorVersion="4" MinorVersion="0">
	<KeyboardLayout>en-US</KeyboardLayout>
	<YawLeftButton><Primary Device="Keyboard" Key="Key_A" /><Secondary Device="{NoDevice}" Key="" /></YawLeftButton>
	<YawRightButton><Primary Device="Keyboard" Key="Key_D" /><Secondary Device="{NoDevice}" Key="" /></YawRightButton>
	<PitchUpButton><Primary Device="Keyboard" Key="Key_S" /><Secondary Device="{NoDevice}" Key="" /></PitchUpButton>
	<PitchDownButton><Primary Device="Keyboard" Key="Key_W" /><Secondary Device="{NoDevice}" Key="" /></PitchDownButton>
	<RollLeftButton><Primary Device="Keyboard" Key="Key_Q" /><Secondary Device="{NoDevice}" Key="" /></RollLeftButton>
	<RollRightButton><Primary Device="Keyboard" Key="Key_E" /><Secondary Device="{NoDevice}" Key="" /></RollRightButton>
	<SetSpeedZero><Primary Device="Keyboard" Key="Key_0" /><Secondary Device="{NoDevice}" Key="" /></SetSpeedZero>
	<SetSpeed100><Primary Device="Keyboard" Key="Key_5" /><Secondary Device="{NoDevice}" Key="" /></SetSpeed100>
	<HyperSuperCombination><Primary Device="Keyboard" Key="Key_J" /><Secondary Device="{NoDevice}" Key="" /></HyperSuperCombination>
	<Supercruise><Primary Device="Keyboard" Key="Key_H" /><Secondary Device="{NoDevice}" Key="" /></Supercruise>
	<UIFocus><Primary Device="Keyboard" Key="Key_LeftShift" /><Secondary Device="{NoDevice}" Key="" /></UIFocus>
	<UI_Up><Primary Device="Keyboard" Key="Key_UpArrow" /><Secondary Device="{NoDevice}" Key="" /></UI_Up>
	<UI_Down><Primary Device="Keyboard" Key="Key_DownArrow" /><Secondary Device="{NoDevice}" Key="" /></UI_Down>
	<UI_Left><Primary Device="Keyboard" Key="Key_LeftArrow" /><Secondary Device="{NoDevice}" Key="" /></UI_Left>
	<UI_Right><Primary Device="Keyboard" Key="Key_RightArrow" /><Secondary Device="{NoDevice}" Key="" /></UI_Right>
	<UI_Select><Primary Device="Keyboard" Key="Key_Space" /><Secondary Device="{NoDevice}" Key="" /></UI_Select>
	<UI_Back><Primary Device="Keyboard" Key="Key_Backspace" /><Secondary Device="{NoDevice}" Key="" /></UI_Back>
	<FocusCommsPanel><Primary Device="Keyboard" Key="Key_2" /><Secondary Device="{NoDevice}" Key="" /></FocusCommsPanel>
	<FocusLeftPanel><Primary Device="Keyboard" Key="Key_1" /><Secondary Device="{NoDevice}" Key="" /></FocusLeftPanel>
	<FocusRightPanel><Primary Device="Keyboard" Key="Key_4" /><Secondary Device="{NoDevice}" Key="" /></FocusRightPanel>
	<GalaxyMapOpen><Primary Device="Keyboard" Key="Key_M" /><Secondary Device="{NoDevice}" Key="" /></GalaxyMapOpen>
	<SystemMapOpen><Primary Device="Keyboard" Key="Key_N" /><Secondary Device="{NoDevice}" Key="" /></SystemMapOpen>
	<LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle>
	<DeployHeatSink><Primary Device="Keyboard" Key="Key_V" /><Secondary Device="{NoDevice}" Key="" /></DeployHeatSink>
	<IncreaseEnginesPower><Primary Device="Keyboard" Key="Key_UpArrow" /><Secondary Device="{NoDevice}" Key="" /></IncreaseEnginesPower>
	<ExplorationFSSEnter><Primary Device="Keyboard" Key="Key_B" /><Secondary Device="{NoDevice}" Key="" /></ExplorationFSSEnter>
</Root>
'@

Write-Host 'Creating mock ED journal + live JSON files...'
Write-File (Join-Path $jrnDir 'Journal.2026-07-06T140000.01.log') @'
{ "timestamp":"2026-07-06T14:00:00Z", "event":"Fileheader", "part":1, "language":"English/UK", "Odyssey":true, "gameversion":"4.0.0.1904", "build":"r308767/r0 " }
{ "timestamp":"2026-07-06T14:00:05Z", "event":"LoadGame", "Commander":"TestCmdr", "FID":"F0000000", "Horizons":true, "Odyssey":true, "Ship":"mandalay", "Ship_Localised":"Mandalay", "ShipID":1, "ShipName":"test", "ShipIdent":"TS-01", "FuelLevel":32.000000, "FuelCapacity":32.000000, "GameMode":"Solo", "Credits":1000000, "Loan":0 }
{ "timestamp":"2026-07-06T14:00:06Z", "event":"Loadout", "Ship":"mandalay", "ShipID":1, "ShipName":"test", "ShipIdent":"TS-01", "HullValue":0, "ModulesValue":0, "HullHealth":1.000000, "UnladenMass":0.0, "CargoCapacity":0, "FuelCapacity":{ "Main":32.000000, "Reserve":0.630000 }, "MaxJumpRange":60.0, "Rebuy":0 }
'@

$liveFiles = @{
    'Cargo.json'       = '{ "timestamp":"' + $ts + '", "event":"Cargo", "Vessel":"Ship", "Count":0, "Inventory":[] }'
    'Status.json'      = '{ "timestamp":"' + $ts + '", "event":"Status", "Flags":16777240, "Flags2":0, "Pips":[4,8,0], "FireGroup":0, "GuiFocus":0, "Fuel":{ "FuelMain":32.000000, "FuelReservoir":0.630000 }, "Cargo":0.000000, "LegalState":"Clean" }'
    'NavRoute.json'    = '{ "timestamp":"' + $ts + '", "event":"NavRoute", "Route":[] }'
    'Market.json'      = '{ "timestamp":"' + $ts + '", "event":"Market", "MarketID":0, "StationName":"", "StarSystem":"", "Items":[] }'
    'ModulesInfo.json' = '{ "timestamp":"' + $ts + '", "event":"ModulesInfo", "Modules":[] }'
    'Backpack.json'    = '{ "timestamp":"' + $ts + '", "event":"Backpack", "Items":[], "Components":[], "Consumables":[], "Data":[] }'
    'ShipLocker.json'  = '{ "timestamp":"' + $ts + '", "event":"ShipLocker", "Items":[], "Components":[], "Consumables":[], "Data":[] }'
    'Outfitting.json'  = '{ "timestamp":"' + $ts + '", "event":"Outfitting", "MarketID":0, "StationName":"", "StarSystem":"", "Items":[] }'
    'Shipyard.json'    = '{ "timestamp":"' + $ts + '", "event":"Shipyard", "MarketID":0, "StationName":"", "StarSystem":"", "PriceList":[] }'
    'FCMaterials.json' = '{ "timestamp":"' + $ts + '", "event":"FCMaterials", "MarketID":0, "CarrierName":"", "CarrierID":"", "Items":[] }'
}
foreach ($name in $liveFiles.Keys) {
    Write-File (Join-Path $jrnDir $name) $liveFiles[$name]
}

Write-Host ''
Write-Host 'Mock ED environment ready. Launch GUI with:' -ForegroundColor Green
Write-Host '  .\venv\Scripts\python.exe EDAPGui.py'
