#!/usr/bin/env bash
# Crée la base source de démonstration + un rôle LECTURE SEULE dédié à Noreon.
# Usage : sudo -u postgres bash scripts/setup_demo.sh   (ou adapter PSQL)
set -euo pipefail

PSQL="${PSQL:-psql}"

echo ">> (Re)création de la base noreon_demo"
$PSQL -v ON_ERROR_STOP=1 <<'SQL'
DROP DATABASE IF EXISTS noreon_demo;
DROP ROLE IF EXISTS noreon_ro;
CREATE DATABASE noreon_demo;
CREATE ROLE noreon_ro LOGIN PASSWORD 'readonly';
SQL

echo ">> Chargement des données de démo"
$PSQL -v ON_ERROR_STOP=1 -d noreon_demo -f "$(dirname "$0")/seed_demo.sql"

echo ">> Attribution des droits LECTURE SEULE à noreon_ro"
$PSQL -v ON_ERROR_STOP=1 -d noreon_demo <<'SQL'
GRANT CONNECT ON DATABASE noreon_demo TO noreon_ro;
GRANT USAGE ON SCHEMA public TO noreon_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO noreon_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO noreon_ro;
SQL

echo ">> Terminé : base noreon_demo prête, rôle read-only 'noreon_ro' / mot de passe 'readonly'."
