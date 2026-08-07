#!/bin/sh
if test "$CONFIGURATION" == 'Deployment'; then

    USER_NAME=keisuke.miyako@4d.com
    UUID=`uuidgen | tr -d - | tr -d '\n' | tr '[:upper:]' '[:lower:]'`
    DEVELOPER_ID=`security find-identity -p codesigning -v | egrep 'Developer ID Application[^"]+' -o`
    PRODUCT_PATH="$CODESIGNING_FOLDER_PATH"
    
    #clean
    xattr -cr "$PRODUCT_PATH"
    codesign --remove-signature "$PRODUCT_PATH"
    
    #sign
    codesign --verbose --deep --timestamp --force --sign "$DEVELOPER_ID" "$PRODUCT_PATH"
    
    #archive
    DMG_PATH="$PROJECT_DIR/$PRODUCT_NAME.dmg"
    ZIP_PATH="$PROJECT_DIR/$PRODUCT_NAME.zip" #for windows
    rm -f "$DMG_PATH"
    hdiutil create -format UDBZ -plist -srcfolder "$PRODUCT_PATH" "$DMG_PATH"
    rm -f "$ZIP_PATH"
    ditto -c -k --keepParent "$PRODUCT_PATH" "$ZIP_PATH"
    
    # must staple the same dmg that was submitted for notarisation
    # to staple the bundle inside the dmg too,
    # one must:
    # sign the bundle
    # archive the bundle and notarise the dmg
    # staple the bundle
    # archive the bundle and notarise the dmg again
    # staple the dmg
    # here, we just staple the dmg. it should be sufficient    
    
    #round 2
    echo "# staple only the dmg"
    echo "\r"
    echo "xcrun stapler staple \"$DMG_PATH\""
    echo "\r"
    
    #round 3 (optional)
    echo "# staple the bundle and the dmg"
    echo "\r"
    echo "xcrun stapler staple \"$PRODUCT_PATH\""
    echo "rm -f \"$DMG_PATH\""
    echo "hdiutil create -format UDBZ -plist -srcfolder  \"$PRODUCT_PATH\" \"$DMG_PATH\" "
    echo "xcrun altool --notarize-app --file \"$DMG_PATH\" --username \"$USER_NAME\" --password \"@keychain:altool\" --primary-bundle-id $PRODUCT_BUNDLE_IDENTIFIER.$UUID"
    echo "\r"
    
    #round 1
    xcrun altool --notarize-app --file "$DMG_PATH" --username "$USER_NAME" --password "@keychain:altool" --primary-bundle-id $PRODUCT_BUNDLE_IDENTIFIER.$UUID
    
    #for round 3    
    UUID=`uuidgen | tr -d - | tr -d '\n' | tr '[:upper:]' '[:lower:]'`
else
    echo "No notarization performed as this is not a release build."
fi

