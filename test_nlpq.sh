#!/usr/bin/env bash
# test_nlpq.sh — vérifie la route /nlpq (génération de payload SQL/chart)
# Usage :
#   ./test_nlpq.sh                 # cible http://localhost:8080
#   ./test_nlpq.sh http://host:port

set -euo pipefail

API="${1:-${API:-http://localhost:8080}}"
PROMPT="${2:-\"donne moi les buts moyens\"}"

leagues=(
  "NBA"
  "Premier League"
  "Ligue 1 McDonald's"
  "Bundesliga"
  "Serie A"
  "LaLiga"
  "Liqui Moly StarLigue"
  "La Boulangère Wonderligue"
)

echo "# Test /nlpq sur ${API} avec le prompt : ${PROMPT}"

check_png() {
  local file="$1"
  if [[ ! -s "$file" ]]; then echo "❌ $file vide"; return 1; fi
  local sig
  sig=$(hexdump -n 8 -C "$file" | head -n1 | awk '{print $2,$3,$4,$5,$6,$7,$8,$9}')
  if [[ "$sig" != "89 50 4e 47 0d 0a 1a 0a" ]]; then
    echo "❌ $file pas un PNG (sig=$sig)"; return 1
  fi
  echo "✅ $file OK"
}

mkdir -p out_nlpq

for lg in "${leagues[@]}"; do
  echo
  echo "→ ${lg}"
  slug=$(echo "$lg" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g')
  outfile="out_nlpq/${slug}.png"
  jq -n --arg prompt "$PROMPT" --arg league "$lg" \
    '{prompt:$prompt, league:$league}' \
    | curl -s -X POST "$API/nlpq" \
        -H "Content-Type: application/json" \
        -o "$outfile" \
        -d @-
  check_png "$outfile" || true
done

echo
echo "Fin des tests /nlpq."
