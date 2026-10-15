#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npm install --no-audit --no-fund
node mobile-build.mjs

# Publisher injects the signing files before this command, while cap add
# requires that android/ does not exist yet. Preserve them securely.
if [ -d android ] && [ ! -f android/gradlew ]; then
  mkdir -p .rf-native-signing
  for file in upload-keystore.jks key.properties; do
    if [ -f "android/$file" ]; then mv "android/$file" ".rf-native-signing/$file"; fi
  done
  rmdir android || true
fi
if [ ! -f android/gradlew ]; then npx cap add android; fi
if [ -d .rf-native-signing ]; then
  mv .rf-native-signing/* android/
  rmdir .rf-native-signing
fi
npx cap sync android
npx @capacitor/assets generate --android --iconBackgroundColor '#1A132B' --iconBackgroundColorDark '#1A132B' --splashBackgroundColor '#1A132B' --splashBackgroundColorDark '#1A132B'
python3 scripts/prepare-android.py
chmod +x android/gradlew
(cd android && ./gradlew --no-daemon bundleRelease)
test -s android/app/build/outputs/bundle/release/app-release.aab
echo "REIMFLOW_SIGNED_ANDROID_AAB_READY"
