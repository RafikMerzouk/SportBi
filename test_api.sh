#!/usr/bin/env bash
# test_api.sh — tests end-to-end LBWL Analytics
# Usage:
#   ./test_api.sh                # http://localhost:8080
#   ./test_api.sh http://host:port

set -euo pipefail

API="${1:-${API:-http://localhost:8080}}"
OUT="out"
mkdir -p "$OUT"

red() { printf "\033[31m%s\033[0m\n" "$*"; }
grn() { printf "\033[32m%s\033[0m\n" "$*"; }
ylw() { printf "\033[33m%s\033[0m\n" "$*"; }
sec() { printf "\n\033[36m# %s\033[0m\n" "$*"; }

check_png() {
  local file="$1"
  if [[ ! -s "$file" ]]; then red "❌ $file vide"; return 1; fi
  local sig
  sig=$(hexdump -n 8 -C "$file" | head -n1 | awk '{print $2,$3,$4,$5,$6,$7,$8,$9}')
  if [[ "$sig" != "89 50 4e 47 0d 0a 1a 0a" ]]; then
    red "❌ $file pas un PNG (sig=$sig)"; echo "---- tail ----"; tail -c 200 "$file" || true
    return 1
  fi
  grn "✅ $file PNG OK"
}

FAILS=0
fail_plus() { FAILS=$((FAILS+1)); }

sec "Ping $API/docs"
if curl -s -o /dev/null -w "%{http_code}\n" "$API/docs" | grep -qE "200|404"; then
  grn "API joignable"
else
  red "❌ API injoignable"; exit 1
fi

# 1) /render — smoke
sec "1) /render — smoke"
curl -s -D "$OUT/h_smoke.txt" -o "$OUT/chart_smoke.png" \
  -H "Content-Type: application/json" \
  -w "time_total=%{time_total}\n" \
  -X POST "$API/render" \
  -d '{"sql":"SELECT 1 AS x, 2 AS y","params":{},"chart":{"type":"line","x":"x","y":"y","title":"Smoke test"}}' \
  || { red "curl KO"; fail_plus; }
grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_smoke.txt" || true
check_png "$OUT/chart_smoke.png" || fail_plus

# 2) /render — synth
sec "2) /render — synth"
curl -s -D "$OUT/h_synth.txt" -o "$OUT/chart_synth.png" \
  -H "Content-Type: application/json" \
  -w "time_total=%{time_total}\n" \
  -X POST "$API/render" \
  -d "{\"sql\":\"SELECT generate_series(1,50) AS x, (random()*100)::int AS y ORDER BY x\",\"params\":{},\"chart\":{\"type\":\"line\",\"x\":\"x\",\"y\":\"y\",\"title\":\"Synthetic\"}}" \
  || { red "curl KO"; fail_plus; }
grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_synth.txt" || true
check_png "$OUT/chart_synth.png" || fail_plus

# 3) /dry-run — monthly preview (SCORE)
sec "3) /dry-run — monthly preview"
cat > "$OUT/payload_dry.json" <<'JSON'
{
  "sql": "WITH scores AS (SELECT stm.matchid, stm.teamid, stm.value::int AS score FROM statteammatch stm JOIN statname sn ON sn.statnameid = stm.statnameid WHERE UPPER(sn.statnamelib) = 'SCORE') SELECT date_trunc('month', m.startdatematch) AS month, AVG(s.score) AS avg_score FROM match m JOIN scores s ON s.matchid = m.matchid GROUP BY month ORDER BY month",
  "params": {},
  "chart": { "type": "line", "x": "month", "y": "avg_score" }
}
JSON
curl -s -D "$OUT/h_dry.txt" -o "$OUT/dry.json" \
  -H "Content-Type: application/json" \
  -w "time_total=%{time_total}\n" \
  -X POST "$API/dry-run" \
  -d @"$OUT/payload_dry.json" \
  || { red "curl KO"; fail_plus; }
grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_dry.txt" || true
ylw "preview:"; head -c 220 "$OUT/dry.json" || true; echo

COUNT=$(python3 - <<'PY' "$OUT/dry.json" 2>/dev/null || echo 0
import sys, json, pathlib
p=pathlib.Path(sys.argv[1])
print(json.load(open(p)).get("count", 0) if p.exists() else 0)
PY
)

