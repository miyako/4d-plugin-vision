![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm&color=blue)
![version](https://img.shields.io/badge/version-17%2B-3E8B93)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-vision)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-vision/total)

# 4d-plugin-vision

The `vision` plugin exposes Apple's **Vision** framework (`Vision.framework`, macOS) to 4D as two commands: one that runs a configurable set of image-detection requests (faces, text, barcodes, rectangles, the horizon line, human figures, animals) against a single image and returns everything it found as an `Object`, and one that reports what the current OS/Vision revision actually supports (recognized languages, barcode symbologies, known animal identifiers). All detection is done in-process via Apple's Vision APIs — no network calls, no external service.

| Command | Returns | Purpose |
|---|---|---|
| [`vision process data`](#vision-process-data) | Object | Run one or more Vision detection requests against an image and return the results |
| [`vision get version`](#vision-get-version) | Object | Report supported barcode symbologies, text-recognition languages, and known animal identifiers for the current OS |

**Platforms:** macOS only. The plugin is built directly against `Cocoa` and `Vision.framework`; there is no Windows implementation.

---

## Requirements & platform notes

- **macOS 10.13+ minimum**, for the Vision framework itself. Several individual features need newer OS versions — see the table below. On an older OS, the affected target is silently skipped rather than causing an error (the corresponding result key just won't appear — see next point).
- **The result object only contains keys for targets you actually requested — there's no placeholder empty array for a target you didn't ask for, or one Vision doesn't support on the current OS.** If `targets` is empty, contains only unrecognized strings, or names a target unavailable on the running OS, that target's key is simply absent from the response.
- **`targets` values are matched case-sensitively and exactly** (no wildcards, no partial matches) against: `"face"`, `"part"`, `"string"`, `"text"`, `"horizon"`, `"barcode"`, `"rect"`, `"human"`, `"animal"`.
- Per-target minimum OS versions:

  | Target | Result key | Minimum macOS |
  |---|---|---|
  | `"face"` | `faces` | 10.13 (roll/yaw values need 10.14; `faceCaptureQuality` needs 10.15) |
  | `"part"` | `faceLandmarks` | 10.13 (`constellation` option needs 10.15) |
  | `"string"` | `texts` | 10.13 |
  | `"rect"` | `rects` | 10.13 |
  | `"horizon"` | `horizons` | 10.13 |
  | `"barcode"` | `barcodes` | 10.13 |
  | `"text"` | `recognizedTexts` | 10.15 |
  | `"human"` | `humans` | 10.15 |
  | `"animal"` | `animals` | 10.15 |

- **On failure, the response has no result keys at all** — just `success: false`, `code` (the underlying `NSError` code), and `description` (its localized message). This happens when Apple's `VNImageRequestHandler` itself fails (e.g. `imageData` isn't valid image data for the given `orientation`), not per-target.
- If `imageData` is empty or can't be read as a blob at all, the response is just `{success: false}` — no `code`/`description`, because no Vision request was ever attempted.
- **`preferBackgroundProcessing` and `usesCPUOnly`** (both Boolean) apply to *every* request type and are optional.
- **`regionOfInterest`** (Object: `x`, `y`, `width`, `height`, all Numbers 0–1, normalized) also applies to every request type and is optional. Omit it to search the whole image.

---

## vision process data

### Syntax

```4d
vision process data ( imageData : Blob ; params : Object ) -> Object
```

| Parameter | Type | Description |
|---|---|---|
| `imageData` | Blob | The image's raw bytes (e.g. from `DOCUMENT TO BLOB`). Read only — the command doesn't modify it. |
| `params` | Object | Detection options — see below. Read only. |
| Result | Object | `success` (Boolean) plus one key per requested, supported target (see the table in [Requirements & platform notes](#requirements--platform-notes)), or `code`/`description` on failure. |

### `params` object reference

| Property | Type | Applies to | Description |
|---|---|---|---|
| `targets` | Collection of Text | all | Which detectors to run. See the exact-match list above. Required in practice — omit it (or use unrecognized strings) and no detector runs at all. |
| `orientation` | Text | all | One of `"up"` (default), `"mirrored"`, `"down"`, `"downMirrored"`, `"leftMirrored"`, `"right"`, `"rightMirrored"`, `"left"`. Any other value (or omitted) falls back to `"up"`. |
| `preferBackgroundProcessing` | Boolean | all | Passed straight through to each `VNRequest`. Optional. |
| `usesCPUOnly` | Boolean | all | Passed straight through to each `VNRequest`. Optional. |
| `regionOfInterest` | Object `{x;y;width;height}` | all | Normalized (0–1) rectangle to restrict detection to. Optional — defaults to the whole image if omitted. |
| `maxCandidateCount` | Number | `"text"` only | How many OCR candidates Vision considers per text region before the plugin returns the single best one, as `string`/`confidence` on that result. Range 1–10; values outside that range (or `0`, or omitted) fall back to `1`. Raising this does **not** return more than one string per detected text region — it only lets Vision consider more internal candidates when picking its best answer. |
| `reportCharacterBoxes` | Boolean | `"string"` only | If `true`, each result in `texts` also gets a `characters` sub-collection (one entry per character, each with its own bounding box). |
| `minimumTextHeight` | Number | `"text"` only | Normalized (0–1) minimum height a text region must have to be considered. |
| `usesLanguageCorrection` | Boolean | `"text"` only | Enables Vision's built-in language-model correction pass. |
| `recognitionLevel` | Number | `"text"` only | `0` = accurate, `1` = fast, per Apple's `VNRequestTextRecognitionLevel` enum. Check the Vision framework header for your SDK if you need to confirm these values for a specific OS version. |
| `recognitionLanguages` | Collection of Text | `"text"` only | BCP-47 language codes (e.g. `"en-US"`). Per the plugin's own test comment, only `"en-US"` was supported as of macOS Catalina — check `vision get version`'s `text.languages` output for what your target OS actually supports. |
| `customWords` | Collection of Text | `"text"` only | Supplementary vocabulary fed into Vision's language correction. |
| `constellation` | Number | `"part"` only, macOS 10.15+ | Selects Vision's `VNRequestFaceLandmarksConstellation` landmark density (e.g. 65-point vs. 76-point). Check Apple's Vision framework header for the exact integer values on your target OS rather than assuming — this review didn't need to pin them down. |

### Result object reference, by target

**`"face"` → `faces`** (also produced, with landmark data, by `"part"` → `faceLandmarks` below): a Collection of Objects, each:

| Property | Type | Description |
|---|---|---|
| `x`, `y`, `width`, `height` | Number | Normalized bounding box, top-left origin. |
| `confidence` | Number | Detection confidence. |
| `roll`, `yaw` | Number | Head pose, macOS 10.14+ (`0` if Vision didn't compute a value). |
| `faceCaptureQuality` | Number | macOS 10.15+ only (`0` if not computed). |
| `parts` | Collection of Object | **Only present when the request also computed landmarks** — i.e. always present under `"part"`/`faceLandmarks`, never present under plain `"face"`/`faces`. Each entry: `type` (Text — one of `leftPupil`, `rightPupil`, `leftEyebrow`, `rightEyebrow`, `leftEye`, `rightEye`, `innerLips`, `outerLips`, `nose`, `noseCrest`, `medianLine`, `faceContour`, `allPoints`) and `points` (Collection of Text, each `"x,y"` in normalized, top-left-origin coordinates). |

**`"string"` → `texts`**: Collection of Objects, each `x`/`y`/`width`/`height`/`confidence` plus, only if `reportCharacterBoxes` was `true`, a `characters` sub-collection of the same `x`/`y`/`width`/`height`/`confidence` shape, one per character.

**`"text"` → `recognizedTexts`** (macOS 10.15+): Collection of Objects, each `x`/`y`/`width`/`height` plus `string` (Text, the best OCR guess for that region) and `confidence` (Number — note this is the *text candidate's* confidence, not the region-detection confidence).

**`"horizon"` → `horizons`**: Collection of Objects, each `angle` (Number, radians) plus the affine transform describing it: `a`, `b`, `c`, `d`, `tx`, `ty`.

**`"barcode"` → `barcodes`**: Collection of Objects, each `x`/`y`/`width`/`height`/`confidence` plus `symbology` (Text, e.g. `"VNBarcodeSymbologyQR"`) and `payloadStringValue` (Text — empty string if Vision decoded a payload that isn't representable as text).

**`"rect"` → `rects`**: Collection of Objects, each just `x`/`y`/`width`/`height`/`confidence`.

**`"human"` → `humans`** (macOS 10.15+): Collection of Objects, each just `x`/`y`/`width`/`height`/`confidence`.

**`"animal"` → `animals`** (macOS 10.15+): Collection of Objects, each `x`/`y`/`width`/`height`/`confidence` plus whatever identifying properties Vision's animal observation exposes for the detected animal.

### Example

From the plugin's own test method (`TEST_animal.4dm`):

```4d
$file:=Folder(fk resources folder).file("creatures.jpg")

DOCUMENT TO BLOB($file.platformPath;$imageData)

$params:=New object
$params.targets:=New collection("animal";"human")

  //all targets
$params.preferBackgroundProcessing:=True
$params.usesCPUOnly:=True
$params.orientation:="up"
$params.regionOfInterest:=New object
$params.regionOfInterest.x:=0
$params.regionOfInterest.y:=0
$params.regionOfInterest.width:=1
$params.regionOfInterest.height:=1

$status:=vision process data ($imageData;$params)

If ($status.success)
	
	BLOB TO PICTURE($imageData;$image)
	
	C_OBJECT($animal)
	For each ($animal;$status.animals)
		$animal.stroke:="yellow"
		$animal.fill:="orange"
		$animal.fillOpacity:=0.3
	End for each 
	
	C_OBJECT($human)
	For each ($human;$status.humans)
		$human.stroke:="yellow"
		$human.fill:="red"
		$human.fillOpacity:=0.3
	End for each 
	
	$image:=add_highlights ($image;$status)
	
	SET PICTURE TO PASTEBOARD($image)
	
End if 
```

From the plugin's own test method (`TEST_text.4dm`), showing the full text/OCR option set:

```4d
$params:=New object
$params.targets:=New collection("string"; "barcode"; "text")  //text=recognizeText

//string
$params.reportCharacterBoxes:=True

//text
$params.maxCandidateCount:=1
$params.minimumTextHeight:=0
$params.usesLanguageCorrection:=False
$params.recognitionLevel:=0
$params.recognitionLanguages:=New collection("en-US")  //only US English is supported as of Catalina
$params.customWords:=New collection("4D")

$status:=vision process data($imageData; $params)
```

A minimal call requesting a single target:

```4d
DOCUMENT TO BLOB(Folder(fk resources folder).file("photo.jpg").platformPath;$imageData)

$params:=New object
$params.targets:=New collection("barcode")

$status:=vision process data($imageData;$params)

If ($status.success)
	For each ($barcode;$status.barcodes)
		ALERT($barcode.symbology+": "+$barcode.payloadStringValue)
	End for each 
Else 
	ALERT("Vision error "+String($status.code)+": "+$status.description)
End if 
```

---

## vision get version

### Syntax

```4d
vision get version -> Object
```

| Parameter | Type | Description |
|---|---|---|
| Result | Object | `success` (Boolean), `barcode` (Object), and — macOS 10.15+ only — `animal` and `text` (Objects). |

### Description

- `success` reflects whether *any* section that was actually attempted on the current OS succeeded. The `barcode` section always runs and always contributes to `success`; the `animal` and `text` sections only run (and only affect `success`) on macOS 10.15+.
- `barcode.symbologies`: Collection of Text — every `VNBarcodeSymbology` name (e.g. `"VNBarcodeSymbologyQR"`) Vision's `VNDetectBarcodesRequest` supports on this OS. Always present.
- `animal.knownAnimalIdentifiers` (macOS 10.15+ only, and only if Apple's API call itself didn't error): Collection of Text — animal identifiers (e.g. `"Cat"`, `"Dog"`) `VNRecognizeAnimalsRequest` can currently recognize.
- `text.languages.accurate` / `text.languages.fast` (macOS 10.15+ only, each present independently of the other, only if its own API call didn't error): Collection of Text — BCP-47 language codes `VNRecognizeTextRequest` supports for that recognition level on this OS.

### Example

From the plugin's own test method (`TEST_version.4dm`), including the comment documenting a real observed result on macOS 10.15+:

```4d
$info:=vision get version 

/*
animals support: 10.15 or later
{
success:true,
animals:{knownAnimalIdentifiers:[Cat,Dog]}
symbologies:[VNBarcodeSymbologyAztec,VNBarcodeSymbologyCode128,VNBarcodeSymbologyCode39,VNBarcodeSymbologyCode39Checksum,VNBarcodeSymbologyCode39FullASCII,VNBarcodeSymbologyCode39FullASCIIChecksum,VNBarcodeSymbologyCode93,VNBarcodeSymbologyCode93i,VNBarcodeSymbologyDataMatrix,VNBarcodeSymbologyEAN13,VNBarcodeSymbologyEAN8,VNBarcodeSymbologyI2of5,VNBarcodeSymbologyI2of5Checksum,VNBarcodeSymbologyITF14,VNBarcodeSymbologyPDF417,VNBarcodeSymbologyQR,VNBarcodeSymbologyUPCE]
}
*/
```

A typical use — checking support before calling `vision process data`:

```4d
$info:=vision get version

If ($info.success)
	If ($info.text.languages.accurate.indexOf("en-US")>=0)
		//safe to request recognitionLanguages:=New collection("en-US")
	End if 
End if 
```

---

## Reference helper method: add_highlights

The plugin's test suite ships (and every one of its own sample methods calls) a project method that overlays a `vision process data` result onto the source image as a visual highlight — face boxes, barcode outlines, text boxes, and so on — by driving an SVG template through `PROCESS 4D TAGS`.

**`add_highlights ( image : Picture ; result : Object ) -> Picture`**

| Parameter | Type | Description |
|---|---|---|
| `image` | Picture | The source image (e.g. from `BLOB TO PICTURE` on the same blob you passed to `vision process data`). |
| `result` | Object | The Object returned by `vision process data` — typically after adding your own `stroke`/`fill`/`fillOpacity` properties onto its sub-collections, as shown in every sample above. |
| Result (`$0`) | Picture | The source image with highlight overlays burned in. |

Verbatim from the plugin's own project method (`add_highlights.4dm`):

```4d
//%attributes = {"invisible":true,"preemptive":"capable"}
C_PICTURE($1;$image;$0)
C_OBJECT($2;$params)

$image:=$1
$params:=$2

$template:=Folder(fk resources folder).file("preview.svg")

$templateXml:=$template.getText()

PROCESS 4D TAGS($templateXml;$svg;$image;$params)

C_BLOB($data)
CONVERT FROM TEXT($svg;"utf-8";$data)
BLOB TO PICTURE($data;$image)

$0:=$image
```

This method expects an SVG template (`preview.svg`, shipped in the plugin's resources folder) that references the same property names shown in the samples above (`stroke`, `fill`, `fillOpacity`, and each target's own sub-collection name) — it's not part of the plugin's compiled command surface, just glue code the samples reuse, and you're free to write your own instead.

### Full worked example (faces + landmarks + OCR)

From the plugin's own test method (`TEST_faces.4dm`):

```4d
$file:=Folder(fk resources folder).file("faces.jpg")

DOCUMENT TO BLOB($file.platformPath;$imageData)

$params:=New object

$params.targets:=New collection("part";"text")

$status:=vision process data ($imageData;$params)

If ($status.success)
	
	BLOB TO PICTURE($imageData;$image)
	
	C_OBJECT($part;$faceLandmark)
	C_BLOB($data)
	PICTURE PROPERTIES($image;$imageWidth;$imageHeight)
	
	For each ($faceLandmark;$status.faceLandmarks)
		$faceLandmark.stroke:="yellow"
		$faceLandmark.fill:="red"
		$faceLandmark.fillOpacity:=0.3
		For each ($parts;$faceLandmark.parts)
			$parts.points:=$parts.points.join(" ")
			$parts.stroke:="white"
		End for each 
	End for each 
	
	C_OBJECT($text)
	For each ($text;$status.recognizedTexts)
		$text.stroke:="yellow"
		$text.fill:="green"
		$text.fillOpacity:=0.3
	End for each 
	
	$image:=add_highlights ($image;$status)
	
	SET PICTURE TO PASTEBOARD($image)
	
End if 
```

---

## Error handling & troubleshooting

- **`success: false` with no other keys at all** means `imageData` was empty or unreadable as a blob — the command never even attempted a Vision request. Check that your `DOCUMENT TO BLOB` (or equivalent) call actually populated the blob before calling `vision process data`.
- **`success: false` with `code`/`description`** means Apple's `VNImageRequestHandler` rejected the image data itself (e.g. corrupt/unsupported image format, or an `orientation` mismatch) — `description` is Apple's own localized error text, useful to surface directly to the user or log.
- **A target you requested doesn't show up in the result at all** — this is normal, not a failure. It means either the target string didn't exactly match one of the recognized values (check spelling/case), or the target needs macOS 10.15+ and you're on an older OS. It does *not* mean nothing was found — an empty Collection would mean that; a missing key means the request never ran.
- **Requesting `"text"` with `maxCandidateCount` > 1 doesn't give you multiple strings per region.** Each `recognizedTexts` entry still has exactly one `string`/`confidence` pair — the best one Vision picked after considering that many internal candidates. If you need to inspect alternate candidates yourself, that isn't exposed through this command.
- **`recognitionLanguages` may be more restrictive than you expect.** Per the plugin's own test comment, only `en-US` was supported as of macOS Catalina for `VNRecognizeTextRequest`. Call `vision get version` and check `text.languages.accurate`/`text.languages.fast` for what your OS actually supports before setting this.
- **`payloadStringValue` on a barcode result can be an empty string**, not necessarily the barcode's full payload — this happens when Vision decoded a barcode whose payload isn't representable as text.
- **`roll`, `yaw`, and `faceCaptureQuality` come back as `0` rather than being omitted** when Vision didn't compute a value for a given face (rather than the key being absent) — don't treat `0` as a confident "no rotation"/"low quality" reading without also checking whether the underlying OS version/request supports that field at all (see the per-target OS table above).

---

## Quick reference

```4d
// Detect + highlight
DOCUMENT TO BLOB($file.platformPath;$imageData)
$params:=New object
$params.targets:=New collection("face";"barcode";"text")
$status:=vision process data($imageData;$params)
If ($status.success)
	BLOB TO PICTURE($imageData;$image)
	$image:=add_highlights($image;$status)
	SET PICTURE TO PASTEBOARD($image)
Else 
	ALERT("Vision error "+String($status.code)+": "+$status.description)
End if 

// Capability check
$info:=vision get version
If ($info.success)
	$symbologies:=$info.barcode.symbologies
	$languages:=$info.text.languages.accurate  // macOS 10.15+
	$animals:=$info.animal.knownAnimalIdentifiers  // macOS 10.15+
End if 
```
