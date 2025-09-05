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

def _recv_json(ws: any) -> dict: 
    """
    Lit un message JSON depuis le WS et le décode.
    Args:
        ws: WebSocket connecté
    Raises:
        Exception: en cas d'erreur de réception ou de décodage
    Returns:
        dict: message JSON décodé
    """ 
    return json.loads(ws.recv())

def _wait_result(ws: any, 
                 expect_id: int,
                 ) -> dict:
    """
    Attend un message de type 'result' avec l'ID attendu.
    Args:
        ws: WebSocket connecté
        expect_id: ID attendu dans le message 'result'
    Raises:
        Exception: en cas d'erreur de réception ou de décodage
    Returns:
        dict: message JSON décodé de type 'result' avec l'ID attendu
    """    
    while True:
        msg = _recv_json(ws)
        if msg.get("type") == "result" and msg.get("id") == expect_id:
            return msg

def _normalize_result(result: any) -> list:
    """
    retourne une liste de points dict depuis recorder/statistics_during_period
    Args:
        result: résultat brut du WS
    Returns:
        list: liste de points dict
    """
    if not result or isinstance(result, int): 
        return []
    if isinstance(result, list):
        blk = result[0] if result else {}
        return blk.get("data", []) if isinstance(blk, dict) else []
    if isinstance(result, dict):
        return next(iter(result.values()), [])
    return []

def _ts_to_iso_min(ts: any) -> str:
    """
        Convertit un timestamp (ms ou ISO) en "YYYY-MM-DD HH:MM" locale
    Args:
        ts (int|float|str): timestamp en ms ou chaîne ISO
    Returns:
        str: date/heure formatée "YYYY-MM-DD HH:MM"
    Raises:
        None
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

def _fetch_change_or_sum(ws: any, 
                         entity: str, 
                         start_iso: str, 
                         end_iso: str, 
                         req_id: int = 1, 
                         period: str = "hour",
                         ) -> tuple[list, str]:
    """
    Tente de récupérer les points horaires en 'change' (delta) ou 'sum' (cumul)
    depuis recorder/statistics_during_period.

    Args:
        ws: WebSocket connecté
        entity (str): entity_id de la statistique HA
        start_iso (str): date/heure ISO début (inclus)  "YYYY-MM-DDTHH:MM:SS"
        end_iso (str): date/heure ISO fin (exclus)      "YYYY-MM-DDTHH:MM:SS"
        req_id (int): ID de la requête WS
        period (str): période de l'agrégation ("hour", "day", ...)
    Raises:
        RuntimeError: si la requête WS échoue
    Returns:
        tuple: (list des points dict, "change"|"sum")
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

def _cumul_to_diffs(points: list, 
                    value_key: str,
                    ) -> dict:
    """
        Convertit une liste de points cumulés en deltas horaires.
        Retourne dict { 'YYYY-MM-DD HH:MM': kWh_sur_l_heure }
    Args:
        points (list): liste de points dict avec 'start' et value_key
        value_key (str): clé du cumul dans les points ("sum", "total", ...)
    Returns:
        dict: dict des deltas horaires
    Raises:
        None
    """
    def key_ts(p: dict) -> int:
        """ 
        clé de tri par timestamp
        Args:
            p (dict): point avec 'start'
        Returns:
            int: timestamp en ms
        Raises:
            None
        """
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

def _points_to_changes(points: list) -> dict:
    """
    Convertit une liste de points dict en deltas horaires.
    Si les points ont une clé 'change', on l'utilise. Sinon on convertit les 'sum' en deltas.
    Retourne dict { 'YYYY-MM-DD HH:MM': kWh_sur_l_heure }
    Args:
        points (list): liste de points dict avec 'start' et 'change' ou 'sum'
    Returns:
        dict: dict des deltas horaires
    Raises:
        None
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
        Source de données PV/LOAD depuis Home Assistant via WebSocket API.
        Args:
            base_url (str): URL du WS (ws:// ou wss://)
            token (str): token d'accès long-lived
            pv_entity (str): entity_id de la statistique PV
            load_entity (str): entity_id de la statistique LOAD
            ssl_verify (bool): si True, vérifie le certificat SSL (défaut: True)
        Raises:
            RuntimeError: en cas d'erreur de connexion ou d'authentification
        Returns: 
            None
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
        Args:
            base_url (str): URL du WS (ws:// ou wss://)
            token (str): token d'accès long-lived
            pv_entity (str): entity_id de la statistique PV
            load_entity (str): entity_id de la statistique LOAD
            ssl_verify (bool): si True, vérifie le certificat SSL (défaut: True)
        Raises:
            None
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
        Fournit des deltas horaires (kWh/h) pour PV et LOAD
        Retour: liste de dicts alignés par 'date' "YYYY-MM-DD HH:MM"
            [{"date": "...", "pv": float, "load": float}, ...]
        Args:
            start_iso (str): date/heure ISO début (inclus)  "YYYY-MM-DDTHH:MM:SS"
            end_iso (str): date/heure ISO fin (exclus)      "YYYY-MM-DDTHH:MM:SS"
        Raises:
            RuntimeError: en cas d'erreur de connexion ou d'authentification
        Returns: 
            List[Dict]: liste des données horaires
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
        return [{"date": h,
                 "pv": float(pv_hour.get(h,0.0)),
                 "load": float(load_hour.get(h,0.0))} for h in hours]
