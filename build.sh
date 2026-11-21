#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
: "${ANDROID_JAR:?Path to android-35/android.jar}" "${TOOLS:?Android build-tools directory}" "${STORE:?Signing keystore}" "${STORE_PASS:?Keystore password}" "${ALIAS:?Key alias}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/classes" "$tmp/assets"
cp ../server/index.html "$tmp/assets/"
if [[ -n "${ECJ:-}" ]]; then
 java -jar "$ECJ" -8 -proc:none -bootclasspath "$ANDROID_JAR" -d "$tmp/classes" Main.java
else
 javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -d "$tmp/classes" Main.java
fi
(cd "$tmp/classes" && zip -qr "$tmp/classes.jar" .)
"$TOOLS/d8" --min-api 24 --lib "$ANDROID_JAR" --output "$tmp" "$tmp/classes.jar"
"$TOOLS/aapt" package -f -M AndroidManifest.xml -A "$tmp/assets" -I "$ANDROID_JAR" -F "$tmp/base.apk"
(cd "$tmp" && zip -q base.apk classes.dex)
"$TOOLS/zipalign" -f 4 "$tmp/base.apk" "$tmp/aligned.apk"
"$TOOLS/apksigner" sign --ks "$STORE" --ks-key-alias "$ALIAS" --ks-pass env:STORE_PASS --out Etawah-Cafe.apk "$tmp/aligned.apk"
"$TOOLS/apksigner" verify --verbose Etawah-Cafe.apk
