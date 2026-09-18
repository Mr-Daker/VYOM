import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db

# We use an in-memory SQLite database specifically for API logic tests, 
# although PostgreSQL is recommended for full DB constraint testing.
# For these test cases, we test the logic constraints.

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


import os
from sqlalchemy import create_engine, text

@pytest.fixture
def postgres_db_engine():
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@db_test:5432/saarthi_test",
    )
    engine = create_engine(url)
    
    # SAFETY ISOLATION CHECK
    assert engine.url.database.endswith("_test"), f"Database {engine.url.database} does not end with _test. Refusing destructive reset."
    
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        
    try:
        yield engine
    finally:
        engine.dispose()
