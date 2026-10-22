from sqlmodel import create_engine, Session
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # drops dead connections instead of erroring
    # Cloud Postgres/proxies commonly drop idle connections after 5 minutes;
    # recycle before that so a slept-in worker cannot grab a dead socket.
    pool_recycle=1800,
    # echo=settings.ENVIRONMENT == "development",
    echo=False,
)


def get_session():
    with Session(engine) as session:
        yield session