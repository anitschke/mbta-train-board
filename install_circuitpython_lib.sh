#!/bin/bash -e

BUNDLE_VERSION="20261016"
DEST="/run/media/anitschk/CIRCUITPY"

ZIP_BASE_NAME="adafruit-circuitpython-bundle-10.x-mpy-$BUNDLE_VERSION"
ZIP_URL="https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/download/$BUNDLE_VERSION/$ZIP_BASE_NAME.zip"
TEMP_DIR="/tmp/circuitpython_bundle"

mkdir -p "$TEMP_DIR"

rm -f "$TEMP_DIR/bundle.zip"
rm -rf "$TEMP_DIR/$ZIP_BASE_NAME"
curl -L "$ZIP_URL" -o "$TEMP_DIR/bundle.zip"
unzip -q "$TEMP_DIR/bundle.zip" -d "$TEMP_DIR"

rsync -avu --delete "$TEMP_DIR/$ZIP_BASE_NAME/lib" "$DEST"