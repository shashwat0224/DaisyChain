import requests, time
from bs4 import BeautifulSoup

BASE_URL = "https://www.ixigo.com/trains/{}"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def scrape_train(train_no):
    url = BASE_URL.format(train_no)
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print("Failed to load page")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")

    # -------- Extract Train Info --------
    if soup.find('span', class_='name') == None:
        time.sleep(10)
        scrape_train(train_no)
    else:
        train_name = soup.find('span', class_='name').text.rstrip(f' {train_no} Train')
    
        info_table = tables[0]
        info_data = {}
    
        for row in info_table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all(["td","th"])]
            if len(cols) == 2:
                info_data[cols[0]] = cols[1]
    
        # -------- Extract Schedule --------
        schedule_table = tables[1]
        rows = schedule_table.find_all("tr")[1:]  # skip header
    
        stops = []
    
        for idx, row in enumerate(rows):
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
    
            if len(cols) < 10:
                continue
            
            station_code = cols[0]
            station_name = cols[1]
            arrival_time = None if cols[2].lower() == "starts" else cols[2]
            departure_time = None if cols[3].lower() == "ends" else cols[3]
            day_offset = int(cols[8]) - 1   # ixigo shows Day starting from 1
    
            stops.append({
                "station_code": station_code,
                "station_name": station_name,
                "arrival_time": arrival_time,
                "departure_time": departure_time,
                "day": day_offset
            })
    
        return {
            "train_no": train_no,
            "train_name": train_name,
            "classes": info_data.get("Classes", ""),
            "service_days": info_data.get("Service Days", ""),
            "stops": stops
        }