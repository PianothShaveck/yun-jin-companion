#!/bin/bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
trap 'printf "\nInstallazione interrotta. Consulta Guida.pdf. Premi Invio per chiudere.\n"; read -r answer' ERR
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 13 ]; then
    printf 'Serve macOS 13 o successivo.\n'; exit 1
fi
find_python() {
    # Prefer an existing python.org installation over a Homebrew Cellar version.
    for candidate in /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if [ -x "$candidate" ] && "$candidate" -I -c 'import csv, ctypes, ensurepip, sqlite3, ssl, sys, venv; sys.exit(0 if ((3,13,17)<=sys.version_info[:3]<(3,14) or (3,14,9)<=sys.version_info[:3]<(3,15)) and sys.maxsize>2**32 else 1)' 2>/dev/null; then
            printf '%s\n' "$candidate"; return 0
        fi
    done
    return 1
}
if ! PYTHON_EXE="$(find_python)"; then
    DOWNLOAD_DIR="$(mktemp -d -t yun-jin-python)"
    trap 'rm -rf -- "$DOWNLOAD_DIR"' EXIT
    printf 'Scarico Python 3.13.17 dal sito ufficiale...\n'
    curl --fail --location --proto '=https' --tlsv1.2 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-macos11.pkg' -o "$DOWNLOAD_DIR/Python.pkg"
    EXPECTED_SHA='3053592af66128269efab37fe7851a4894920b27c442aeec99ce4d34d17c07e3'
    ACTUAL_SHA="$(shasum -a 256 "$DOWNLOAD_DIR/Python.pkg" | awk '{print $1}')"
    if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then printf 'Verifica SHA256 fallita.\n'; exit 1; fi
    printf 'Completa la finestra di installazione di Python, poi torna qui e premi Invio.\n'
    open "$DOWNLOAD_DIR/Python.pkg"
    read -r answer
    PYTHON_EXE="$(find_python)" || { printf 'Python non trovato. Completa la sua installazione e riapri Mac.command.\n'; exit 1; }
fi
printf 'Python: %s\n' "$PYTHON_EXE"
"$PYTHON_EXE" --version
"$PYTHON_EXE" -I "$PROJECT_DIR/installer/install.py"
printf '\nPuoi chiudere questa finestra. Dal prossimo avvio usa Yun Jin Companion in /Applications o sulla Scrivania.\n'
