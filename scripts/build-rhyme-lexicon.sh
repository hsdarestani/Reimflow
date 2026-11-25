#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL --retry 2 https://raw.githubusercontent.com/open-dict-data/ipa-dict/972cd67dd5f96bc5660e28070cde26e3928abcd7/data/de.txt -o "$work/ipa.txt"
curl -fsSL --retry 2 https://raw.githubusercontent.com/hermitdave/FrequencyWords/525f9b560de45753a5ea01069454e72e9aa541c6/content/2018/de/de_50k.txt -o "$work/frequency.txt"
curl -fsSL --retry 2 https://raw.githubusercontent.com/LibreOffice/dictionaries/79195b017e6d70151337856c59e7d13d311d6630/de/de_DE_frami.dic -o "$work/dictionary.dic"
curl -fsSL --retry 2 https://raw.githubusercontent.com/unimorph/deu/d226d2112d3490d8f04ece10d4538123d4297a39/deu -o "$work/morphology.tsv"
curl -fsSL --retry 2 https://raw.githubusercontent.com/open-dict-data/ipa-dict/972cd67dd5f96bc5660e28070cde26e3928abcd7/data/en_US.txt -o "$work/english.txt"
curl -fsSL --retry 2 https://raw.githubusercontent.com/gambolputty/german-nouns/da71a2bc519b952b28c9b0b80971cff6efb508f6/german_nouns/nouns.csv -o "$work/nouns.csv"
(cd "$work" && sha256sum -c <<'EOF'
d36d11dbcc226468a22f0fb3a0794ee0ce142bf277e26e517a8bfd0de1ec2653  ipa.txt
d9e50546fd7e8b6fe6542a2b33c51d1331092b2a3916ec09f80d97856068705b  frequency.txt
4ca3c958b0e5545910999bc246f668840bf8ede3df8e5e6790d05edd5a586c38  dictionary.dic
8bc98487e3caf86188e2c072ebf2dc734f2ca35afef016bb399eb5a43e69d7c0  morphology.tsv
2af6f154a5c363275f052d1f85acedef38ed185ca9745aa4314be77f6b70de67  english.txt
7b34ca76bb753fa5d3d2b683ecc987824ae874b375ac999a797074fafba2768e  nouns.csv
EOF
)
python3 "$root/rhyme_lexicon.py" "$work/ipa.txt" "$work/frequency.txt" "$work/index.sqlite" "$work/dictionary.dic" "$work/morphology.tsv" "$work/english.txt" "$work/nouns.csv"
mv "$work/index.sqlite" "$root/rhyme-lexicon.sqlite"
