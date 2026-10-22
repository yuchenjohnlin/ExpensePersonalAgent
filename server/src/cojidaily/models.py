"""Every module's tables, imported so that Base.metadata knows all of them (Alembic, tests)."""
from .auth import models as auth  # noqa: F401
from .ledger import models as ledger  # noqa: F401
from .photos import models as photos  # noqa: F401
from .platform import jobs  # noqa: F401
from .reading import models as reading  # noqa: F401
from .receipts import models as receipts  # noqa: F401
from .platform.db import Base

metadata = Base.metadata
