import psycopg
from datetime import date, timedelta, datetime, timezone
from app.core.db import SessionLocal
from app.models.connection import Connection
from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan, MeasurementRun
from app.models.space import Space, SpaceConnection
from app.services.spaces import slugify

CONN_ID = 2414                                # source retail de DÉMO
TARGET = ["Marseille Prado", "Nice Lingostiere"]
# Vivier de témoins CANDIDATS — dont deux magasins PACA (Toulon, Avignon) déjà
# engagés dans le recul régional : ils seront ÉVALUÉS puis ÉCARTÉS (pré-tendance
# divergente). C'est ce qui permet de répondre « pourquoi pas des témoins PACA ? ».
CANDIDATES = [
    {"id": "Lyon Part-Dieu", "region": "Rhône-Alpes"},
    {"id": "Paris Rivoli", "region": "Île-de-France"},
    {"id": "Toulon Grand Var", "region": "PACA"},
    {"id": "Avignon Cap Sud", "region": "PACA"},
]
STABLE = ["Lyon Part-Dieu", "Paris Rivoli"]        # niveau ~1080, plats
DECLINING = ["Toulon Grand Var", "Avignon Cap Sud"]  # PACA, déjà en recul avant action

# Chronologie DÉTERMINISTE, alignée sur le dossier PACA historique (2025) — pas de
# saut d'un an entre un rapport 2025 et une action mise en œuvre en 2026.
IMPL = date(2025, 7, 1)                        # action mise en œuvre le 1er juillet 2025
BW = 30                                        # fenêtres de 30 j
MEASURED_AT = datetime(2025, 8, 1, 9, 42, tzinfo=timezone.utc)  # échéance J+30 mesurée

# --- table de mesure ---------------------------------------------------------
c = psycopg.connect("host=127.0.0.1 dbname=noreon_demo_retail user=noreon password=noreon")
cur = c.cursor()
cur.execute("DROP TABLE IF EXISTS action_impact")
cur.execute("CREATE TABLE action_impact (store text, day date, revenue numeric)")
rows = []
for d in range(-BW, BW):
    day = IMPL + timedelta(days=d)
    after = day >= IMPL
    second_half = d >= -BW / 2                  # 2e moitié de la fenêtre baseline
    for s in TARGET:
        # baseline avg 1000 (léger uptrend +1 %), observation 1031 → +3,1 %.
        rows.append((s, day, 1031 if after else (1005 if second_half else 995)))
    for s in STABLE:
        # baseline plate 1080, observation 1128,6 → +4,5 % (plus comparables).
        rows.append((s, day, 1128.6 if after else 1080))
    for s in DECLINING:
        # PACA déjà en recul : baseline 1080 → 940 (pré-tendance très divergente).
        rows.append((s, day, 900 if after else (940 if second_half else 1080)))
cur.executemany("INSERT INTO action_impact VALUES (%s,%s,%s)", rows)
cur.execute("GRANT SELECT ON action_impact TO PUBLIC")
cur.execute("GRANT SELECT ON action_impact TO noreon_ro")
c.commit(); c.close()

# --- décision + plan DÉJÀ mis en œuvre (baseline figé à IMPL) ----------------
db = SessionLocal()
conn = db.get(Connection, CONN_ID)
old = db.query(DecisionRecord).filter(DecisionRecord.connection_id == CONN_ID,
      DecisionRecord.recommendation.like("Plan de relance commerciale%")).all()
for o in old:
    db.query(MeasurementPlan).filter(MeasurementPlan.decision_id == o.id).delete(synchronize_session=False)
    db.delete(o)
db.commit()
dec = DecisionRecord(tenant_id=conn.tenant_id, connection_id=CONN_ID, subject="orders",
    role="Directeur réseau",
    recommendation="Plan de relance commerciale — magasins Provence-Alpes-Côte d'Azur.",
    status="implemented")
db.add(dec); db.flush()
impl_dt = datetime.combine(IMPL, datetime.min.time(), tzinfo=timezone.utc)
plan = MeasurementPlan(decision_id=dec.id, tenant_id=conn.tenant_id, connection_id=CONN_ID,
    measure_type="impact", metric_label="Chiffre d'affaires", metric_concept_id="revenue",
    metric_definition_version=3,   # version de la définition métier figée par le protocole
    scope={"table": "action_impact", "dim_col": "store", "metric_col": "revenue",
           "date_col": "day", "values": TARGET},
    # Vivier de candidats + comparabilités DÉCLARÉES (attributs magasin) reportées telles quelles.
    control_scope={"candidates": CANDIDATES, "k": 2, "comparability": [
        {"label": "Mix High-Tech", "verdict": "similaire"},
        {"label": "Format de magasin", "verdict": "comparable"},
        {"label": "Saisonnalité", "verdict": "compatible"},
    ]},
    comparison="matched_control", threshold=0.02,
    )
db.add(plan); db.flush()
from app.services.connections import get_source_adapter
from app.services import measurement as meas
adapter = get_source_adapter(conn)
meas.freeze_baseline(db, plan, adapter, implemented_at=impl_dt)
# Mesure J+30 déterministe (snapshot daté du scénario 2025).
run = meas.run_measurement(db, plan, adapter)
run.measured_at = MEASURED_AT
dec.status = "measured"

# --- espace DÉMO dédié : le scénario mesurable vit ici, JAMAIS dans un live ----
demo = db.query(Space).filter(Space.tenant_id == conn.tenant_id,
                              Space.name == "Démo Retail").first()
if demo is None:
    demo = Space(tenant_id=conn.tenant_id, name="Démo Retail", slug=slugify("Démo Retail"),
                 description="Scénario vitrine — données de démonstration (non réelles).")
    db.add(demo); db.flush()
if not db.query(SpaceConnection).filter(SpaceConnection.space_id == demo.id,
        SpaceConnection.connection_id == CONN_ID).first():
    db.add(SpaceConnection(space_id=demo.id, connection_id=CONN_ID))
db.query(SpaceConnection).filter(
    SpaceConnection.connection_id == CONN_ID,
    SpaceConnection.space_id != demo.id).delete(synchronize_session=False)

db.commit()
print("decision:", dec.id, "| plan:", plan.id, "| impl:", IMPL.isoformat(),
      "| retained:", plan.control_selection["control_ids"],
      "| result:", run.result, "| adjusted:", run.adjusted_delta)
for c in plan.control_selection["considered"]:
    print("  candidate", c["id"], c["region"], "match", c["matching_score"],
          "pretrend", c["pretrend_score"], "->", "RETENU" if c["retained"] else "écarté", c.get("reason", ""))
db.close()
