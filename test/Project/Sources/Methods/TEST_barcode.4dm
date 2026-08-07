//%attributes = {}
$file:=Folder:C1567(fk desktop folder:K87:19).file("調整後.png")

DOCUMENT TO BLOB:C525($file.platformPath; $imageData)

$params:=New object:C1471

$params.targets:=New collection:C1472("barcode")

//all targets
$params.preferBackgroundProcessing:=True:C214
$params.usesCPUOnly:=True:C214
$params.orientation:="up"
$params.regionOfInterest:=New object:C1471
$params.regionOfInterest.x:=0
$params.regionOfInterest.y:=0
$params.regionOfInterest.width:=1
$params.regionOfInterest.height:=1

$status:=vision process data($imageData; $params)