# 4) /render — monthly chart si données
sec "4) /render — monthly chart (si données)"
if [[ "${COUNT:-0}" -gt 0 ]]; then
  cat > "$OUT/payload_month.json" <<'JSON'
{
  "sql": "WITH scores AS (SELECT stm.matchid, stm.teamid, stm.value::int AS score FROM statteammatch stm JOIN statname sn ON sn.statnameid = stm.statnameid WHERE UPPER(sn.statnamelib) = 'SCORE') SELECT date_trunc('month', m.startdatematch) AS month, AVG(s.score) AS avg_score FROM match m JOIN scores s ON s.matchid = m.matchid GROUP BY month ORDER BY month",
  "params": {},
  "chart": {
    "type": "line",
    "x": "month",
    "y": "avg_score",
    "title": "LBWL — Score moyen par mois",
    "x_label": "Mois",
    "y_label": "Score moyen",
    "options": { "sort": true, "rolling": 3, "x_rotate": 0, "y_fmt": "float1", "theme": "light" }
  }
}
JSON
  curl -s -D "$OUT/h_month.txt" -o "$OUT/chart_monthly.png" \
    -H "Content-Type: application/json" \
    -w "time_total=%{time_total}\n" \
    -X POST "$API/render" \
    -d @"$OUT/payload_month.json" \
    || { red "curl KO"; fail_plus; }
  grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_month.txt" || true
  check_png "$OUT/chart_monthly.png" || fail_plus
else
  ylw "↷ Pas de données LBWL (count=$COUNT) — on saute le PNG monthly."
fi

# 5) /render — Top-10 équipes (bar + options)
sec "5) /render — Top-10 équipes par score moyen"
cat > "$OUT/payload_top.json" <<'JSON'
{
  "sql": "WITH scores AS (SELECT stm.teamid, stm.value::int AS score FROM statteammatch stm JOIN statname sn ON sn.statnameid = stm.statnameid WHERE UPPER(sn.statnamelib) = 'SCORE') SELECT t.teamname AS team, AVG(scores.score) AS avg_score FROM team t JOIN scores ON scores.teamid=t.teamid GROUP BY team ORDER BY avg_score DESC",
  "params": {},
  "chart": {
    "type": "bar",
    "x": "team",
    "y": "avg_score",
    "title": "LBWL — Top 10 moyennes de score (équipes)",
    "x_label": "",
    "y_label": "Score moyen",
    "options": { "top_n": 10, "x_rotate": 30, "y_fmt": "int", "sort": false, "theme": "light" }
  }
}
JSON
curl -s -D "$OUT/h_top.txt" -o "$OUT/chart_top.png" \
  -H "Content-Type: application/json" \
  -w "time_total=%{time_total}\n" \
  -X POST "$API/render" \
  -d @"$OUT/payload_top.json" \
  || { red "curl KO"; fail_plus; }
grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_top.txt" || true
check_png "$OUT/chart_top.png" || fail_plus

# 6) /render/base64 — smoke
sec "6) /render/base64 — smoke"
curl -s -D "$OUT/h_b64.txt" -o "$OUT/b64.json" \
  -H "Content-Type: application/json" \
  -w "time_total=%{time_total}\n" \
  -X POST "$API/render/base64" \
  -d '{"sql":"SELECT 1 AS x, 3 AS y","params":{},"chart":{"type":"bar","x":"x","y":"y","title":"B64"}}' \
  || { red "curl KO"; fail_plus; }
grep -iE 'HTTP/|Content-Type|Content-Length|time_total' "$OUT/h_b64.txt" || true
python3 - <<'PY' "$OUT/b64.json" "$OUT/chart_b64.png"
import sys, json, base64, pathlib
j=json.load(open(sys.argv[1]))
pathlib.Path(sys.argv[2]).write_bytes(base64.b64decode(j["base64"]))
print("→ écrit", sys.argv[2])
PY
check_png "$OUT/chart_b64.png" || fail_plus

# Bilan
if [[ "$FAILS" -eq 0 ]]; then
  grn "🎉 Tous les tests OK (API = $API)"
  exit 0
else
  red "❌ $FAILS test(s) en échec (API = $API)"
  exit 1
fi
