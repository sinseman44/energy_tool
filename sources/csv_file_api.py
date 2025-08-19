import csv
from typing import List, Dict
from .base import EnergySource

class CSVSource(EnergySource):
    """
        Lit un CSV horaire avec colonnes: date,pv_diff,load_diff
        (optionnel: import,export – ignorés ici)
    """
    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def get_hourly_pv_load(self, start_iso: str, end_iso: str) -> List[Dict]:
        rows=[]
        with open(self.csv_path) as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                rows.append({
                    "date": r["date"],
                    "pv": float(r.get("pv_diff", 0.0)),
                    "load": float(r.get("load_diff", 0.0)),
                })
        return rows
