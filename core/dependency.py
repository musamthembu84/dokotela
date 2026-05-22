from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

from core.database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]