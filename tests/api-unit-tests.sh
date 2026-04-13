#!/usr/bin/env bash
# test.sh — post-deploy smoke tests for Obit Watch
# Usage:   ./test.sh [API_BASE_URL]
# Default: http://watermelon:8001

API="${1:-https://api-obit-watch.mkdwns.duckdns.org}"
#API="${1:-http://watermelon:8001}"

PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

WATCH_ID=""
OBIT_ID=""
MATCH_ID=""
TEST_FIRST="zzzsmoketest"
TEST_LAST="zzzsmoketest"

section() {
    echo ""
    echo -e "${YELLOW}━━━ $1${NC}"
}

pass() {
    echo -e "${GREEN}  ✓ PASS${NC}  $1"
    PASS=$((PASS+1))
}

fail() {
    echo -e "${RED}  ✗ FAIL${NC}  $1"
    FAIL=$((FAIL+1))
}

show_field() {
    echo -e "${CYAN}  ·${NC} $1: $2"
}

do_get() {
    local path="$1"
    echo -e "${DIM}  → GET ${API}${path}${NC}"
    local http_code resp
    http_code=$(curl -s -o /tmp/ow_resp -w "%{http_code}" "${API}${path}" 2>/dev/null)
    resp=$(cat /tmp/ow_resp 2>/dev/null || echo "")
    echo -e "${DIM}  ← HTTP ${http_code}${NC}"
    if [ -n "$resp" ]; then
        echo -e "${DIM}  ← $(echo "$resp" | python3 -m json.tool 2>/dev/null || echo "$resp")${NC}"
    fi
    HTTP_CODE="$http_code"
    LAST_RESP="$resp"
}

do_post() {
    local path="$1" body="$2"
    echo -e "${DIM}  → POST ${API}${path}${NC}"
    echo -e "${DIM}  → body: $body${NC}"
    local http_code resp
    http_code=$(curl -s -o /tmp/ow_resp -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" -d "$body" "${API}${path}" 2>/dev/null)
    resp=$(cat /tmp/ow_resp 2>/dev/null || echo "")
    echo -e "${DIM}  ← HTTP ${http_code}${NC}"
    if [ -n "$resp" ]; then
        echo -e "${DIM}  ← $(echo "$resp" | python3 -m json.tool 2>/dev/null || echo "$resp")${NC}"
    fi
    HTTP_CODE="$http_code"
    LAST_RESP="$resp"
}

do_delete() {
    local path="$1"
    echo -e "${DIM}  → DELETE ${API}${path}${NC}"
    local http_code resp
    http_code=$(curl -s -o /tmp/ow_resp -w "%{http_code}" -X DELETE "${API}${path}" 2>/dev/null)
    resp=$(cat /tmp/ow_resp 2>/dev/null || echo "")
    echo -e "${DIM}  ← HTTP ${http_code}${NC}"
    HTTP_CODE="$http_code"
    LAST_RESP="$resp"
}

jget() {
    python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('${2}',''))" "$1" 2>/dev/null || echo ""
}

jlen() {
    python3 -c "import sys,json; print(len(json.loads(sys.argv[1])))" "$1" 2>/dev/null || echo "0"
}

cleanup() {
    section "Cleanup"
    if [ -n "$WATCH_ID" ]; then
        do_delete "/api/watchlist/${WATCH_ID}"
        pass "Deleted test watchlist entry (id=${WATCH_ID})"
    fi
    if [ -n "$OBIT_ID" ]; then
        do_delete "/api/test/obits/${OBIT_ID}"
        pass "Deleted test obit (id=${OBIT_ID})"
    fi
    section "Summary"
    echo -e "  ${GREEN}${PASS} passed${NC}   ${RED}${FAIL} failed${NC}"
    echo ""
    if [ "$FAIL" -eq 0 ]; then
        echo -e "  ${GREEN}DEPLOY OK${NC}"
    else
        echo -e "  ${RED}DEPLOY FAILED${NC}"
    fi
    echo ""
}
trap cleanup EXIT

