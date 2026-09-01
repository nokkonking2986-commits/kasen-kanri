import requests
from datetime import datetime, timedelta, timezone

FIREBASE_URL = "https://kasen-kanri-default-rtdb.asia-southeast1.firebasedatabase.app"
OFC_CD = 22061
ITMKND_CD = 1  # 雨量
FORECAST_HORIZON_H = 6  # 将来分は0で埋める時間数(アプリ側のFORECAST_HORIZON_Hと合わせる)
PAGES = 2  # 50時間 x 2 = 約100時間(4日強)分をさかのぼって取得

# (英語キー, 日本語名, obsCd)
# 英語キー: rain_live/rain_history(流域雨量・流域水文図の雨量表示)用
# 日本語名: kwRainRaw(実測雨量ベースの流量予測モデルの入力)用。こちらは従来通り大堰を含まない16観測所。
# obsCdは旧fetch_rain.py(RAIN_OBSCD)と旧fetch_kawabou.py(KAWABOU_STATIONS)で完全一致することを確認済み。
STATIONS = [
    ("aogaki",    "青垣",   10),
    ("hikami",    "氷上",    1),
    ("kaibara",   "柏原",   11),
    ("funamachi", "船町",    3),
    ("sugihara",  "杉原",   22),
    ("yachiyo",   "八千代", 13),
    ("itanami",   "板波",   15),
    ("tenjin",    "天神",    6),
    ("hojo",      "北条",    9),
    ("ono",       "小野",    7),
    ("yoshikawa", "吉川",   23),
    ("hosokawa",  "細川",   14),
    ("taniue",    "谷上",   24),
    ("fukuzumi",  "福住",   12),
    ("hiuchi",    "火打岩",  2),
    ("konda",     "今田",    5),
    ("oze",       "大堰(加古川)", 17),
]

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.river.go.jp/kawabou/pcfull/tm?itmkndCd=1&ofcCd=22061&obsCd=15&isCurrent=true&fld=0",
}
JST = timezone(timedelta(hours=9))


def obs_fcd(obs_cd):
    return f"{OFC_CD:05d}{ITMKND_CD:03d}{obs_cd:05d}"


def fetch_json(obs_cd, app_time):
    # river.go.jpは10分値ファイルの公開が数分遅れることがあるため、
    # 丸めた時刻からさらに10分引いて、確実に公開済みのファイルを参照する
    # (旧fetch_rain.pyと同じ調整。cron-job.orgでぴったり実行するようになった際、
    # この調整が無いと全観測所404でクラッシュすることを確認済み)。
    app_time = app_time.replace(minute=(app_time.minute // 10) * 10, second=0, microsecond=0) - timedelta(minutes=10)
    fcd = obs_fcd(obs_cd)
    date_str = app_time.strftime("%Y%m%d")
    time_str = app_time.strftime("%H%M")
    url = f"https://www.river.go.jp/kawabou/file/files/tmlist/rn/{date_str}/{time_str}/{fcd}.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"  取得失敗: {res.status_code}")
        return None
    return res.json()


def hourly_from_json(data):
    result = {}
    for v in (data or {}).get("hrValues", []):
        dt = datetime.strptime(v["obsTime"], "%Y/%m/%d %H:%M")
        result[dt] = v.get("rnHr") or 0
    return result


def fetch_station_series(obs_cd, now):
    """時間雨量の履歴(kwRainRaw用)をPAGES回さかのぼって取得しつつ、
    1回目(=最新)の生レスポンスも合わせて返す(rain_live/rain_history用、旧fetch_rain.py分)。"""
    merged = {}
    latest_json = None
    app_time = now
    for i in range(PAGES):
        data = fetch_json(obs_cd, app_time)
        if i == 0:
            latest_json = data
        page = hourly_from_json(data)
        merged.update(page)
        if not page:
            break
        app_time = min(page.keys()) - timedelta(hours=1)
    return merged, latest_json


print("kawabou実測雨量取得中...")
now = datetime.now(JST).replace(tzinfo=None)
now_hour = now.replace(minute=0, second=0, microsecond=0)

per_station_hourly = {}
all_hours = set()
rain_live = {}
for key, name, obs_cd in STATIONS:
    hourly, latest_json = fetch_station_series(obs_cd, now)
    per_station_hourly[name] = hourly
    all_hours.update(hourly.keys())
    nonzero = sorted([(t, v) for t, v in hourly.items() if v], key=lambda x: x[0])[-1:]
    print(f"  {name}: 直近非ゼロ={nonzero if nonzero else 'なし'}")

    ov = (latest_json or {}).get("obsValue", {})
    rain_live[key] = {
        "rnInc": ov.get("rnInc") if ov.get("rnIncCcd") == 0 else None,
        "rnHr":  ov.get("rnHr")  if ov.get("rnHrCcd")  == 0 else None,
        "rn10m": ov.get("rn10m") if ov.get("rn10mCcd") == 0 else None,
        "obsTime": ov.get("obsTime"),
    }

# ===== kwRainRaw(時間雨量の実測履歴、実測雨量ベースの流量予測モデル入力用)=====
if not all_hours:
    print("全観測所で取得失敗のため、今回はkwRainRaw/rain_liveへの書き込みをスキップします。")
    raise SystemExit(1)
start_hour = min(all_hours)
n_past = int((now_hour - start_hour).total_seconds() // 3600) + 1
times = [start_hour + timedelta(hours=i) for i in range(n_past)]
times += [now_hour + timedelta(hours=i) for i in range(1, FORECAST_HORIZON_H + 1)]
time_labels = [t.strftime("%Y-%m-%dT%H:00") for t in times]

stations = {}
for key, name, obs_cd in STATIONS:
    if key == "oze":
        continue  # kwRainRaw(流量予測)は従来通り大堰を含まない16観測所のみ
    hourly = per_station_hourly[name]
    precip = [round(hourly.get(t, 0), 1) if t <= now_hour else 0 for t in times]
    stations[name] = {"time": time_labels, "precip": precip}

kw_payload = {"取得時刻": now.strftime("%Y-%m-%dT%H:%M"), "stations": stations}

ok1 = requests.put(f"{FIREBASE_URL}/kwRainRaw.json", json=kw_payload)
ok2 = requests.post(f"{FIREBASE_URL}/kwRainLog.json", json=kw_payload)
print(f"Firebase書き込み(kwRainRaw){'成功✅' if ok1.status_code == 200 else '失敗❌'}")
print(f"Firebase書き込み(kwRainLog){'成功✅' if ok2.status_code == 200 else '失敗❌'}")

# ===== rain_live/rain_history(流域雨量・流域水文図の雨量表示用、旧fetch_rain.py分を統合)=====
ok3 = requests.put(f"{FIREBASE_URL}/rain_live.json", json=rain_live)
print(f"Firebase書き込み(rain_live){'成功✅' if ok3.status_code == 200 else '失敗❌'}")

history_key = now.strftime("%Y%m%d%H%M")
history_entry = {k: {"rnHr": v.get("rnHr"), "rn10m": v.get("rn10m"), "rnInc": v.get("rnInc")} for k, v in rain_live.items()}
history_entry["_time"] = now.strftime("%Y-%m-%d %H:%M")
ok4 = requests.put(f"{FIREBASE_URL}/rain_history/{history_key}.json", json=history_entry)
print(f"Firebase書き込み(rain_history/{history_key}){'成功✅' if ok4.status_code == 200 else '失敗❌'}")
