"""Releva en Jira la configuración que usa la integración (sólo lectura).

Útil si cambian el tablero IA-SEC, su filtro, las columnas o los tipos de
solicitud: muestra lo que hay que ajustar en AISEC_JIRA_*.

    uv run python scripts/jira_discover.py

Usa las credenciales de backend/.env (no requiere AISEC_JIRA_ENABLED).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.integraciones.jira.client import JiraClient  # noqa: E402
from app.integraciones.jira.mapping import estados_por_status  # noqa: E402


def main() -> None:
    s = get_settings()
    with JiraClient(s) as client:
        yo = client._request("GET", "/rest/api/3/myself")
        print(f"Cuenta: {yo['displayName']} <{yo.get('emailAddress')}>")

        config = client.get_board_configuration(s.jira_board_id)
        filtro = client._request("GET", f"/rest/api/3/filter/{config['filter']['id']}")
        print(f"\nTablero {s.jira_board_id}: {config['name']}")
        print(f"Filtro {filtro['id']} ({filtro['name']}):\n  {' '.join(filtro['jql'].split())}")

        mapa = estados_por_status(config)
        print("\nColumnas:")
        for columna in config["columnConfig"]["columns"]:
            ids = [st["id"] for st in columna["statuses"]]
            estado = mapa.get(ids[0]).value if ids and ids[0] in mapa else "(no es un estado del caso)"
            print(f"  {columna['name']:<22} -> {estado:<22} status {', '.join(ids) or '-'}")

        campos = client._request(
            "GET", f"/rest/api/3/issue/createmeta/{s.jira_project_key}/issuetypes/{s.jira_issue_type_id}"
        )
        print(f"\nCampos al crear ({s.jira_project_key} / issuetype {s.jira_issue_type_id}):")
        for f in campos.get("fields", []):
            print(f"  {f['fieldId']:<20} {f['name']:<40} requerido={f['required']}")

        print("\nTipos de solicitud configurados:")
        for id_, nombre in s.jira_request_types.items():
            print(f"  {id_}: {nombre}")


if __name__ == "__main__":
    main()
