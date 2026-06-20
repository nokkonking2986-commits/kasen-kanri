import requests
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://kasen-kanri-default-rtdb.asia-southeast1.firebasedatabase.app"
RIVER_FILES = {
    "oshima":    "2206100400006",
    "bessho":    "2206100400007",
    "itanami":   "2206100400002",
    "funamachi": "2206100400001",
    "manganji":  "2206100400008",
}
HEADERS = {
    "Referer": "https://www.river.go.jp/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}
JST = timezone(timedelta(hours=9))

def get_suii_history(file_id):
    now = datetime.now(JST)
    minute = (now.minute // 10) * 10 - 10
    hour = now.hour
    if minute < 0:
        minute += 60
        hour -= 1
    date_str = now.strftime("%Y%m%d")
    time_str = f"{hour:02d}{minute:02d}"
    url = f"https://www.river.go.jp/kawabou/file/files/tmlist/stg/{date_str}/{time_str}/{file_id}.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"取得失敗: {res.status_code}")
        return {}
    data = res.json()
    result = {}
    for v in data.get("min10Values", []):
        if v.get("obsTime") and v.get("stg") is not None:
            result[v["obsTime"]] = v["stg"]
    if data.get("obsTime") and data.get("obsValue", {}).get("stg") is not None:
        result[data["obsTime"]] = data["obsValue"]["stg"]
    return result

def make_row(obs_time, suii_dict):
    parts = obs_time.split(" ")
    dp = parts[0].split("/")
    uid = obs_time.replace("/","").replace(" ","").replace(":","")
    return {
        "id": uid,
        "month": str(int(dp[1])),
        "day": str(int(dp[2])),
        "time": parts[1] if len(parts) > 1 else "00:00",
        "rain": "",
        "os": str(suii_dict.get("oshima","")) if suii_dict.get("oshima") is not None else "",
        "bs": str(suii_dict.get("bessho","")) if suii_dict.get("bessho") is not None else "",
        "it": str(suii_dict.get("itanami","")) if suii_dict.get("itanami") is not None else "",
        "fm": str(suii_dict.get("funamachi","")) if suii_dict.get("funamachi") is not None else "",
        "mg": str(suii_dict.get("manganji","")) if suii_dict.get("manganji") is not None else "",
    }

print("取得中...")
all_data = {}
for site, fid in RIVER_FILES.items():
    all_data[site] = get_suii_history(fid)
    print(f"  {site}: {len(all_data[site])}件")

times = sorted(all_data["itanami"].keys())[-12:]
rows = []
for t in times:
    suii = {site: all_data[site].get(t) for site in RIVER_FILES}
    rows.append(make_row(t, suii))
    print(f"  {t}: 大島={suii['oshima']} 別所橋={suii['bessho']} 板波={suii['itanami']} 万願寺={suii['manganji']} 船町={suii['funamachi']}")

ok = requests.put(f"{FIREBASE_URL}/kasen.json", json={"rows": rows})
print(f"Firebase書き込み{'成功✅' if ok.status_code==200 else '失敗❌'}")
