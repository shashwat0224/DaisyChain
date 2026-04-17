from sqlalchemy import Column, String, Boolean, Integer, Time, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Station(Base):
    __tablename__ = "stations"

    station_code = Column(String(10), primary_key=True)
    station_name = Column(String, nullable=False)
    is_major_junction = Column(Boolean, nullable=False)


class Train(Base):
    __tablename__ = "trains"

    train_no = Column(String(5), primary_key=True)
    train_name = Column(String, nullable=False)
    source_station = Column(String(10), ForeignKey("stations.station_code"))
    destination_station = Column(String(10), ForeignKey("stations.station_code"))
    classes = Column(String, nullable=False)
    days = Column(String, nullable=False)


class TrainStop(Base):
    __tablename__ = "train_stops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    train_no = Column(String(5), ForeignKey("trains.train_no"))
    station_code = Column(String(10), ForeignKey("stations.station_code"))
    Station_name = Column(String, nullable=False)
    stop_index = Column(Integer, nullable=False)
    arrival_time = Column(Time, nullable=False)
    departure_time = Column(Time, nullable=False)
    halt_time = Column(String(10), nullable=False)
    day_offset = Column(Integer, nullable=False)
    avg_delay = Column(String(10), nullable=False)