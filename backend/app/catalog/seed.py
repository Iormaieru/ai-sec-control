import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.catalog.models import Dominio, Polaridad, Pregunta, PreguntaTipo, Tier

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "seed" / "catalogo_maestro.json"


def load_catalog(db: Session, path: Path = DEFAULT_SEED_PATH) -> None:
    """Loads the 138-question master catalog from the versioned JSON seed
    (see scripts/extract_catalog_from_excel.py) into Dominio/Pregunta.
    Refuses to run if the catalog already has data, to avoid duplicates."""
    if db.query(Dominio).count() > 0:
        raise RuntimeError("El catálogo ya tiene dominios cargados; no se vuelve a sembrar.")

    payload = json.loads(path.read_text(encoding="utf-8"))

    dominio_by_codigo: dict[str, Dominio] = {}
    for d in payload["dominios"]:
        dominio = Dominio(
            codigo=d["codigo"], nombre=d["nombre"], peso=d["peso"], total_preguntas=d["total_preguntas"]
        )
        db.add(dominio)
        dominio_by_codigo[d["codigo"]] = dominio
    db.flush()  # assigns dominio.id (client-side UUID default) for the FK below

    for p in payload["preguntas"]:
        dominio = dominio_by_codigo[p["dominio_codigo"]]
        db.add(
            Pregunta(
                dominio_id=dominio.id,
                numero=p["numero"],
                texto_es=p["texto_es"],
                texto_en=p["texto_en"],
                tipo=PreguntaTipo(p["tipo"]),
                polaridad=Polaridad(p["polaridad"]),
                tier=Tier(p["tier"]),
                multiplicador=p["multiplicador"],
                impacto_primario=p.get("impacto_primario"),
                referencias_regulatorias=p.get("referencias_regulatorias"),
                justificacion_tier=p.get("justificacion_tier"),
                explicacion_control_es=p.get("explicacion_control_es"),
                explicacion_control_en=p.get("explicacion_control_en"),
            )
        )

    db.commit()
