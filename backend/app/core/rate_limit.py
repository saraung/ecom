from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Storage is configurable: "memory://" is per-process (fine for a single API
# process), while "redis://host:6379/0" shares buckets across replicas so a
# client cannot bypass a limit by hitting another worker.
#
# Production deployments with more than one API process should set
# RATE_LIMIT_STORAGE_URI to a Redis URL and REQUIRE_SHARED_RATE_LIMIT=true,
# which makes boot fail rather than silently allowing N× the limit.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    default_limits=["200/minute"],
)
