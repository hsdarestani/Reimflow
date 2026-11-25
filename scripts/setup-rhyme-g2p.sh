#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
python3 -m pip install --disable-pip-version-check --only-binary=:all: --no-deps --require-hashes --target "$root/rhyme-g2p" -r "$root/scripts/rhyme-g2p-requirements.txt"
PYTHONPATH="$root/rhyme-g2p:$root" python3 -c 'import rhyme_pronunciation as g; assert g.available(); assert g.phonemize("Schmetterling","de")'
