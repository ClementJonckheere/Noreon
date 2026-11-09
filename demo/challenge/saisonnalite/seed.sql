-- =============================================================================
-- Noreon CHALLENGE · « Saisonnalité »
-- Base source : noreon_demo_challenge_saisonnalite
--
-- Question :  « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- PIÈGE (cf. notes.md) : la baisse des 4 derniers mois est... NORMALE. Le CA
-- suit un cycle SAISONNIER (creux estival juin→août) qui se répète CHAQUE année,
-- dans les mêmes proportions. Comparer au mois précédent → « ça baisse ! ».
-- Comparer à la MÊME période l'an dernier → « c'est identique, rien d'anormal ».
--
-- 30 mois d'historique (janv. 2023 → juin 2025), léger +3 %/an de croissance.
-- Réponse attendue d'un analyste senior :
--   « Cette baisse est SAISONNIÈRE (juin est toujours plus faible). En glissement
--     annuel, le CA est même légèrement au-dessus de l'an dernier : pas d'anomalie. »
--
-- Un moteur naïf crie à la baisse. Un bon moteur reconnaît la saisonnalité.
-- =============================================================================

DROP TABLE IF EXISTS orders, stores CASCADE;

CREATE TABLE stores (
    id serial PRIMARY KEY, name varchar(120), city varchar(100), region varchar(100)
);
CREATE TABLE orders (
    id serial PRIMARY KEY, store_id integer REFERENCES stores(id),
    order_date date, amount_ttc numeric(10,2)
);

INSERT INTO stores (name, city, region) VALUES
 ('Paris Centre', 'Paris', 'Île-de-France'),
 ('Lyon Presqu''île', 'Lyon', 'Auvergne-Rhône-Alpes'),
 ('Marseille Prado', 'Marseille', 'Provence-Alpes-Côte d''Azur'),
 ('Lille Grand Place', 'Lille', 'Hauts-de-France');

SELECT setseed(0.61);

DO $$
DECLARE
    s RECORD; m integer; k integer; n integer;
    base_orders numeric; base_basket numeric;
    seasonal numeric; growth numeric; cal_month integer;
    amt numeric; odate date;
BEGIN
    FOR s IN SELECT * FROM stores ORDER BY id LOOP
        base_orders := CASE s.id WHEN 1 THEN 90 WHEN 2 THEN 72 WHEN 3 THEN 80 ELSE 55 END;
        base_basket := CASE s.id WHEN 1 THEN 92 WHEN 2 THEN 80 WHEN 3 THEN 86 ELSE 74 END;
        FOR m IN 0..29 LOOP    -- janv. 2023 (0) → juin 2025 (29)
            cal_month := 1 + ((m) % 12);   -- 1 = janvier … 12 = décembre
            -- Facteur SAISONNIER identique chaque année (creux estival, pic déc.).
            seasonal := CASE cal_month
                WHEN 1 THEN 1.00 WHEN 2 THEN 1.00 WHEN 3 THEN 1.05 WHEN 4 THEN 1.05
                WHEN 5 THEN 1.00 WHEN 6 THEN 0.86 WHEN 7 THEN 0.76 WHEN 8 THEN 0.80
                WHEN 9 THEN 1.02 WHEN 10 THEN 1.06 WHEN 11 THEN 1.10 WHEN 12 THEN 1.18 END;
            growth := (1 + 0.0025) ^ m;    -- ~ +3 %/an, régulier
            n := round(base_orders * seasonal);
            FOR k IN 1..n LOOP
                odate := (DATE '2023-01-01' + (m || ' months')::interval)::date + floor(random() * 28)::int;
                amt := base_basket * growth * (0.6 + random() * 0.8);
                INSERT INTO orders (store_id, order_date, amount_ttc)
                VALUES (s.id, odate, round(amt::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
