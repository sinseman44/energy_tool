from typing import List, Dict

class EnergySource:
    """
        Interface: doit fournir des deltas horaires (kWh/h) pour PV et LOAD
        Retour: liste de dicts alignés par 'date' "YYYY-MM-DD HH:MM"
            [{"date": "...", "pv": float, "load": float}, ...]
    """

    def get_hourly_pv_load(self, start_iso: str, end_iso: str) -> List[Dict]:
        raise NotImplementedError