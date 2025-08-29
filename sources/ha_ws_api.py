import json, ssl
from datetime import datetime
from websocket import create_connection
from typing import List, Dict
from .base import EnergySource
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None

LOCAL_TZ = ZoneInfo("Europe/Paris") if ZoneInfo else None

def _recv_json(ws): 
    """ 
    """ 
    return json.loads(ws.recv())

def _wait_result(ws, 
                 expect_id,
                 ):
    """ 
    """    
    while True:
        msg = _recv_json(ws)
        if msg.get("type") == "result" and msg.get("id") == expect_id:
            return msg

def _normalize_result(result):
    """
        retourne une liste de points dict depuis recorder/statistics_during_period
    """
    if not result or isinstance(result, int): 
        return []
    if isinstance(result, list):
        blk = result[0] if result else {}
        return blk.get("data", []) if isinstance(blk, dict) else []
    if isinstance(result, dict):
        return next(iter(result.values()), [])
    return []

def _ts_to_iso_min(ts):
    """
        ms epoch -> "YYYY-MM-DD HH:MM"
    """
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        if LOCAL_TZ:
            dt = dt.astimezone(LOCAL_TZ)
        return dt.strftime("%Y-%m-%d %H:%M")
    try:
        # Si HA renvoie déjà un ISO8601 → on parse et on convertit en local
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if LOCAL_TZ:
            dt = dt.astimezone(LOCAL_TZ)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]

def _fetch_change_or_sum(ws, 
                         entity, 
                         start_iso, 
                         end_iso, 
                         req_id, 
                         period="hour",
                         ):
    """
        1) essaie types=['change'] -> kWh sur l'heure
        2) sinon types=['sum'] (cumul) -> on fera diff côté Python
    """
    # 1) CHANGE
    req = {"id": req_id, 
           "type": "recorder/statistics_during_period",
           "start_time": start_iso, 
           "end_time": end_iso,
           "statistic_ids": [entity], 
           "period": period, 
           "types": ["change"]}
    ws.send(json.dumps(req))
    resp = _wait_result(ws, req_id)
    if not resp.get("success"):
        raise RuntimeError(f"WS not success (change): {resp}")
    pts = [p for p in _normalize_result(resp.get("result")) if isinstance(p, dict)]
    if any("change" in p for p in pts):
        return pts, "change"

    # 2) SUM
    req["id"] = req_id + 1000; req["types"] = ["sum"]
    ws.send(json.dumps(req))
    resp = _wait_result(ws, req["id"])
    if not resp.get("success"):
        raise RuntimeError(f"WS not success (sum): {resp}")
    pts = [p for p in _normalize_result(resp.get("result")) if isinstance(p, dict)]
    return pts, "sum"

def _cumul_to_diffs(points, 
                    value_key,
                    ):
    """
        # trie, fait la différence successive (>=0)
    """
    def key_ts(p):
        t = p.get("start")
        if isinstance(t,(int,float)): return int(t)
        try:
            return int(datetime.fromisoformat(str(t).replace("Z","+00:00")).timestamp()*1000)
        except: return 0
    pts = sorted(points, key=key_ts)
    out={}; prev=None
    for p in pts:
        ts = _ts_to_iso_min(p.get("start"))
        v  = float(p.get(value_key) or 0.0)
        diff = 0.0 if prev is None else max(0.0, v - prev)
        out[ts] = diff; prev = v
    return out

def _points_to_changes(points):
    """
        retourne dict { 'YYYY-MM-DD HH:MM': kWh_sur_l_heure }
    """
    if not points:
        return {}
    if "change" in points[0]:
        d = {}
        for p in points:
            ts = _ts_to_iso_min(p.get("start"))
            try:
                d[ts] = max(0.0, float(p.get("change") or 0.0))
            except Exception:
                d[ts] = 0.0
        return d
    return _cumul_to_diffs(points, "sum")

class HAWebSocketSource(EnergySource):
    """

    """
    def __init__(self, 
                 base_url: str, 
                 token: str, 
                 pv_entity: str, 
                 load_entity: str, 
                 ssl_verify: bool = True,
                 ):
        """
            Constructor
        """
        self.base_url = base_url
        self.token = token
        self.pv_entity = pv_entity
        self.load_entity = load_entity
        self.ssl_verify = ssl_verify

    def get_hourly_pv_load(self, 
                           start_iso: str, 
                           end_iso: str,
                           ) -> List[Dict]:
        """
        """
        sslopt = None
        if self.base_url.startswith("wss://"):
            sslopt = {"cert_reqs": ssl.CERT_REQUIRED if self.ssl_verify else ssl.CERT_NONE}

        ws = create_connection(self.base_url, sslopt=sslopt, timeout=15)
        hello = _recv_json(ws)
        if hello.get("type") != "auth_required":
            ws.close(); raise RuntimeError(f"Unexpected hello: {hello}")
        ws.send(json.dumps({"type":"auth","access_token": self.token}))
        auth = _recv_json(ws)
        if auth.get("type") != "auth_ok":
            ws.close(); raise RuntimeError(f"Auth failed: {auth}")

        pv_pts, _   = _fetch_change_or_sum(ws, self.pv_entity,   start_iso, end_iso, req_id=1, period="hour")
        load_pts, _ = _fetch_change_or_sum(ws, self.load_entity, start_iso, end_iso, req_id=2, period="hour")
        ws.close()

        pv_hour   = _points_to_changes(pv_pts)
        load_hour = _points_to_changes(load_pts)
        hours = sorted(set(pv_hour) | set(load_hour))
        return [{"date": h, "pv": float(pv_hour.get(h,0.0)), "load": float(load_hour.get(h,0.0))} for h in hours]
