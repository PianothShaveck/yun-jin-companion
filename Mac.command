#!/bin/bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
trap 'printf "\nInstallazione interrotta. Consulta Guida.pdf. Premi Invio per chiudere.\n"; read -r answer' ERR
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 13 ]; then
    printf 'Serve macOS 13 o successivo.\n'; exit 1
fi
find_python() {
    for candidate in /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3; do
        if [ -x "$candidate" ] && "$candidate" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,15) and sys.maxsize>2**32 else 1)' 2>/dev/null; then
            printf '%s\n' "$candidate"; return 0
        fi
    done
    return 1
}
if ! PYTHON_EXE="$(find_python)"; then
    DOWNLOAD_DIR="$(mktemp -d -t yun-jin-python)"
    trap 'rm -rf -- "$DOWNLOAD_DIR"' EXIT
    printf 'Scarico Python dal sito ufficiale...\n'
    curl --fail --location --proto '=https' --tlsv1.2 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-macos11.pkg' -o "$DOWNLOAD_DIR/Python.pkg"
    EXPECTED_SHA='3b7eaf7f29825f796e8267024435540ddf1f17fc9a97ad58095daa7a75bfdcd3'
    ACTUAL_SHA="$(shasum -a 256 "$DOWNLOAD_DIR/Python.pkg" | awk '{print $1}')"
    if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then printf 'Verifica SHA256 fallita.\n'; exit 1; fi
    printf 'Completa la finestra di installazione di Python, poi torna qui e premi Invio.\n'
    open "$DOWNLOAD_DIR/Python.pkg"
    read -r answer
    PYTHON_EXE="$(find_python)" || { printf 'Python non trovato. Completa la sua installazione e riapri Mac.command.\n'; exit 1; }
fi
"$PYTHON_EXE" "$PROJECT_DIR/installer/install.py"
printf '\nPuoi chiudere questa finestra. Dal prossimo avvio usa Yun Jin Companion nella Scrivania.\n'
