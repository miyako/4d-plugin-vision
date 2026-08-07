//%attributes = {}
$file:=Folder:C1567(fk resources folder:K87:11).file("faces.jpg")

DOCUMENT TO BLOB:C525($file.platformPath;$imageData)

$params:=New object:C1471

  //$params.targets:=New collection("face";"text";"string";"rect";"horizon";"barcode";"human")
$params.targets:=New collection:C1472("part";"text")

$status:=vision process data ($imageData;$params)

If ($status.success)
	
	BLOB TO PICTURE:C682($imageData;$image)
	
	C_OBJECT:C1216($part;$faceLandmark)
	C_BLOB:C604($data)
	PICTURE PROPERTIES:C457($image;$imageWidth;$imageHeight)
	
	For each ($faceLandmark;$status.faceLandmarks)
		$faceLandmark.stroke:="yellow"
		$faceLandmark.fill:="red"
		$faceLandmark.fillOpacity:=0.3
		For each ($parts;$faceLandmark.parts)
			$parts.points:=$parts.points.join(" ")
			$parts.stroke:="white"
		End for each 
	End for each 
	
	C_OBJECT:C1216($text)
	For each ($text;$status.recognizedTexts)
		$text.stroke:="yellow"
		$text.fill:="green"
		$text.fillOpacity:=0.3
	End for each 
	
	$image:=add_highlights ($image;$status)
	
	SET PICTURE TO PASTEBOARD:C521($image)
	
End if 