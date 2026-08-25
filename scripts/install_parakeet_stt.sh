#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
package_dir="$repo_root/native/parakeet_stt"
hermes_home="${HERMES_HOME:-$HOME/.hermes}"
source_model="${1:-$HOME/Library/Application Support/Multiplexer/Dictation/FluidAudio/Models/parakeet-tdt-0.6b-v3}"
model_name="parakeet-tdt-0.6b-v3"
model_root="$hermes_home/models"
model_target="$model_root/$model_name"
binary_target="$hermes_home/bin/hermes-parakeet-stt"

if [[ ! -d "$source_model" ]]; then
  echo "error: source Parakeet model directory not found: $source_model" >&2
  exit 1
fi

swift build --package-path "$package_dir" -c release --product hermes-parakeet-stt
binary_dir="$(swift build --package-path "$package_dir" -c release --show-bin-path)"
mkdir -p "$(dirname "$binary_target")" "$model_root"
install -m 0755 "$binary_dir/hermes-parakeet-stt" "$binary_target"

if [[ ! -d "$model_target" ]]; then
  staging_root="$(mktemp -d "$model_root/.parakeet-staging.XXXXXX")"
  trap 'rm -rf "$staging_root"' EXIT
  staging_model="$staging_root/$model_name"
  if ! cp -cR "$source_model" "$staging_model" 2>/dev/null; then
    cp -R "$source_model" "$staging_model"
  fi
  "$binary_target" --check-model --model-dir "$staging_model"
  mv "$staging_model" "$model_target"
  rm -rf "$staging_root"
  trap - EXIT
fi

"$binary_target" --check-model --model-dir "$model_target"
echo "Installed Hermes Parakeet STT binary: $binary_target"
echo "Installed Hermes Parakeet v3 model: $model_target"
