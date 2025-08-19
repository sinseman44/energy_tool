from typing import List, Dict
from .base import EnergySource

class EnlightenSource(EnergySource):
    """
        TODO:
            - Appels API v4 (production et éventuellement consumption si dispo chez toi)
            - Agrégation heure par heure sur [start,end]
        Retour: [{"date":"YYYY-MM-DD HH:MM","pv":kWh,"load":kWh}, ...]
    """
    def __init__(self, api_key: str, user_id: str, system_id: str, site_id: str | None = None):
        self.api_key = api_key
        self.user_id = user_id
        self.system_id = system_id
        self.site_id = site_id

    def get_hourly_pv_load(self, start_iso: str, end_iso: str) -> List[Dict]:
        # TODO:
        # 1) appeler /systems/{system_id}/energy_lifetime ou /energy_day ? (selon dispo)
        # 2) reconstituer une série horaire en kWh/h
        # 3) pour 'load', si l’API ne fournit pas: soit 0, soit lecture d’un autre endpoint (Envoy metering), soit retour None
        raise NotImplementedError("EnlightenSource to be implemented")
