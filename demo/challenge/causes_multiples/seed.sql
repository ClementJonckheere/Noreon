-- =============================================================================
-- Noreon CHALLENGE · « Causes multiples » (40 / 35 / 25 %)
-- Base source : noreon_demo_challenge_causes_multiples
--
-- Question :  « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- PIÈGE (cf. notes.md) : il n'y a PAS une cause unique. La baisse se répartit sur
-- TROIS magasins, situés dans TROIS régions différentes (pour qu'aucun
-- regroupement géographique ne reconcentre la cause) :
--   • Lyon (Auvergne-Rhône-Alpes)   ~ 35 %
--   • Marseille (PACA)              ~ 40 %
--   • Lille (Hauts-de-France)       ~ 25 %
-- Les trois autres magasins (Paris ×2, Nice) sont stables.
--
-- Un mauvais moteur répond « la cause est X ». Un bon moteur répond « TROIS
-- facteurs expliquent la baisse : Marseille (~40 %), Lyon (~35 %), Lille (~25 %) ».
-- =============================================================================

DROP TABLE IF EXISTS orders, customers, stores CASCADE;

CREATE TABLE stores (
    id serial PRIMARY KEY, name varchar(120), city varchar(100), region varchar(100)
);
CREATE TABLE customers (
    id serial PRIMARY KEY, full_name varchar(200), email varchar(200),
    segment varchar(20), home_store_id integer
);
CREATE TABLE orders (
    id serial PRIMARY KEY, customer_id integer REFERENCES customers(id),
    store_id integer REFERENCES stores(id), order_date date, amount_ttc numeric(10,2)
);

INSERT INTO stores (name, city, region) VALUES
 ('Paris Rive Droite', 'Paris', 'Île-de-France'),
 ('Paris Rive Gauche', 'Paris', 'Île-de-France'),
 ('Lyon Presqu''île', 'Lyon', 'Auvergne-Rhône-Alpes'),
 ('Lille Grand Place', 'Lille', 'Hauts-de-France'),
 ('Marseille Prado', 'Marseille', 'Provence-Alpes-Côte d''Azur'),
 ('Nice Étoile', 'Nice', 'Provence-Alpes-Côte d''Azur');

INSERT INTO customers (full_name, email, segment, home_store_id)
SELECT 'Client ' || g, 'client' || g || '@example.com',
       (ARRAY['Particulier','Particulier','Pro','VIP'])[1 + (g % 4)], 1 + (g % 6)
FROM generate_series(1, 520) g;

SELECT setseed(0.24);

DO $$
DECLARE
    s RECORD; custids integer[]; m integer; k integer; n integer;
    base_orders numeric; base_basket numeric; basket_mult numeric;
    cust integer; amt numeric; odate date;
BEGIN
    FOR s IN SELECT * FROM stores ORDER BY id LOOP
        custids := ARRAY(SELECT id FROM customers WHERE home_store_id = s.id);
        base_orders := CASE s.id WHEN 1 THEN 92 WHEN 2 THEN 86 WHEN 3 THEN 78
                                 WHEN 4 THEN 60 WHEN 5 THEN 88 ELSE 70 END;
        base_basket := CASE s.id WHEN 1 THEN 94 WHEN 2 THEN 90 WHEN 3 THEN 82
                                 WHEN 4 THEN 76 WHEN 5 THEN 88 ELSE 83 END;
        FOR m IN 0..17 LOOP
            basket_mult := 1.0;
            -- Baisse répartie : Lyon (3), Lille (4), Marseille (5) décrochent ;
            -- Paris (1,2) et Nice (6) restent stables.
            IF m >= 14 AND s.id IN (3, 4, 5) THEN
                basket_mult := CASE m WHEN 14 THEN 0.90 WHEN 15 THEN 0.82
                                      WHEN 16 THEN 0.74 WHEN 17 THEN 0.66 END;
            END IF;
            n := base_orders;
            FOR k IN 1..n LOOP
                cust := custids[1 + floor(random() * array_length(custids, 1))::int];
                odate := (DATE '2024-01-01' + (m || ' months')::interval)::date + floor(random() * 28)::int;
                amt := base_basket * basket_mult * (0.6 + random() * 0.8);
                INSERT INTO orders (customer_id, store_id, order_date, amount_ttc)
                VALUES (cust, s.id, odate, round(amt::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
