-- =============================================================================
-- Noreon — Bibliothèque de démonstration · Scénario VITRINE « Retail »
-- Base source : noreon_demo_retail  (enseigne fictive « Maison Lumière »)
--
-- Question de démonstration :
--     « Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ? »
--
-- HISTOIRE PLANTÉE (la vraie réponse — cf. demo/retail/notes.md) :
--   • Le CA progresse doucement de janv. 2024 à févr. 2025, puis DÉCLINE sur les
--     4 derniers mois (mars→juin 2025), de façon ACCÉLÉRÉE.
--   • Cause dominante : la région PACA (magasins Marseille Prado + Nice Étoile)
--     s'effondre — un concurrent a ouvert. Le PANIER MOYEN y chute (~ -36 %) ;
--     le TRAFIC (nombre de commandes) tient presque : ce n'est donc PAS
--     « moins de clients », c'est le panier qui s'effondre.
--   • Cause secondaire : la gamme « High-Tech » subit une rupture
--     d'approvisionnement (quantités vendues divisées ~ par 2 sur la fenêtre).
--   • Diversion à écarter : le nombre de clients actifs reste stable au global.
--
-- PIÈGE SÉMANTIQUE : orders.amount_ttc est TTC ; products.net_price est HT.
-- IMPERFECTIONS QUALITÉ VOLONTAIRES : emails invalides, store_id orphelins,
--   montants de paiement manquants — pour que le score qualité soit parlant.
--
-- Données 100 % synthétiques et déterministes (setseed) : reproductible.
-- =============================================================================

DROP TABLE IF EXISTS payments, order_items, orders, products, customers, stores CASCADE;

CREATE TABLE stores (
    id      serial PRIMARY KEY,
    name    varchar(120) NOT NULL,
    city    varchar(100),
    region  varchar(100)
);

CREATE TABLE customers (
    id             serial PRIMARY KEY,
    full_name      varchar(200) NOT NULL,
    email          varchar(200),
    phone          varchar(30),
    city           varchar(100),
    age            integer,
    gender         varchar(10),
    segment        varchar(20),      -- Particulier | Pro | VIP (axe CRM)
    loyalty_points integer DEFAULT 0,
    signup_date    date,
    home_store_id  integer           -- FK implicite (non déclarée) vers stores.id
);

CREATE TABLE products (
    id        serial PRIMARY KEY,
    name      varchar(200) NOT NULL,
    category  varchar(100),
    net_price numeric(10,2)          -- HT (piège vs amount_ttc)
);

CREATE TABLE orders (
    id          serial PRIMARY KEY,
    customer_id integer REFERENCES customers(id),  -- FK déclarée
    store_id    integer,                           -- FK implicite vers stores.id
    order_date  date,
    amount_ttc  numeric(10,2)                      -- TTC
);

CREATE TABLE order_items (
    id         serial PRIMARY KEY,
    order_id   integer REFERENCES orders(id),
    product_id integer,                            -- FK implicite vers products.id
    quantity   integer
);

CREATE TABLE payments (
    id       serial PRIMARY KEY,
    order_id integer,                              -- FK implicite vers orders.id
    method   varchar(30),
    amount   numeric(10,2),
    paid_at  timestamp
);

-- --- Référentiels -----------------------------------------------------------
INSERT INTO stores (name, city, region) VALUES
 ('Paris Rive Droite', 'Paris',     'Île-de-France'),
 ('Paris Rive Gauche', 'Paris',     'Île-de-France'),
 ('Lyon Presqu''île',  'Lyon',      'Auvergne-Rhône-Alpes'),
 ('Lille Grand Place', 'Lille',     'Hauts-de-France'),
 ('Marseille Prado',   'Marseille', 'Provence-Alpes-Côte d''Azur'),
 ('Nice Étoile',       'Nice',      'Provence-Alpes-Côte d''Azur');

INSERT INTO products (name, category, net_price)
SELECT
    'Produit ' || g,
    (ARRAY['Textile','High-Tech','Maison','Alimentaire','Déco'])[1 + (g % 5)],
    round((8 + (g % 180) + random() * 5)::numeric, 2)
FROM generate_series(1, 90) g;

-- 520 clients rattachés à un magasin « d'origine » ; segment CRM pondéré.
INSERT INTO customers (full_name, email, phone, city, age, gender, segment,
                       loyalty_points, signup_date, home_store_id)
SELECT
    'Client ' || g,
    CASE WHEN g % 13 = 0 THEN NULL ELSE 'client' || g || '@example.com' END,
    '+3360000' || lpad(g::text, 4, '0'),
    (ARRAY['Paris','Paris','Lyon','Lille','Marseille','Nice'])[1 + (g % 6)],
    18 + ((g * 13) % 55),
    (ARRAY['F','M'])[1 + (g % 2)],
    CASE WHEN g % 10 = 0 THEN 'VIP'
         WHEN g % 5  = 0 THEN 'Pro'
         ELSE 'Particulier' END,
    (g * 7) % 500,
    DATE '2022-06-01' + (g % 900),
    1 + (g % 6)
FROM generate_series(1, 520) g;

