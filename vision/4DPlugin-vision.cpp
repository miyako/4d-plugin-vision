/* --------------------------------------------------------------------------------
 #
 #  4DPlugin-vision.cpp
 #	source generated by 4D Plugin Wizard
 #	Project : vision
 #	author : miyako
 #	2020/12/31
 #  
 # --------------------------------------------------------------------------------*/

#include "4DPlugin-vision.h"

#pragma mark -

void PluginMain(PA_long32 selector, PA_PluginParameters params) {
    
	try
	{
        switch(selector)
        {
			// --- vision
            
			case 1 :
				vision_process_data(params);
				break;
            case 2 :
                vision_get_version(params);
                break;

        }

	}
	catch(...)
	{

	}
}

#pragma mark utilities

static void collection_push(PA_CollectionRef c, CFStringRef str) {

    if(str){
        CFIndex len = CFStringGetLength(str);
        std::vector<uint8_t> buf((len+1) * sizeof(PA_Unichar));
        CFStringGetCharacters(str, CFRangeMake(0, len), (UniChar *)&buf[0]);
        PA_Unistring _value = PA_CreateUnistring((PA_Unichar *)&buf[0]);
        PA_Variable v = PA_CreateVariable(eVK_Unistring);
        PA_SetStringVariable(&v, &_value);
        PA_SetCollectionElement(c, PA_GetCollectionLength(c), v);
//        the unistring belongs to the collection
//        PA_DisposeUnistring(&_value);
        PA_ClearVariable(&v);
    }
  
}

static void collection_push(PA_CollectionRef c, PA_ObjectRef value) {

    if (value) {
        PA_Variable v = PA_CreateVariable(eVK_Object);
        PA_SetObjectVariable(&v, value);
        PA_SetCollectionElement(c, PA_GetCollectionLength(c), v);
        PA_ClearVariable(&v);
    }
}

static void collection_push(PA_CollectionRef c, const char *value) {

    if (value) {
  
        CFStringRef str = CFStringCreateWithBytes(kCFAllocatorDefault,
                                                  (const UInt8 *)value, strlen(value),
                                                  kCFStringEncodingUTF8, true);
        if(str){
            collection_push(c, str);
            CFRelease(str);
        }        
    }
}

static void collection_push(PA_CollectionRef c, NSString *str) {
    collection_push(c, (CFStringRef)str);
}

#pragma mark params

static NSUInteger getMaxCandidateCount(PA_ObjectRef param) {
    
    NSUInteger maxCandidateCount = 1;
    
    if(param) {
        if(ob_is_defined(param, L"maxCandidateCount")) {
            NSUInteger value = ob_get_n(param, L"maxCandidateCount");
            if((value < 11) && (value > 0))
                maxCandidateCount = value;
        }
    }
    
    return maxCandidateCount;
}

static CGImagePropertyOrientation getOrientation(PA_ObjectRef param) {
    
    CGImagePropertyOrientation orientation = kCGImagePropertyOrientationUp;
    
    if(param) {
        if(ob_is_defined(param, L"orientation")) {
            CUTF8String _orientation;
            if(ob_get_s(param, L"orientation", &_orientation)) {
                if(_orientation == (const uint8_t *)"mirrored") {
                    orientation = kCGImagePropertyOrientationUpMirrored;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"down") {
                    orientation = kCGImagePropertyOrientationDown;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"downMirrored") {
                    orientation = kCGImagePropertyOrientationDownMirrored;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"leftMirrored") {
                    orientation = kCGImagePropertyOrientationLeftMirrored;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"right") {
                    orientation = kCGImagePropertyOrientationRight;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"rightMirrored") {
                    orientation = kCGImagePropertyOrientationRightMirrored;
                    goto exit;
                }
                if(_orientation == (const uint8_t *)"left") {
                    orientation = kCGImagePropertyOrientationLeft;
                    goto exit;
                }
            }
        }
    }
    
    exit:
    
    return orientation;
}

#pragma mark configure request

static void getParamsForRequest(PA_ObjectRef detect, VNRequest *request) {
    
    if(ob_is_defined(detect, L"preferBackgroundProcessing")) {
        request.preferBackgroundProcessing = ob_get_b(detect, L"preferBackgroundProcessing");
    }
    if(ob_is_defined(detect, L"usesCPUOnly")) {
        request.usesCPUOnly = ob_get_b(detect, L"usesCPUOnly");
    }
    
}

