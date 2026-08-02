-- =============================================================================
-- Noreon — Démonstration · Scénario « Supply Chain »  (distributeur « LogiPro »)
-- Base source : noreon_demo_supply_chain
--
-- Question :  « Pourquoi les ruptures de stock augmentent-elles ? »
--
-- HISTOIRE PLANTÉE (cf. demo/supply_chain/notes.md) :
--   • Les ruptures (jours de rupture cumulés / mois) sont stables, puis
--     AUGMENTENT sur 4 mois, de façon accélérée.
--   • Cause dominante : le fournisseur « Fournisseur Delta » — son délai de
--     livraison a explosé, ses SKU tombent en rupture. Il porte l'essentiel de la
--     hausse (~ 85 %+). Les autres fournisseurs restent stables.
--
-- Mesure choisie par le moteur : sum(cout_rupture)  (indice « cout »).
-- Axe causal : fournisseur (colonne propre de la table de faits).
-- =============================================================================

DROP TABLE IF EXISTS stockouts, entrepots CASCADE;

CREATE TABLE entrepots (
    id    serial PRIMARY KEY,
    nom   varchar(100) NOT NULL,
    ville varchar(100)
);

CREATE TABLE stockouts (
    id            serial PRIMARY KEY,
    entrepot_id   integer REFERENCES entrepots(id),  -- FK → fait sortant
    date_rupture  date,
    sku           varchar(40),
    fournisseur   varchar(60),        -- axe causal
    jours_rupture integer,
    cout_rupture  numeric(10,2)       -- MESURE (indice « cout ») : ventes perdues €
);

INSERT INTO entrepots (nom, ville) VALUES
 ('Entrepôt Nord', 'Lille'), ('Entrepôt Sud', 'Marseille'),
 ('Entrepôt Ouest', 'Nantes'), ('Entrepôt Est', 'Strasbourg');

SELECT setseed(0.33);

DO $$
DECLARE
    f       text;
    m       integer;
    k       integer;
    n       integer;
    base    integer;      -- ruptures/mois de référence pour le fournisseur
    mult    numeric;
    jours   integer;
    cout_v  numeric;
    rdate   date;
    suppliers text[] := ARRAY['Fournisseur Alpha','Fournisseur Beta','Fournisseur Delta','Fournisseur Gamma'];
BEGIN
    FOREACH f IN ARRAY suppliers LOOP
        base := CASE f WHEN 'Fournisseur Alpha' THEN 8 WHEN 'Fournisseur Beta' THEN 6
                       WHEN 'Fournisseur Delta' THEN 7 ELSE 5 END;

        FOR m IN 0..17 LOOP
            mult := 1.0;
            -- Délais qui explosent chez « Delta » sur les 4 derniers mois.
            IF f = 'Fournisseur Delta' AND m >= 14 THEN
                mult := CASE m WHEN 14 THEN 1.5 WHEN 15 THEN 1.9
                               WHEN 16 THEN 2.3 WHEN 17 THEN 2.7 END;
            END IF;
            n := round(base * mult);

            FOR k IN 1..n LOOP
                -- Chez Delta en crise, les ruptures durent plus longtemps aussi.
                jours := CASE WHEN f = 'Fournisseur Delta' AND m >= 14
                              THEN 2 + floor(random() * 6)::int
                              ELSE 1 + floor(random() * 5)::int END;
                cout_v := jours * (80 + random() * 120);
                rdate := (DATE '2024-01-01' + (m || ' months')::interval)::date
                         + floor(random() * 28)::int;
                INSERT INTO stockouts (entrepot_id, date_rupture, sku, fournisseur,
                                       jours_rupture, cout_rupture)
                VALUES (1 + floor(random() * 4)::int, rdate,
                        'SKU-' || (1000 + floor(random() * 400)::int),
                        f, jours, round(cout_v::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
