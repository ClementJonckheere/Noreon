-- Requêtes clés attendues (toutes en LECTURE SEULE). Chaque chiffre du rapport
-- est adossé à l'une d'elles — c'est l'exigence d'auditabilité de Noreon.

-- 1) Tendance : CA (TTC) par mois -------------------------------------------
SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS periode,
       round(sum(amount_ttc))                              AS ca
FROM orders
GROUP BY 1 ORDER BY 1;

-- 2) ATTRIBUTION DE LA VARIATION : contribution à la baisse, par région ------
--    (fenêtre récente mars–juin vs précédente nov.–févr.)
SELECT s.region,
       round(sum(o.amount_ttc) FILTER (
             WHERE o.order_date >= DATE '2025-03-01'))                     AS recent,
       round(sum(o.amount_ttc) FILTER (
             WHERE o.order_date >= DATE '2024-11-01'
               AND o.order_date <  DATE '2025-03-01'))                     AS prior,
       round(sum(o.amount_ttc) FILTER (WHERE o.order_date >= DATE '2025-03-01')
           - sum(o.amount_ttc) FILTER (
             WHERE o.order_date >= DATE '2024-11-01'
               AND o.order_date <  DATE '2025-03-01'))                     AS delta
FROM orders o
JOIN stores s ON o.store_id = s.id      -- FK IMPLICITE retrouvée par le scanner
GROUP BY s.region
ORDER BY delta;                          -- PACA en tête de la baisse (~ -14 000)

-- 3) Trafic vs panier en PACA (écarter « moins de clients ») -----------------
SELECT CASE WHEN o.order_date >= DATE '2025-03-01' THEN 'fenetre_baisse'
            ELSE 'avant' END                AS periode,
       count(*)                             AS commandes,
       round(avg(o.amount_ttc))             AS panier_moyen
FROM orders o
JOIN stores s ON o.store_id = s.id
WHERE s.region = 'Provence-Alpes-Côte d''Azur'
  AND o.order_date >= DATE '2024-11-01'
GROUP BY 1 ORDER BY 1;                    -- trafic ~ stable, panier -23 %

-- 4) Clients actifs par mois (stabilité de la fréquentation globale) ---------
SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS periode,
       count(DISTINCT customer_id)                         AS clients_actifs
FROM orders
WHERE order_date >= DATE '2025-01-01'
GROUP BY 1 ORDER BY 1;

-- 5) Facteur aggravant : quantités High-Tech par mois (rupture) --------------
SELECT to_char(date_trunc('month', o.order_date), 'YYYY-MM') AS periode,
       coalesce(sum(oi.quantity), 0)                         AS quantite
FROM orders o
JOIN order_items oi ON oi.order_id = o.id     -- FK déclarée
JOIN products p     ON oi.product_id = p.id   -- FK implicite
WHERE p.category = 'High-Tech'
  AND o.order_date >= DATE '2025-01-01'
GROUP BY 1 ORDER BY 1;                        -- ÷ 2 dès mars 2025
