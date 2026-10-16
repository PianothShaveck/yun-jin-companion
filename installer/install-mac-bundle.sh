#!/bin/sh
# Publish a prepared bundle atomically; retain the previous app on failure.
set -eu
source_bundle=$1
target_bundle=$2
applications_dir=$(dirname "$target_bundle")
staging_dir=$(mktemp -d "$applications_dir/.yun-jin-install.XXXXXX")
restore_previous=0
cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ "$restore_previous" = 1 ] && [ ! -e "$target_bundle" ]; then
        if ! mv "$staging_dir/previous.app" "$target_bundle"; then
            printf 'Ripristino non riuscito. App precedente conservata in: %s\n' "$staging_dir" >&2
            exit 1
        fi
    fi
    rm -rf "$staging_dir"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
cp -R "$source_bundle" "$staging_dir/new.app"
if [ -e "$target_bundle" ] || [ -L "$target_bundle" ]; then
    mv "$target_bundle" "$staging_dir/previous.app"
    restore_previous=1
fi
mv "$staging_dir/new.app" "$target_bundle"
restore_previous=0
