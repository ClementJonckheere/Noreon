-- =============================================================================
-- Noreon — Démonstration · Scénario « Finance »  (industriel fictif « Novindus »)
-- Base source : noreon_demo_finance
--
-- Question :  « Pourquoi la marge diminue-t-elle ? »
--
-- HISTOIRE PLANTÉE (cf. demo/finance/notes.md) :
--   • La marge (€) est stable, puis DIMINUE sur 4 mois, de façon accélérée.
--   • Cause dominante : la ligne de produits « Composants » — le coût
--     d'approvisionnement a bondi (fournisseur), la marge s'y effondre alors que
--     le chiffre d'affaires tient. Elle porte l'essentiel de la baisse (~ 85 %+).
--   • Les autres lignes (Assemblage, Services, Maintenance) restent stables.
--
-- Mesure choisie par le moteur : sum(montant_marge)  (indice « montant »).
-- Axe causal : ligne_produit (colonne propre de la table de faits).
-- Piège : marge = revenue - cout ; on expose les trois (revenue & cout gardés
-- pour la preuve, la mesure principale reste la marge).
-- =============================================================================

DROP TABLE IF EXISTS transactions, clients CASCADE;

CREATE TABLE clients (
    id     serial PRIMARY KEY,
    nom    varchar(200) NOT NULL,
    email  varchar(200),
    region varchar(80)
);

CREATE TABLE transactions (
    id            serial PRIMARY KEY,
    client_id     integer REFERENCES clients(id),   -- FK → fait sortant
    date_facture  date,
    ligne_produit varchar(40),        -- axe causal
    montant_marge numeric(12,2),      -- MESURE (indice « montant ») : marge €
    revenue       numeric(12,2),      -- preuve : CA
    cout          numeric(12,2)       -- preuve : coût
);

INSERT INTO clients (nom, email, region)
SELECT 'Client ' || g,
       CASE WHEN g % 35 = 0 THEN 'pas-un-email' ELSE 'client' || g || '@example.com' END,
       (ARRAY['Nord','Sud','Est','Ouest'])[1 + (g % 4)]
FROM generate_series(1, 300) g;

SELECT setseed(0.55);

DO $$
DECLARE
    lp        text;
    m         integer;
    k         integer;
    n         integer;
    base_n    integer;      -- volume de factures/mois pour la ligne
    base_rev  numeric;      -- CA moyen par facture
    margin_r  numeric;      -- taux de marge « normal »
    mr        numeric;      -- taux de marge appliqué (érodé sur la fenêtre)
    cust      integer;
    rev       numeric;
    cout_v    numeric;
    fdate     date;
    lines text[] := ARRAY['Composants','Assemblage','Services','Maintenance'];
BEGIN
    FOREACH lp IN ARRAY lines LOOP
        base_n   := CASE lp WHEN 'Composants' THEN 60 WHEN 'Assemblage' THEN 40
                            WHEN 'Services' THEN 30 ELSE 25 END;
        base_rev := CASE lp WHEN 'Composants' THEN 900 WHEN 'Assemblage' THEN 1400
                            WHEN 'Services' THEN 700 ELSE 500 END;
        margin_r := CASE lp WHEN 'Composants' THEN 0.32 WHEN 'Assemblage' THEN 0.28
                            WHEN 'Services' THEN 0.45 ELSE 0.40 END;

        FOR m IN 0..17 LOOP
            mr := margin_r;
            -- Choc fournisseur sur « Composants » : le coût grimpe, la marge fond.
            IF lp = 'Composants' AND m >= 14 THEN
                mr := margin_r - CASE m WHEN 14 THEN 0.08 WHEN 15 THEN 0.14
                                        WHEN 16 THEN 0.20 WHEN 17 THEN 0.26 END;
            END IF;

            FOR k IN 1..base_n LOOP
                cust := 1 + floor(random() * 300)::int;
                rev  := base_rev * (0.7 + random() * 0.6);
                cout_v := rev * (1 - mr);
                fdate := (DATE '2024-01-01' + (m || ' months')::interval)::date
                         + floor(random() * 28)::int;
                INSERT INTO transactions (client_id, date_facture, ligne_produit,
                                          montant_marge, revenue, cout)
                VALUES (cust, fdate, lp,
                        round((rev - cout_v)::numeric, 2),
                        round(rev::numeric, 2), round(cout_v::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

-- Imperfection qualité : quelques marges manquantes (complétude).
UPDATE transactions SET montant_marge = NULL WHERE id % 90 = 0;

ANALYZE;
