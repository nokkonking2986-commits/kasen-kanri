import requests
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://kasen-kanri-default-rtdb.asia-southeast1.firebasedatabase.app"
DAM_OBSCD = {
    "kawashiro": 3,
    "gongen":    1,
    "heiso":     2,
    "okawase":   4,
    "donto":     5,
    "kojiya":    6,
}
HEADERS = {
    "Referer": "https://www.river.go.jp/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}
JST = timezone(timedelta(hours=9))

def get_dam_value(obs_cd):
    now = datetime.now(JST)
    minute = (now.minute // 10) * 10 - 10
    hour = now.hour
    if minute < 0:
        minute += 60
        hour -= 1
    date_str = now.strftime("%Y%m%d")
    time_str = f"{hour:02d}{minute:02d}"
    file_id = f"22061007{obs_cd:05d}"
    url = f"https://www.river.go.jp/kawabou/file/files/tmlist/dam/{date_str}/{time_str}/{file_id}.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"  取得失敗: {res.status_code}")
        return {}
    ov = res.json().get("obsValue", {})
    return {
        "stg": ov.get("storLvl") if ov.get("storLvlCcd") == 0 else None,
        "in":  ov.get("allSink") if ov.get("allSinkCcd") == 0 else None,
        "out": ov.get("allDisch") if ov.get("allDischCcd") == 0 else None,
        "obsTime": ov.get("obsTime"),
    }

print("ダム諸量取得中...")
all_data = {}
for site, obs_cd in DAM_OBSCD.items():
    all_data[site] = get_dam_value(obs_cd)
    v = all_data[site]
    print(f"  {site}: 貯水位={v.get('stg')} 流入量={v.get('in')} 放流量={v.get('out')}")

ok = requests.put(f"{FIREBASE_URL}/dam_live.json", json=all_data)
print(f"Firebase書き込み{'成功✅' if ok.status_code == 200 else '失敗❌'}")