# ── Begin ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${YELLOW}Obit Watch — smoke tests${NC}"
echo -e "API: ${CYAN}${API}${NC}"

# 1. Health
section "1. Health — GET /api/health"
do_get "/api/health"
status=$(jget "$LAST_RESP" "status")
db_path=$(jget "$LAST_RESP" "db")
show_field "status"  "$status"
show_field "db_path" "$db_path"
[ "$status" = "ok" ] && pass "API is healthy" || fail "API health check failed"

# 2. Watchlist list
section "2. Watchlist — GET /api/watchlist"
do_get "/api/watchlist"
count=$(jlen "$LAST_RESP")
show_field "active entries" "$count"
python3 -c "import sys,json; [print(f\"  · id={e['id']} {e['first_name']} {e['last_name']}\") for e in json.loads(sys.argv[1])[:5]]" "$LAST_RESP" 2>/dev/null || true
pass "Watchlist returned ${count} active entries"

# 3. Watchlist create
section "3. Watchlist — POST /api/watchlist"
do_post "/api/watchlist" "{\"first_name\":\"${TEST_FIRST}\",\"last_name\":\"${TEST_LAST}\",\"city\":\"Testville\",\"state\":\"OH\",\"note\":\"smoke test\"}"
WATCH_ID=$(jget "$LAST_RESP" "id")
show_field "id"         "$WATCH_ID"
show_field "first_name" "$(jget "$LAST_RESP" "first_name")"
show_field "last_name"  "$(jget "$LAST_RESP" "last_name")"
show_field "added_at"   "$(jget "$LAST_RESP" "added_at")"
[ -n "$WATCH_ID" ] && pass "Watchlist entry created (id=${WATCH_ID})" || fail "Watchlist create failed"

# 4. Verify entry persisted
section "4. Watchlist — verify entry persisted"
do_get "/api/watchlist"
found=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print('yes' if any(e['id']==${WATCH_ID:-0} for e in d) else 'no')" "$LAST_RESP" 2>/dev/null || echo "no")
show_field "entry id=${WATCH_ID} in list" "$found"
[ "$found" = "yes" ] && pass "Entry visible in watchlist" || fail "Entry not found in watchlist"

# 5. Test obit create
section "5. Test obits — POST /api/test/obits"
do_post "/api/test/obits" "{\"first_name\":\"${TEST_FIRST}\",\"last_name\":\"${TEST_LAST}\",\"location\":\"Testville, OH\",\"death_year\":\"2026\",\"obit_snippet\":\"Smoke test. Hated owner of cats.\"}"
OBIT_ID=$(jget "$LAST_RESP" "id")
show_field "id"       "$OBIT_ID"
show_field "obit_url" "$(jget "$LAST_RESP" "obit_url")"
show_field "source"   "$(jget "$LAST_RESP" "source")"
[ -n "$OBIT_ID" ] && pass "Test obit created (id=${OBIT_ID})" || fail "Test obit creation failed"

# 6. Test obit search
section "6. Test obits — GET /api/test/obits/search"
do_get "/api/test/obits/search?first_name=${TEST_FIRST}&last_name=${TEST_LAST}"
count=$(jlen "$LAST_RESP")
show_field "results" "$count"
[ "$count" -ge 1 ] && pass "Search returned ${count} result(s)" || fail "Search returned 0 results"

# 7. Matches before scan
section "7. Matches — GET /api/matches (before scan)"
do_get "/api/matches"
count=$(jlen "$LAST_RESP")
show_field "active matches" "$count"
pass "Matches endpoint returned ${count} active match(es)"

# 8. Scan
section "8. Scan — POST /api/scan"
echo "  Running full scan across all sources (~30s)..."
do_post "/api/scan" "{}"
scanned=$(jget "$LAST_RESP" "scanned")
new_matches=$(jget "$LAST_RESP" "new_matches")
show_field "names scanned" "$scanned"
show_field "new matches"   "$new_matches"
[ -n "$scanned" ] && pass "Scan completed (scanned=${scanned} new=${new_matches})" || fail "Scan returned unexpected result"

