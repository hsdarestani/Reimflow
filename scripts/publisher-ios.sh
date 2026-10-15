#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "\${IOS_TEAM_ID:?Missing Publisher Apple Team}"
: "\${IOS_PROVISIONING_PROFILE_SPECIFIER:?Missing Publisher App Store provisioning profile}"
: "\${IOS_SIGNING_KEYCHAIN:?Missing ephemeral signing keychain}"
npm install --no-audit --no-fund
node mobile-build.mjs
if [ ! -f ios/App/App.xcodeproj/project.pbxproj ]; then npx cap add ios; fi
npx cap sync ios
npx @capacitor/assets generate --ios --iconBackgroundColor '#1A132B' --iconBackgroundColorDark '#1A132B' --splashBackgroundColor '#1A132B' --splashBackgroundColorDark '#1A132B'
/usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string 'Reimflow benötigt dein Mikrofon nur für freiwillige Rap und Rhythmus Aufnahmen.'" ios/App/App/Info.plist 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription 'Reimflow benötigt dein Mikrofon nur für freiwillige Rap und Rhythmus Aufnahmen.'" ios/App/App/Info.plist
mkdir -p artifacts
python3 scripts/prepare-ios-export.py
xcodebuild -workspace ios/App/App.xcworkspace -scheme App -configuration Release -sdk iphoneos \
  -archivePath "$PWD/artifacts/Reimflow.xcarchive" \
  -destination 'generic/platform=iOS' \
  "DEVELOPMENT_TEAM=$IOS_TEAM_ID" CODE_SIGN_STYLE=Manual \
  "PROVISIONING_PROFILE_SPECIFIER=$IOS_PROVISIONING_PROFILE_SPECIFIER" \
  "CODE_SIGN_IDENTITY=Apple Distribution" \
  "OTHER_CODE_SIGN_FLAGS=--keychain $IOS_SIGNING_KEYCHAIN" \
  "MARKETING_VERSION=\${APP_VERSION_NAME:-1.0.0}" \
  "CURRENT_PROJECT_VERSION=\${APP_BUILD_NUMBER:-1}" \
  archive
xcodebuild -exportArchive -archivePath "$PWD/artifacts/Reimflow.xcarchive" \
  -exportPath "$PWD/artifacts/export" \
  -exportOptionsPlist "$PWD/artifacts/ExportOptions.plist" \
  "OTHER_CODE_SIGN_FLAGS=--keychain $IOS_SIGNING_KEYCHAIN"
test -s artifacts/export/App.ipa
echo "REIMFLOW_SIGNED_IOS_IPA_READY"
