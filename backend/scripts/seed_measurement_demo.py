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
CONTROL = ["Lyon Part-Dieu", "Paris Rivoli"]
IMPL = date.today() - timedelta(days=45)      # action mise en œuvre il y a 45 j
BW = 30                                        # fenêtres de 30 j

# --- table de mesure ---------------------------------------------------------
# Baselines VOLONTAIREMENT non identiques pour un appariement RÉALISTE (≠ 100 %) :
#   cible ≈ 1000/j (léger uptrend intra-fenêtre → pré-tendance ~95 %),
#   témoins ≈ 1080/j, plats (niveau ~92 %).
# Après action : cible +3,1 %, témoins +4,5 % → écart contrôlé −1,4 pt.
c = psycopg.connect("host=127.0.0.1 dbname=noreon_demo_retail user=noreon password=noreon")
cur = c.cursor()
cur.execute("DROP TABLE IF EXISTS action_impact")
cur.execute("CREATE TABLE action_impact (store text, day date, revenue numeric)")
rows = []
for d in range(-BW, BW):
    day = IMPL + timedelta(days=d)
    after = day >= IMPL
    for s in TARGET:
        # baseline : 1re moitié 995, 2e moitié 1005 (avg 1000, pré-tendance +1 %) ;
        # observation : 1031 → +3,1 % vs baseline.
        rows.append((s, day, 1031 if after else (1005 if d >= -BW / 2 else 995)))
    for s in CONTROL:
        # baseline plate 1080 ; observation 1128,6 → +4,5 %.
        rows.append((s, day, 1128.6 if after else 1080))
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
    # Témoins + comparabilités DÉCLARÉES (attributs magasin) reportées telles quelles.
    control_scope={"values": CONTROL, "comparability": [
        {"label": "Mix High-Tech", "verdict": "similaire"},
        {"label": "Format de magasin", "verdict": "comparable"},
        {"label": "Saisonnalité", "verdict": "compatible"},
    ]},
    comparison="matched_control", threshold=0.02,
    )
db.add(plan); db.flush()
from app.services.connections import get_source_adapter
from app.services import measurement as meas
meas.freeze_baseline(db, plan, get_source_adapter(conn), implemented_at=impl_dt)

# --- espace DÉMO dédié : le scénario mesurable vit ici, JAMAIS dans un live ----
# Le cloisonnement par espace (list_plan filtre par connexions de l'espace) garantit
# qu'un espace « live » ne peut pas afficher ces fixtures.
demo = db.query(Space).filter(Space.tenant_id == conn.tenant_id,
                              Space.name == "Démo Retail").first()
if demo is None:
    demo = Space(tenant_id=conn.tenant_id, name="Démo Retail", slug=slugify("Démo Retail"),
                 description="Scénario vitrine — données de démonstration (non réelles).")
    db.add(demo); db.flush()
if not db.query(SpaceConnection).filter(SpaceConnection.space_id == demo.id,
        SpaceConnection.connection_id == CONN_ID).first():
    db.add(SpaceConnection(space_id=demo.id, connection_id=CONN_ID))
# La connexion de démo ne doit être rattachée à AUCUN espace live.
db.query(SpaceConnection).filter(
    SpaceConnection.connection_id == CONN_ID,
    SpaceConnection.space_id != demo.id).delete(synchronize_session=False)

db.commit()
print("decision:", dec.id, "| plan:", plan.id, "| implemented_at:", IMPL.isoformat(),
      "| demo space:", demo.id, "| control_selection:", plan.control_selection)
db.close()
