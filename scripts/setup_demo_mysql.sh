#!/usr/bin/env bash
# Base source de démonstration MySQL/MariaDB + rôle LECTURE SEULE dédié.
# Usage : bash scripts/setup_demo_mysql.sh   (MySQL/MariaDB doit être démarré)
set -euo pipefail

MYSQL="${MYSQL:-mariadb}"   # ou "mysql"

echo ">> (Re)création de la base noreon_demo_mysql + rôle read-only"
$MYSQL <<'SQL'
DROP DATABASE IF EXISTS noreon_demo_mysql;
CREATE DATABASE noreon_demo_mysql;
CREATE USER IF NOT EXISTS 'noreon_ro'@'%' IDENTIFIED BY 'readonly';
CREATE USER IF NOT EXISTS 'noreon_ro'@'localhost' IDENTIFIED BY 'readonly';
GRANT SELECT ON noreon_demo_mysql.* TO 'noreon_ro'@'%';
GRANT SELECT ON noreon_demo_mysql.* TO 'noreon_ro'@'localhost';
FLUSH PRIVILEGES;
SQL

echo ">> Schéma + données (retail : stores, customers, orders)"
$MYSQL noreon_demo_mysql <<'SQL'
CREATE TABLE stores (
  id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, city VARCHAR(100));
CREATE TABLE customers (
  id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(200) NOT NULL,
  email VARCHAR(200), city VARCHAR(100),
  store_id INT);                                  -- FK implicite vers stores.id
CREATE TABLE orders (
  id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT,
  amount_ttc DECIMAL(10,2), order_date DATE,
  CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id));

INSERT INTO stores (name, city) VALUES ('Paris','Paris'),('Lyon','Lyon'),('Lille','Lille');
INSERT INTO customers (full_name, email, city, store_id)
SELECT CONCAT('Client ', n),
       CASE WHEN n % 11 = 0 THEN NULL ELSE CONCAT('client', n, '@example.com') END,
       ELT(1 + (n MOD 3), 'Paris','Lyon','Lille'), 1 + (n MOD 3)
FROM (SELECT a.N + b.N*10 + 1 AS n FROM
  (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
  (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b) x
WHERE n <= 100;
INSERT INTO orders (customer_id, amount_ttc, order_date)
SELECT 1 + (n MOD 100), ROUND(20 + (n MOD 400) + RAND()*30, 2), DATE_ADD('2024-01-01', INTERVAL (n MOD 500) DAY)
FROM (SELECT a.N + b.N*10 + c.N*100 + 1 AS n FROM
  (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
  (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b,
  (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) c) x
WHERE n <= 800;
SQL

echo ">> Terminé : base noreon_demo_mysql prête (utilisateur read-only 'noreon_ro' / 'readonly')."
