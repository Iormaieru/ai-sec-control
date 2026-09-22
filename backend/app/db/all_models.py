"""Import every ORM model module here so Base.metadata is complete for Alembic autogenerate."""

from app.audit import models as audit_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.casos import models as casos_models  # noqa: F401
from app.catalog import models as catalog_models  # noqa: F401
