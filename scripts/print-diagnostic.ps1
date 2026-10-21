# Print a fictitious receipt raster using an EXISTING Windows printer/driver.
# Does not install drivers, change default printers, cut paper or open a cash drawer.
param(
    [Parameter(Mandatory=$true)][string]$PrinterName,
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [double]$PrintableWidthMm = 48
)
$ErrorActionPreference = 'Stop'
if ($PrintableWidthMm -lt 30 -or $PrintableWidthMm -gt 110) { throw 'Invalid printable width' }
Add-Type -AssemblyName System.Drawing
$ompImage = [System.Drawing.Image]::FromFile((Resolve-Path $ImagePath).Path)
$ompDocument = New-Object System.Drawing.Printing.PrintDocument
try {
    $ompDocument.PrinterSettings.PrinterName = $PrinterName
    if (-not $ompDocument.PrinterSettings.IsValid) { throw 'Printer is not available' }
    $ompDocument.DocumentName = 'OpenMultiPOS - diagnostic demo receipt'
    $ompDocument.PrintController = New-Object System.Drawing.Printing.StandardPrintController
    $ompDocument.DefaultPageSettings.Margins = New-Object System.Drawing.Printing.Margins(0,0,0,0)
    $ompWidth = [single]($PrintableWidthMm / 25.4 * 100)
    $ompHeight = [single]($ompImage.Height / $ompImage.Width * $ompWidth)
    $ompDocument.DefaultPageSettings.PaperSize = New-Object System.Drawing.Printing.PaperSize('OMP continuous demo', [int][Math]::Ceiling($ompWidth), [int][Math]::Ceiling($ompHeight + 12))
    $ompResolution = $ompDocument.PrinterSettings.PrinterResolutions | Where-Object { $_.X -eq 203 -and $_.Y -eq 203 } | Select-Object -First 1
    if ($ompResolution) { $ompDocument.DefaultPageSettings.PrinterResolution = $ompResolution }
    $ompAttributes = New-Object System.Drawing.Imaging.ImageAttributes
    $ompAttributes.SetThreshold(0.65, [System.Drawing.Imaging.ColorAdjustType]::Bitmap)
    $ompHandler = [System.Drawing.Printing.PrintPageEventHandler]{
        param($sender, $eventArgs)
        $eventArgs.Graphics.PageUnit = [System.Drawing.GraphicsUnit]::Pixel
        $eventArgs.Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
        $eventArgs.Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
        $ompPixels = [int][Math]::Round($PrintableWidthMm / 25.4 * $eventArgs.Graphics.DpiX)
        $ompPixelHeight = [int][Math]::Round($ompImage.Height / $ompImage.Width * $ompPixels)
        $ompRect = New-Object System.Drawing.Rectangle(0,0,$ompPixels,$ompPixelHeight)
        $eventArgs.Graphics.DrawImage($ompImage, $ompRect, 0, 0, $ompImage.Width, $ompImage.Height, [System.Drawing.GraphicsUnit]::Pixel, $ompAttributes)
        $eventArgs.HasMorePages = $false
    }
    $ompDocument.add_PrintPage($ompHandler)
    $ompDocument.Print()
    Write-Output 'Job submitted to Windows. Physical output and QR reading must be confirmed separately.'
} finally {
    if ($ompAttributes) { $ompAttributes.Dispose() }
    $ompDocument.Dispose()
    $ompImage.Dispose()
}
