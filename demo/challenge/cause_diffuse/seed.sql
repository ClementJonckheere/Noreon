-- =============================================================================
-- Noreon CHALLENGE · « Cause diffuse »  (enseigne fictive « Maison Lumière bis »)
-- Base source : noreon_demo_challenge_cause_diffuse
--
-- Question :  « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- PIÈGE (cf. notes.md) : contrairement au scénario retail « facile », il n'y a
-- ICI AUCUN coupable localisé. La baisse est SYSTÉMIQUE : le panier moyen recule
-- d'environ -15 % PARTOUT (tous magasins, toutes régions, tous segments) — un
-- effet macro (pouvoir d'achat / repositionnement prix). Aucune région ne porte
-- plus de ~40 % de la baisse.
--
-- Réponse attendue d'un analyste senior :
--   « La baisse est GÉNÉRALISÉE, pas localisée. Cherchez une cause transverse
--     (prix, macro, saison) plutôt qu'un magasin ou une région. »
--
-- Le moteur, lui, cherche une cause dominante (seuil ≥ 55 %) : il n'en trouve
-- pas → il RISQUE de retomber sur une tautologie (« structuré par le plus gros
-- segment »). C'est exactement le genre d'échec que ce challenge doit exposer.
-- =============================================================================

DROP TABLE IF EXISTS payments, order_items, orders, products, customers, stores CASCADE;

CREATE TABLE stores (
    id serial PRIMARY KEY, name varchar(120) NOT NULL, city varchar(100), region varchar(100)
);
CREATE TABLE customers (
    id serial PRIMARY KEY, full_name varchar(200) NOT NULL, email varchar(200),
    city varchar(100), age integer, gender varchar(10), segment varchar(20),
    signup_date date, home_store_id integer
);
CREATE TABLE products (
    id serial PRIMARY KEY, name varchar(200) NOT NULL, category varchar(100), net_price numeric(10,2)
);
CREATE TABLE orders (
    id serial PRIMARY KEY, customer_id integer REFERENCES customers(id),
    store_id integer, order_date date, amount_ttc numeric(10,2)
);

INSERT INTO stores (name, city, region) VALUES
 ('Paris Rive Droite', 'Paris', 'Île-de-France'),
 ('Paris Rive Gauche', 'Paris', 'Île-de-France'),
 ('Lyon Presqu''île', 'Lyon', 'Auvergne-Rhône-Alpes'),
 ('Lille Grand Place', 'Lille', 'Hauts-de-France'),
 ('Marseille Prado', 'Marseille', 'Provence-Alpes-Côte d''Azur'),
 ('Nice Étoile', 'Nice', 'Provence-Alpes-Côte d''Azur');

INSERT INTO products (name, category, net_price)
SELECT 'Produit ' || g, (ARRAY['Textile','High-Tech','Maison','Alimentaire','Déco'])[1 + (g % 5)],
       round((8 + (g % 180))::numeric, 2)
FROM generate_series(1, 90) g;

INSERT INTO customers (full_name, email, city, age, gender, segment, signup_date, home_store_id)
SELECT 'Client ' || g, 'client' || g || '@example.com',
       (ARRAY['Paris','Paris','Lyon','Lille','Marseille','Nice'])[1 + (g % 6)],
       18 + ((g * 13) % 55), (ARRAY['F','M'])[1 + (g % 2)],
       CASE WHEN g % 10 = 0 THEN 'VIP' WHEN g % 5 = 0 THEN 'Pro' ELSE 'Particulier' END,
       DATE '2022-06-01' + (g % 900), 1 + (g % 6)
FROM generate_series(1, 520) g;

SELECT setseed(0.31);

DO $$
DECLARE
    s RECORD; custids integer[]; m integer; k integer; n integer;
    base_orders numeric; base_basket numeric; basket_mult numeric;
    cust integer; amt numeric; odate date;
BEGIN
    FOR s IN SELECT * FROM stores ORDER BY id LOOP
        custids := ARRAY(SELECT id FROM customers WHERE home_store_id = s.id);
        base_orders := CASE s.id WHEN 1 THEN 92 WHEN 2 THEN 86 WHEN 3 THEN 72
                                 WHEN 4 THEN 54 WHEN 5 THEN 80 ELSE 70 END;
        base_basket := CASE s.id WHEN 1 THEN 94 WHEN 2 THEN 90 WHEN 3 THEN 80
                                 WHEN 4 THEN 74 WHEN 5 THEN 86 ELSE 83 END;
        FOR m IN 0..17 LOOP
            -- BAISSE SYSTÉMIQUE : même érosion de panier partout sur les 4 mois.
            basket_mult := 1.0;
            IF m >= 14 THEN
                basket_mult := CASE m WHEN 14 THEN 0.96 WHEN 15 THEN 0.92
                                      WHEN 16 THEN 0.88 WHEN 17 THEN 0.85 END;
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
