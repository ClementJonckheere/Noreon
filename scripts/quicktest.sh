#!/usr/bin/env bash
# =============================================================================
# Noreon — test rapide de bout en bout : connexion → scan → profil → question.
#
# Enchaîne les appels API (auth dev via en-tête X-Tenant) contre une base source,
# puis imprime la réponse du moteur. Nécessite que le backend tourne
# (uvicorn app.main:app) et que la base source existe.
#
# Usage :
#   bash scripts/quicktest.sh                 # scénario « retail » par défaut
#   bash scripts/quicktest.sh crm             # un scénario de la démo
#   bash scripts/quicktest.sh --db ma_base --question "Pourquoi ... ?"
#
# Variables d'environnement (surchargeables) :
#   API=http://localhost:8000  TENANT=demo
#   DBHOST=localhost  DBPORT=5432  DBUSER=noreon_ro  DBPASS=readonly
# =============================================================================
set -euo pipefail

API="${API:-http://localhost:8000}"
TENANT="${TENANT:-demo}"
DBHOST="${DBHOST:-localhost}"
DBPORT="${DBPORT:-5432}"
DBUSER="${DBUSER:-noreon_ro}"
DBPASS="${DBPASS:-readonly}"

# --- Résolution du scénario / des surcharges --------------------------------
SCENARIO="retail"; DB=""; QUESTION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --db)       DB="$2"; shift 2 ;;
    --question) QUESTION="$2"; shift 2 ;;
    --api)      API="$2"; shift 2 ;;
    -*)         echo "Option inconnue : $1" >&2; exit 2 ;;
    *)          SCENARIO="$1"; shift ;;
  esac
done

case "$SCENARIO" in
  retail)       DEF_DB="noreon_demo_retail";       DEF_Q="Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ?" ;;
  crm)          DEF_DB="noreon_demo_crm";          DEF_Q="Pourquoi le churn augmente-t-il ?" ;;
  finance)      DEF_DB="noreon_demo_finance";      DEF_Q="Pourquoi la marge diminue-t-elle ?" ;;
  supply_chain) DEF_DB="noreon_demo_supply_chain"; DEF_Q="Pourquoi les ruptures de stock augmentent-elles ?" ;;
  hr)           DEF_DB="noreon_demo_hr";           DEF_Q="Pourquoi les départs augmentent-ils ?" ;;
  *)            DEF_DB="noreon_demo_${SCENARIO}";  DEF_Q="Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ?" ;;
esac
DB="${DB:-$DEF_DB}"
QUESTION="${QUESTION:-$DEF_Q}"
NAME="quicktest-${SCENARIO}-$$"

hdr=(-H "Content-Type: application/json" -H "X-Tenant: ${TENANT}")
# Petit extracteur JSON (pas de dépendance à jq).
jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

echo "▶ API=$API  base=$DB  (utilisateur $DBUSER)"
if ! curl -sf "${hdr[@]}" "$API/health" >/dev/null 2>&1 && ! curl -sf "$API/docs" >/dev/null 2>&1; then
  echo "✗ Backend injoignable sur $API. Lancez : (cd backend && uvicorn app.main:app --reload)" >&2
  exit 1
fi

# --- 1) Connexion (vérifie automatiquement le read-only) --------------------
echo "▶ 1/4 Création de la connexion + vérification read-only…"
CREATE=$(curl -s "${hdr[@]}" -X POST "$API/connections" -d "$(python3 - "$NAME" "$DBHOST" "$DBPORT" "$DB" "$DBUSER" "$DBPASS" <<'PY'
import json,sys
n,h,p,d,u,pw=sys.argv[1:7]
print(json.dumps({"name":n,"engine":"postgresql","host":h,"port":int(p),
                  "database":d,"username":u,"password":pw}))
PY
)")
CID=$(printf '%s' "$CREATE" | jget "['connection']['id']" 2>/dev/null || true)
if [ -z "${CID:-}" ]; then
  echo "✗ Échec de la création :"; printf '%s\n' "$CREATE" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$CREATE"
  exit 1
fi
RO=$(printf '%s' "$CREATE" | jget "['connection'].get('is_read_only')" 2>/dev/null || echo "?")
ALERT=$(printf '%s' "$CREATE" | jget "(d.get('read_only_alert') or '')" 2>/dev/null || echo "")
echo "  ✓ connexion #$CID créée — lecture seule vérifiée : $RO"
[ -n "$ALERT" ] && echo "  ⚠ $ALERT"

# --- 2) Scan du schéma ------------------------------------------------------
echo "▶ 2/4 Scan du schéma (tables, colonnes, FK déclarées et inférées)…"
SCAN=$(curl -s "${hdr[@]}" -X POST "$API/connections/$CID/scan")
printf '%s' "$SCAN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"  ✓ {d.get('table_count','?')} table(s) — {d.get('message','scan effectué')}\")
" 2>/dev/null || echo "  ✓ scan effectué"
# Nombre de relations (déclarées + inférées).
REL=$(curl -s "${hdr[@]}" "$API/connections/$CID/relations" | python3 -c "
import sys,json
try: print(len(json.load(sys.stdin)))
except Exception: print('?')
" 2>/dev/null || echo "?")
echo "  ✓ $REL relation(s) (FK déclarées + inférées)"

# --- 3) Profilage (asynchrone) ---------------------------------------------
echo "▶ 3/4 Profilage (types réels, PII, qualité)…"
JOB=$(curl -s "${hdr[@]}" -X POST "$API/connections/$CID/profile")
JID=$(printf '%s' "$JOB" | jget "['id']" 2>/dev/null || true)
if [ -n "${JID:-}" ]; then
  for _ in $(seq 1 40); do
    ST=$(curl -s "${hdr[@]}" "$API/connections/$CID/profile/jobs/$JID" | jget "['status']" 2>/dev/null || echo "?")
    [ "$ST" = "done" ] && { echo "  ✓ profilage terminé"; break; }
    [ "$ST" = "error" ] && { echo "  ⚠ profilage en erreur — on continue quand même"; break; }
    sleep 1
  done
else
  echo "  (profilage lancé)"
fi

# --- 4) Question au moteur --------------------------------------------------
echo "▶ 4/4 Question : « $QUESTION »"
ANS=$(curl -s "${hdr[@]}" -X POST "$API/connections/$CID/chat" \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"question":sys.argv[1]}))' "$QUESTION")")

printf '%s' "$ANS" | python3 -c "
import sys,json
r=json.load(sys.stdin)
inv=r.get('investigation') or {}
print()
print('  Statut     :', r.get('status'))
print('  Message    :', (r.get('message') or '')[:400])
if inv.get('conclusion'): print('  Conclusion :', inv['conclusion'])
ds=(r.get('decisions') or {}).get('decisions') if r.get('decisions') else None
if ds:
    print('  Décisions  :')
    for x in ds:
        stars='★'*int(x.get('stars',3))
        print(f\"    {stars} {x['role']} — {x['recommendation']}\")
    if (r['decisions'] or {}).get('inaction'):
        print('  Inaction   :', r['decisions']['inaction'])
if r.get('serendipity'): print('  Sérendipité:', r['serendipity'].get('title'))
c=r.get('confidence') or {}
if c.get('score') is not None: print('  Confiance  :', c['score'])
" 2>/dev/null || { echo "  Réponse brute :"; printf '%s\n' "$ANS" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$ANS"; }

echo
echo "✔ Terminé. Interface : http://localhost:3000  ·  API docs : $API/docs"
