from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Chart(Base):
    __tablename__ = 'charts'
    
    id = Column(Integer, primary_key=True)
    chart_type = Column(String(50))
    title = Column(String(200))
    file_path = Column(String(500))
    file_url = Column(String(500))
    x_label = Column(String(100))
    y_label = Column(String(100))
    description = Column(Text)
    data_points = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    thread_id = Column(String(100))  
    
    def to_dict(self):
        return {
            'id': self.id,
            'chart_type': self.chart_type,
            'title': self.title,
            'file_path': self.file_path,
            'file_url': self.file_url,
            'x_label': self.x_label,
            'y_label': self.y_label,
            'description': self.description,
            'data_points': self.data_points,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'thread_id': self.thread_id
        }

# Database setup
try:
    engine = create_engine(os.getenv("DATABASE_URL"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Warning: Could not initialize chart database: {e}")
    Session = None