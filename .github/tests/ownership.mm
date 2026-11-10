#include "4DPlugin-vision.cpp"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <cassert>
#include <cstdlib>
#include <cstring>
#include <map>
#include <set>

extern "C" Call4DProcPtr gCall4D;

using Text = std::basic_string<PA_Unichar>;

struct Node {
    int refs = 1;
    std::map<Text, PA_Variable> properties;
    std::vector<PA_Variable> elements;
};

static std::set<PA_Unichar *> strings;
static std::set<Node *> nodes;
static std::map<PA_Handle, size_t> handles;
static bool allocatedEmpty;
static bool failRead;
static size_t clears;

static void check(bool condition, const char *message) {
    if(!condition) {
        std::cerr << "ownership assertion: " << message << "\n";
        std::exit(1);
    }
}

static Text text(const char16_t *value) {
    Text result;
    while(*value) result.push_back(*value++);
    return result;
}

static PA_Unistring makeString(const Text &value) {
    PA_Unistring result = {};
    result.fLength = static_cast<PA_long32>(value.size());
    if(!value.empty() || allocatedEmpty) {
        result.fString = new PA_Unichar[value.size() + 1];
        std::copy(value.begin(), value.end(), result.fString);
        result.fString[value.size()] = 0;
        PA_Unichar *buffer = result.fString;
        check(strings.insert(buffer).second, "unique string allocation");
    }
    return result;
}

static Text readString(PA_Unistring value) {
    PA_Unichar *buffer = value.fString;
    if(value.fString) {
        check(strings.count(buffer), "read live string");
        check(value.fString[value.fLength] == 0, "UTF-16 terminator");
        return Text(value.fString, value.fLength);
    }
    check(value.fLength == 0, "null string is empty");
    return {};
}

static void freeString(PA_Unistring value) {
    PA_Unichar *buffer = value.fString;
    if(value.fString) {
        check(strings.erase(buffer) == 1, "string disposed exactly once");
        delete[] value.fString;
    }
}

static Node *node(void *ref) {
    auto result = static_cast<Node *>(ref);
    check(nodes.count(result), "live object/collection reference");
    return result;
}

static Node *makeNode() {
    auto result = new Node;
    nodes.insert(result);
    return result;
}

static PA_Variable copyVariable(PA_Variable value) {
    if(value.fType == eVK_Unistring)
        value.uValue.fString = makeString(readString(value.uValue.fString));
    else if(value.fType == eVK_Object && value.uValue.fObject)
        ++node(value.uValue.fObject)->refs;
    else if(value.fType == eVK_Collection && value.uValue.fCollection)
        ++node(value.uValue.fCollection)->refs;
    return value;
}

static void clearVariable(PA_Variable *value);

static void releaseNode(void *ref) {
    if(!ref) return;
    Node *value = node(ref);
    if(--value->refs) return;
    for(auto &entry : value->properties) clearVariable(&entry.second);
    for(auto &entry : value->elements) clearVariable(&entry);
    nodes.erase(value);
    delete value;
}

static void clearVariable(PA_Variable *value) {
    ++clears;
    switch(value->fType) {
        case eVK_Unistring: freeString(value->uValue.fString); break;
        case eVK_Object: releaseNode(value->uValue.fObject); break;
        case eVK_Collection: releaseNode(value->uValue.fCollection); break;
        case eVK_ArrayUnicode:
            if(value->uValue.fArray.fData) {
                auto data = reinterpret_cast<PA_Unistring *>(*value->uValue.fArray.fData);
                for(int i = 0; i <= value->uValue.fArray.fNbElements; ++i)
                    freeString(data[i]);
                PA_DisposeHandle(value->uValue.fArray.fData);
            }
            break;
        case eVK_Undefined:
        case eVK_Null:
        case eVK_Real:
        case eVK_Longint:
        case eVK_Boolean: break;
        default: check(false, "unexpected variable cleanup kind");
    }
    *value = {};
    value->fType = eVK_Undefined;
}

