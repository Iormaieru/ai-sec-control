"""Los tests del worker corren contra la misma base de test que los del
backend y reutilizan sus fixtures (base de test con migraciones, db, client,
auth_headers, jira y la limpieza entre tests). Se ejecutan con el entorno
del backend:

    cd worker && ../backend/.venv/bin/python -m pytest
"""

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_RAIZ / "backend"), str(_RAIZ / "worker")]

# tests.conftest apunta la configuración a la base de test antes de que se
# importe `app`; tests.integration.conftest trae los fixtures.
pytest_plugins = ["tests.conftest", "tests.integration.conftest"]
