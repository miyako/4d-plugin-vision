![platform](https://img.shields.io/static/v1?label=platform&message=osx-64&color=blue)
![version](https://img.shields.io/badge/version-17%2B-3E8B93)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-vision)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-vision/total)

# 4d-plugin-vision
Use [Vision](https://developer.apple.com/documentation/vision?language=objc) API (macOS).

### Syntax

```4d
$file:=Folder(fk resources folder).file("faces.jpg")
DOCUMENT TO BLOB($file.platformPath;$imageData)
$params.targets:=New collection("part";"text")
$status:=vision process data ($imageData;$params)
```

#### possible targets:

* face
* part (face landmarks=facial features)
* text (OCR)
* string (characters)
* rect
* horizon
* barcode
* human
* animal

#### About OCR by Vision

The plugin is configured to target 10.13 minimum, but API availability is progressive.

##### 10.14 or above

* faceLandmark

##### 10.15 or above

* faceLandmark > faceCaptureQuality
* recognizeText (OCR, en-US only)
* human
* recognizeAnimal (dog or cat only)

To use on v17, move manifest.json to contents.

* [Text example](https://github.com/miyako/4d-plugin-vision/blob/main/vision/test/Project/Sources/Methods/TEST_text.4dm)

<img src="https://user-images.githubusercontent.com/1725068/103431450-50494200-4c13-11eb-8d90-1e6690268c4e.png" width="400" />

* [Faces example](https://github.com/miyako/4d-plugin-vision/blob/main/vision/test/Project/Sources/Methods/TEST_faces.4dm)

<img src="https://user-images.githubusercontent.com/1725068/103431530-a36fc480-4c14-11eb-9f6f-45864cb60a7e.jpg" width="400" />

* [Animal example](https://github.com/miyako/4d-plugin-vision/blob/main/vision/test/Project/Sources/Methods/TEST_animal.4dm)

<img src="https://user-images.githubusercontent.com/1725068/103433511-74b61600-4c35-11eb-9cd9-a1ddbc599c01.png" width="400" />
