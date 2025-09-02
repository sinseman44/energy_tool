from typing import List, Dict

class EnergySource:
    """
    Interface: doit fournir des deltas horaires (kWh/h) pour PV et LOAD
    Retour: liste de dicts alignés par 'date' "YYYY-MM-DD HH:MM"
        [{"date": "...", "pv": float, "load": float}, ...]
    Args:
        start_iso (str): date/heure ISO début (inclus)  "YYYY-MM-DDTHH:MM:SS"
        end_iso (str): date/heure ISO fin (exclus)      "YYYY-MM-DDTHH:MM:SS"
    Raises:
        NotImplementedError: si la méthode n'est pas implémentée
    Returns: 
        List[Dict]: liste des données horaires
    """

    def get_hourly_pv_load(self, start_iso: str, end_iso: str) -> List[Dict]:
        """ 
        Doit être implémentée dans les sous-classes. 
        """
        raise NotImplementedError