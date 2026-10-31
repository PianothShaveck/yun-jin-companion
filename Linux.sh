#!/bin/sh
set -e
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$PROJECT_DIR/installer/language.sh"
if ! command -v python3 >/dev/null 2>&1; then
    yj_text 'Installa Python aggiornato (3.11.17, 3.12.15, 3.13.17 o 3.14.9) e python3-venv con il gestore pacchetti della distribuzione. Consulta Guida.pdf.' 'Install a supported Python (3.11.17, 3.12.15, 3.13.17 or 3.14.9) and python3-venv using your package manager. See Guide.pdf.' '请使用发行版包管理器安装受支持的 Python（3.11.17、3.12.15、3.13.17 或 3.14.9）和 python3-venv。请参阅 Guide.zh-CN.pdf。'; exit 1
fi
python3 "$PROJECT_DIR/installer/install.py"
