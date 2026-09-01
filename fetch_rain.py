import requests
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://kasen-kanri-default-rtdb.asia-southeast1.firebasedatabase.app"
RAIN_OBSCD = {
    "aogaki":   10,  # 青垣
    "sugihara": 22,  # 杉原
    "hikami":    1,  # 氷上
    "kaibara":  11,  # 柏原
    "fukuzumi": 12,  # 福住
    "hiuchi":    2,  # 火打岩
    "funamachi": 3,  # 船町
    "konda":     5,  # 今田
    "itanami":  15,  # 板波
    "tenjin":    6,  # 天神
    "yoshikawa":23,  # 吉川
    "taniue":   24,  # 谷上
    "hojo":      9,  # 北条
    "yachiyo":  13,  # 八千代
    "ono":       7,  # 小野
    "hosokawa": 14,  # 細川
    "oze":      17,  # 大堰(加古川)
}
HEADERS = {
    "Referer": "https://www.river.go.jp/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}
JST = timezone(timedelta(hours=9))

def get_rain_value(obs_cd):
    now = datetime.now(JST)
    minute = (now.minute // 10) * 10 - 10
    hour = now.hour
    if minute < 0:
        minute += 60
        hour -= 1
    date_str = now.strftime("%Y%m%d")
    time_str = f"{hour:02d}{minute:02d}"
    file_id = f"22061001{obs_cd:05d}"
    url = f"https://www.river.go.jp/kawabou/file/files/tmlist/rn/{date_str}/{time_str}/{file_id}.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"  取得失敗: {res.status_code}")
        return {}
    ov = res.json().get("obsValue", {})
    return {
        "rnInc": ov.get("rnInc") if ov.get("rnIncCcd") == 0 else None,
        "rnHr":  ov.get("rnHr")  if ov.get("rnHrCcd")  == 0 else None,
        "rn10m": ov.get("rn10m") if ov.get("rn10mCcd") == 0 else None,
        "obsTime": ov.get("obsTime"),
    }

print("雨量取得中...")
all_data = {}
for site, obs_cd in RAIN_OBSCD.items():
    all_data[site] = get_rain_value(obs_cd)
    v = all_data[site]
    print(f"  {site}: 累計={v.get('rnInc')} 時間={v.get('rnHr')} 10分={v.get('rn10m')}")

ok = requests.put(f"{FIREBASE_URL}/rain_live.json", json=all_data)
print(f"Firebase書き込み(rain_live){'成功✅' if ok.status_code == 200 else '失敗❌'}")

# 「流域雨量」表用に、実行のたびに10分刻みの履歴として時刻キーで積み上げ保存する
# (rain_liveは最新値の上書きのみなので、これとは別に履歴を残す)。
now = datetime.now(JST)
history_key = now.strftime("%Y%m%d%H%M")
history_entry = {site: {"rnHr": v.get("rnHr"), "rn10m": v.get("rn10m")} for site, v in all_data.items()}
history_entry["_time"] = now.strftime("%Y-%m-%d %H:%M")
ok2 = requests.put(f"{FIREBASE_URL}/rain_history/{history_key}.json", json=history_entry)
print(f"Firebase書き込み(rain_history/{history_key}){'成功✅' if ok2.status_code == 200 else '失敗❌'}")
