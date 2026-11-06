#!/bin/bash
# No Apple account, provisioning profile, or signing certificate is used.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/logs
if [[ "${FREETUBE_BUILD_LOGGED:-0}" != 1 ]]; then
    set +e
    FREETUBE_BUILD_LOGGED=1 bash scripts/build-ipa.sh "$@" 2>&1 | tee build/logs/build-ipa.log
    build_status=${PIPESTATUS[0]}
    exit "$build_status"
fi

if ! command -v xcodebuild >/dev/null 2>&1; then
    echo 'BUILD BLOCKED: macOS with Xcode 26.2+ is required; no IPA was produced.'
    exit 69
fi
xcodebuild -version
xcrun swift --version
xcodebuild -showsdks
python3 - <<'PY'
import re, subprocess
version = subprocess.check_output(['xcodebuild', '-version'], text=True)
match = re.search(r'Xcode (\d+)\.(\d+)', version)
if not match or tuple(map(int, match.groups())) < (26, 2):
    raise SystemExit('Xcode 26.2+ required for default actor isolation / Swift 6.2 syntax')
PY

project=FreeTube/FreeTube.xcodeproj
packages="$PWD/build/SourcePackages"
derived="$PWD/build/DerivedData"
# Fresh output only. Never accidentally deliver an older successful binary.
rm -f build/FreeTube-fixed.ipa build/FreeTube-fixed.ipa.sha256
rm -rf build/staging build/Build.xcresult

python3 -m unittest discover -s tests -v
python3 scripts/check-source.py
xcodebuild -resolvePackageDependencies \
    -project "$project" -scheme FreeTube \
    -clonedSourcePackagesDirPath "$packages" \
    | tee build/logs/resolve.log
python3 scripts/check-source.py
xcodebuild build \
    -project "$project" -scheme FreeTube -configuration Release \
    -sdk iphoneos -destination 'generic/platform=iOS' \
    -derivedDataPath "$derived" -clonedSourcePackagesDirPath "$packages" \
    -disableAutomaticPackageResolution \
    -resultBundlePath "$PWD/build/Build.xcresult" \
    ARCHS=arm64 ONLY_ACTIVE_ARCH=NO \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= \
    DEVELOPMENT_TEAM= PROVISIONING_PROFILE_SPECIFIER= \
    SWIFT_OPTIMIZATION_LEVEL=-O COMPILER_INDEX_STORE_ENABLE=NO \
    | tee build/logs/xcodebuild.log

app="$derived/Build/Products/Release-iphoneos/FreeTube.app"
test -d "$app"
plutil -lint "$app/Info.plist"
mkdir -p build/staging/Payload
ditto "$app" build/staging/Payload/FreeTube.app
# Existing vendor signatures are immaterial to SideStore; strip them for a clean
# re-signable package and remove profiles if a vendor package included one.
find build/staging/Payload -name embedded.mobileprovision -delete
while IFS= read -r -d '' binary; do
    if codesign -d "$binary" >/dev/null 2>&1; then
        codesign --remove-signature "$binary"
    fi
done < <(find build/staging/Payload -type f -print0 | while IFS= read -r -d '' candidate; do
    if file -b "$candidate" | grep -q 'Mach-O'; then
        printf '%s\0' "$candidate"
    fi
done)
find build/staging/Payload -type d -name _CodeSignature -prune -exec rm -rf '{}' +
ditto -c -k --keepParent build/staging/Payload build/FreeTube-fixed.ipa
python3 scripts/verify-ipa.py build/FreeTube-fixed.ipa \
    --output build/ipa-verification.json
shasum -a 256 build/FreeTube-fixed.ipa > build/FreeTube-fixed.ipa.sha256
echo 'BUILD AND PACKAGE VERIFICATION SUCCEEDED. Device launch is still unverified.'
