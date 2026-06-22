import os, sys, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

log = open("imports_test.log", "w", encoding="utf-8")
def l(msg): log.write(msg + "\n"); log.flush()

t0 = time.time()
l("start")

steps = [
    "from app.infrastructure.persistence.database import engine",
    "from app.infrastructure.persistence.orm.models import Base",
    "from app.infrastructure.persistence.repositories.project_repository import SqlAlchemyProjectRepository",
    "from app.infrastructure.persistence.repositories.media_asset_repository import SqlAlchemyMediaAssetRepository",
    "from app.application.use_cases.projects.list_projects import ListProjects",
    "from app.application.use_cases.projects.bulk_action import BulkAction",
    "from app.application.use_cases.projects.get_status_counts import GetStatusCounts",
    "from app.api.v1.dependencies.providers import get_list_projects",
    "from app.api.v1.endpoints.projects import router as proj_router",
    "from app.api.v1.endpoints.media import router as media_router",
    "from app.api.v1.router import api_router",
    "from app.main import app",
]

for step in steps:
    l(f">>> {step}")
    t = time.time()
    try:
        exec(step)
        l(f"    OK ({time.time()-t:.2f}s, total {time.time()-t0:.2f}s)")
    except Exception as e:
        import traceback
        l(f"    FAILED: {e}")
        traceback.print_exc(file=log)
        log.flush()
        log.close()
        sys.exit(1)

l("ALL DONE")
log.close()
