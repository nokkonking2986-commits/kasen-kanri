import requests
from datetime import datetime, timedelta, timezone

FIREBASE_URL = "https://kasen-kanri-default-rtdb.asia-southeast1.firebasedatabase.app"
OFC_CD = 22061
ITMKND_CD = 1  # 雨量
FORECAST_HORIZON_H = 6  # 将来分は0で埋める時間数(アプリ側のFORECAST_HORIZON_Hと合わせる)
PAGES = 2  # 50時間 x 2 = 約100時間(4日強)分をさかのぼって取得

KAWABOU_STATIONS = {
    "青垣": 10, "氷上": 1, "柏原": 11, "船町": 3, "杉原": 22, "八千代": 13,
    "板波": 15, "天神": 6, "北条": 9, "小野": 7, "吉川": 23, "細川": 14,
    "谷上": 24, "福住": 12, "火打岩": 2, "今田": 5,
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.river.go.jp/kawabou/pcfull/tm?itmkndCd=1&ofcCd=22061&obsCd=15&isCurrent=true&fld=0",
}
JST = timezone(timedelta(hours=9))


def obs_fcd(obs_cd):
    return f"{OFC_CD:05d}{ITMKND_CD:03d}{obs_cd:05d}"


def fetch_hourly(obs_cd, app_time):
    app_time = app_time.replace(minute=(app_time.minute // 10) * 10, second=0, microsecond=0)
    fcd = obs_fcd(obs_cd)
    date_str = app_time.strftime("%Y%m%d")
    time_str = app_time.strftime("%H%M")
    url = f"https://www.river.go.jp/kawabou/file/files/tmlist/rn/{date_str}/{time_str}/{fcd}.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"  取得失敗: {res.status_code}")
        return {}
    result = {}
    for v in res.json().get("hrValues", []):
        dt = datetime.strptime(v["obsTime"], "%Y/%m/%d %H:%M")
        result[dt] = v.get("rnHr") or 0
    return result


def fetch_station_series(obs_cd, now):
    merged = {}
    app_time = now
    for _ in range(PAGES):
        page = fetch_hourly(obs_cd, app_time)
        merged.update(page)
        if not page:
            break
        app_time = min(page.keys()) - timedelta(hours=1)
    return merged


print("kawabou実測雨量取得中...")
now = datetime.now(JST).replace(tzinfo=None)
now_hour = now.replace(minute=0, second=0, microsecond=0)

per_station_hourly = {}
all_hours = set()
for name, obs_cd in KAWABOU_STATIONS.items():
    hourly = fetch_station_series(obs_cd, now)
    per_station_hourly[name] = hourly
    all_hours.update(hourly.keys())
    nonzero = sorted([(t, v) for t, v in hourly.items() if v], key=lambda x: x[0])[-1:]
    print(f"  {name}: 直近非ゼロ={nonzero if nonzero else 'なし'}")

start_hour = min(all_hours)
n_past = int((now_hour - start_hour).total_seconds() // 3600) + 1
times = [start_hour + timedelta(hours=i) for i in range(n_past)]
times += [now_hour + timedelta(hours=i) for i in range(1, FORECAST_HORIZON_H + 1)]
time_labels = [t.strftime("%Y-%m-%dT%H:00") for t in times]

stations = {}
for name, hourly in per_station_hourly.items():
    precip = [round(hourly.get(t, 0), 1) if t <= now_hour else 0 for t in times]
    stations[name] = {"time": time_labels, "precip": precip}

payload = {"取得時刻": now.strftime("%Y-%m-%dT%H:%M"), "stations": stations}

ok1 = requests.put(f"{FIREBASE_URL}/kwRainRaw.json", json=payload)
ok2 = requests.post(f"{FIREBASE_URL}/kwRainLog.json", json=payload)
print(f"Firebase書き込み(kwRainRaw){'成功✅' if ok1.status_code == 200 else '失敗❌'}")
print(f"Firebase書き込み(kwRainLog){'成功✅' if ok2.status_code == 200 else '失敗❌'}")
