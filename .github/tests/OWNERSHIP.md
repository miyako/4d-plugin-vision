# Vision native string ownership

## Inventory and provenance

Audited baseline: `58010f27b2a4d0c2f687b7ffc905f4148057dc5b`.
The source and tracked bundle manifests agree on two commands:
`vision process data(&O;&J):J` (selector 1) and `vision get version:J`
(selector 2). Neither declares text arrays. The inventory below includes
helpers independently of those declarations.

| Surface | Reachability and ownership findings |
|---|---|
| `4DPlugin-vision.cpp`, `4DPlugin-vision.h` | Both selectors dispatch through `PluginMain`. Text collection output uses a fresh descriptor, shallow scalar assignment and variable cleanup after collection insertion; no extra string disposal is needed. Object/collection outputs retain the existing successful handoffs. |
| Main `ob_get_o` and parameter consumers | Successful object references transfer the owning getter result to the caller. Mismatches must clear the result. `regionOfInterest` needs one release after consumption. |
| Main `createStringArrayForParam` | Collection elements are owning getter results. Copy strings into Foundation before clearing every successful result, including empty and mismatched values. |
| Main `ob_get_c` consumers | `targets`, `recognitionLanguages`, and `customWords` each need one release after conversion. No changed lifetime or borrowed-reference API. |
| `support/4DPlugin-JSON.cpp/.h` | Compiled by the macOS target. Four text setters overwrite preallocated empty strings; use an initially undefined variable before the shallow setter. Text/scalar getters copy then clear; mismatched reference getters clear; successful collection references remain owning handoffs. `ob_stringify` already copies before clearing its command result and independent argument. |
| `Classes/ARRAY_TEXT.cpp/.h` | Tracked, not included or compiled by either target. Reads copy borrowed array text into independent C++ strings; writes create independent descriptors and transfer to the array. Allocation/resize failure behavior is deferred, not certified by normal-array coverage. |
| `Classes/C_TEXT.cpp/.h`, `C_TYPES.h` | Dormant. C++ copies own their content; parameter/result setters use the engine-backed content setter. No scalar descriptor transfer/dispose pair. |
| `Classes/C_BLOB.cpp/.h`, `C_LONGINT.cpp/.h` | Dormant. BLOB/number wrappers have no native string descriptor ownership handoff requiring a change. No CPicture or C_POINTER wrapper exists in this checkout. |
| Bundled `4DPluginAPI.c` and headers | Compiled unchanged; inspected as contract evidence, not rewritten. Third-party `include/json` and static libraries excluded. |

The macOS source phase compiles the main file, JSON helper and SDK as
Objective-C++. The historical Visual Studio project lists only main and
SDK; main unconditionally imports Cocoa/Vision. A tracked Windows binary is
not proof that current source builds or runs on Windows.

Bundled SDK Git blob IDs:

- `4DPluginAPI.c`: `62f745e91d81ef2c3c901c656ea8e175d3b173e8`
- `4DPluginAPI.h`: `528bf1d2552df08d6a8b1bc95011a9b72934ad5c`

The source/header identify themselves as `rev : v14`; this is not a verified
upstream release identity. Guidance consulted:
`miyako/skills/4d-skills/skills/4dplugin/SKILL.md`, blob
`aabdd402ca8bd87be6c84a1a61f2118ad4d4cb13` at repository revision
`e6b492fcb81e5e1a7f7db723594b420e63bf6eb9`.

## Bundled contracts and fix

`PA_CreateVariable(eVK_Unistring)` (SDK lines 4029-4031) creates an empty
string through the engine. `PA_SetStringVariable` (4254-4259) overwrites the
descriptor without disposing the previous one. Initially undefined variables
avoid orphaning allocated empty strings without changing successful property
insertion or the final variable cleanup.

`PA_GetObjectProperty` (637-651) and `PA_GetCollectionElement` (587-601)
explicitly require clearing returned variables. Their engine output is not
initialized by the SDK, so no valid owning output is assumed on failure.
The fixes inspect `PA_GetLastError` immediately, do not inspect or clear
failed outputs, and otherwise preserve existing default/skip behavior.
Failure-side ownership remains undocumented and deferred. Successful
object/collection results hand their reference to the caller instead of
clearing it prematurely; all current consumers release it after use.

`PA_GetStringInArray` (4738-4755) is a borrowed alias.
`PA_SetStringInArray` (4933-4948) disposes the old element then shallow
transfers the incoming descriptor only for Unicode arrays with non-null
data, an accepted index (including zero), and a non-null input descriptor.
Rejected insertion leaves the caller owning its string. No production array
code is changed here.

`PA_GetStringVariable` delegates to `EX_VARIABLE_TO_STRING`; the harness
models its string-variable result as an alias valid while the owning
variable is alive. Object and collection setters/getters use the documented
owning getter result plus engine reference retention at property/element
insertion, not independent ownership of one unretained reference.

No plugin method/command callback result is ignored; the only first-party
command execution is dormant `ob_stringify`, whose owning result is already
cleared on both matching and mismatched types. Vision completion blocks are
synchronous-request configuration callbacks with no PA string arguments.
Undocumented SDK-only application-path/picture-data output ownership and
pointer metadata semantics are not grounds for speculative cleanup.

## Regressions

On macOS with Xcode:

```sh
python3 .github/tests/run_ownership.py
python3 .github/tests/run_ownership.py \
  --source-ref 58010f27b2a4d0c2f687b7ffc905f4148057dc5b \
  --expect-baseline-failure
```

The harness includes the **actual complete main source**, compiles the
actual JSON helper and **full unchanged bundled SDK**, and supplies only
the `gCall4D` engine boundary. No copied replacement of the fixed functions
is used. Revision mode extracts immutable source from Git and applies the
same current harness. Builds and executables use temporary directories;
no bundle, signing, packaging, camera, screen or user-document input.

Six groups run with allocated and null empty-string representations:

- Four setter overloads: exact ASCII, BMP, supplementary surrogate pair and
  empty text; repeated replacement and complete cleanup.
- All five property getters against text, boolean, real, object and
  collection values, including owning mismatches. Successful nested refs
  survive parent disposal and receive exactly one release or transfer.
- Actual text-collection push/conversion: exact Unicode, allocated/null
  empties, mixed object/collection elements, independent Foundation copies.
- All four nested-reference consumers; Foundation request values survive
  parent disposal.
- Actual SDK arrays: independent borrowed copies/transfers, replacement,
  shrink, clear, rejected type/index/null-data and null input.
- Failed property reads with deliberately untouched engine output; no
  cleanup is invented for uninitialized outputs.

The immutable baseline produces named ownership assertions in all four
defect groups (setters with allocated empties; getters, collection elements,
and consumers also with null empties). Array contract controls and
null-empty setters pass. Failed-read cases are fixed-source-only because
the baseline reads an undocumented uninitialized output. The fixed source
passes all twelve cases with ASan/UBSan and zero tracked string, node
reference and SDK-handle allocations. LSan is disabled on macOS; explicit
accounting covers shim-managed resources, not arbitrary host allocations.

An unsigned `Development` Xcode build also succeeds for arm64 and x86_64,
with all outputs outside the checkout and code signing disabled. The
inspected shell phase performs release actions only for `Deployment`,
which was not used. Neither manual Bump nor Build workflow was dispatched.
The PR workflow only compiles/runs this unsigned sanitizer harness.

This is engine-shim and native build evidence, not real 4D execution,
Windows certification, allocator-failure certification, Vision image
recognition validation, or a reproduction of Poppler's Windows crash.
