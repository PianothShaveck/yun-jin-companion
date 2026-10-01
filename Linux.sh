#!/bin/sh
set -e
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    printf 'Installa Python 3.11–3.14 e python3-venv con il gestore pacchetti della distribuzione. Consulta Guida.pdf.\n'; exit 1
fi
python3 "$PROJECT_DIR/installer/install.py"
