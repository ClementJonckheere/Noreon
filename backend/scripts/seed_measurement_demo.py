import psycopg
from datetime import date, timedelta, datetime, timezone
from app.core.db import SessionLocal
from app.models.connection import Connection
from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan, MeasurementRun

TARGET = ["Marseille Prado", "Nice Lingostiere"]
CONTROL = ["Lyon Part-Dieu", "Paris Rivoli"]
IMPL = date.today() - timedelta(days=45)     # action mise en œuvre il y a 45 j
BW = 30                                       # fenêtres de 30 j

# --- table de mesure (baseline 1000 avant IMPL ; après : cible +3,1 %, témoins +4,5 %) ---
c = psycopg.connect("host=127.0.0.1 dbname=noreon_demo_retail user=noreon password=noreon")
cur = c.cursor()
cur.execute("DROP TABLE IF EXISTS action_impact")
cur.execute("CREATE TABLE action_impact (store text, day date, revenue numeric)")
rows = []
for d in range(-BW, BW):
    day = IMPL + timedelta(days=d)
    after = day >= IMPL
    for s in TARGET:  rows.append((s, day, 1031 if after else 1000))
    for s in CONTROL: rows.append((s, day, 1045 if after else 1000))
cur.executemany("INSERT INTO action_impact VALUES (%s,%s,%s)", rows)
cur.execute("GRANT SELECT ON action_impact TO PUBLIC")
cur.execute("GRANT SELECT ON action_impact TO noreon_ro")
c.commit(); c.close()

# --- décision + plan DÉJÀ mis en œuvre (baseline figé à IMPL) ---
db = SessionLocal()
conn = db.get(Connection, 2414)
old = db.query(DecisionRecord).filter(DecisionRecord.connection_id==2414,
      DecisionRecord.recommendation.like("Plan de relance commerciale%")).all()
for o in old:
    db.query(MeasurementPlan).filter(MeasurementPlan.decision_id==o.id).delete(synchronize_session=False)
    db.delete(o)
db.commit()
dec = DecisionRecord(tenant_id=conn.tenant_id, connection_id=2414, subject="orders",
    role="Directeur réseau",
    recommendation="Plan de relance commerciale — magasins Provence-Alpes-Côte d'Azur.",
    status="implemented")
db.add(dec); db.flush()
impl_dt = datetime.combine(IMPL, datetime.min.time(), tzinfo=timezone.utc)
plan = MeasurementPlan(decision_id=dec.id, tenant_id=conn.tenant_id, connection_id=2414,
    measure_type="impact", metric_label="Chiffre d'affaires",
    scope={"table":"action_impact","dim_col":"store","metric_col":"revenue","date_col":"day","values":TARGET},
    control_scope={"values":CONTROL}, comparison="matched_control", threshold=0.02,
    )
db.add(plan); db.flush()
from app.services.connections import get_source_adapter
from app.services import measurement as meas
meas.freeze_baseline(db, plan, get_source_adapter(conn), implemented_at=impl_dt)
db.commit()
print("decision:", dec.id, "| plan:", plan.id, "| implemented_at:", IMPL.isoformat())
db.close()