static void engine(short selector, EngineBlock *eb) {
    switch(selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(Text(reinterpret_cast<PA_Unichar *>(eb->fHandle)));
            return;
        case EX_DISPOSE_UNISTRING: freeString(eb->fUniString1); return;
        case EX_SET_UNISTRING: {
            Text content(reinterpret_cast<PA_Unichar *>(eb->fHandle));
            freeString(eb->fUniString1);
            eb->fUniString1 = makeString(content);
            return;
        }
        case EX_CLEAR_VARIABLE:
            clearVariable(static_cast<PA_Variable *>(eb->fPtr1));
            return;
        case EX_VARIABLE_TO_STRING: {
            auto value = reinterpret_cast<PA_Variable *>(eb->fHandle);
            check(value->fType == eVK_Unistring, "string getter kind");
            readString(value->uValue.fString);
            eb->fUniString1 = value->uValue.fString;
            return;
        }
        case EX_HANDLE_MANAGER: {
            const sLONG_PTR size = (eb->fParam1 == 1 || eb->fParam1 == 3) ? eb->fParam2 : 0;
            PA_Handle handle = eb->fParam1 == 1 ? nullptr : eb->fHandle;
            switch(eb->fParam1) {
                case 1: {
                    auto handle = new char *;
                    *handle = new char[std::max<sLONG_PTR>(1, size)]();
                    handles[handle] = eb->fParam2;
                    eb->fHandle = handle;
                    return;
                }
                case 2:
                    check(handles.erase(handle) == 1, "handle disposed once");
                    delete[] *eb->fHandle;
                    delete eb->fHandle;
                    return;
                case 3: {
                    auto found = handles.find(handle);
                    check(found != handles.end(), "resize live handle");
                    auto data = new char[std::max<sLONG_PTR>(1, size)]();
                    std::memcpy(data, *eb->fHandle, std::min<size_t>(found->second, eb->fParam2));
                    delete[] *eb->fHandle;
                    *eb->fHandle = data;
                    found->second = eb->fParam2;
                    return;
                }
                case 4: eb->fParam2 = handles.at(handle); return;
                case 5: eb->fParam3 = reinterpret_cast<sLONG_PTR>(*eb->fHandle); return;
                case 6: return;
                default: check(false, "unexpected handle operation");
            }
            return;
        }
        case EX_GET_INFORMATION:
            eb->fParam2 = 0x00002000;
            return;
        case EX_EXECUTE_COMMAND_BY_ID: {
            auto result = static_cast<PA_Variable *>(eb->fPtr2);
            auto args = static_cast<PA_Variable **>(eb->fPtr1);
            *result = {};
            switch(eb->fParam1) {
                case 1471: PA_SetObjectVariable(result, makeNode()); return;
                case 1472: PA_SetCollectionVariable(result, makeNode()); return;
                case 1231:
                    PA_SetBooleanVariable(result,
                        node(args[0]->uValue.fObject)->properties.count(readString(args[1]->uValue.fString)));
                    return;
                default: check(false, "unexpected 4D command");
            }
            return;
        }
        case EX_GET_OBJ_VALUE: {
            if(failRead) {
                // The SDK does not promise a valid output on failure.
                eb->fError = -1;
                return;
            }
            auto source = node(eb->fPtr1);
            auto result = static_cast<PA_Variable *>(eb->fPtr2);
            if(eb->fShort == eVK_Collection) {
                if(eb->fLongint == -1)
                    PA_SetLongintVariable(result, static_cast<PA_long32>(source->elements.size()));
                else
                    *result = copyVariable(source->elements.at(eb->fLongint));
            } else {
                *result = copyVariable(source->properties.at(readString(eb->fUniString1)));
            }
            return;
        }
        case EX_SET_OBJ_VALUE: {
            auto destination = node(eb->fPtr1);
            auto input = static_cast<PA_Variable *>(eb->fPtr2);
            PA_Variable copy = copyVariable(*input);
            if(eb->fShort == eVK_Collection) {
                auto index = static_cast<size_t>(eb->fLongint);
                check(index <= destination->elements.size(), "accepted collection index");
                if(index == destination->elements.size()) destination->elements.push_back(copy);
                else {
                    clearVariable(&destination->elements[index]);
                    destination->elements[index] = copy;
                }
            } else {
                Text key = readString(eb->fUniString1);
                auto found = destination->properties.find(key);
                if(found != destination->properties.end()) clearVariable(&found->second);
                destination->properties[key] = copy;
            }
            return;
        }
        default:
            std::cerr << "unexpected engine selector: " << selector << "\n";
            std::exit(1);
    }
}

static void balanced(const char *message) {
    check(strings.empty() && nodes.empty() && handles.empty(), message);
}

static void assertProperty(PA_ObjectRef object, const Text &expected) {
    auto value = node(object)->properties.at(text(u"value"));
    check(value.fType == eVK_Unistring, "text property kind");
    check(readString(value.uValue.fString) == expected, "exact text property");
}

static void churn() {
    std::vector<PA_Unistring> temporary;
    Text value = text(u"churn\u65E5\U0001F600");
    for(int i = 0; i != 32; ++i)
        temporary.push_back(PA_CreateUnistring(const_cast<PA_Unichar *>(value.c_str())));
    for(auto &entry : temporary) PA_DisposeUnistring(&entry);
}

