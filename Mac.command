#!/bin/bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
. "$PROJECT_DIR/installer/language.sh"
yj_failed() { yj_text 'Installazione interrotta. Consulta Guida.pdf. Premi Invio.' 'Installation interrupted. See Guide.pdf. Press Enter.' '安装已中断。请参阅 Guide.zh-CN.pdf。按回车键关闭。'; read -r answer; }
trap yj_failed ERR
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 13 ]; then
    yj_text 'Serve macOS 13 o successivo.' 'macOS 13 or later is required.' '需要 macOS 13 或更高版本。'; exit 1
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
    yj_text 'Scarico Python 3.13.17 dal sito ufficiale...' 'Downloading Python 3.13.17 from the official website…' '正在从官方网站下载 Python 3.13.17…'
    curl --fail --location --proto '=https' --tlsv1.2 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-macos11.pkg' -o "$DOWNLOAD_DIR/Python.pkg"
    EXPECTED_SHA='3053592af66128269efab37fe7851a4894920b27c442aeec99ce4d34d17c07e3'
    ACTUAL_SHA="$(shasum -a 256 "$DOWNLOAD_DIR/Python.pkg" | awk '{print $1}')"
    if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then yj_text 'Verifica SHA256 fallita.' 'SHA-256 verification failed.' 'SHA-256 校验失败。'; exit 1; fi
    yj_text 'Completa la finestra di installazione di Python, poi torna qui e premi Invio.' 'Complete the Python installer, then return here and press Enter.' '请完成 Python 安装，然后返回此处按回车键。'
    open "$DOWNLOAD_DIR/Python.pkg"
    read -r answer
    PYTHON_EXE="$(find_python)" || { yj_text 'Python non trovato. Completa la sua installazione e riapri Mac.command.' 'Python not found. Finish installing it and reopen Mac.command.' '未找到 Python。请完成安装后重新打开 Mac.command。'; exit 1; }
fi
printf 'Python: %s\n' "$PYTHON_EXE"
"$PYTHON_EXE" --version
"$PYTHON_EXE" -I "$PROJECT_DIR/installer/install.py"
yj_text 'Puoi chiudere questa finestra. Dal prossimo avvio usa Yun Jin Companion in /Applications o sulla Scrivania.' 'You can close this window. Open Yun Jin Companion from /Applications or the desktop.' '可以关闭此窗口。以后请从 /Applications 或桌面打开 Yun Jin Companion。'