static void getParamsForImageRequest(PA_ObjectRef detect, VNImageBasedRequest *request) {
    
    PA_ObjectRef regionOfInterest = ob_get_o(detect, L"regionOfInterest");
    if(regionOfInterest) {
        CGRect rect;
        rect.origin.x = ob_get_n(regionOfInterest, L"x");
        rect.origin.y = ob_get_n(regionOfInterest, L"y");
        rect.size.width = ob_get_n(regionOfInterest, L"width");
        rect.size.height = ob_get_n(regionOfInterest, L"height");
        request.regionOfInterest = rect;
    }
}

static NSArray *createStringArrayForParam(PA_CollectionRef col) {
    NSMutableArray *arr = [[NSMutableArray alloc]init];
    PA_long32 len = PA_GetCollectionLength(col);
    for(PA_long32 i = 0; i < len; ++i) {
        PA_Variable v = PA_GetCollectionElement(col, i);
        if(PA_GetVariableKind(v) == eVK_Unistring) {
            PA_Unistring ustr = PA_GetStringVariable(v);
            if(ustr.fLength) {
                NSString *str = [[NSString alloc]initWithCharacters:(const unichar *)ustr.fString length:ustr.fLength];
                [arr addObject:str];
                [str release];
            }
        }
    }
    return arr;
}

API_AVAILABLE(macos(10.15))
static void getParamsForTextRequest(PA_ObjectRef detect, VNRecognizeTextRequest *request) {

    if(ob_is_defined(detect, L"minimumTextHeight")) {
        request.minimumTextHeight = ob_get_n(detect, L"minimumTextHeight");
    }
    if(ob_is_defined(detect, L"usesLanguageCorrection")) {
        request.usesLanguageCorrection = ob_get_b(detect, L"usesLanguageCorrection");
    }
    if(ob_is_defined(detect, L"recognitionLevel")) {
        request.recognitionLevel = (VNRequestTextRecognitionLevel)ob_get_n(detect, L"recognitionLevel");
    }
    PA_CollectionRef recognitionLanguages = ob_get_c(detect, L"recognitionLanguages");
    if(recognitionLanguages) {
        NSArray *arr = createStringArrayForParam(recognitionLanguages);
        request.customWords = arr;
        [arr release];
    }
    PA_CollectionRef customWords = ob_get_c(detect, L"customWords");
    if(customWords) {
        NSArray *arr = createStringArrayForParam(customWords);
        request.customWords = arr;
        [arr release];
    }
    
}

static void getParamsForTextRequest(PA_ObjectRef detect, VNDetectTextRectanglesRequest *request) {

    if(ob_is_defined(detect, L"reportCharacterBoxes")) {
        request.reportCharacterBoxes = ob_get_b(detect, L"reportCharacterBoxes");
    }

}

static void getParamsForLandmarkRequest(PA_ObjectRef detect, VNDetectFaceLandmarksRequest *request) {

    if(ob_is_defined(detect, L"constellation")) {
        if (@available(macOS 10.15, *)) {
            request.constellation = (VNRequestFaceLandmarksConstellation)ob_get_n(detect, L"constellation");
        } else {
            // Fallback on earlier versions
        }
    }

}

#pragma mark get result for observation

static bool targetContains(PA_ObjectRef param, NSString *target) {
    
    bool contains = false;
    
    if(param) {
        PA_CollectionRef targets = ob_get_c(param, L"targets");
        if(targets) {
            NSArray *arr = createStringArrayForParam(targets);
            NSPredicate *predicate = [NSPredicate predicateWithFormat:@"SELF LIKE %@", target];
            contains = [[arr filteredArrayUsingPredicate:predicate]count];
            [arr release];
        }
    }
    
    return contains;
}

