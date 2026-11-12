#!/bin/sh
# Prints a version's section of CHANGELOG.md (its text, without the "## [x.y.z]" heading), for the release notes.
# Fails if the section is missing or empty: a release is never published without its changes.
#
#   scripts/release-notes.sh 0.2.0
set -eu
version="${1:?usage: release-notes.sh <version>}"
changelog="$(dirname "$0")/../CHANGELOG.md"
section="$(awk -v v="$version" '
  index($0, "## [" v "]") == 1 { found = 1; next }
  found && /^## \[/ { exit }
  found && /^\[[^]]+\]: / { exit }
  found { print }
' "$changelog")"
if [ -z "$(printf '%s' "$section" | tr -d '[:space:]')" ]; then
  echo "CHANGELOG.md has no section for $version" >&2
  exit 1
fi
printf '%s\n' "$section"
