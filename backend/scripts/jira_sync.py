"""Sincroniza los casos con Jira: empuja la outbox y trae los cambios.

En Cloud Run esto lo hace Cloud Scheduler contra POST /integraciones/jira/sync;
en local (Jira no puede llegar a localhost) se corre este script:

    uv run python scripts/jira_sync.py            # una vez
    uv run python scripts/jira_sync.py --loop 60  # cada 60 segundos

Requiere AISEC_JIRA_ENABLED=true y las credenciales en backend/.env.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.integraciones.jira import sync  # noqa: E402


def _una_vez() -> None:
    db = SessionLocal()
    try:
        with sync.crear_cliente() as client:
            resultado = sync.sincronizar(db, client)
    finally:
        db.close()
    if not resultado.ejecutado:
        print("Ya hay una sincronización en curso; se omite.")
        return
    print(f"push: {resultado.push.enviados} enviados, {len(resultado.push.errores)} con error")
    print(f"pull: {resultado.pull.nuevos} nuevos, {resultado.pull.actualizados} actualizados, "
          f"{len(resultado.pull.errores)} con error")
    for error in resultado.push.errores + resultado.pull.errores:
        print(f"  - {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--loop", type=int, metavar="SEGUNDOS", help="repetir cada N segundos")
    args = parser.parse_args()

    try:
        _una_vez()
        while args.loop:
            time.sleep(args.loop)
            _una_vez()
    except sync.JiraDeshabilitada as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