static VNDetectBarcodesRequest *getBarcodesRequest(PA_ObjectRef param) {
    //VNDetectBarcodesRequest < VNImageBasedRequest < VNRequest
    VNDetectBarcodesRequest *request = nil;
    
    if(targetContains(param, @"barcode")) {
        request = [[VNDetectBarcodesRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
    }
       
    return request;
}

static VNDetectFaceRectanglesRequest *getFaceRectanglesRequest(PA_ObjectRef param) {
    //VNDetectFaceRectanglesRequest < VNImageBasedRequest < VNRequest
    VNDetectFaceRectanglesRequest *request = nil;
    
    if(targetContains(param, @"face")) {
        request = [[VNDetectFaceRectanglesRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
    }
 
    return request;
}

static VNDetectFaceLandmarksRequest *getFaceLandmarksRequest(PA_ObjectRef param) {
    //VNDetectFaceLandmarksRequest < VNImageBasedRequest < VNRequest
    VNDetectFaceLandmarksRequest *request = nil;
    
    if(targetContains(param, @"part")) {
        request = [[VNDetectFaceLandmarksRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
        getParamsForLandmarkRequest(param, request);
    }
 
    return request;
}

static VNDetectRectanglesRequest *getRectanglesRequest(PA_ObjectRef param) {
    //VNDetectRectanglesRequest < VNImageBasedRequest < VNRequest
    VNDetectRectanglesRequest *request = nil;

    if(targetContains(param, @"rect")) {
        request = [[VNDetectRectanglesRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
    }

    return request;
}

static VNDetectHorizonRequest *getHorizonRequest(PA_ObjectRef param) {
    //VNDetectHorizonRequest < VNImageBasedRequest < VNRequest
    VNDetectHorizonRequest *request = nil;
    
    if(targetContains(param, @"horizon")) {
        request = [[VNDetectHorizonRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
    }
  
    return request;
}

API_AVAILABLE(macos(10.15))
static VNDetectHumanRectanglesRequest *getHumanRectanglesRequest(PA_ObjectRef param) {
    //VNDetectHumanRectanglesRequest < VNImageBasedRequest < VNRequest
    VNDetectHumanRectanglesRequest *request = nil;
    
    if(targetContains(param, @"human")) {
        request = [[VNDetectHumanRectanglesRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
    }
    
    return request;
}

static VNDetectTextRectanglesRequest *getTextRectanglesRequest(PA_ObjectRef param) {
    //VNDetectTextRectanglesRequest < VNImageBasedRequest < VNRequest
    VNDetectTextRectanglesRequest *request = nil;
    
    if(targetContains(param, @"string")) {
        request = [[VNDetectTextRectanglesRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
        getParamsForTextRequest(param, request);
    }
  
    return request;
}

API_AVAILABLE(macos(10.15))
static VNRecognizeTextRequest *getTextRequest(PA_ObjectRef param) {
    //VNRecognizeTextRequest < VNImageBasedRequest < VNRequest
    VNRecognizeTextRequest *request = nil;
    
    if(targetContains(param, @"text")) {
        request = [[VNRecognizeTextRequest alloc]initWithCompletionHandler:^void(VNRequest *request, NSError *error){
            
        }];
        
        getParamsForRequest(param, request);
        getParamsForImageRequest(param, request);
        getParamsForTextRequest(param, request);
    }
    
    return request;
}

#pragma mark -

static void getResultsForObject(PA_ObjectRef result,
                                VNDetectedObjectObservation *observation) {
    
    if(observation) {
        CGRect rect = observation.boundingBox;
        ob_set_n(result, L"x", rect.origin.x);
        ob_set_n(result, L"y", 1-rect.size.height-rect.origin.y);
        ob_set_n(result, L"width", rect.size.width);
        ob_set_n(result, L"height", rect.size.height);
        ob_set_n(result, L"confidence", observation.confidence);
    }
    
}

static void getResultsForHorizon(PA_ObjectRef result, VNHorizonObservation *observation) {
    
    if(observation) {
                
        ob_set_n(result, L"angle", observation.angle);
        CGAffineTransform transform = observation.transform;
        ob_set_n(result, L"a", transform.a);
        ob_set_n(result, L"b", transform.b);
        ob_set_n(result, L"c", transform.c);
        ob_set_n(result, L"d", transform.d);
        ob_set_n(result, L"tx", transform.tx);
        ob_set_n(result, L"ty", transform.ty);
    }
    
}

API_AVAILABLE(macos(10.15))
static void getResultsForText(PA_ObjectRef result,
                              VNRecognizedTextObservation *observation,
                              NSUInteger maxCandidateCount) {
    
    if(observation) {
        
        getResultsForObject(result, observation);
        
        NSArray<VNRecognizedText*> *topCandidates = [observation topCandidates:maxCandidateCount];
        for(VNRecognizedText *candidate in topCandidates) {
            ob_set_s(result, L"string", (const char *)[candidate.string UTF8String]);
            ob_set_n(result, L"confidence", candidate.confidence);
        }
    }
}

static void getResultsForText(PA_ObjectRef result,
                              VNTextObservation *observation) {
    
    if(observation) {
        
        getResultsForObject(result, observation);
        
        NSArray<VNRectangleObservation *> *characterBoxes = [observation characterBoxes];
        if(characterBoxes) {
            PA_CollectionRef characters = PA_CreateCollection();
            for(VNRectangleObservation *characterBox in characterBoxes) {
                PA_ObjectRef character = PA_CreateObject();
                getResultsForObject(character, characterBox);
                collection_push(characters, character);
            }
            ob_set_c(result, L"characters", characters);
        }
    }
}

static void getResultsForBarcode(PA_ObjectRef result, VNBarcodeObservation *observation) {
    
    if(observation) {
        
        getResultsForObject(result, observation);
        
        VNBarcodeSymbology symbology = observation.symbology;
        NSString *payloadStringValue = observation.payloadStringValue;
        ob_set_s(result, L"symbology", (const char *)[symbology UTF8String]);
        ob_set_s(result, L"payloadStringValue", (const char *)[payloadStringValue UTF8String]);
    }
    
}

static void getResultsForFace(PA_ObjectRef result, VNFaceObservation *observation) {
   
    if (@available(macOS 10.14, *)) {
        if(observation) {
            
            getResultsForObject(result, observation);

            VNFaceLandmarks2D *landmarks = observation.landmarks;
            if(landmarks) {
                
                NSArray *parts = @[
                    @"leftPupil",
                    @"rightPupil",
                    @"leftEyebrow",
                    @"rightEyebrow",
                    @"leftEye",
                    @"rightEye",
                    @"innerLips", @"outerLips",
                    @"nose", @"noseCrest",
                    @"medianLine",
                    @"faceContour",
                    @"allPoints"
                ];
                
                PA_CollectionRef col = PA_CreateCollection();
                
                CGFloat height = observation.boundingBox.size.height;
                
                for(NSString *part in parts) {
                    
                    PA_ObjectRef o = PA_CreateObject();
                    
                    VNFaceLandmarkRegion2D *region = [landmarks valueForKey:part];
                    const CGPoint *pts = region.normalizedPoints;
                    NSUInteger len = region.pointCount;
                    PA_CollectionRef points = PA_CreateCollection();
                    
                    for(NSUInteger i = 0; i < len; ++i) {
                        CGPoint p = *pts;
                        NSString *xy = [NSString stringWithFormat:@"%lf,%lf", p.x, 1-p.y];
                        collection_push(points, xy);
                        pts++;
                    }
                    ob_set_c(o, L"points", points);
                    ob_set_s(o, L"type", (const char *)[part UTF8String]);
                    collection_push(col, o);
                }
                
                
                ob_set_c(result, L"parts", col);
            }
            
            ob_set_n(result, L"roll", [observation.roll doubleValue]);
            ob_set_n(result, L"yaw", [observation.yaw doubleValue]);
            if (@available(macOS 10.15, *)) {
                ob_set_n(result, L"faceCaptureQuality", [observation.faceCaptureQuality doubleValue]);
            }
        }
    }
}

#pragma mark get result for request

static void getResultsForRects(PA_ObjectRef returnValue, VNDetectRectanglesRequest *request) {
    
    PA_CollectionRef barcodes = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNRectangleObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForObject(result, observation);
            
            collection_push(barcodes, result);
        }
    }
    
    ob_set_c(returnValue, L"barcodes", barcodes);
}

static void getResultsForBarcodes(PA_ObjectRef returnValue, VNDetectBarcodesRequest *request) {
    
    PA_CollectionRef barcodes = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNBarcodeObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForBarcode(result, observation);
            
            collection_push(barcodes, result);
        }
    }
    
    ob_set_c(returnValue, L"barcodes", barcodes);
}

static void getResultsForHorizon(PA_ObjectRef returnValue, VNDetectHorizonRequest *request) {
    
    PA_CollectionRef barcodes = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNHorizonObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForHorizon(result, observation);
            
            collection_push(barcodes, result);
        }
    }
    
    ob_set_c(returnValue, L"barcodes", barcodes);
}


static void getResultsForTexts(PA_ObjectRef returnValue, VNDetectTextRectanglesRequest *request) {
    
    PA_CollectionRef texts = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNTextObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForText(result, observation);
            
            collection_push(texts, result);
        }
    }
    
    ob_set_c(returnValue, L"texts", texts);
}

static void getResultsForFaces(PA_ObjectRef returnValue, VNDetectFaceRectanglesRequest *request) {
    
    PA_CollectionRef faces = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNFaceObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForFace(result, observation);
            
            collection_push(faces, result);
        }
    }
    
    ob_set_c(returnValue, L"faces", faces);
}

static void getResultsForFaceLandmarks(PA_ObjectRef returnValue, VNDetectFaceLandmarksRequest *request) {
    
    PA_CollectionRef parts = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNFaceObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForFace(result, observation);
            
            collection_push(parts, result);
        }
    }
    
    ob_set_c(returnValue, L"faceLandmarks", parts);
}

API_AVAILABLE(macos(10.15))
static void getResultsForTexts(PA_ObjectRef returnValue, VNRecognizeTextRequest *request, NSUInteger maxCandidateCount) {
    
    PA_CollectionRef texts = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNRecognizedTextObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForText(result, observation, maxCandidateCount);
            
            collection_push(texts, result);
        }
    }
    
    ob_set_c(returnValue, L"recognizedTexts", texts);
}

