//%attributes = {"invisible":true,"preemptive":"capable"}
C_PICTURE:C286($1;$image;$0)
C_OBJECT:C1216($2;$params)

$image:=$1
$params:=$2

$template:=Folder:C1567(fk resources folder:K87:11).file("preview.svg")

$templateXml:=$template.getText()

PROCESS 4D TAGS:C816($templateXml;$svg;$image;$params)

  //SET TEXT TO PASTEBOARD($svg)

C_BLOB:C604($data)
CONVERT FROM TEXT:C1011($svg;"utf-8";$data)
BLOB TO PICTURE:C682($data;$image)

$0:=$image