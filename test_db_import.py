"""Test exactly what happens inside database.py import."""
import os, sys, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

log = open("db_import_test.log", "w", encoding="utf-8")
def l(msg): log.write(msg + "\n"); log.flush(); print(msg, flush=True)

t0 = time.time()
l("step 1: import sqlalchemy")
from sqlalchemy import create_engine
l(f"  done {time.time()-t0:.2f}s")

l("step 2: import sessionmaker")
from sqlalchemy.orm import DeclarativeBase, sessionmaker
l(f"  done {time.time()-t0:.2f}s")

l("step 3: import settings")
from app.infrastructure.config import settings
l(f"  done {time.time()-t0:.2f}s")

l("step 4: create Base")
class Base(DeclarativeBase):
    pass
l(f"  done {time.time()-t0:.2f}s")

l("step 5: create_engine (WITHOUT connect_args)")
eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
l(f"  done {time.time()-t0:.2f}s")

l("step 6: sessionmaker")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng)
l(f"  done {time.time()-t0:.2f}s")

l("ALL STEPS DONE - database.py would complete normally")
log.close()
