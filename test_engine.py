import os, sys, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

log = open("engine_test.log", "w", encoding="utf-8")
def l(msg): log.write(msg + "\n"); log.flush(); print(msg)

t0 = time.time()
l(f"start: {t0}")

l("import sqlalchemy...")
from sqlalchemy import create_engine
l(f"sqlalchemy done: {time.time()-t0:.2f}s")

l("load settings...")
from app.infrastructure.config import settings
l(f"settings done: {time.time()-t0:.2f}s")
l(f"DB URL: {settings.DATABASE_URL[:50]}")

l("create_engine() call starting...")
eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5})
l(f"create_engine done: {time.time()-t0:.2f}s")

l("test connect()...")
try:
    conn = eng.connect()
    l("connect OK!")
    conn.close()
except Exception as e:
    l(f"connect FAILED: {e}")

l("DONE")
log.close()
