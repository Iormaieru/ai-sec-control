import hmac

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.integraciones.jira import sync
from app.integraciones.jira.client import JiraError

router = APIRouter(prefix="/integraciones/jira", tags=["jira"])


def _verificar_secreto(esperado: str | None, recibido: str | None) -> None:
    if not esperado:
        # Sin secreto configurado el endpoint no existe: nunca queda abierto.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not recibido or not hmac.compare_digest(esperado.encode(), recibido.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Secreto inválido")


def _cliente():
    try:
        return sync.crear_cliente()
    except sync.JiraDeshabilitada as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/sync")
def sincronizar(
    x_aisec_secret: str | None = Header(default=None), db: Session = Depends(get_db)
) -> dict:
    """Lo llama Cloud Scheduler cada pocos minutos: empuja la outbox y trae
    los cambios de Jira."""
    _verificar_secreto(get_settings().jira_sync_secret, x_aisec_secret)
    with _cliente() as client:
        try:
            resultado = sync.sincronizar(db, client)
        except JiraError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if not resultado.ejecutado:
        return {"ejecutado": False, "motivo": "Ya hay una sincronización en curso"}
    return {
        "ejecutado": True,
        "push": {"enviados": resultado.push.enviados, "errores": resultado.push.errores},
        "pull": {
            "nuevos": resultado.pull.nuevos,
            "actualizados": resultado.pull.actualizados,
            "errores": resultado.pull.errores,
        },
    }


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
def webhook(
    payload: dict = Body(...),
    x_aisec_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    """Aviso de Jira (regla de Automation o webhook nativo) de que un ticket
    cambió. No se usa el contenido del aviso más allá de la clave: el ticket
    se vuelve a leer de Jira."""
    _verificar_secreto(get_settings().jira_webhook_secret, x_aisec_secret)
    issue_key = payload.get("issueKey") or (payload.get("issue") or {}).get("key")
    if not isinstance(issue_key, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Falta issueKey")
    with _cliente() as client:
        try:
            sync.pull_issue(db, client, issue_key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except JiraError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
