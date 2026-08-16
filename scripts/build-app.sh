#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
(cd app/RAWdogPrintworks && xcodegen generate)
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  -derivedDataPath app/build build
APP="app/build/Build/Products/Release/RAWdogPrintworks.app"
codesign --force --sign - "$APP"
codesign --verify --strict "$APP"
echo "Built + ad-hoc signed: $APP"
echo "Install: cp -R \"$APP\" /Applications/"
