import time, random
from bs4 import BeautifulSoup

BASE_URL = "https://www.ixigo.com/trains/{}"

def scrape_train_pw(train_no, page):

    url = BASE_URL.format(train_no)

    #open landing page first 
    page.goto("https://www.ixigo.com/trains")
    time.sleep(random.uniform(2,4))

    # open train page
    page.goto(url, timeout=60000)
    page.wait_for_load_state("networkidle")

    # detect redirect
    if page.url != url:
        print("redirected to :", page.url)
        return "BLOCKED"
    
    #Give time for js to render
    time.sleep(random.uniform(3,6))
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # ----------Extract train information-------------- 
    print(soup.find('span', class_='name'))
    if page.locator("table").count() < 2:
        return "WRONG"

    try:
        name_tag = soup.find('span', class_='name')

        if not name_tag:
            print(f"Missing train name for {train_no}")
            return "WRONG"
        
        train_name = name_tag.text.strip()
        train_name = soup.find('span', class_='name').text.rstrip(f' {train_no} Train')
        train_time = soup.find_all('div', class_='time')
        tables = soup.find_all("table")
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
            arrival_time = train_time[0].text if cols[2].lower() == "starts" else cols[2]
            departure_time = train_time[1].text if cols[3].lower() == "ends" else cols[3]
            halt_time = cols[4]
            day_offset = int(cols[8]) - 1   # ixigo shows Day starting from 1
            avg_delay = cols[9]
            stops.append({
                "station_code": station_code,
                "station_name": station_name,
                "arrival_time": arrival_time,
                "departure_time": departure_time,
                "halt_time": halt_time,
                "day": day_offset,
                "avg_delay": avg_delay
            })

        return {
            "train_no": train_no,
            "train_name": train_name,
            "classes": info_data.get("Classes", ""),
            "days": info_data.get("Service Days", ""),
            "stops": stops
        }
    except Exception as e:
        print(f"Error parsing {train_no}: {e}")
        return None