-- --- Génération des commandes (le cœur de l'histoire) -----------------------
-- 18 mois : 2024-01 (idx 0) → 2025-06 (idx 17). Fenêtre de baisse : idx 14..17.
SELECT setseed(0.4242);

DO $$
DECLARE
    s              RECORD;
    custids        integer[];
    m              integer;      -- index de mois 0..17
    k              integer;
    n_orders       integer;      -- commandes du mois pour ce magasin
    base_orders    numeric;      -- trafic mensuel de référence
    base_basket    numeric;      -- panier moyen TTC de référence
    growth_rate    numeric;      -- croissance mensuelle « normale »
    is_paca        boolean;
    vol_mult       numeric;      -- multiplicateur de trafic (fenêtre de baisse)
    basket_mult    numeric;      -- multiplicateur de panier (fenêtre de baisse)
    cust           integer;
    amt            numeric;
    odate          date;
    seg            varchar(20);
BEGIN
    FOR s IN SELECT * FROM stores ORDER BY id LOOP
        custids := ARRAY(SELECT id FROM customers WHERE home_store_id = s.id);
        is_paca := (s.region = 'Provence-Alpes-Côte d''Azur');

        -- Profil de référence par magasin (trafic, panier, croissance).
        base_orders := CASE s.id
            WHEN 1 THEN 92 WHEN 2 THEN 86 WHEN 3 THEN 72
            WHEN 4 THEN 54 WHEN 5 THEN 80 WHEN 6 THEN 70 END;
        base_basket := CASE s.id
            WHEN 1 THEN 94 WHEN 2 THEN 90 WHEN 3 THEN 80
            WHEN 4 THEN 74 WHEN 5 THEN 86 WHEN 6 THEN 83 END;
        growth_rate := CASE s.id
            WHEN 3 THEN 0.010    -- Lyon en croissance
            WHEN 1 THEN 0.004 WHEN 2 THEN 0.004
            ELSE 0.002 END;

        FOR m IN 0..17 LOOP
            vol_mult := 1.0;
            basket_mult := 1.0;

            -- Effondrement PACA sur les 4 derniers mois : le PANIER chute
            -- (concurrent), le trafic ne baisse que légèrement.
            IF is_paca AND m >= 14 THEN
                basket_mult := CASE m
                    WHEN 14 THEN 0.88 WHEN 15 THEN 0.80
                    WHEN 16 THEN 0.72 WHEN 17 THEN 0.64 END;   -- ~ -36 % cumulé, accéléré
                vol_mult := 0.95;
            END IF;

            n_orders := round(base_orders * vol_mult);

            FOR k IN 1..n_orders LOOP
                cust := custids[1 + floor(random() * array_length(custids, 1))::int];
                SELECT segment INTO seg FROM customers WHERE id = cust;
                odate := (DATE '2024-01-01' + (m || ' months')::interval)::date
                         + floor(random() * 28)::int;

                amt := base_basket
                       * (1 + growth_rate) ^ m               -- dérive « normale »
                       * basket_mult                          -- choc PACA
                       * (0.6 + random() * 0.8);              -- dispersion réaliste

                -- Gel budgétaire B2B : les « Pro » resserrent aussi sur la fenêtre.
                IF seg = 'Pro' AND m >= 14 THEN
                    amt := amt * 0.9;
                END IF;

                INSERT INTO orders (customer_id, store_id, order_date, amount_ttc)
                VALUES (cust, s.id, odate, round(amt::numeric, 2));
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

-- --- Lignes de commande : rupture High-Tech sur la fenêtre de baisse --------
-- Cas normal : 1 à 4 lignes par commande, produit aléatoire.
INSERT INTO order_items (order_id, product_id, quantity)
SELECT o.id,
       1 + floor(random() * 90)::int,
       1 + floor(random() * 4)::int
FROM orders o, generate_series(1, 3) gs
WHERE random() < 0.7;

-- Rupture : sur les 4 derniers mois, on RETIRE la moitié des lignes High-Tech
-- (approvisionnement en tension) → la gamme décroche, visible à l'analyse produit.
DELETE FROM order_items oi
USING orders o, products p
WHERE oi.order_id = o.id AND oi.product_id = p.id
  AND p.category = 'High-Tech'
  AND o.order_date >= DATE '2025-03-01'
  AND (oi.id % 2 = 0);

-- --- Paiements (1 par commande, quelques montants manquants) -----------------
INSERT INTO payments (order_id, method, amount, paid_at)
SELECT o.id,
       (ARRAY['card','card','cash','transfer','paypal'])[1 + (o.id % 5)],
       CASE WHEN o.id % 25 = 0 THEN NULL ELSE o.amount_ttc END,  -- ~4 % manquants
       o.order_date + TIME '10:30'
FROM orders o;

-- --- Imperfections qualité volontaires --------------------------------------
UPDATE customers SET email = 'pas-un-email' WHERE id % 40 = 0;   -- Validité
UPDATE customers SET home_store_id = 99 WHERE id % 70 = 0;       -- Cohérence (magasin 99 inexistant)
UPDATE orders    SET store_id = 99 WHERE id % 120 = 0;           -- Cohérence

ANALYZE;
