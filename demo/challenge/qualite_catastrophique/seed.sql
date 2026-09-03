-- =============================================================================
-- Noreon CHALLENGE · « Qualité catastrophique »
-- Base source : noreon_demo_challenge_qualite_catastrophique
--
-- Question :  « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- PIÈGE (cf. notes.md) : les données sont TROP MAUVAISES pour conclure.
--   • ~ 55 % des montants (amount_ttc) sont NULL ;
--   • ~ 50 % des dates (order_date) sont NULL → aucune tendance fiable ;
--   • ~ 60 % des store_id sont NULL ou orphelins → aucune ventilation fiable ;
--   • valeurs sentinelles mélangées (0, -1) qui signifient « inconnu ».
--
-- Le meilleur comportement N'EST PAS de fabriquer une réponse. C'est de dire :
--   « Je ne peux pas conclure avec suffisamment de confiance : la qualité des
--     données est insuffisante (montants et dates majoritairement manquants). »
--
-- C'est un signe de MATURITÉ : mieux vaut une honnête abstention qu'une fausse
-- certitude tirée de données trouées.
-- =============================================================================

DROP TABLE IF EXISTS orders, stores CASCADE;

CREATE TABLE stores (
    id serial PRIMARY KEY, name varchar(120), region varchar(100)
);
CREATE TABLE orders (
    id serial PRIMARY KEY, store_id integer, order_date date, amount_ttc numeric(10,2)
);

INSERT INTO stores (name, region) VALUES
 ('Store A', 'Nord'), ('Store B', 'Sud'), ('Store C', 'Est'), ('Store D', 'Ouest');

SELECT setseed(0.17);

INSERT INTO orders (store_id, order_date, amount_ttc)
SELECT
    -- 60 % de store_id inutilisables (NULL ou magasin 99 inexistant).
    CASE WHEN g % 5 = 0 THEN NULL WHEN g % 5 = 1 THEN 99 ELSE 1 + (g % 4) END,
    -- 50 % de dates manquantes → aucune tendance temporelle fiable.
    CASE WHEN g % 2 = 0 THEN NULL
         ELSE (DATE '2024-01-01' + (g % 550))::date END,
    -- ~ 55 % de montants inutilisables : NULL, 0 ou -1 (sentinelles « inconnu »).
    CASE WHEN g % 20 < 9 THEN NULL
         WHEN g % 20 = 9 THEN 0
         WHEN g % 20 = 10 THEN -1
         ELSE round((20 + (g % 400))::numeric, 2) END
FROM generate_series(1, 3000) g;

ANALYZE;