# 9. Verify match created
section "9. Matches — verify test entry was matched"
do_get "/api/matches"
MATCH_ID=$(python3 -c "
import sys,json
data=json.loads(sys.argv[1])
hit=next((m for m in data if m.get('first_name','').lower()=='${TEST_FIRST}' and m.get('last_name','').lower()=='${TEST_LAST}'),None)
print(hit['id'] if hit else '')
" "$LAST_RESP" 2>/dev/null || echo "")
if [ -n "$MATCH_ID" ]; then
    show_field "match id" "$MATCH_ID"
    show_field "source"   "$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); hit=next((m for m in d if m['id']==${MATCH_ID}),{}); print(hit.get('source',''))" "$LAST_RESP" 2>/dev/null)"
    show_field "location" "$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); hit=next((m for m in d if m['id']==${MATCH_ID}),{}); print(hit.get('location',''))" "$LAST_RESP" 2>/dev/null)"
    show_field "snippet"  "$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); hit=next((m for m in d if m['id']==${MATCH_ID}),{}); print((hit.get('obit_snippet') or '')[:60])" "$LAST_RESP" 2>/dev/null)"
    pass "Match created for test entry (id=${MATCH_ID})"
else
    fail "No match found for test entry after scan"
fi

# 10. Dismiss
section "10. Matches — POST /api/matches/${MATCH_ID}/dismiss"
if [ -n "$MATCH_ID" ]; then
    do_post "/api/matches/${MATCH_ID}/dismiss" "{}"
    show_field "response" "$LAST_RESP"
    echo "$LAST_RESP" | grep -qi '"ok"' && pass "Match dismissed" || fail "Dismiss did not return ok"

    do_get "/api/matches"
    still=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print('yes' if any(m['id']==${MATCH_ID} for m in d) else 'no')" "$LAST_RESP" 2>/dev/null || echo "yes")
    show_field "still in active list" "$still"
    [ "$still" = "no" ] && pass "Dismissed match no longer in active list" || fail "Dismissed match still in active list"
else
    fail "Skipping dismiss — no match ID (scan may have failed)"
fi

# 11. Settings
section "11. Settings — GET /api/settings"
do_get "/api/settings"
alert_to=$(jget "$LAST_RESP" "alert_to")
smtp_host=$(jget "$LAST_RESP" "smtp_host")
smtp_user=$(jget "$LAST_RESP" "smtp_user")
show_field "alert_to"  "$alert_to"
show_field "smtp_host" "$smtp_host"
show_field "smtp_user" "$smtp_user"
[ -n "$alert_to" ] && pass "Settings returns alert_to=${alert_to}" || fail "Settings missing alert_to"

# 12. Sources
section "12. Sources — GET /api/sources"
do_get "/api/sources"
count=$(jlen "$LAST_RESP")
show_field "total sources" "$count"
python3 -c "
import sys,json
for s in json.loads(sys.argv[1]):
    state='enabled' if s.get('enabled') else 'disabled'
    print(f\"  · {s.get('name','?')} ({s.get('label','?')}) — {state}\")
" "$LAST_RESP" 2>/dev/null || true
[ "$count" -ge 1 ] && pass "Sources returned ${count} source(s)" || fail "Sources returned no sources"

# 13. Scan log
section "13. Scan log — GET /api/scan/log"
do_get "/api/scan/log"
count=$(jlen "$LAST_RESP")
show_field "log entries" "$count"
python3 -c "
import sys,json
d=json.loads(sys.argv[1])
if d:
    e=d[0]
    print(f\"  · latest: started={e.get('started_at','?')} scanned={e.get('names_scanned','?')} matches={e.get('matches_found','?')} errors={e.get('errors','none')}\")
" "$LAST_RESP" 2>/dev/null || true
[ "$count" -ge 1 ] && pass "Scan log has ${count} entr(ies)" || fail "Scan log is empty"
