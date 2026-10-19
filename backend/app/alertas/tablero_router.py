"""Tablero "Seguridad de IA" (Dashboards): métricas y exportación.

Lo ven todos los usuarios autenticados, igual que el sector Alertas.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.alertas.models import SeveridadAlerta
from app.alertas.schemas_tablero import TableroIAOut
from app.alertas.tablero import FiltrosIA, Poblacion, tablero
from app.alertas.tablero_export import TablaCSV, exportar_csv, exportar_xlsx
from app.auth.models import User
from app.core.deps import get_current_user
from app.db.session import get_db

router = APIRouter(prefix="/metricas/ia", tags=["metricas"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _filtros(
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
    regla_id: uuid.UUID | None = None,
    severidad: SeveridadAlerta | None = None,
    poblacion: Poblacion | None = None,
    _user: User = Depends(get_current_user),
) -> FiltrosIA:
    return FiltrosIA.armar(desde, hasta, regla_id=regla_id, severidad=severidad, poblacion=poblacion)


def _adjunto(nombre: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{nombre}"'}


@router.get("", response_model=TableroIAOut)
def obtener(f: FiltrosIA = Depends(_filtros), db: Session = Depends(get_db)) -> TableroIAOut:
    return tablero(db, f)


@router.get("/export.xlsx")
def exportar_excel(f: FiltrosIA = Depends(_filtros), db: Session = Depends(get_db)) -> Response:
    return Response(exportar_xlsx(db, f), media_type=XLSX, headers=_adjunto(f"seguridad-ia_{f.desde}_{f.hasta}.xlsx"))


@router.get("/export.csv")
def exportar_tabla_csv(
    tabla: TablaCSV = TablaCSV.ALERTAS, f: FiltrosIA = Depends(_filtros), db: Session = Depends(get_db)
) -> Response:
    return Response(
        exportar_csv(db, f, tabla),
        media_type="text/csv; charset=utf-8",
        headers=_adjunto(f"seguridad-ia_{tabla.value}_{f.desde}_{f.hasta}.csv"),
    )
