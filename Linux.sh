#!/bin/sh
set -e
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    printf 'Installa Python aggiornato (3.11.17, 3.12.15, 3.13.17 o 3.14.9) e python3-venv con il gestore pacchetti della distribuzione. Consulta Guida.pdf.\n'; exit 1
fi
python3 "$PROJECT_DIR/installer/install.py"
