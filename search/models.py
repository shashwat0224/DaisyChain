from dataclasses import dataclass
from datetime import time
from typing import Optional


@dataclass
class StopInfo:
    station_code: str
    station_name: str
    departure_time: Optional[time]
    arrival_time:   Optional[time]
    day_offset:     int

@dataclass
class TransferInfo:
    station_code:    str
    station_name:    str
    is_major:        bool
    wait_minutes:    int
    arrive_time:     time
    arrive_day:      int
    depart_time:     time
    depart_day:      int

@dataclass
class DirectResult:
    train_no:         str
    train_name:       str
    source_station:   str
    dest_station:     str
    arrival_time:     time
    arrival_day:      int
    departure_time:   time
    departure_day:    int
    journey_minutes:  int
    stops_in_between: int
    classes:          str
    service_days:     str

    @property
    def journey_duration_str(self) -> str:
        h, m = divmod(self.journey_minutes, 60)
        return f"{h}h {m}m"
    
    @property
    def departure_str(self) -> str:
        return self.departure_time.strftime("%H:%M") if self.departure_time else "--"

    @property
    def arrival_str(self) -> str:
        return self.arrival_time.strftime("%H:%M") if self.arrival_time else "--"



@dataclass
class IndirectResult:
    leg1:             DirectResult
    leg2:             DirectResult
    transfer:         TransferInfo
    total_minutes:    int        # leg1 + wait + leg2
    is_major_junction: bool

    @property
    def total_duration_str(self) -> str:
        h, m = divmod(self.total_minutes, 60)
        return f"{h}h {m}m"
    
    @property
    def departure_str(self) -> str:
        return self.departure_time.strftime("%H:%M") if self.departure_time else "--"
    
    @property
    def arrival_str(self) -> str:
        return self.arrival_time.strftime("%H:%M") if self.arrival_time else "--"