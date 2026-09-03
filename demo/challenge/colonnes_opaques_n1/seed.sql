-- =============================================================================
-- Noreon CHALLENGE · « Colonnes opaques — Niveau 1 »
-- Base source : noreon_demo_challenge_colonnes_opaques_n1
--
-- Question :  « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- MÊME HISTOIRE que le scénario retail (PACA porte ~97 % de la baisse), MAIS
-- TOUTES LES COLONNES SONT RENOMMÉES en identifiants opaques. Le moteur ne peut
-- plus s'appuyer sur les NOMS (« amount_ttc », « region »…). Il doit retrouver :
--   • la MESURE via le profil (variable numérique continue, ni clé ni FK) ;
--   • les AXES via les types + relations + valeurs ;
--   • le SEGMENT causal via les VALEURS (« Provence-Alpes-Côte d'Azur »).
--
-- Niveau 1 = renommage des colonnes uniquement. Les FK restent DÉCLARÉES
-- (métadonnée, pas un nom) → les relations survivent. Le test porte donc sur la
-- capacité à comprendre les DONNÉES, pas le vocabulaire du schéma.
--
-- Correspondance (pour l'humain — le moteur ne l'a pas) :
--   orders.col_003 = amount_ttc | col_z = order_date | col_001 = customer_id
--   col_002 = store_id | stores.a3 = region | customers.b6 = segment …
-- =============================================================================

DROP TABLE IF EXISTS t_o, t_p, t_c, t_s CASCADE;

CREATE TABLE t_s (            -- « stores »
    k0 serial PRIMARY KEY, a1 varchar(120), a2 varchar(100), a3 varchar(100)
);
CREATE TABLE t_c (            -- « customers »
    k1 serial PRIMARY KEY, b1 varchar(200), b2 varchar(200), b3 varchar(100),
    b4 integer, b5 varchar(10), b6 varchar(20), b7 date, b8 integer
);
CREATE TABLE t_p (            -- « products »
    k2 serial PRIMARY KEY, d1 varchar(200), d2 varchar(100), d3 numeric(10,2)
);
CREATE TABLE t_o (            -- « orders »
    k3 serial PRIMARY KEY,
    col_001 integer REFERENCES t_c(k1),   -- FK déclarée (métadonnée, pas un nom)
    col_002 integer REFERENCES t_s(k0),   -- FK déclarée
    col_z   date,
    col_003 numeric(10,2)                 -- la MESURE (à retrouver par les données)
);

INSERT INTO t_s (a1, a2, a3) VALUES
 ('Paris Rive Droite', 'Paris', 'Île-de-France'),
 ('Paris Rive Gauche', 'Paris', 'Île-de-France'),
 ('Lyon Presqu''île', 'Lyon', 'Auvergne-Rhône-Alpes'),
 ('Lille Grand Place', 'Lille', 'Hauts-de-France'),
 ('Marseille Prado', 'Marseille', 'Provence-Alpes-Côte d''Azur'),
 ('Nice Étoile', 'Nice', 'Provence-Alpes-Côte d''Azur');

INSERT INTO t_p (d1, d2, d3)
SELECT 'Produit ' || g, (ARRAY['Textile','High-Tech','Maison','Alimentaire','Déco'])[1 + (g % 5)],
       round((8 + (g % 180))::numeric, 2)
FROM generate_series(1, 90) g;

INSERT INTO t_c (b1, b2, b3, b4, b5, b6, b7, b8)
SELECT 'Client ' || g,
       CASE WHEN g % 13 = 0 THEN NULL ELSE 'client' || g || '@example.com' END,
       (ARRAY['Paris','Paris','Lyon','Lille','Marseille','Nice'])[1 + (g % 6)],
       18 + ((g * 13) % 55), (ARRAY['F','M'])[1 + (g % 2)],
       CASE WHEN g % 10 = 0 THEN 'VIP' WHEN g % 5 = 0 THEN 'Pro' ELSE 'Particulier' END,
       DATE '2022-06-01' + (g % 900), 1 + (g % 6)
FROM generate_series(1, 520) g;

SELECT setseed(0.4242);

DO $$
DECLARE
    s RECORD; custids integer[]; m integer; k integer; n_orders integer;
    base_orders numeric; base_basket numeric; growth_rate numeric;
    is_paca boolean; vol_mult numeric; basket_mult numeric;
    cust integer; amt numeric; odate date; seg varchar(20);
BEGIN
    FOR s IN SELECT * FROM t_s ORDER BY k0 LOOP
        custids := ARRAY(SELECT k1 FROM t_c WHERE b8 = s.k0);
        is_paca := (s.a3 = 'Provence-Alpes-Côte d''Azur');
        base_orders := CASE s.k0 WHEN 1 THEN 92 WHEN 2 THEN 86 WHEN 3 THEN 72
                                 WHEN 4 THEN 54 WHEN 5 THEN 80 ELSE 70 END;
        base_basket := CASE s.k0 WHEN 1 THEN 94 WHEN 2 THEN 90 WHEN 3 THEN 80
                                 WHEN 4 THEN 74 WHEN 5 THEN 86 ELSE 83 END;
        growth_rate := CASE s.k0 WHEN 3 THEN 0.010 WHEN 1 THEN 0.004 WHEN 2 THEN 0.004 ELSE 0.002 END;
        FOR m IN 0..17 LOOP
            vol_mult := 1.0; basket_mult := 1.0;
            IF is_paca AND m >= 14 THEN
                basket_mult := CASE m WHEN 14 THEN 0.88 WHEN 15 THEN 0.80
                                      WHEN 16 THEN 0.72 WHEN 17 THEN 0.64 END;
                vol_mult := 0.95;
            END IF;
            n_orders := round(base_orders * vol_mult);
            FOR k IN 1..n_orders LOOP
                cust := custids[1 + floor(random() * array_length(custids, 1))::int];
                SELECT b6 INTO seg FROM t_c WHERE k1 = cust;
                odate := (DATE '2024-01-01' + (m || ' months')::interval)::date + floor(random() * 28)::int;
                amt := base_basket * (1 + growth_rate) ^ m * basket_mult * (0.6 + random() * 0.8);
                IF seg = 'Pro' AND m >= 14 THEN amt := amt * 0.9; END IF;
                INSERT INTO t_o (col_001, col_002, col_z, col_003)
                VALUES (cust, s.k0, odate, round(amt::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