API_AVAILABLE(macos(10.15))
static void getResultsForHumans(PA_ObjectRef returnValue, VNDetectHumanRectanglesRequest *request) {
    
    PA_CollectionRef humans = PA_CreateCollection();
    
    if(request) {
        
        NSArray *results = [request results];
        
        for(VNDetectedObjectObservation *observation in results) {
            
            PA_ObjectRef result = PA_CreateObject();

            getResultsForObject(result, observation);
            
            collection_push(humans, result);
        }
    }
    
    ob_set_c(returnValue, L"humans", humans);
}

#pragma mark API

void vision_get_version(PA_PluginParameters params) {
    //animal,barcode,text
    PA_ObjectRef returnValue = PA_CreateObject();
    ob_set_b(returnValue, L"success", false);
    BOOL success = false;
    NSError *error = nil;
    NSUInteger revision = 1;
    NSArray *supportedLanguages = nil;
    
    if (@available(macOS 10.15, *)) {
        
        PA_ObjectRef animal = PA_CreateObject();
        revision = [VNRecognizeAnimalsRequest currentRevision];
        NSArray *knownAnimalIdentifiersForRevision = [VNRecognizeAnimalsRequest
                                                      knownAnimalIdentifiersForRevision:revision
                                                      error:&error];
        if(!error) {
            success = true;
            PA_CollectionRef knownAnimalIdentifiers = PA_CreateCollection();
            for(VNAnimalIdentifier animalIdentifier in knownAnimalIdentifiersForRevision) {
                collection_push(knownAnimalIdentifiers, animalIdentifier);
            }
            ob_set_c(animal, L"knownAnimalIdentifiers", knownAnimalIdentifiers);
            ob_set_o(returnValue, L"animal", animal);
        }

    }
    
    PA_ObjectRef barcode = PA_CreateObject();
    PA_CollectionRef symbologies = PA_CreateCollection();
    NSArray<VNBarcodeSymbology> *supportedSymbologies = [VNDetectBarcodesRequest supportedSymbologies];
    for(VNBarcodeSymbology symbology in supportedSymbologies) {
        collection_push(symbologies, symbology);
    }
    ob_set_c(barcode, L"symbologies", symbologies);
    ob_set_o(returnValue, L"barcode", barcode);
    
    if (@available(macOS 10.15, *)) {
                
        PA_ObjectRef text = PA_CreateObject();
        PA_ObjectRef languages = PA_CreateObject();
        revision = [VNRecognizeTextRequest currentRevision];

        supportedLanguages = [VNRecognizeTextRequest
                              supportedRecognitionLanguagesForTextRecognitionLevel:VNRequestTextRecognitionLevelAccurate
                              revision:revision
                              error:&error];
        
        if(!error) {
            PA_CollectionRef _languages = PA_CreateCollection();
            for(NSString *language in supportedLanguages) {
                collection_push(_languages, language);
            }
            ob_set_c(languages, L"accurate", _languages);
        }

        supportedLanguages = [VNRecognizeTextRequest
                              supportedRecognitionLanguagesForTextRecognitionLevel:VNRequestTextRecognitionLevelFast
                              revision:revision
                              error:&error];
        
        if(!error) {
            PA_CollectionRef _languages = PA_CreateCollection();
            for(NSString *language in supportedLanguages) {
                collection_push(_languages, language);
            }
            ob_set_c(languages, L"fast", _languages);
        }
        
        ob_set_o(text, L"languages", languages);
        ob_set_o(returnValue, L"text", text);
    }
    
    ob_set_b(returnValue, L"success", success);
    PA_ReturnObject(params, returnValue);
}

