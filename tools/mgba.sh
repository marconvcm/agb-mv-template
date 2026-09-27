#!/bin/sh
# Resolve an mGBA and run it. Used as the cargo runner for the gba crate, so
# `cargo run` just works regardless of how mGBA was installed.
#
# Order: $MGBA, mgba-qt/mgba on PATH, a flatpak, then an AppImage in the usual
# download spots.
set -e

find_mgba() {
    [ -n "$MGBA" ] && { echo "$MGBA"; return; }
    for c in mgba-qt mgba; do
        command -v "$c" >/dev/null 2>&1 && { echo "$c"; return; }
    done
    if command -v flatpak >/dev/null 2>&1 && flatpak info io.mgba.mGBA >/dev/null 2>&1; then
        echo "flatpak run io.mgba.mGBA"
        return
    fi
    for d in "$HOME/Downloads" "$HOME/Applications" "$HOME/.local/share/AppImage"; do
        for f in "$d"/*mGBA*.appimage "$d"/*mgba*.AppImage "$d"/*mGBA*.AppImage; do
            [ -x "$f" ] && { echo "$f"; return; }
        done
    done
    echo "tools/mgba.sh: no mGBA found. Install it, or set MGBA=/path/to/mgba" >&2
    exit 1
}

exec $(find_mgba) -C logToStdout=1 -C logLevel.gba.debug=127 "$@"
