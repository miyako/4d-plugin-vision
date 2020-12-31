//%attributes = {}
$file:=Folder:C1567(fk resources folder:K87:11).file("sample.png")

DOCUMENT TO BLOB:C525($file.platformPath;$imageData)

$params:=New object:C1471

$params.targets:=New collection:C1472("face";"text";"string";"rect";"horizon";"barcode";"human")
$params.targets:=New collection:C1472("string";"barcode")

  //all targets
$params.preferBackgroundProcessing:=True:C214
$params.usesCPUOnly:=True:C214
$params.orientation:="up"
$params.regionOfInterest:=New object:C1471
$params.regionOfInterest.x:=0
$params.regionOfInterest.y:=0
$params.regionOfInterest.width:=1
$params.regionOfInterest.height:=1

  //string
$params.reportCharacterBoxes:=True:C214

  //text
$params.maxCandidateCount:=1
$params.minimumTextHeight:=0
$params.minimumTextHeight:=0
$params.usesLanguageCorrection:=False:C215
$params.recognitionLevel:=0
$params.recognitionLanguages:=New collection:C1472("en-US")  //only US English is supported as of Catalina
$params.customWords:=New collection:C1472("4D")

$status:=vision process data ($imageData;$params)

If ($status.success)
	
	BLOB TO PICTURE:C682($imageData;$image)
	
	C_OBJECT:C1216($barcode)
	For each ($barcode;$status.barcodes)
		$barcode.stroke:="yellow"
		$barcode.fill:="green"
		$barcode.fillOpacity:=0.3
	End for each 
	
	C_OBJECT:C1216($text;$characters)
	For each ($text;$status.texts)
		$text.stroke:="yellow"
		$text.fill:="blue"
		$text.fillOpacity:=0.3
		For each ($characters;$text.characters)
			$characters.stroke:="red"
			$characters.fill:="red"
			$characters.fillOpacity:=0.3
		End for each 
	End for each 
	
	
	$image:=add_highlights ($image;$status)
	
	SET PICTURE TO PASTEBOARD:C521($image)
	
End if 