static NSData *createDataParameter(PA_PluginParameters params, short index) {
    
    NSData *data = nil;
    
    void *bytes = NULL;
    PA_long32 len = PA_GetBlobParameter(params, 1, bytes);
    
    if(len) {
        std::vector<uint8_t>buf(len);
        bytes = &buf[0];
        PA_GetBlobParameter(params, 1, bytes);
        data = [[NSData alloc]initWithBytes:(const void *)bytes length:(NSUInteger)len];
    }
    
    return data;
}

void vision_process_data(PA_PluginParameters params) {

    PA_ObjectRef returnValue = PA_CreateObject();
    ob_set_b(returnValue, L"success", false);
    
    NSData *imageData = createDataParameter(params, 1);
    PA_ObjectRef param = PA_GetObjectParameter(params, 2);
    
    if(imageData) {
        
        CGImagePropertyOrientation orientation = getOrientation(param);
        NSUInteger maxCandidateCount = getMaxCandidateCount(param);
        
        VNImageRequestHandler *requestHandler = [[VNImageRequestHandler alloc]
                                                initWithData:imageData
                                                 orientation:orientation
                                                 options:[NSDictionary dictionary]];

        NSMutableArray *requests = [[NSMutableArray alloc]init];
        
        VNDetectFaceRectanglesRequest *faceRequest = getFaceRectanglesRequest(param);
        VNDetectTextRectanglesRequest *textRequest = getTextRectanglesRequest(param);
        VNDetectHorizonRequest *horizonRequest = getHorizonRequest(param);
        VNDetectBarcodesRequest *barcodeRequest = getBarcodesRequest(param);
        VNDetectRectanglesRequest *rectRequest = getRectanglesRequest(param);
        VNDetectFaceLandmarksRequest *partRequest = getFaceLandmarksRequest(param);
        
        id recognizeTextRequest = nil;
        if (@available(macOS 10.15, *)) {
            recognizeTextRequest = getTextRequest(param);
        }
        
        id humanRequest = nil;
        if (@available(macOS 10.15, *)) {
            humanRequest = getHumanRectanglesRequest(param);
        }

        if(faceRequest) {
            [requests addObject:faceRequest];
        }
        if(partRequest) {
            [requests addObject:partRequest];
        }
        if(textRequest) {
            [requests addObject:textRequest];
        }
        if(horizonRequest) {
            [requests addObject:horizonRequest];
        }
        if(barcodeRequest) {
            [requests addObject:barcodeRequest];
        }
        if(rectRequest) {
            [requests addObject:rectRequest];
        }
        if(recognizeTextRequest) {
            [requests addObject:recognizeTextRequest];
        }
        if(humanRequest) {
            [requests addObject:humanRequest];
        }
 
        NSError *error;
        BOOL success = [requestHandler performRequests:requests error:&error];
                
        if(!success) {
            ob_set_n(returnValue, L"code", [error code]);
            ob_set_s(returnValue, L"description", [[error localizedDescription]UTF8String]);
        }else {
            
            if(partRequest) getResultsForFaceLandmarks(returnValue, partRequest);
            if(faceRequest) getResultsForFaces(returnValue, faceRequest);
            if(textRequest) getResultsForTexts(returnValue, textRequest);
            if(horizonRequest) getResultsForHorizon(returnValue, horizonRequest);
            if(barcodeRequest) getResultsForBarcodes(returnValue, barcodeRequest);
            if(rectRequest) getResultsForRects(returnValue, rectRequest);

            if (@available(macOS 10.15, *)) {
                if(humanRequest) getResultsForHumans(returnValue,humanRequest);
            }
            
            if (@available(macOS 10.15, *)) {
                if(recognizeTextRequest) getResultsForTexts(returnValue,recognizeTextRequest, maxCandidateCount);
            }
            
        }

        ob_set_b(returnValue, L"success", success);

        if(partRequest) [partRequest release];
        if(faceRequest) [faceRequest release];
        if(textRequest) [textRequest release];
        if(horizonRequest) [horizonRequest release];
        if(barcodeRequest) [barcodeRequest release];
        if(rectRequest) [rectRequest release];
        
        if(recognizeTextRequest) [recognizeTextRequest release];
        if(humanRequest) [humanRequest release];
        
        [requests release];
        [requestHandler release];
        
        [imageData release];
    }
    
    PA_ReturnObject(params, returnValue);
}
