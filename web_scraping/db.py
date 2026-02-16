from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = 'postgresql://postgres:20357@localhost:5432/train_data'

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)