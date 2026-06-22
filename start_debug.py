"""Debug startup - captures all errors to a file."""
import sys
import os
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))

log_file = open("startup_errors.log", "w", encoding="utf-8")

def log(msg):
    log_file.write(msg + "\n")
    log_file.flush()

log(f"Python: {sys.version}")
log(f"CWD: {os.getcwd()}")

try:
    from app.infrastructure.config import settings
    log("Settings OK")
except Exception as e:
    log(f"Settings FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing app.infrastructure.persistence.database...")
    from app.infrastructure.persistence import database
    log("database OK")
except Exception as e:
    log(f"database FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing app.infrastructure.persistence.orm.models...")
    from app.infrastructure.persistence.orm import models
    log("models OK")
except Exception as e:
    log(f"models FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing app.domain.exceptions...")
    from app.domain import exceptions
    log("exceptions OK")
except Exception as e:
    log(f"exceptions FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing app.api.v1.endpoints.projects...")
    from app.api.v1.endpoints import projects
    log("projects endpoint OK")
except Exception as e:
    log(f"projects endpoint FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing app.api.v1.endpoints.media...")
    from app.api.v1.endpoints import media
    log("media endpoint OK")
except Exception as e:
    log(f"media endpoint FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

try:
    log("Importing full app...")
    from app.main import app
    log("Full app OK!")
except Exception as e:
    log(f"Full app FAILED: {e}")
    traceback.print_exc(file=log_file)
    log_file.close()
    sys.exit(1)

log("All imports succeeded - starting uvicorn now")
log_file.close()

import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
