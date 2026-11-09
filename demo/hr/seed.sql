-- =============================================================================
-- Noreon — Démonstration · Scénario « RH »  (ESN fictive « TalentForge »)
-- Base source : noreon_demo_hr
--
-- Question :  « Pourquoi les départs augmentent-ils ? »
--
-- HISTOIRE PLANTÉE (cf. demo/hr/notes.md) :
--   • Les départs (coût de remplacement cumulé / mois) sont stables, puis
--     AUGMENTENT sur 4 mois, de façon accélérée.
--   • Cause dominante : le département « Ingénierie » — vague de démissions
--     (surcharge + marché tendu). Il porte l'essentiel de la hausse (~ 80 %+).
--     Les autres départements (Ventes, Support, Marketing) restent stables.
--   • Motif dominant sur la fenêtre : « Démission ».
--
-- Mesure choisie par le moteur : sum(cout_remplacement)  (indice « cout »).
-- Axe causal : departement (colonne propre de la table de faits).
-- =============================================================================

DROP TABLE IF EXISTS departs, employes CASCADE;

CREATE TABLE employes (
    id            serial PRIMARY KEY,
    nom           varchar(200) NOT NULL,
    email         varchar(200),
    departement   varchar(60),
    date_embauche date
);

CREATE TABLE departs (
    id                serial PRIMARY KEY,
    employe_id        integer REFERENCES employes(id),   -- FK → fait sortant
    date_depart       date,
    departement       varchar(60),      -- axe causal
    motif             varchar(40),      -- Démission | Fin de contrat | Licenciement | Retraite
    duree_poste_mois   integer,
    cout_remplacement numeric(10,2)     -- MESURE (indice « cout ») : coût de remplacement €
);

INSERT INTO employes (nom, email, departement, date_embauche)
SELECT 'Salarié ' || g,
       CASE WHEN g % 45 = 0 THEN 'pas-un-email' ELSE 'salarie' || g || '@example.com' END,
       (ARRAY['Ingénierie','Ventes','Support','Marketing'])[1 + (g % 4)],
       DATE '2019-01-01' + (g % 1800)
FROM generate_series(1, 700) g;

SELECT setseed(0.9);

DO $$
DECLARE
    d       text;
    m       integer;
    k       integer;
    n       integer;
    base    integer;      -- départs/mois de référence pour le département
    mult    numeric;
    emp     integer;
    mtf     text;
    anc     integer;
    cout_v  numeric;
    ddate   date;
    deps text[] := ARRAY['Ingénierie','Ventes','Support','Marketing'];
BEGIN
    FOREACH d IN ARRAY deps LOOP
        base := CASE d WHEN 'Ingénierie' THEN 5 WHEN 'Ventes' THEN 4
                       WHEN 'Support' THEN 4 ELSE 3 END;

        FOR m IN 0..17 LOOP
            mult := 1.0;
            -- Vague de démissions en « Ingénierie » sur les 4 derniers mois.
            IF d = 'Ingénierie' AND m >= 14 THEN
                mult := CASE m WHEN 14 THEN 1.6 WHEN 15 THEN 2.0
                               WHEN 16 THEN 2.4 WHEN 17 THEN 2.8 END;
            END IF;
            n := round(base * mult);

            FOR k IN 1..n LOOP
                emp := 1 + floor(random() * 700)::int;
                -- Sur la fenêtre en Ingénierie, ce sont surtout des démissions.
                IF d = 'Ingénierie' AND m >= 14 THEN
                    mtf := (ARRAY['Démission','Démission','Démission','Fin de contrat'])[1 + floor(random()*4)::int];
                ELSE
                    mtf := (ARRAY['Démission','Fin de contrat','Retraite','Licenciement'])[1 + floor(random()*4)::int];
                END IF;
                anc := 6 + floor(random() * 90)::int;
                -- Un ingénieur coûte plus cher à remplacer.
                cout_v := CASE d WHEN 'Ingénierie' THEN 14000 WHEN 'Ventes' THEN 9000
                                 WHEN 'Support' THEN 6000 ELSE 8000 END
                          * (0.8 + random() * 0.4);
                ddate := (DATE '2024-01-01' + (m || ' months')::interval)::date
                         + floor(random() * 28)::int;
                INSERT INTO departs (employe_id, date_depart, departement, motif,
                                     duree_poste_mois, cout_remplacement)
                VALUES (emp, ddate, d, mtf, anc, round(cout_v::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
