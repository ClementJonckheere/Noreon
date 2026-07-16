-- Base source de démonstration pour Noreon (simule un ERP/CRM de retail).
-- Exécutée sur la base `noreon_demo`.

DROP TABLE IF EXISTS payments, order_items, orders, products, customers, stores CASCADE;

CREATE TABLE stores (
    id          serial PRIMARY KEY,
    name        varchar(100) NOT NULL,
    city        varchar(100),
    region      varchar(100)
);

CREATE TABLE customers (
    id             serial PRIMARY KEY,
    full_name      varchar(200) NOT NULL,
    email          varchar(200),
    phone          varchar(30),
    city           varchar(100),
    loyalty_points integer DEFAULT 0,
    signup_date    date,
    store_id       integer  -- FK implicite (non déclarée) vers stores.id
);

CREATE TABLE products (
    id         serial PRIMARY KEY,
    name       varchar(200) NOT NULL,
    category   varchar(100),
    net_price  numeric(10,2)  -- HT
);

CREATE TABLE orders (
    id           serial PRIMARY KEY,
    customer_id  integer REFERENCES customers(id),  -- FK déclarée
    store_id     integer,                           -- FK implicite vers stores.id
    order_date   date,
    amount_ttc   numeric(10,2)  -- TTC (piège sémantique vs net_price HT)
);

CREATE TABLE order_items (
    id         serial PRIMARY KEY,
    order_id   integer REFERENCES orders(id),
    product_id integer,   -- FK implicite vers products.id
    quantity   integer
);

CREATE TABLE payments (
    id         serial PRIMARY KEY,
    order_id   integer,   -- FK implicite vers orders.id
    method     varchar(30),
    amount     numeric(10,2),
    paid_at    timestamp
);

-- Données --------------------------------------------------------------
INSERT INTO stores (name, city, region) VALUES
 ('Paris Centre', 'Paris', 'Île-de-France'),
 ('Lyon Part-Dieu', 'Lyon', 'Auvergne-Rhône-Alpes'),
 ('Marseille Vieux-Port', 'Marseille', 'PACA'),
 ('Lille Grand Place', 'Lille', 'Hauts-de-France');

INSERT INTO customers (full_name, email, phone, city, loyalty_points, signup_date, store_id)
SELECT
    'Client ' || g,
    CASE WHEN g % 13 = 0 THEN NULL ELSE 'client' || g || '@example.com' END,
    '+3360000' || lpad(g::text, 4, '0'),
    (ARRAY['Paris','Lyon','Marseille','Lille'])[1 + (g % 4)],
    (g * 7) % 500,
    DATE '2023-01-01' + (g % 700),
    1 + (g % 4)
FROM generate_series(1, 500) g;

INSERT INTO products (name, category, net_price)
SELECT
    'Produit ' || g,
    (ARRAY['Textile','High-Tech','Maison','Alimentaire'])[1 + (g % 4)],
    round((5 + (g % 200) + random())::numeric, 2)
FROM generate_series(1, 80) g;

INSERT INTO orders (customer_id, store_id, order_date, amount_ttc)
SELECT
    1 + (g % 500),
    1 + (g % 4),
    DATE '2024-01-01' + (g % 550),
    round((20 + (g % 400) + random() * 50)::numeric, 2)
FROM generate_series(1, 3000) g;

INSERT INTO order_items (order_id, product_id, quantity)
SELECT
    1 + (g % 3000),
    1 + (g % 80),
    1 + (g % 5)
FROM generate_series(1, 9000) g;

INSERT INTO payments (order_id, method, amount, paid_at)
SELECT
    1 + (g % 3000),
    (ARRAY['card','cash','transfer','paypal'])[1 + (g % 4)],
    CASE WHEN g % 25 = 0 THEN NULL ELSE round((20 + (g % 400))::numeric, 2) END,
    TIMESTAMP '2024-01-01 09:00:00' + (g % 550) * INTERVAL '1 day'
FROM generate_series(1, 3000) g;

ANALYZE;
