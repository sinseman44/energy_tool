import csv
from typing import List, Dict
from .base import EnergySource

class CSVSource(EnergySource):
    """
    Lit un CSV horaire avec colonnes: date,pv_diff,load_diff
    (optionnel: import,export – ignorés ici)
    Fournit les données au format attendu par la simulation
    1 ligne par heure, date au format ISO 8601
    Exemple de ligne:
    2023-01-01T00:00:00+01:00,0.0,0.3
    2023-01-01T01:00:00+01:00,0.0,0.25
    2023-01-01T02:00:00+01:00,0.0,0.2
    2023-01-01T03:00:00+01:00,0.0,0.15
    2023-01-01T04:00:00+01:00,0.0,0.1
    2023-01-01T05:00:00+01:00,0.0,0.1
    2023-01-01T06:00:00+01:00,0.0,0.15
    2023-01-01T07:00:00+01:00,0.0,0.2
    2023-01-01T08:00:00+01:00,0.0,0.3
    2023-01-01T09:00:00+01:00,0.1,0.4
    
    Arguments:
        csv_path: chemin vers le fichier CSV
    Returns:
        Liste de dictionnaires avec clés: date (str), pv (float), load (float
        (import et export sont ignorés)
    """
    def __init__(self, csv_path: str):
        """
        Initialise la source CSV avec le chemin du fichier CSV.
        Arguments:
            csv_path: Chemin vers le fichier CSV.
        Returns:
            None
        Raises:
            None
        """
        self.csv_path = csv_path

    def get_hourly_pv_load(self, 
                           start_iso: str, 
                           end_iso: str,
                           ) -> List[Dict]:
        """ Lit le fichier CSV et retourne les données au format attendu par la simulation.
        Arguments:
            start_iso: Date de début au format ISO 8601 (non utilisée ici).
            end_iso: Date de fin au format ISO 8601 (non utilisée ici).
        Returns:
            Liste de dictionnaires avec clés: date (str), pv (float), load (float).
        Raises:
            None
        """
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
