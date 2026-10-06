from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import enable_foreign_keys
from app.models.user import User
from app.models.user_session import UserSession
from app.repository.session_repository import SessionRepository
from app.security import hash_token, utc_now


# Проверяет конкуренцию refresh-запросов на разных соединениях SQLite.
class SessionConcurrencyTests(unittest.TestCase):
    # Разрешает только одну замену исходного refresh-токена.
    def test_single_refresh_winner(self):
        with TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "test.db"))
            event.listen(engine, "connect", enable_foreign_keys)
            sessions = sessionmaker(bind=engine)
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            try:
                with engine.begin() as connection:
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                with sessions() as db:
                    user = User(email="test@example.com", hashed_password="test-only")
                    db.add(user)
                    db.flush()
                    db.add(UserSession(id="a" * 32, user_id=user.id, refresh_token_hash=hash_token("old"),
                                       created_at=utc_now(), expires_at=utc_now() + timedelta(days=1)))
                    db.commit()
                barrier = Barrier(2)

                # Начинает замену одновременно со вторым запросом.
                def rotate(value):
                    with sessions() as db:
                        barrier.wait(timeout=10)
                        return SessionRepository(db).rotate("a" * 32, hash_token("old"), hash_token(value), utc_now())

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(rotate, ["first", "second"]))
                self.assertEqual(sorted(results), [False, True])
            finally:
                engine.dispose()
