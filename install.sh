#!/bin/bash
# Link this checkout into the Omarchy shell and enable Kaigi.
#   ./install.sh            link + enable (widget goes next to the clock)
#   ./install.sh --remove   disable + unlink
set -euo pipefail

id="penguinwokrs.kaigi"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugins="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
config="${XDG_CONFIG_HOME:-$HOME/.config}/kaigi/config.json"

if [[ ${1:-} == "--remove" ]]; then
  omarchy plugin disable "$id" || true
  [[ -L $plugins/$id ]] && rm "$plugins/$id"
  echo "Kaigi removed (config kept at $config)"
  exit 0
fi

omarchy plugin validate "$src"
mkdir -p "$plugins"
if [[ -e $plugins/$id && ! -L $plugins/$id ]]; then
  echo "$plugins/$id exists and is not a symlink; leaving it alone" >&2
  exit 1
fi
ln -sfn "$src" "$plugins/$id"

if [[ ! -e $config ]]; then
  mkdir -p "$(dirname "$config")"
  install -m 600 "$src/config.example.json" "$config"
  echo "Created $config — add your calendar feed URL(s) there."
fi
chmod 600 "$config"

omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
# The shell discovers the new folder asynchronously.
for _ in $(seq 1 20); do
  omarchy plugin list | grep -q "^$id " && break
  sleep 0.5
done
omarchy plugin enable "$id" --section centerEnd --index 0
echo "Kaigi enabled."