static void setters() {
    const char *utf8[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC", "\xF0\x9F\x98\x80", ""};
    const wchar_t *wide[] = {L"ASCII", L"\u65E5\u672C", L"\U0001F600", L""};
    const char16_t *utf16[] = {u"ASCII", u"\u65E5\u672C", u"\U0001F600", u""};
    for(int overload = 0; overload != 4; ++overload) {
        for(int i = 0; i != 4; ++i) {
            auto object = PA_CreateObject();
            for(int repeat = 0; repeat != 4; ++repeat) {
                switch(overload) {
                    case 0: ob_set_s(object, "value", utf8[i]); break;
                    case 1: ob_set_s(object, L"value", utf8[i]); break;
                    case 2: ob_set_a(object, L"value", wide[i]); break;
                    case 3: {
                        Text value = text(utf16[i]);
                        ob_set_a(object, L"value", &value);
                        break;
                    }
                }
                churn();
                assertProperty(object, text(utf16[i]));
            }
            PA_DisposeObject(object);
            balanced("setter leaked an overwritten empty allocation");
        }
    }
}

static void getters() {
    auto emptyObject = PA_CreateObject();
    CUTF8String absent;
    check(!ob_get_a(emptyObject, L"missing", &absent), "missing text property");
    check(!ob_get_a(nullptr, L"missing", &absent), "null object");
    check(!ob_get_c(emptyObject, L"missing"), "missing collection");
    check(!ob_get_o(emptyObject, L"missing"), "missing object");
    PA_DisposeObject(emptyObject);
    balanced("missing getter properties");
    for(int kind = 0; kind != 5; ++kind) {
        for(int getter = 0; getter != 5; ++getter) {
            auto object = PA_CreateObject();
            switch(kind) {
                case 0: ob_set_s(object, L"value", "\xF0\x9F\x98\x80"); break;
                case 1: ob_set_b(object, L"value", true); break;
                case 2: ob_set_n(object, L"value", 1.25); break;
                case 3: {
                    auto collection = PA_CreateCollection();
                    collection_push(collection, @"\u65E5\U0001F600");
                    ob_set_c(object, L"value", collection);
                    break;
                }
                case 4: {
                    auto child = PA_CreateObject();
                    ob_set_s(child, L"value", "child");
                    ob_set_o(object, L"value", child);
                    break;
                }
            }
            CUTF8String value;
            PA_CollectionRef collection = nullptr;
            PA_ObjectRef child = nullptr;
            switch(getter) {
                case 0:
                    check(ob_get_a(object, L"value", &value), "existing property");
                    if(kind == 0) check(value == CUTF8String((const uint8_t *)"\xF0\x9F\x98\x80"), "getter exact UTF-8");
                    else check(value.empty(), "mismatched text getter");
                    break;
                case 1: check(ob_get_b(object, L"value") == (kind == 1), "boolean getter"); break;
                case 2: check(ob_get_n(object, L"value") == (kind == 2 ? 1.25 : 0), "real getter"); break;
                case 3:
                    collection = ob_get_c(object, L"value");
                    check(bool(collection) == (kind == 3), "collection getter");
                    break;
                case 4:
                    child = ob_get_o(object, L"value");
                    check(bool(child) == (kind == 4), "object getter");
                    break;
            }
            PA_DisposeObject(object);
            if(collection) {
                check(node(collection)->refs == 1, "owning collection survives parent disposal");
                NSArray *copy = createStringArrayForParam(collection);
                PA_DisposeCollection(collection);
                churn();
                check([copy count] == 1 && [copy[0] isEqualToString:@"\u65E5\U0001F600"], "independent collection text");
                [copy release];
            }
            if(child) {
                check(node(child)->refs == 1, "owning object survives parent disposal");
                assertProperty(child, text(u"child"));
                // A successful owning handoff can also be transferred to another object.
                auto destination = PA_CreateObject();
                ob_set_o(destination, L"child", child);
                PA_DisposeObject(destination);
            }
            balanced("getter leaked owning result (including mismatches)");
        }
    }
}

static void collections() {
    auto collection = PA_CreateCollection();
    const NSString *fixtures[] = {@"ASCII", @"\u65E5\u672C", @"\U0001F600", @""};
    for(auto fixture : fixtures) collection_push(collection, (NSString *)fixture);
    auto child = PA_CreateObject();
    collection_push(collection, child);
    auto nested = PA_CreateCollection();
    PA_Variable variable = PA_CreateVariable(eVK_Undefined);
    PA_SetCollectionVariable(&variable, nested);
    PA_SetCollectionElement(collection, PA_GetCollectionLength(collection), variable);
    PA_ClearVariable(&variable);
    NSArray *copy = createStringArrayForParam(collection);
    PA_DisposeCollection(collection);
    check([copy isEqualToArray:@[@"ASCII", @"\u65E5\u672C", @"\U0001F600"]], "copied strings, empty/nontext skipped");
    [copy release];
    balanced("collection element results leaked");
}

static void consumers() {
    auto object = PA_CreateObject();
    auto targets = PA_CreateCollection();
    collection_push(targets, @"text");
    ob_set_c(object, L"targets", targets);
    check(targetContains(object, @"text"), "target matching");
    check(!targetContains(object, @"barcode"), "target mismatch");
    auto region = PA_CreateObject();
    ob_set_n(region, L"x", 0.1);
    ob_set_n(region, L"y", 0.2);
    ob_set_n(region, L"width", 0.3);
    ob_set_n(region, L"height", 0.4);
    ob_set_o(object, L"regionOfInterest", region);
    VNDetectTextRectanglesRequest *rectangles = [[VNDetectTextRectanglesRequest alloc] init];
    getParamsForImageRequest(object, rectangles);
    check(rectangles.regionOfInterest.size.width == 0.3, "region consumed before disposal");
    [rectangles release];
    if(@available(macOS 10.15, *)) {
        auto languages = PA_CreateCollection();
        collection_push(languages, @"en-US");
        ob_set_c(object, L"recognitionLanguages", languages);
        auto words = PA_CreateCollection();
        collection_push(words, @"\u65E5\U0001F600");
        ob_set_c(object, L"customWords", words);
        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
        getParamsForTextRequest(object, request);
        PA_DisposeObject(object);
        check([request.recognitionLanguages isEqualToArray:@[@"en-US"]], "request retains copied languages");
        check([request.customWords isEqualToArray:@[@"\u65E5\U0001F600"]], "request retains copied words");
        [request release];
    } else {
        PA_DisposeObject(object);
    }
    balanced("consumer leaked owning nested reference");
}

static void arrays() {
    auto array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_ResizeArray(&array, 3);
    const char16_t *fixtures[] = {u"ASCII", u"\u65E5\u672C", u"\U0001F600", u""};
    for(int i = 0; i <= 3; ++i) {
        Text value = text(fixtures[i]);
        auto owned = PA_CreateUnistring(const_cast<PA_Unichar *>(value.c_str()));
        PA_SetStringInArray(array, i, &owned);
    }
    auto borrowed = PA_GetStringInArray(array, 1);
    Text independent = readString(borrowed);
    auto copy = PA_CreateUnistring(const_cast<PA_Unichar *>(independent.c_str()));
    PA_SetStringInArray(array, 2, &copy);
    auto replacementText = text(u"replacement");
    auto replacement = PA_CreateUnistring(const_cast<PA_Unichar *>(replacementText.c_str()));
    PA_SetStringInArray(array, 1, &replacement);
    check(readString(PA_GetStringInArray(array, 2)) == text(u"\u65E5\u672C"), "independent transfer");
    PA_ResizeArray(&array, 1);
    check(readString(PA_GetStringInArray(array, 1)) == replacementText, "replacement survives shrink");
    for(int rejection = 0; rejection != 4; ++rejection) {
        auto destination = array;
        int index = 1;
        if(rejection == 0) destination.fType = eVK_Real;
        if(rejection == 1) index = -1;
        if(rejection == 2) index = 2;
        if(rejection == 3) destination.uValue.fArray.fData = nullptr;
        auto owned = PA_CreateUnistring(const_cast<PA_Unichar *>(independent.c_str()));
        size_t count = strings.size();
        PA_SetStringInArray(destination, index, &owned);
        check(strings.size() == count && readString(owned) == independent, "rejection retains caller ownership");
        PA_DisposeUnistring(&owned);
    }
    PA_SetStringInArray(array, 0, nullptr);
    PA_ClearVariable(&array);
    balanced("array contract cleanup");
}

static void failedReads() {
    auto object = PA_CreateObject();
    ob_set_s(object, L"value", "value");
    size_t before = clears;
    failRead = true;
    CUTF8String value;
    ob_get_a(object, L"value", &value);
    ob_get_b(object, L"value");
    ob_get_n(object, L"value");
    ob_get_c(object, L"value");
    ob_get_o(object, L"value");
    failRead = false;
    check(clears == before, "failed read output is not assumed initialized/owning");
    PA_DisposeObject(object);
    balanced("failed read ownership");
}

int main(int argc, const char **argv) {
    check(argc == 3, "usage: ownership GROUP allocated|null");
    allocatedEmpty = std::strcmp(argv[2], "allocated") == 0;
    gCall4D = engine;
    @autoreleasepool {
        if(std::strcmp(argv[1], "setters") == 0) setters();
        else if(std::strcmp(argv[1], "getters") == 0) getters();
        else if(std::strcmp(argv[1], "collections") == 0) collections();
        else if(std::strcmp(argv[1], "consumers") == 0) consumers();
        else if(std::strcmp(argv[1], "arrays") == 0) arrays();
        else if(std::strcmp(argv[1], "failed-reads") == 0) failedReads();
        else check(false, "unknown group");
    }
    balanced("final allocation/reference balance");
    std::cout << argv[1] << " " << argv[2] << ": PASS\n";
}
