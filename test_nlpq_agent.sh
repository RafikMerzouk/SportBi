#!/usr/bin/env bash
# test_nlpq_agent.sh — teste la route /nlpq (agent LLM) et /nlpq/structured
# Usage:
#   ./test_nlpq_agent.sh                  # cible http://localhost:8080
#   ./test_nlpq_agent.sh http://host:port

set -euo pipefail

API="${1:-${API:-http://localhost:8080}}"
OUT="out_nlpq_agent"
mkdir -p "$OUT"

PROMPTS=(
  # On limite aux ligues où on a plusieurs saisons : Bundesliga, Serie A, LaLiga
  "buts totaux par saison en bundesliga"
  "buts totaux par saison en serie a"
  "buts totaux par saison en laliga"
  "repartition victoires/défaites en bundesliga"
  # Prompts club pour tester les filtres d'équipe
  "nombre de victoires par saison du bayern munich en bundesliga"
  "buts totaux par saison du real madrid en laliga"
  "repartition victoires défaites juventus en serie a"
)

echo "# Test /nlpq (agent LLM) sur ${API}"

for i in "${!PROMPTS[@]}"; do
  p="${PROMPTS[$i]}"
  slug=$(echo "$p" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | sed 's/_\\+/_/g')
  img="${OUT}/${i}_${slug}.png"
  echo "→ $p"
  curl -s -X POST "$API/nlpq" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"${p}\"}" \
    -o "$img"
  sig=$(hexdump -n 8 -C "$img" 2>/dev/null | head -n1 | awk '{print $2,$3,$4,$5,$6,$7,$8,$9}')
  if [[ "$sig" == "89 50 4e 47 0d 0a 1a 0a" ]]; then
    echo "  ✅ PNG ok ($img)"
  else
    echo "  ❌ pas un PNG (sig=$sig) — contenu:"
    head -c 200 "$img" || true
    echo
  fi
done

echo
echo "Fin des tests nlpq agent."
