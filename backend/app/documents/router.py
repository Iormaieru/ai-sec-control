from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.casos.deps import get_caso_from_path
from app.casos.models import Caso
from app.core.deps import get_current_user
from app.db.session import get_db
from app.documents import service
from app.documents.parsing import SUPPORTED_CONTENT_TYPES, UnsupportedDocumentType
from app.documents.schemas import DocumentoAnalizadoOut

router = APIRouter(prefix="/casos/{caso_id}/documentos", tags=["documentos"])


@router.post("", response_model=DocumentoAnalizadoOut, status_code=status.HTTP_201_CREATED)
async def analizar_documento(
    file: UploadFile,
    caso: Caso = Depends(get_caso_from_path),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DocumentoAnalizadoOut:
    if file.content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de documento no soportado: {file.content_type!r}. Se acepta PDF o Word (.docx).",
        )

    content = await file.read()
    try:
        return service.analyze_document(
            db, caso, filename=file.filename or "documento", content=content, content_type=file.content_type
        )
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
