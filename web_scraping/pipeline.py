from db import SessionLocal
from models import Station, Train, TrainStop
from datetime import datetime
from sqlalchemy.exc import IntegrityError

def parse_time(t):
    if not t:
        return None
    return datetime.strptime(t, "%H:%M").time()

def parse_service_days(text):
    days = {
        "Mon": False, "Tue": False, "Wed": False,
        "Thu": False, "Fri": False, "Sat": False, "Sun": False
    }

    for d in days.keys():
        if d in text:
            days[d] = True

    return days

# def insert_station(session, code, name):
#     if not session.get(Station, code):
#         station = Station(
#             station_code=code,
#             station_name=name
#         )
#         session.add(station)

# def insert_train(session, train_data):
#     if not session.get(Train, train_data["train_no"]):
#         train = Train(**train_data)
#         session.add(train)

# def insert_train_stops(session, train_no, stops):
#     for idx, stop in enumerate(stops):
#         ts = TrainStop(
#             train_no=train_no,
#             station_code=stop["station_code"],
#             stop_index=idx,
#             arrival_time=stop["arrival_time"],
#             departure_time=stop["departure_time"],
#             day_offset=stop["day"]
#         )
#         session.add(ts)

def save_train(data):
    session = SessionLocal()

    try:
        for stop in data["stops"]:
            if not session.get(Station, stop["station_code"]):
                station = Station(
                    station_code = stop["station_code"],
                    station_name = stop["station_name"]
                )
                session.add(station)

        service_days = parse_service_days(data["service_days"])

        if not session.get(Train, data["train_no"]):
            train = Train(
                train_no = data["train_no"],
                train_name = data["train_name"],
                source_station = data["stops"][0]["station_code"],
                destination_station = data["stops"][-1]["station_code"],
                classes = data["classes"],
                runs_mon = service_days["Mon"],
                runs_tue = service_days["Tue"],
                runs_wed = service_days["Wed"],
                runs_thu = service_days["Thu"],
                runs_fri = service_days["Fri"],
                runs_sat = service_days["Sat"],
                runs_sun = service_days["Sun"],
            )
            session.add(train)
        
        for idx, stop in enumerate(data["stops"]):
            exists = session.query(TrainStop).filter_by(
                train_no = data["train_no"],
                stop_index = idx
            ).first()

            if not exists:
                trainstop = TrainStop(
                    train_no = data["train_no"],
                    station_code = stop["station_code"],
                    stop_index = idx,
                    arrival_time = stop["arrival_time"],
                    departure_time = stop["departure_time"],
                    day_offset = stop["day"],
                )
                session.add(trainstop)

        session.commit()

    except Exception as e:
        session.rollback()
        print("Error :", e)

    finally:
        session.close()