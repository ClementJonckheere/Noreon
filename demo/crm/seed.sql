-- =============================================================================
-- Noreon — Démonstration · Scénario « CRM »  (SaaS fictif « FluxCRM »)
-- Base source : noreon_demo_crm
--
-- Question :  « Pourquoi le churn augmente-t-il ? »
--
-- HISTOIRE PLANTÉE (cf. demo/crm/notes.md) :
--   • Le churn (revenu perdu / mois) est stable, puis AUGMENTE sur 4 mois, accéléré.
--   • Cause dominante : le canal d'acquisition « Publicité payante » — ces clients,
--     acquis à coups de promotions, se désabonnent massivement (attentes déçues).
--     Sa contribution à la HAUSSE du churn est écrasante (~ 90 %+).
--   • Les autres canaux (bouche-à-oreille, référencement, partenariats) sont stables.
--
-- Mesure choisie par le moteur : sum(revenu_perdu)  (indice « revenu »).
-- Axe causal : acquisition_channel (colonne propre de la table de faits).
-- Imperfections : emails invalides ; quelques revenus perdus manquants.
-- =============================================================================

DROP TABLE IF EXISTS churn_events, customers CASCADE;

CREATE TABLE customers (
    id          serial PRIMARY KEY,
    full_name   varchar(200) NOT NULL,
    email       varchar(200),
    plan        varchar(20),          -- Basic | Pro | Business
    signup_date date
);

CREATE TABLE churn_events (
    id                  serial PRIMARY KEY,
    customer_id         integer REFERENCES customers(id),  -- FK → fait sortant
    churn_date          date,
    plan                varchar(20),
    acquisition_channel varchar(40),   -- axe causal
    revenu_perdu        numeric(10,2)  -- MRR perdu (mesure additive, indice « revenu »)
);

INSERT INTO customers (full_name, email, plan, signup_date)
SELECT 'Compte ' || g,
       CASE WHEN g % 30 = 0 THEN 'pas-un-email' ELSE 'compte' || g || '@example.com' END,
       (ARRAY['Basic','Basic','Pro','Business'])[1 + (g % 4)],
       DATE '2022-06-01' + (g % 1000)
FROM generate_series(1, 800) g;

-- MRR de référence par plan.
-- Génération des désabonnements : 18 mois (idx 0..17), hausse sur 14..17.
SELECT setseed(0.7);

DO $$
DECLARE
    ch      text;
    m       integer;
    k       integer;
    n       integer;      -- désabonnements du mois pour ce canal
    base    integer;      -- niveau de churn de référence du canal
    mult    numeric;      -- multiplicateur (fenêtre de hausse, canal « payant »)
    cust    integer;
    pl      text;
    mrr     numeric;
    cdate   date;
    channels text[] := ARRAY['Bouche-à-oreille','Référencement','Publicité payante','Partenariats'];
BEGIN
    FOREACH ch IN ARRAY channels LOOP
        base := CASE ch
            WHEN 'Bouche-à-oreille' THEN 6
            WHEN 'Référencement'    THEN 10
            WHEN 'Publicité payante' THEN 12
            WHEN 'Partenariats'     THEN 8 END;

        FOR m IN 0..17 LOOP
            mult := 1.0;
            -- Explosion du churn « Publicité payante » sur les 4 derniers mois.
            IF ch = 'Publicité payante' AND m >= 14 THEN
                mult := CASE m WHEN 14 THEN 1.7 WHEN 15 THEN 2.4
                               WHEN 16 THEN 3.1 WHEN 17 THEN 3.9 END;
            END IF;
            n := round(base * mult);

            FOR k IN 1..n LOOP
                cust := 1 + floor(random() * 800)::int;
                -- Les clients « payants » sont surtout des Basic (faible valeur, volatils).
                IF ch = 'Publicité payante' THEN
                    pl := (ARRAY['Basic','Basic','Basic','Pro'])[1 + floor(random()*4)::int];
                ELSE
                    pl := (ARRAY['Basic','Pro','Pro','Business'])[1 + floor(random()*4)::int];
                END IF;
                mrr := CASE pl WHEN 'Basic' THEN 29 WHEN 'Pro' THEN 79 ELSE 199 END
                       * (0.85 + random() * 0.3);
                cdate := (DATE '2024-01-01' + (m || ' months')::interval)::date
                         + floor(random() * 28)::int;
                INSERT INTO churn_events (customer_id, churn_date, plan, acquisition_channel, revenu_perdu)
                VALUES (cust, cdate, pl,
                        ch,
                        CASE WHEN random() < 0.04 THEN NULL ELSE round(mrr::numeric, 2) END);
            END LOOP;
        END LOOP;
    END LOOP;
END $$;

ANALYZE;
