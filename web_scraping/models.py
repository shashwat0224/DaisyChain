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

    runs_mon = Column(Boolean)
    runs_tue = Column(Boolean)
    runs_wed = Column(Boolean)
    runs_thu = Column(Boolean)
    runs_fri = Column(Boolean)
    runs_sat = Column(Boolean)
    runs_sun = Column(Boolean)


class TrainStop(Base):
    __tablename__ = "train_stops"

    id = Column(Integer, primary_key=True, autoincrement=True)

    train_no = Column(String(5), ForeignKey("trains.train_no"))
    station_code = Column(String(10), ForeignKey("stations.station_code"))

    stop_index = Column(Integer, nullable=False)
    arrival_time = Column(Time)
    departure_time = Column(Time)
    day_offset = Column(Integer, nullable=False)