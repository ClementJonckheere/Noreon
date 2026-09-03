#!/usr/bin/env bash
# Crée (ou recrée) la base source d'un scénario de démonstration + le rôle
# LECTURE SEULE partagé `noreon_ro`. Une base Postgres par scénario = une
# « entreprise » autonome, la connexion la plus réaliste pour une démo.
#
# Usage :  sudo -u postgres bash demo/setup_scenario.sh retail
#          (le nom du scénario = sous-dossier de demo/ contenant seed.sql)
set -euo pipefail

SCENARIO="${1:?Usage: setup_scenario.sh <scenario>  (ex. retail, challenge/cause_diffuse)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SEED="$HERE/$SCENARIO/seed.sql"
# Les scénarios imbriqués (challenge/xxx) → base noreon_demo_challenge_xxx.
DB="noreon_demo_${SCENARIO//\//_}"
PSQL="${PSQL:-psql}"

[ -f "$SEED" ] || { echo "!! Introuvable : $SEED" >&2; exit 1; }

echo ">> (Re)création de la base $DB + rôle read-only noreon_ro"
$PSQL -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS ${DB};
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'noreon_ro') THEN
    CREATE ROLE noreon_ro LOGIN PASSWORD 'readonly';
  END IF;
END \$\$;
CREATE DATABASE ${DB};
SQL

echo ">> Chargement des données de démo ($SCENARIO)"
$PSQL -v ON_ERROR_STOP=1 -d "$DB" -f "$SEED"

echo ">> Attribution des droits LECTURE SEULE à noreon_ro"
$PSQL -v ON_ERROR_STOP=1 -d "$DB" <<SQL
GRANT CONNECT ON DATABASE ${DB} TO noreon_ro;
GRANT USAGE ON SCHEMA public TO noreon_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO noreon_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO noreon_ro;
SQL

echo ">> Terminé : $DB prête (rôle read-only noreon_ro / mot de passe readonly)."
