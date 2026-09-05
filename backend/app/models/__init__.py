"""Import every model module so Base.metadata is fully populated for
Alembic autogenerate and for create_all() in tests."""

from app.models import (
    agent,  # noqa: F401
    campaigns,  # noqa: F401
    catalog,  # noqa: F401
    commerce,  # noqa: F401
    customers,  # noqa: F401
    identity,  # noqa: F401
    opportunities,  # noqa: F401
    ops,  # noqa: F401
)
