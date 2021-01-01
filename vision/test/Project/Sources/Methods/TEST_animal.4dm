//%attributes = {}
$file:=Folder:C1567(fk resources folder:K87:11).file("creatures.jpg")

DOCUMENT TO BLOB:C525($file.platformPath;$imageData)

$params:=New object:C1471

$params.targets:=New collection:C1472("animal";"human")

  //all targets
$params.preferBackgroundProcessing:=True:C214
$params.usesCPUOnly:=True:C214
$params.orientation:="up"
$params.regionOfInterest:=New object:C1471
$params.regionOfInterest.x:=0
$params.regionOfInterest.y:=0
$params.regionOfInterest.width:=1
$params.regionOfInterest.height:=1

$status:=vision process data ($imageData;$params)

If ($status.success)
	
	BLOB TO PICTURE:C682($imageData;$image)
	
	C_OBJECT:C1216($animal)
	For each ($animal;$status.animals)
		$animal.stroke:="yellow"
		$animal.fill:="orange"
		$animal.fillOpacity:=0.3
	End for each 
	
	C_OBJECT:C1216($human)
	For each ($human;$status.humans)
		$human.stroke:="yellow"
		$human.fill:="red"
		$human.fillOpacity:=0.3
	End for each 
	
	$image:=add_highlights ($image;$status)
	
	SET PICTURE TO PASTEBOARD:C521($image)
	
End if 