#!/bin/zsh
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
if (( $# > 0 )); then
  app_path="$1"
else
  app_path="$repo_root/build/Paper Lab.app"
fi
contents="$app_path/Contents"
module_cache="$repo_root/.cache/swift-module-cache"

rm -rf "$app_path"
mkdir -p "$contents/MacOS" "$contents/Resources" "$module_cache"

/usr/bin/swiftc \
  "$repo_root/macos/PaperLabLauncher.swift" \
  -parse-as-library \
  -module-cache-path "$module_cache" \
  -framework AppKit \
  -framework Foundation \
  -o "$contents/MacOS/PaperLabLauncher"

cp "$repo_root/macos/Info.plist" "$contents/Info.plist"
printf '%s\n' "$repo_root" > "$contents/Resources/repo-path.txt"
/usr/bin/codesign --force --deep --sign - "$app_path"

echo "Built $app_path"
