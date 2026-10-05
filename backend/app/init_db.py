from sqlalchemy import select, text

from . import models  # noqa: F401  (registers every table on Base.metadata)
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Cpse, Setting, User
from .security import hash_password
from .settings_store import DEFAULTS

CPSES = [("IOCL", "Indian Oil Corporation Ltd", "Oil & Gas"), ("ONGC", "Oil and Natural Gas Corporation", "Oil & Gas"),
         ("BPCL", "Bharat Petroleum Corporation Ltd", "Oil & Gas"),
         ("HPCL", "Hindustan Petroleum Corporation Ltd", "Oil & Gas"),
         ("GAIL", "GAIL (India) Ltd", "Oil & Gas"), ("NTPC", "NTPC Ltd", "Power"),
         ("SAIL", "Steel Authority of India Ltd", "Steel"),
         ("BHEL", "Bharat Heavy Electricals Ltd", "Heavy Engineering"), ("CIL", "Coal India Ltd", "Mining")]

__all__ = ["DEFAULTS", "main"]


def main():
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        # Columns added after the first release: create_all() never alters existing tables.
        c.execute(text("ALTER TABLE ingest_job ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_nm_successor ON national_material (successor_nmc)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_raw_emb ON raw_material USING hnsw (embedding vector_cosine_ops)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_raw_trgm ON raw_material USING gin (norm_text gin_trgm_ops)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_raw_attrs ON raw_material USING gin (attributes jsonb_path_ops)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_pair_status ON match_pair (status, impact DESC)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_pair_b ON match_pair (b_id)"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_map_nmc ON code_mapping (nmc)"))
    admin_email = settings.admin_email.strip().lower()     # login lowercases, so the stored email must be too
    with SessionLocal() as db:
        for code, name, sector in CPSES:
            if not db.scalar(select(Cpse).where(Cpse.code == code)):
                db.add(Cpse(code=code, name=name, sector=sector))
        if not db.scalar(select(User).where(User.email == admin_email)):
            db.add(User(email=admin_email, name="Platform Admin", role="admin",
                        password_hash=hash_password(settings.admin_password)))
        for k, v in DEFAULTS.items():
            if not db.get(Setting, k):
                db.add(Setting(key=k, value=v))
        db.commit()
    print("database ready")


if __name__ == "__main__":
    main()
