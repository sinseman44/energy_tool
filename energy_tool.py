#!/usr/bin/env python3
import json, os, sys, ssl, csv, argparse
from pathlib import Path
import csv
from pprint import pprint
from sources.ha_ws_api import HAWebSocketSource
from sources.csv_file_api import CSVSource
from sources.enlighten_api import EnlightenSource  # prêt pour plus tard

from cli_output import ConsoleUI
from collections import defaultdict
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None

LOCAL_TZ = ZoneInfo("Europe/Paris") if ZoneInfo else None

# =========================
# CONFIG LOADER (JSON)
# =========================
DEFAULTS = {
    "OUT_CSV_DETAIL":               "ha_energy_import_export_hourly.csv",
    "OUT_CSV_DAILY":                "ha_energy_import_export_daily.csv",
    "OUT_CSV_SIMU":                 "ha_energy_simulation_combos.csv",
    "TARGET_AC_MIN":                85.0, # %
    "TARGET_AC_MAX":                100.0, # 100 = pas de plafond
    "TARGET_TC_MIN":                80.0, # %
    "BATTERY_SIZES":                [0,5,10,12,14,16,18,20,22,24,26,28,30], # kWh
    "PV_FACTORS":                   [1.0,1.2,1.5,1.8,2.0,2.2,2.4,2.6,3.0], # 1.0 = actuel
    "BATTERY_EFF":                  0.90, # 90%
    "PV_ACTUAL_KW":                 4.0, # kWc installé
    "INITIAL_SOC":                  0.90, # 90%
    "BATT_MIN_SOC":                 0.10, # 10 = 100% (jamais décharger)
    "MAX_DISCHARGE_KW_PER_HOUR":    4.0, # kW max décharge batterie
    "ALLOW_DISCHARGE_IN_HC":        True, # autoriser la décharge en HC
    "GRID_CHARGE_IN_HC":            False, # autoriser la recharge en HC
    "GRID_HOURS":                   [0,1,2,3,4,5,22,23], # heures creuses
    "GRID_TARGET_SOC":              0.8, # 80% (0.0 → 0%, 1.0 → 100%)
    "GRID_CHARGE_LIMIT":            3.0, # kW max charge réseau en HC
}

ui = ConsoleUI()

def save_sim_detail(csv_path: str, 
                    sim_rows: list, 
                    date_key: str = "date", 
                    context: dict = None,
                    ) -> None:
    """
    Écrit un CSV horaire détaillé pour un scénario unique.
    `sim_rows` est la liste de dicts renvoyée par `simulate_battery(...)`,
    chaque élément devant contenir au minimum :
        date, pv, load, pv_direct, pv_to_batt, batt_to_load, grid_to_batt, import, export, soc, context
    où :
        context: ex. {
            "pv_factor": 2.4,
            "batt_kwh": 24,
            "eff": 0.90,
            "initial_soc": 0.5,   # 50% (ou 50 si tu préfères)
            "pv_kwc": 4.0,
            "scenario": "PV x2.4, Batt 24 kWh"
        }
        - date peut être str ("YYYY-MM-DD HH:MM") ou datetime -> converti en ISO minutes
        - les valeurs sont arrondies proprement
        - les champs meta sont répétés sur chaque ligne

    Args:
        csv_path (str): chemin du fichier CSV de sortie
        sim_rows (list): liste des lignes horaires simulées
        date_key (str, optional): clé pour la date dans chaque ligne. Defaults to "date".
        context (dict, optional): contexte à ajouter en méta. Defaults to None.

    Returns:
        None

    Raises:
        IOError: en cas de problème d'écriture du fichier
    """
    fields = [
        "date",
        "pv",
        "load",
        "pv_direct",
        "pv_to_batt",
        "batt_to_load",
        "grid_to_batt",
        "imp_to_load",
        "import",
        "export",
        "soc"
    ]

    meta_fields = ["pv_factor","batt_kwh","eff","initial_soc","pv_kwc","scenario"]
    all_fields = fields + meta_fields
    
    def _fmt_date(dt):
        """ Formatte une date en ISO "YYYY-MM-DD HH:MM"

        Args:
            dt (str|datetime): date à formater
        Returns:
            str: date formatée
        Raises:
            ValueError: si la date n'est pas au format attendu
        """
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M")
        s = str(dt)
        # normalise un ISO avec 'T' et secondes -> 'YYYY-MM-DD HH:MM'
        if "T" in s:
            try:
                return datetime.fromisoformat(s.replace("Z","")).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        return s[:16]  # tronque prudemment

    ctx = context or {}

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_fields)
        w.writeheader()
        for r in sim_rows:
            row = {
                "date": _fmt_date(r.get(date_key)),
                "pv": round(float(r.get("pv", 0.0)), 6),
                "load": round(float(r.get("load", 0.0)), 6),
                "pv_direct": round(float(r.get("pv_direct", 0.0)), 6),
                "pv_to_batt": round(float(r.get("pv_to_batt", 0.0)), 6),
                "batt_to_load": round(float(r.get("batt_to_load", 0.0)), 6),
                "grid_to_batt": round(float(r.get("imp_grid", 0.0)), 6),
                "imp_to_load": round(float(r.get("imp_load", 0.0)), 6),
                "import": round(float(r.get("import", 0.0)), 6),
                "export": round(float(r.get("export", 0.0)), 6),
                # `soc` accepté en kWh ou %, on écrit ce que la simu fournit
                "soc": round(float(r.get("soc", 0.0)), 6),
                # meta (répétées)
                "pv_factor": ctx.get("pv_factor"),
                "batt_kwh": ctx.get("batt_kwh"),
                "eff": ctx.get("eff"),
                "initial_soc": ctx.get("initial_soc"),
                "pv_kwc": ctx.get("pv_kwc"),
                "scenario": ctx.get("scenario"),
            }
            w.writerow(row)

def to_utc_iso(s: str, 
               tz_name: str = "Europe/Paris",
               ) -> str:
    """
    Convertit une date fournie en LOCAL (sans offset) ou déjà tz-aware en ISO UTC.
        - Ex: "2025-06-01T00:00:00" (local) -> "2025-05-31T22:00:00Z" en été
        - Ex: "2025-06-01T00:00:00+02:00" -> converti en Z
        - Ex: "2025-06-01T00:00:00Z" -> inchangé
        - Ex: "2025-06-01 00:00" -> "2025-05-31T22:00:00Z" en été
        - Ex: "" -> ""
        - Ex: None -> None
    Args:
        s (str): date en ISO locale ou tz-aware
        tz_name (str, optional): nom de la timezone locale si `s` est naïf. Defaults to "Europe/Paris".
    Returns:
        str: date en ISO UTC (avec 'Z'), ou chaîne vide si entrée vide
    Raises:
        RuntimeError: si `s` est naïf et zoneinfo indisponible
    """
    s = (s or "").strip()
    if not s:
        return s
    if s.endswith("Z") or "+" in s[10:]:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        # timestamp naïf → on le considère en heure locale
        if not ZoneInfo:
            raise RuntimeError("zoneinfo indisponible : installe Python ≥ 3.9")
        dt = datetime.fromisoformat(s)
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.isoformat().replace("+00:00", "Z")

def aggregate_daily(sim_rows:list) -> dict:
    """
    Agrège les résultats horaires en journalier.
    Renvoie un dict { "YYYY-MM-DD": {pv, load, imp, exp, pv_direct, batt_to_load, pv_to_batt} }

    Args:
        sim_rows (list): liste des lignes horaires simulées
    Returns:
        dict: agrégation journalière
    """
    day = defaultdict(lambda: {"pv":0.0,
                                "load":0.0,
                                "imp":0.0,
                                "exp":0.0,
                                "pv_direct":0.0,
                                "batt_to_load":0.0,
                                "pv_to_batt":0.0})
    for r in sim_rows:
        d = str(r["date"])[:10]
        day[d]["pv"]           += r["pv"]
        day[d]["load"]         += r["load"]
        day[d]["imp"]          += r["import"]
        day[d]["exp"]          += r["export"]
        day[d]["pv_direct"]    += r.get("pv_direct", 0.0)
        day[d]["batt_to_load"] += r.get("batt_to_load", 0.0)
        day[d]["pv_to_batt"]   += r.get("pv_to_batt", 0.0)
    return dict(sorted(day.items()))

def _as_float(x:any, name:str) -> float:
    """ 
    Coercition d'un float

    Args:
        x (any): valeur à convertir
        name (str): nom du paramètre (pour message d'erreur)
    Returns:
        float: valeur convertie en float
    Raises:
        ValueError: si x ne peut être converti en float
    """
    try: return float(x)
    except: raise ValueError(f"Paramètre '{name}' doit être un nombre (float), reçu: {x!r}")

def _as_list_float(x:list, 
                   name:str,
                   ) -> list:
    """
    Coercition d'une liste de float

    Args:
        x (list): _description_
        name (str): nom du paramètre (pour message d'erreur)
    Returns:
        list: liste de float
    Raises:
        ValueError: si x n'est pas une liste ou si un élément ne peut être converti en float
    """
    if not isinstance(x, list):
        raise ValueError(f"Paramètre '{name}' doit être une liste de nombres")
    return [float(v) for v in x]

def load_config(path: Path) -> dict:
    """ 
    Charge la configuration JSON, applique les valeurs par défaut et vérifie les champs obligatoires.

    Args:
        path (Path): chemin vers le fichier JSON
    Raises:
        ValueError: si des champs obligatoires sont manquants ou mal formés
    Returns:
        dict: configuration complète
    """
    
    if not path.exists():
        print(f"[ERREUR] Fichier de config introuvable: {path.resolve()}")
        sys.exit(1)
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))

    # Obligatoires
    required = ["BASE_URL","TOKEN","PV_ENTITY","LOAD_ENTITY","START","END"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(f"[ERREUR] Clés manquantes dans la config: {', '.join(missing)}")
        sys.exit(1)

    # Valeurs par défaut
    for k,v in DEFAULTS.items():
        cfg[k] = cfg.get(k, v)

    # Coercition types
    cfg["TARGET_AC_MIN"] = _as_float(cfg["TARGET_AC_MIN"], "TARGET_AC_MIN")
    cfg["TARGET_AC_MAX"] = _as_float(cfg["TARGET_AC_MAX"], "TARGET_AC_MAX")
    cfg["TARGET_TC_MIN"] = _as_float(cfg["TARGET_TC_MIN"], "TARGET_TC_MIN")
    cfg["BATTERY_EFF"]   = _as_float(cfg["BATTERY_EFF"],   "BATTERY_EFF")
    cfg["PV_ACTUAL_KW"]  = _as_float(cfg["PV_ACTUAL_KW"],  "PV_ACTUAL_KW")
    cfg["BATTERY_SIZES"] = sorted({v for v in _as_list_float(cfg["BATTERY_SIZES"], "BATTERY_SIZES") if v >= 0})
    cfg["PV_FACTORS"]    = sorted({v for v in _as_list_float(cfg["PV_FACTORS"], "PV_FACTORS") if v > 0})

    return cfg


def make_source(cfg: dict,
                args: argparse.Namespace = None,
               ) -> object:
    """ 
    sources de données suivant l'argument passé en paramètre.

    Args:
        cfg (dict): configuration chargée via `load_config()`
        args (argparse.Namespace, optional): paramètres passés au script. Defaults to None.
    Raises:
        ValueError: si la source est inconnue
    Returns:
        object: instance de la source de données
    """
    if args.source == "ha_ws":
        return HAWebSocketSource(
            base_url=cfg["BASE_URL"],
            token=cfg["TOKEN"],
            pv_entity=cfg["PV_ENTITY"],
            load_entity=cfg["LOAD_ENTITY"],
            ssl_verify=cfg.get("SSL_VERIFY", False)
        )
    elif args.source == "csv":
        return CSVSource(cfg["IN_CSV"])  # ajoutes "IN_CSV" dans ton JSON si tu veux
    elif args.source == "enlighten":
        return EnlightenSource(
            api_key=cfg["ENPHASE_API_KEY"],
            user_id=cfg["ENPHASE_USER_ID"],
            system_id=cfg["ENPHASE_SYSTEM_ID"],
            site_id=cfg.get("ENPHASE_SITE_ID")
        )
    else:
        raise ValueError(f"Source inconnue: {args.source}")

# =========================
# REPORT MODE
# =========================
def run_report(cfg: dict,
               args: argparse.Namespace = None,
               ) -> None:
    """ 
    Lancement du rapport d'import/export/autoconsommation.
        1) collecte via source
        2) calcul import/export/autoconsommation
        3) écriture CSV horaire
        4) écriture CSV journalier
        5) affichage résumé

    Args:
        cfg (dict): configuration chargée
        args (argparse.Namespace, optional): paramètres passés au script. Defaults to None.
    Returns:
        None
    Raises:
        RuntimeError: en cas d'erreur critique
    """
    if args is None:
        args = argparse.Namespace()
        args.source = "ha_ws"
    if not args.source:
        args.source = "ha_ws"
    if args.source not in ("ha_ws","csv","enlighten"):
        raise ValueError(f"Source inconnue: {args.source}")
    if args.source == "csv" and not cfg.get("IN_CSV"):
        raise ValueError("Pour la source 'csv', le paramètre 'IN_CSV' doit être fourni dans la config")
    if args.source == "enlighten":
        for k in ("ENPHASE_API_KEY","ENPHASE_USER_ID","ENPHASE_SYSTEM_ID"):
            if not cfg.get(k):
                raise ValueError(f"Pour la source 'enlighten', le paramètre '{k}' doit être fourni dans la config")
    if not cfg.get("OUT_CSV_DETAIL"):
        raise ValueError("Le paramètre 'OUT_CSV_DETAIL' doit être fourni dans la config")
    if not cfg.get("OUT_CSV_DAILY"):
        raise ValueError("Le paramètre 'OUT_CSV_DAILY' doit être fourni dans la config")
    if not cfg.get("START") or not cfg.get("END"):
        raise ValueError("Les paramètres 'START' et 'END' doivent être fournis dans la config")
    if not cfg.get("PV_ACTUAL_KW"):
        raise ValueError("Le paramètre 'PV_ACTUAL_KW' doit être fourni dans la config")
    if cfg["PV_ACTUAL_KW"] <= 0:
        raise ValueError("Le paramètre 'PV_ACTUAL_KW' doit être > 0")
    if cfg["TARGET_AC_MIN"] < 0 or cfg["TARGET_AC_MIN"] > 100:
        raise ValueError("Le paramètre 'TARGET_AC_MIN' doit être dans [0,100]")
    if cfg["TARGET_AC_MAX"] < 0 or cfg["TARGET_AC_MAX"] > 100:
        raise ValueError("Le paramètre 'TARGET_AC_MAX' doit être dans [0,100]")
    if cfg["TARGET_AC_MIN"] > cfg["TARGET_AC_MAX"]:
        raise ValueError("Le paramètre 'TARGET_AC_MIN' doit être ≤ 'TARGET_AC_MAX'")
    if cfg["TARGET_TC_MIN"] < 0 or cfg["TARGET_TC_MIN"] > 100:
        raise ValueError("Le paramètre 'TARGET_TC_MIN' doit être dans [0,100]")
    if cfg["BATTERY_EFF"] <= 0 or cfg["BATTERY_EFF"] > 1:
        raise ValueError("Le paramètre 'BATTERY_EFF' doit être dans (0,1]")
    if not cfg["BATTERY_SIZES"]:
        raise ValueError("Le paramètre 'BATTERY_SIZES' doit contenir au moins une valeur")
    if not cfg["PV_FACTORS"]:
        raise ValueError("Le paramètre 'PV_FACTORS' doit contenir au moins une valeur")
    if cfg["INITIAL_SOC"] < 0 or cfg["INITIAL_SOC"] > 1:
        raise ValueError("Le paramètre 'INITIAL_SOC' doit être dans [0,1]")
    if cfg["BATT_MIN_SOC"] < 0 or cfg["BATT_MIN_SOC"] > 1:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être dans [0,1]")
    if cfg["BATT_MIN_SOC"] >= 1.0:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être < 1.0")
    if cfg["BATT_MIN_SOC"] >= cfg["INITIAL_SOC"]:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être < 'INITIAL_SOC'")
    if cfg["MAX_DISCHARGE_KW_PER_HOUR"] <= 0:
        raise ValueError("Le paramètre 'MAX_DISCHARGE_KW_PER_HOUR' doit être > 0")
    if not isinstance(cfg["ALLOW_DISCHARGE_IN_HC"], bool):
        raise ValueError("Le paramètre 'ALLOW_DISCHARGE_IN_HC' doit être booléen (true/false)")
    if not isinstance(cfg["GRID_CHARGE_IN_HC"], bool):  
        raise ValueError("Le paramètre 'GRID_CHARGE_IN_HC' doit être booléen (true/false)")
    if not isinstance(cfg["GRID_HOURS"], list) or not all(isinstance(h,int) and 0<=h<=23 for h in cfg["GRID_HOURS"]):
        raise ValueError("Le paramètre 'GRID_HOURS' doit être une liste d'entiers entre 0 et 23")
    if cfg["GRID_TARGET_SOC"] < 0 or cfg["GRID_TARGET_SOC"] > 1:
        raise ValueError("Le paramètre 'GRID_TARGET_SOC' doit être dans [0,1]")
    if cfg["GRID_CHARGE_LIMIT"] <= 0:
        raise ValueError("Le paramètre 'GRID_CHARGE_LIMIT' doit être > 0")
    if cfg["GRID_TARGET_SOC"] <= cfg["BATT_MIN_SOC"]:
        raise ValueError("Le paramètre 'GRID_TARGET_SOC' doit être > 'BATT_MIN_SOC'")
    if cfg["GRID_CHARGE_IN_HC"] and not cfg["GRID_HOURS"]:
        raise ValueError("Si 'GRID_CHARGE_IN_HC' est true, 'GRID_HOURS' doit contenir au moins une heure")
    if cfg["GRID_CHARGE_IN_HC"] and cfg["GRID_TARGET_SOC"] <= cfg["INITIAL_SOC"]:
        raise ValueError("Si 'GRID_CHARGE_IN_HC' est true, 'GRID_TARGET_SOC' doit être > 'INITIAL_SOC'")
    if not LOCAL_TZ and (not args.source or args.source == "ha_ws"):
        raise RuntimeError("zoneinfo indisponible : installe Python ≥ 3.9")
    if args.source == "ha_ws" and not cfg.get("SSL_VERIFY", False):
        ssl._create_default_https_context = ssl._create_unverified_context
        #ui.warning("La vérification SSL est désactivée (SSL_VERIFY=false)")

    # Paramètres courants
    START = cfg["START"]
    END = cfg["END"]
    OUT_CSV_DETAIL = cfg["OUT_CSV_DETAIL"]
    OUT_CSV_DAILY = cfg["OUT_CSV_DAILY"]
    PV_ACTUAL_KW = cfg["PV_ACTUAL_KW"]

    # 1) collecte via source
    src = make_source(cfg, args)
    tz_name = cfg.get("TZ_NAME", "Europe/Paris")
    start_utc = to_utc_iso(cfg["START"], tz_name)
    end_utc   = to_utc_iso(cfg["END"],   tz_name)
    series = src.get_hourly_pv_load(start_utc, end_utc)

    #all_hours = sorted(set(pv_hour) | set(load_hour))
    rows = []
    for h in series:
        pv, ld = h["pv"], h["load"]
        self_used = min(pv, ld)
        export = max(0.0, pv - self_used)
        imp    = max(0.0, ld - self_used)
        rows.append({"date": h["date"],
                     "pv_diff": pv,
                     "load_diff": ld,
                     "import": imp,
                     "export": export})

    # CSV horaire
    with open(OUT_CSV_DETAIL, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","pv_diff","load_diff","import","export"])
        w.writeheader(); w.writerows(rows)

    # CSV journalier
    daily = {}
    for r in rows:
        d = r["date"][:10]
        if d not in daily:
            daily[d] = {"pv":0.0,"load":0.0,"imp":0.0,"exp":0.0}
        daily[d]["pv"]   += r["pv_diff"]
        daily[d]["load"] += r["load_diff"]
        daily[d]["imp"]  += r["import"]
        daily[d]["exp"]  += r["export"]

    with open(OUT_CSV_DAILY, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date","pv_day_kWh","load_day_kWh","import_kWh","export_kWh","balance_kWh"])
        for d in sorted(daily):
            pv   = daily[d]["pv"]; load = daily[d]["load"]
            imp  = daily[d]["imp"]; exp  = daily[d]["exp"]
            w.writerow([d, round(pv,3), round(load,3), round(imp,3), round(exp,3), round(pv-load,3)])

    pv_tot = sum(r["pv_diff"] for r in rows)
    load_tot = sum(r["load_diff"] for r in rows)
    imp_tot = sum(r["import"] for r in rows)
    exp_tot = sum(r["export"] for r in rows)
    pv_used = pv_tot - exp_tot
    ac = (pv_used / pv_tot * 100) if pv_tot>0 else 0
    tc = (pv_used / load_tot * 100) if load_tot>0 else 0

    ui.summary("Situation actuelle", 
               pv_tot, 
               load_tot, 
               imp_tot, 
               exp_tot, 
               ac, 
               tc, 
               START, 
               END, 
               PV_ACTUAL_KW)

# =========================
# SIMULATION MODE
# =========================
def compute_stats(rows:list) -> dict:
    """
    Calcule les statistiques globales sur une liste de lignes horaires
    contenant au minimum 'pv' et 'load', optionnellement 'export' et 'import'.

    Args:
        rows (list): liste des lignes horaires [{'date', 'pv', 'load', 'export'?, 'import'?}]
    Returns:
        dict: {pv_tot, load_tot, import_tot, export_tot, ac, tc}
    where:
            pv_tot      : production PV totale (kWh)
            load_tot    : consommation totale (kWh)
            import_tot  : import total (kWh)
            export_tot  : export total (kWh)
            ac          : autoconsommation (%)
            tc          : taux de couverture (%)
    """
    eps = 1e-9

    pv = sum(r["pv"] for r in rows)
    load = sum(r["load"] for r in rows)
    exp = sum(r.get("export",0.0) for r in rows)
    imp = sum(r.get("import",0.0) for r in rows)
    # PV réellement utilisé par le foyer (direct + via batterie)
    pv_used = max(0.0, pv - exp)
    onsite  = max(load - imp, 0.0)
    
    # Bornes de sécurité (imprécisions / incohérences)
    #pv_used_capped_for_tc = min(pv_used, load)   # ne peut pas couvrir plus que la conso
    pv_used_capped_for_ac = min(pv_used, pv)     # ne peut pas dépasser la production

    # Pourcentage AC et TC (bornés à [0,100])
    ac = 100.0 * pv_used_capped_for_ac / max(pv, eps) if pv > eps else 0.0
    #tc = 100.0 * pv_used_capped_for_tc / max(load, eps) if load > eps else 0.0
    tc = 100.0 * onsite / max(load, eps) if load > eps else 0.0

    # Clamp final (au cas où)
    ac = max(0.0, min(100.0, ac))
    tc = max(0.0, min(100.0, tc))
    return {"pv_tot":pv,
            "load_tot":load,
            "import_tot":imp,
            "export_tot":exp,
            "ac":ac,
            "tc":tc}

def simulate_pv_scale(rows:list,
                      factor:float,
                      ) -> list:
    """ 
    Renvoie une nouvelle liste de rows avec la production PV multipliée par `factor`.

    Args:
        rows (list): liste des lignes horaires [{'date', 'pv', 'load'}]
        factor (float): facteur de multiplication de la production PV
    Returns:
        list: nouvelles lignes avec PV ajustée
    """
    return [{"date": r["date"],
             "pv": r["pv"]*factor,
             "load": r["load"]} for r in rows]

def _hour_from_iso(ts_str: str) -> int:
    """
    Extrait l'heure locale (0-23) d'une chaîne de caractères ISO "YYYY-MM-DDTHH:MM:SS(+TZ?)"
        
    Args:
        ts_str (str): chaîne de caractères de date/heure
    Returns:
        int: heure locale (0-23), ou -1 en cas d'erreur
    Raises:
        None, renvoie -1 en cas d'erreur
    
    Note: ne gère pas les fuseaux horaires, on extrait juste HH.
    1. "2025-06-01T14:30:00+02:00" -> 14
    2. "2025-06-01T14:30:00Z" -> 14
    3. "2025-06-01 14:30" -> 14
    4. "2025-06-01" -> -1
    5. "" -> -1
    6. None -> -1
    7. "invalid" -> -1
    8. "2025-06-01T14:30:00.123456+02:00" -> 14
    9. "2025-06-01T14:30:00.123456Z" -> 14
    10. "2025-06-01 14:30:00" -> 14
    """
    try:
        # "YYYY-MM-DD HH:MM" ou ISO "YYYY-MM-DDTHH:MM:SS(+TZ?)"
        s = str(ts_str).replace("T", " ")
        if "+" in s: s = s.split("+", 1)[0]
        if "Z" in s: s = s.replace("Z", "")
        return int(s[11:13])
    except Exception:
        return -1

def simulate_battery(rows, 
                     batt_kwh,
                     eff,
                     charge_limit=None, 
                     discharge_limit=None,
                     grid_charge=False, 
                     grid_hours=None,
                     grid_target_soc=0.8, 
                     grid_charge_limit=3.0,
                     soc_reserve=0.10,
                     initial_soc=0.0,
                     allow_discharge_in_hc=True,
                     ) -> list:
    """
    Simule l'utilisation d'une batterie sur une période entière
    en partant d'un SoC initial, sans remise à zéro quotidienne.

        rows                    : liste des mesures horaires [{'date', 'pv', 'load'}]
        batt_kwh                : capacité totale de la batterie (kWh)
        eff                     : rendement de charge/décharge (0-1)
        initial_soc             : fraction initiale de charge (0.0 → 0%, 1.0 → 100%)
        soc_reserve             : pourcentage minimal de SoC non déchargeable
        grid_charge             : autoriser la recharge sur le réseau en heures creuses
        grid_hours              : liste des heures creuses [0..23]
        allow_discharge_in_hc   : décharge autorisée en HC
        grid_target_soc         : cible de SoC en recharge HC (0.0 → 0%, 1.0 → 100%)
        grid_charge_limit       : puissance max de charge réseau en HC (kW)
        charge_limit            : puissance max de charge batterie (kW) (None = illimité)
        discharge_limit         : puissance max de décharge batterie (kW) (None = illimité)
    Returns:
        list: liste des lignes horaires avec simulation batterie
        chaque élément contient au minimum :
            date, pv, load, pv_direct, pv_to_batt, batt_to_load, import, export, soc
        où :
            pv              : production PV (kWh)
            load            : consommation (kWh)
            pv_direct      : PV consommée directement (kWh)
            pv_to_batt     : PV stockée en batterie (kWh)
            batt_to_load   : énergie fournie par la batterie (kWh)
            import         : énergie importée du réseau (kWh)
            export         : énergie exportée vers le réseau (kWh)
            soc            : état de charge de la batterie (kWh)
        Si `batt_kwh` <= 0, la batterie n'est pas simulée et les valeurs de SoC, pv_to_batt et batt_to_load sont à 0.
        Le calcul d'import/export est ajusté en conséquence.
        Le SoC est maintenu entre [batt_kwh * soc_reserve, batt_kwh].
        La batterie n'est pas remise à zéro chaque jour.
        Le rendement `eff` s'applique à la fois en charge et en décharge.
        Le paramètre `grid_hours` est une liste d'heures (0-23) considérées comme heures creuses.
        Si `grid_charge` est False, la batterie n'est jamais rechargée sur le réseau.
        Si `allow_discharge_in_hc` est False, la batterie ne peut pas se décharger en HC.
        Si `charge_limit` ou `discharge_limit` sont fournis, ils limitent respectivement la puissance de charge et de décharge (kW).
        Si `grid_charge` est True, la batterie tente de se recharger sur le réseau en HC pour atteindre `grid_target_soc`,
        limité par `grid_charge_limit`.
        Le calcul d'import/export prend en compte la batterie et les recharges réseau en HC.
    Note: les valeurs de puissance (kW) sont considérées comme des énergies (kWh) sur une période horaire.
    1 kW sur 1 heure = 1 kWh
    1 kW sur 30 minutes = 0.5 kWh
    1 kW sur 15 minutes = 0.25 kWh
    1 kW sur 10 minutes = 1/6 kWh ≈ 0.1667 kWh
    1 kW sur 5 minutes = 1/12 kWh ≈ 0.0833 kWh
    1 kW sur 1 minute = 1/60 kWh ≈ 0.01667 kWh
    1 kW sur 10 secondes = 1/360 kWh ≈ 0.00278 kWh
    1 kW sur 1 seconde = 1/3600 kWh ≈ 0.000278 kWh
    Exemples:
        - Pour une période horaire complète, 1 kW = 1 kWh
        - Pour une période de 30 minutes, 1 kW = 0.5 kWh
        - Pour une période de 15 minutes, 1 kW = 0.25 kWh
        - Pour une période de 10 minutes, 1 kW = 1/6 kWh ≈ 0.1667 kWh
        - Pour une période de 5 minutes, 1 kW = 1/12 kWh ≈ 0.0833 kWh
        - Pour une période de 1 minute, 1 kW = 1/60 kWh ≈ 0.01667 kWh
        - Pour une période de 10 secondes, 1 kW = 1/360 kWh ≈ 0.00278 kWh
        - Pour une période de 1 seconde, 1 kW = 1/3600 kWh ≈ 0.000278 kWh
    Raises:
        ValueError: si les paramètres sont invalides
    -------------------------------------------------------------------------------------------
    Exemples d'utilisation:
    -------------------------------------------------------------------------------------------
    # Simule une batterie de 10 kWh avec un rendement de 90% et un SoC initial de 50%
    simulated = simulate_battery(data, batt_kwh=10, eff=0.9, initial_soc=0.5) # 50% de SoC initial
    # Simule une batterie de 20 kWh avec un rendement de 85%, un SoC initial de 20%,
    # une limite de charge de 5 kW, une limite de décharge de 5 kW, et une réserve de SoC de 10%
    simulated = simulate_battery(data, batt_kwh=20, eff=0.85, initial_soc=0.2, charge_limit=5, discharge_limit=5, soc_reserve=0.1)
    # Simule une batterie de 15 kWh avec un rendement de 90%, un SoC initial de 0%,
    # autorise la recharge sur le réseau en heures creuses (22h-6h) avec une cible de SoC de 80% et une limite de charge réseau de 3 kW
    simulated = simulate_battery(data, batt_kwh=15, eff=0.9, initial_soc=0.0, grid_charge=True, grid_hours=list(range(22,24))+list(range(0,6)), grid_target_soc=0.8, grid_charge_limit=3.0)
    -------------------------------------------------------------------------------------------
    """
    # Validation des paramètres
    if eff <= 0 or eff > 1:
        raise ValueError("eff doit être dans (0,1]")
    if initial_soc < 0 or initial_soc > 1:
        raise ValueError("initial_soc doit être dans [0,1]")
    if soc_reserve < 0 or soc_reserve >= 1:
        raise ValueError("soc_reserve doit être dans [0,1)")
    if grid_target_soc < 0 or grid_target_soc > 1:
        raise ValueError("grid_target_soc doit être dans [0,1]")
    if grid_charge and grid_target_soc <= soc_reserve:
        raise ValueError("Si grid_charge est True, grid_target_soc doit être > soc_reserve")
    if charge_limit is not None and charge_limit <= 0:
        raise ValueError("charge_limit doit être > 0 ou None")
    if discharge_limit is not None and discharge_limit <= 0:
        raise ValueError("discharge_limit doit être > 0 ou None")
    if not isinstance(allow_discharge_in_hc, bool):
        raise ValueError("allow_discharge_in_hc doit être booléen (true/false)")
    if not isinstance(grid_charge, bool):
        raise ValueError("grid_charge doit être booléen (true/false)")
    if grid_charge and (not grid_hours or not all(isinstance(h,int) and 0<=h<=23 for h in grid_hours)):
        raise ValueError("Si grid_charge est True, grid_hours doit être une liste d'entiers entre 0 et 23")
    if grid_charge and grid_charge_limit <= 0:
        raise ValueError("Si grid_charge est True, grid_charge_limit doit être > 0")
    if not rows:
        return []
    # Si pas de batterie, on calcule juste import/export sans batterie
    if batt_kwh <= 0:
        out=[]
        for r in rows:
            pv, ld = float(r["pv"]), float(r["load"])
            pv_direct = min(pv, ld)
            export = max(0.0, pv - pv_direct)
            imp = max(0.0, ld - pv_direct)
            out.append({
                "date": r["date"], 
                "pv": pv, 
                "load": ld,
                "export": export, 
                "import": imp, 
                "soc": 0.0,
                "pv_direct": pv_direct, 
                "batt_to_load": 0.0, 
                "pv_to_batt": 0.0
            })
        return out
    # Initialisation
    grid_hours = set(grid_hours or [])
    soc_min = batt_kwh * max(0.0, min(1.0, soc_reserve))
    soc_max = batt_kwh
    soc = batt_kwh * max(0.0, min(1.0, initial_soc))
    # Simulation horaire
    out=[]
    for r in rows:
        pv = float(r["pv"])
        load = float(r["load"])
        # 0) Déterminer si on est en HC (local)
        hour_local = _hour_from_iso(r["date"])
        # Si l'heure ne peut être déterminée, on considère que ce n'est pas HC
        allow_charge_in_hc = grid_charge and (hour_local in grid_hours)
        in_hc = hour_local in grid_hours if hour_local >= 0 else False

        available_pv = pv
        remaining_load = load
        
        pv_direct      = 0.0
        pv_to_batt     = 0.0
        batt_to_load   = 0.0
        imp_load       = 0.0
        imp_grid       = 0.0
        
        # 1) PV → charges direct
        pv_direct = min(available_pv, remaining_load)
        available_pv   -= pv_direct
        remaining_load -= pv_direct

        # 2) PV -> batterie (stockage) limité par capacité restante + limite horaire
        pv_in_limit = available_pv if charge_limit is None else min(available_pv, charge_limit)
        # énergie pouvant être stockée côté batterie
        can_store_in = (soc_max - soc) / (eff if eff > 0 else 1.0)  # kWh côté entrée PV
        # énergie effectivement stockée côté PV
        pv_to_batt = min(pv_in_limit, max(0.0, can_store_in))
        # Charge effective côté batterie = pv_to_batt * eff
        if pv_to_batt > 0:
            soc += pv_to_batt * eff
            available_pv -= pv_to_batt

        # 3) Batterie -> load (décharge), y compris en HC si autorisée
        #    Par défaut : en HC, bloquée si allow_discharge_in_hc=False
        #    Cas particulier demandé : si on RECHARGE via réseau juste après,
        #    on bloque aussi la décharge pour cette heure (priorité à la recharge)
        batt_out_limit = remaining_load if discharge_limit is None else min(remaining_load, discharge_limit)
        # provisoire, sera raffiné après charge réseau
        if not allow_charge_in_hc and allow_discharge_in_hc or not in_hc:
            can_discharge_now = True
        else:
            can_discharge_now = False
        if batt_out_limit > 0 and can_discharge_now:
            # énergie disponible pour décharge côté batterie
            batt_can_out = max(0.0, soc - soc_min) # kWh *côté batterie*
            # énergie restituée au load = retiré_du_SoC * eff
            batt_to_load = min(batt_out_limit, batt_can_out * eff)
            # mise à jour SoC
            if batt_to_load > 0:
                # côté batterie, il faut retirer plus pour compenser le rendement
                soc -= batt_to_load / (eff if eff > 0 else 1.0)
                # mise à jour load restant
                remaining_load -= batt_to_load

        # 4) Le reste du load est à importer
        imp_load = max(0.0, remaining_load)

        # 5) Surplus PV restant = export
        export = max(0.0, available_pv)
        
        # 6) Charge réseau en HC pour atteindre la cible (séparée du load)
        imp_grid = 0.0
        # Prioriser la recharge réseau uniquement si on est en HC
        # et si la cible est supérieure au SoC actuel
        if allow_charge_in_hc:
            # déterminer la cible de SoC côté batterie
            target_soc = batt_kwh * max(0.0, min(1.0, grid_target_soc))
            # ne recharger que si la cible est supérieure au SoC actuel
            if soc < target_soc:
                # énergie nécessaire pour atteindre la cible côté batterie
                need_batt_side = target_soc - soc                              # kWh côté batterie
                # énergie nécessaire côté réseau (avant rendement)
                grid_in = min(need_batt_side / (eff if eff > 0 else 1.0),      # kWh côté réseau
                              max(0.0, grid_charge_limit))
                # limiter à la capacité restante côté batterie
                if grid_in > 0:
                    soc += grid_in * eff
                    imp_grid += grid_in
                    
                    # Prioriser la recharge : interdire la décharge si elle a eu lieu.
                    # On "annule" toute décharge de l'heure (pas de charge/décharge simultanée).
                    if batt_to_load > 0:
                        # remettre le SoC comme s'il n'y avait pas eu de décharge
                        soc += batt_to_load / (eff if eff > 0 else 1.0)
                        # remettre le load restant comme s'il n'y avait pas eu de décharge
                        remaining_load += batt_to_load
                        # annuler la décharge
                        batt_to_load = 0.0
                        # le load restant devient de l'import
                        imp_load += remaining_load
                        remaining_load = 0.0

        # 7) Clamp SoC
        soc = max(soc_min, min(soc_max, soc))

        # 8) Import total = load + recharge HC
        #    Export total = surplus PV
        #    (la batterie est un tampon interne)
        # 9) Stockage des résultats
        imp = imp_load + imp_grid

        out.append({
            "date": r["date"],
            "pv": pv,
            "load": load,
            "export": export,
            "import": imp_load + imp_grid,
            "soc": soc,
            "pv_direct": pv_direct,
            "batt_to_load": batt_to_load,
            "pv_to_batt": pv_to_batt,
            "imp_grid": imp_grid,
            "imp_load": imp_load,
        })
    return out


def run_simu(cfg: dict,
             args: argparse.Namespace=None,
             ) -> None:
    """
    Lancement de la simulation de batterie :
    1) lit le CSV horaire produit par report
    2) calcule la situation actuelle (sans batterie)
    3) si `--override`, simule la batterie avec les paramètres forcés
        sinon, teste toutes les combinaisons de PV et batterie
    4) affiche les résultats
    5) écrit un CSV horaire détaillé pour la simulation retenue
    6) écrit un CSV journalier pour la simulation retenue
    7) affiche un résumé
    
    Args:
        cfg (dict): configuration chargée
        args (argparse.Namespace, optional): paramètres passés au script. Defaults to None.
    Returns:
        None
    Raises:
        RuntimeError: en cas d'erreur critique
    """
    if args is None:
        args = argparse.Namespace()
        args.override = False
    if args.override not in (True, False):
        raise ValueError(f"Paramètre override invalide: {args.override}")
    if not cfg.get("OUT_CSV_DETAIL"):
        raise ValueError("Le paramètre 'OUT_CSV_DETAIL' doit être fourni dans la config")
    if not cfg.get("OUT_CSV_SIMU"):
        raise ValueError("Le paramètre 'OUT_CSV_SIMU' doit être fourni dans la config")
    if not cfg.get("START") or not cfg.get("END"):  
        raise ValueError("Les paramètres 'START' et 'END' doivent être fournis dans la config")
    if not cfg.get("PV_ACTUAL_KW"):
        raise ValueError("Le paramètre 'PV_ACTUAL_KW' doit être fourni dans la config")
    if cfg["PV_ACTUAL_KW"] <= 0:
        raise ValueError("Le paramètre 'PV_ACTUAL_KW' doit être > 0")
    if cfg["TARGET_AC_MIN"] < 0 or cfg["TARGET_AC_MIN"] > 100:
        raise ValueError("Le paramètre 'TARGET_AC_MIN' doit être dans [0,100]")
    if cfg["TARGET_AC_MAX"] < 0 or cfg["TARGET_AC_MAX"] > 100:
        raise ValueError("Le paramètre 'TARGET_AC_MAX' doit être dans [0,100]")
    if cfg["TARGET_AC_MIN"] > cfg["TARGET_AC_MAX"]:
        raise ValueError("Le paramètre 'TARGET_AC_MIN' doit être ≤ 'TARGET_AC_MAX'")
    if cfg["TARGET_TC_MIN"] < 0 or cfg["TARGET_TC_MIN"] > 100:
        raise ValueError("Le paramètre 'TARGET_TC_MIN' doit être dans [0,100]")
    if cfg["BATTERY_EFF"] <= 0 or cfg["BATTERY_EFF"] > 1:
        raise ValueError("Le paramètre 'BATTERY_EFF' doit être dans (0,1]")
    if not cfg["BATTERY_SIZES"]:
        raise ValueError("Le paramètre 'BATTERY_SIZES' doit contenir au moins une valeur")
    if not cfg["PV_FACTORS"]:
        raise ValueError("Le paramètre 'PV_FACTORS' doit contenir au moins une valeur")
    if cfg["INITIAL_SOC"] < 0 or cfg["INITIAL_SOC"] > 1:
        raise ValueError("Le paramètre 'INITIAL_SOC' doit être dans [0,1]")
    if cfg["BATT_MIN_SOC"] < 0 or cfg["BATT_MIN_SOC"] > 1:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être dans [0,1]")
    if cfg["BATT_MIN_SOC"] >= 1.0:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être < 1.0")
    if cfg["BATT_MIN_SOC"] >= cfg["INITIAL_SOC"]:
        raise ValueError("Le paramètre 'BATT_MIN_SOC' doit être < 'INITIAL_SOC'")
    if cfg.get("MAX_DISCHARGE_KW_PER_HOUR", 0.0) is not None and cfg["MAX_DISCHARGE_KW_PER_HOUR"] <= 0:
        raise ValueError("Le paramètre 'MAX_DISCHARGE_KW_PER_HOUR' doit être > 0")
    if not isinstance(cfg.get("ALLOW_DISCHARGE_IN_HC", False), bool):
        raise ValueError("Le paramètre 'ALLOW_DISCHARGE_IN_HC' doit être booléen (true/false)")
    if not isinstance(cfg.get("GRID_CHARGE_IN_HC", False), bool):  
        raise ValueError("Le paramètre 'GRID_CHARGE_IN_HC' doit être booléen (true/false)")
    if not isinstance(cfg.get("GRID_HOURS", []), list) or not all(isinstance(h,int) and 0<=h<=23 for h in cfg.get("GRID_HOURS", [])):
        raise ValueError("Le paramètre 'GRID_HOURS' doit être une liste d'entiers entre 0 et 23")
    if cfg.get("GRID_TARGET_SOC", 0.8) < 0 or cfg.get("GRID_TARGET_SOC", 0.8) > 1:
        raise ValueError("Le paramètre 'GRID_TARGET_SOC' doit être dans [0,1]")
    if cfg.get("GRID_CHARGE_LIMIT", 3.0) <= 0:
        raise ValueError("Le paramètre 'GRID_CHARGE_LIMIT' doit être > 0")
    if cfg.get("GRID_TARGET_SOC", 0.8) <= cfg["BATT_MIN_SOC"]:
        raise ValueError("Le paramètre 'GRID_TARGET_SOC' doit être > 'BATT_MIN_SOC'")
    if cfg.get("GRID_CHARGE_IN_HC", False) and not cfg.get("GRID_HOURS", []):
        raise ValueError("Si 'GRID_CHARGE_IN_HC' est true, 'GRID_HOURS' doit contenir au moins une heure")
    if cfg.get("GRID_CHARGE_IN_HC", False) and cfg.get("GRID_TARGET_SOC", 0.8) <= cfg["INITIAL_SOC"]:
        raise ValueError("Si 'GRID_CHARGE_IN_HC' est true, 'GRID_TARGET_SOC' doit être > 'INITIAL_SOC'")
    if not LOCAL_TZ and (not args.source or args.source == "ha_ws"):
        raise RuntimeError("zoneinfo indisponible : installe Python ≥ 3.9") 
    if args.source == "ha_ws" and not cfg.get("SSL_VERIFY", False):
        ssl._create_default_https_context = ssl._create_unverified_context
        #ui.warning("La vérification SSL est désactivée (SSL_VERIFY=false)")
    # paramètres courants
    IN_CSV          = cfg["OUT_CSV_DETAIL"]               # on lit le CSV horaire produit par report
    OUT_CSV         = cfg["OUT_CSV_SIMU"]                 # fichier de sortie CSV horaire
    TARGET_AC_MIN   = cfg["TARGET_AC_MIN"]                # cible d'autoconso minimum
    TARGET_AC_MAX   = cfg["TARGET_AC_MAX"]                # cible d'autoconso maximum
    TARGET_TC_MIN   = cfg["TARGET_TC_MIN"]                # cible de taux de couverture minimum
    BATTERY_SIZES   = cfg["BATTERY_SIZES"]                # taille des batteries
    PV_FACTORS      = cfg["PV_FACTORS"]                   # facteur d'ajout de panneaux solaires
    EFF             = cfg["BATTERY_EFF"]                  # efficience de la batterie
    START           = cfg["START"]                        # date et heure de début de l'étude
    END             = cfg["END"]                          # date et heure de fin de l'étude
    PV_ACTUAL_KW    = cfg["PV_ACTUAL_KW"]                 # puissance actuelle des panneaux solaires
    INITIAL_SOC     = float(cfg.get("INITIAL_SOC", 0.0))  # energie de départ de la batterie
    BATT_MIN_SOC    = float(cfg.get("BATT_MIN_SOC", 0.0)) # energie minimum acceptée par la batterie
    MAX_DISCHARGE_KW_PER_HOUR = (
        float(cfg.get("MAX_DISCHARGE_KW_PER_HOUR", 0.0)) or None
    )
    ALLOW_DISCHARGE_IN_HC = cfg.get("ALLOW_DISCHARGE_IN_HC", False)
    GRID_CHARGE_IN_HC    = cfg.get("GRID_CHARGE_IN_HC", False)
    GRID_HOURS           = cfg.get("GRID_HOURS", [0,1,2,3,4,5,22,23])  # Heures creuses par défaut
    GRID_TARGET_SOC      = float(cfg.get("GRID_TARGET_SOC", 0.8))
    GRID_CHARGE_LIMIT    = float(cfg.get("GRID_CHARGE_LIMIT", 3.0))
    # paramètres forcés si `--override`
    PV_FACTOR       = float(cfg.get("SIM_SCENARIO", {}).get("PV_FACTOR", 1.0))
    BATTERY_KWH     = float(cfg.get("SIM_SCENARIO", {}).get("BATTERY_KWH", 0.0))

    if not Path(IN_CSV).exists():
        print(f"[ERREUR] Fichier horaire introuvable: {IN_CSV}\nLance d'abord --mode report.")
        sys.exit(1)

    # charge data horaire
    rows=[]
    with open(IN_CSV) as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append({"date": r["date"], "pv": float(r["pv_diff"]), "load": float(r["load_diff"])})

    # situation actuelle sans batterie
    base_no_batt = simulate_battery(
        rows=rows,
        grid_hours=[0,1,2,3,4,5,22,23],
        batt_kwh=0.0,               # pas de batterie
        eff=EFF,                    # pas utilisé mais requis
        soc_reserve=0.0,            # SoC ignoré
        initial_soc=0.0,            # SoC ignoré
        discharge_limit=None,       # SoC ignoré
        allow_discharge_in_hc=False # Pas de batterie
    )
    base_stats = compute_stats(base_no_batt)

    # résumé de la situation actuelle
    ui.summary("Situation actuelle",
               base_stats["pv_tot"],
               base_stats["load_tot"],
               base_stats["import_tot"],
               base_stats["export_tot"],
               base_stats["ac"],
               base_stats["tc"],
               START,
               END,
               PV_ACTUAL_KW)

    # si override, on force les paramètres
    if args.override:
        # on applique le facteur PV
        scaled_rows = simulate_pv_scale(rows, PV_FACTOR)
        # vérifications
        if PV_FACTOR <= 0:
            raise ValueError(f"Le paramètre forcé PV_FACTOR doit être > 0 (actuel: {PV_FACTOR})")
        if BATTERY_KWH < 0:
            raise ValueError(f"Le paramètre forcé BATTERY_KWH doit être ≥ 0 (actuel: {BATTERY_KWH})")
        if BATTERY_KWH > 0 and BATT_MIN_SOC >= 1.0:
            raise ValueError(f"Le paramètre 'BATT_MIN_SOC' doit être < 1.0 (actuel: {BATT_MIN_SOC})")
        if BATTERY_KWH > 0 and BATT_MIN_SOC >= INITIAL_SOC:
            raise ValueError(f"Le paramètre 'BATT_MIN_SOC' doit être < 'INITIAL_SOC' (actuel: {BATT_MIN_SOC} >= {INITIAL_SOC})")
        # simulation
        sim = simulate_battery(
            rows=scaled_rows,
            grid_hours=GRID_HOURS,                          # Heures creuses
            batt_kwh=BATTERY_KWH,                           # batterie utilisée
            eff=EFF,                                        # Batterie efficiency
            soc_reserve=BATT_MIN_SOC,                       # minimum de capacité pour la batterie
            initial_soc=INITIAL_SOC,                        # batterie avec un pourcentage de départ
            discharge_limit=MAX_DISCHARGE_KW_PER_HOUR,      # décharge limite de batterie
            allow_discharge_in_hc=ALLOW_DISCHARGE_IN_HC,    # Permet la décharge en heure creuse
            grid_charge=GRID_CHARGE_IN_HC,                  # Permet la recharge en HC
            grid_target_soc=GRID_TARGET_SOC,                # cible de SoC en HC
            grid_charge_limit=GRID_CHARGE_LIMIT             # limite de charge en HC
        )

        #pprint(sim)
        # stats et résumé
        daily = aggregate_daily(sim)
        st  = compute_stats(sim)
        ui.summary(f"Simulation forcée (override) PV x{PV_FACTOR:g}, Batt {int(BATTERY_KWH)} kWh",
                     st["pv_tot"],
                     st["load_tot"],
                     st["import_tot"],
                     st["export_tot"],
                     st["ac"],
                     st["tc"],
                     START,
                     END,
                     pv_factor=PV_FACTOR,
                     batt_kw=BATTERY_KWH)
        # CSV détaillé
        csv_detail_path = cfg.get("OUT_CSV_SIM_DETAIL", "ha_energy_sim_detail.csv")
        context = {
            "pv_factor": PV_FACTOR,       # facteur du scénario retenu
            "batt_kwh": BATTERY_KWH,      # capacité batterie
            "eff": EFF,
            "initial_soc": cfg.get("INITIAL_SOC", 0.0),
            "pv_kwc": cfg.get("PV_ACTUAL_KW", 0.0),
            "scenario": f"PV x{PV_FACTOR:g}, Batt {int(BATTERY_KWH)} kWh",
        }
        save_sim_detail(csv_detail_path, sim, context=context)
        ui.definitions()
        return
    # sinon on teste toutes les combinaisons
    results=[]
    for fct in PV_FACTORS:
        # on applique le facteur PV
        scaled = simulate_pv_scale(rows, fct)
        # pour chaque taille de batterie
        for batt_kwh in BATTERY_SIZES:
            # simulation
            sim = simulate_battery(
                rows=scaled,
                grid_hours=GRID_HOURS,                          # Heures creuses
                batt_kwh=batt_kwh,                              # batterie utilisée
                eff=EFF,                                        # Batterie efficiency
                soc_reserve=BATT_MIN_SOC,                       # minimum de capacité pour la batterie
                initial_soc=INITIAL_SOC,                        # batterie avec un pourcentage de départ
                discharge_limit=MAX_DISCHARGE_KW_PER_HOUR,      # décharge limite de batterie
                allow_discharge_in_hc=ALLOW_DISCHARGE_IN_HC,    # Permet la décharge en heure creuse
                grid_charge=GRID_CHARGE_IN_HC,                  # Permet la recharge en HC
                grid_target_soc=GRID_TARGET_SOC,                # cible de SoC en HC
                grid_charge_limit=GRID_CHARGE_LIMIT             # limite de charge en HC
            )
            # stats
            daily = aggregate_daily(sim)
            # stats globales
            st  = compute_stats(sim)
            results.append((fct, batt_kwh, st))

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pv_factor","battery_kWh","pv_tot_kWh","load_tot_kWh","import_kWh","export_kWh","AC_%","TC_%"])
        for fct, b, st in results:
            w.writerow([fct, 
                        b, 
                        st["pv_tot"], 
                        st["load_tot"], 
                        st["import_tot"], 
                        st["export_tot"], 
                        st["ac"], 
                        st["tc"]])

    # filtre les résultats qui passent les cibles
    passing = [(fct,b,st) for (fct,b,st) in results if (TARGET_AC_MIN <= st["ac"] <= TARGET_AC_MAX) and (st["tc"] >= TARGET_TC_MIN)]
    if passing:
        # on prend le premier qui passe (ou trie si tu veux un critère)
        pv_factor, batt_kwh, st = passing[0]
    else:
        ui.show_no_scenarios(TARGET_AC_MIN, TARGET_AC_MAX, TARGET_TC_MIN)
        sys.exit(1)

    # applique le facteur PV aux rows (copie légère)
    scaled_rows = [
        {"date": r["date"], "pv": float(r["pv"]) * pv_factor, "load": float(r["load"])}
        for r in rows
    ]
    # simule une dernière fois pour avoir les détails horaires
    sim = simulate_battery(
        rows=scaled_rows,
        grid_hours=GRID_HOURS,                          # Heures creuses
        batt_kwh=batt_kwh,                              # batterie utilisée
        eff=EFF,                                        # Batterie efficiency
        soc_reserve=BATT_MIN_SOC,                       # minimum de capacité pour la batterie
        initial_soc=INITIAL_SOC,                        # batterie avec un pourcentage de départ
        discharge_limit=MAX_DISCHARGE_KW_PER_HOUR,      # décharge limite de batterie
        allow_discharge_in_hc=ALLOW_DISCHARGE_IN_HC,    # Permet la décharge en heure creuse
        grid_charge=GRID_CHARGE_IN_HC,                  # Permet la recharge en HC
        grid_target_soc=GRID_TARGET_SOC,                # cible de SoC en HC
        grid_charge_limit=GRID_CHARGE_LIMIT             # limite de charge en HC
    )
    # chemin de sortie configurable (ajoute la clé dans ton JSON)
    csv_detail_path = cfg.get("OUT_CSV_SIM_DETAIL", "ha_energy_sim_detail.csv")
    context = {
        "pv_factor": pv_factor,           # facteur du scénario retenu
        "batt_kwh": batt_kwh,
        "eff": EFF,
        "initial_soc": cfg.get("INITIAL_SOC", 0.0),
        "pv_kwc": cfg.get("PV_ACTUAL_KW", 0.0),
        "scenario": f"PV x{pv_factor:g}, Batt {int(batt_kwh)} kWh",
    }
    # CSV détaillé
    save_sim_detail(csv_detail_path, sim, context=context)
    
    # Affichage
    ui.passing(passing, TARGET_AC_MIN, TARGET_AC_MAX, TARGET_TC_MIN, limit=10)
    if passing:
        # déjà triés : passer passing[0]
        ui.best(passing[0], cfg["PV_ACTUAL_KW"])

    ui.definitions()

def csv_available_days(csv_path: str) -> list[str]:
    """
    Retourne la liste triée des jours (YYYY-MM-DD) présents dans le CSV "detail".
    On lit la colonne 'date' et on tronque à 10 caractères.

    Args:
        csv_path (str): chemin du CSV
    Returns:
        list[str]: liste des jours disponibles dans le CSV
    Raises:
        None
    """
    days = set()
    try:
        with open(csv_path, "r", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                ts = str(r.get("date",""))[:10]
                if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
                    days.add(ts)
    except Exception:
        pass
    return sorted(days)

def csv_has_day(csv_path: str, 
                day: str,
                ) -> bool:
    """
    Vérifie si un jour donné (YYYY-MM-DD) est présent dans le CSV "detail".

    Args:
        csv_path (str): chemin du CSV
        day (str): jour au format YYYY-MM-DD
    Returns:
        bool: True si le jour est présent, False sinon
    Raises:
        None
    """
    return day in set(csv_available_days(csv_path))

def run_plot(cfg: dict,
             args=None,
             ) -> None:
    """
    Affiche en console les barres horaires (import/batterie/PV et export)
    pour un jour donné à partir d'un CSV de simulation horaire.
    Le CSV doit contenir: date,pv,load,pv_direct,pv_to_batt,batt_to_load,import,export,soc
    1) lit le CSV horaire de simulation
    2) extrait le jour demandé (ou le premier jour de la période)
    3) affiche les barres en console (2 colonnes: actuel vs simulé si base fourni)
    4) affiche le contexte (paramètres de la simulation)
    5) affiche la légende
    6) affiche les définitions

    Args:
        cfg (dict): configuration chargée
        args (argparse.Namespace, optional): paramètres passés au script. Defaults to None.
    Returns:
        None
    Raises:
        RuntimeError: en cas d'erreur critique
    """
    if args is None:
        args = argparse.Namespace()
    if not cfg.get("START") or not cfg.get("END"):  
        raise ValueError("Les paramètres 'START' et 'END' doivent être fournis dans la config")
    if not LOCAL_TZ:
        raise RuntimeError("zoneinfo indisponible : installe Python ≥ 3.9") 
    if not Path(cfg.get("OUT_CSV_SIM_DETAIL", "ha_energy_sim_detail.csv")).exists():
        raise RuntimeError(f"Fichier horaire introuvable: {cfg.get('OUT_CSV_SIM_DETAIL','ha_energy_sim_detail.csv')}\nLance d'abord --mode simu.")

    # jour à afficher
    # priorité à --day
    # jour cible
    day = None
    if args and getattr(args, "day", None):
        day = args.day
    else:
        # fallback: premier jour de la période de la config
        start = str(cfg.get("START",""))[:10]
        if not start:
            ui.error("Spécifie --day YYYY-MM-DD ou définis START dans la config.")
            return
        day = start
    days = min(2, max(1, int(getattr(args, "days", 1))))
    # chemin CSV de la simulation
    sim_csv_path = None
    if args and getattr(args, "csv", None):
        sim_csv_path = args.csv
    else:
        sim_csv_path = cfg.get("OUT_CSV_SIM_DETAIL") or cfg.get("OUT_CSV_DETAIL") or "ha_energy_sim_detail.csv"

    p_sim = Path(sim_csv_path)
    if not p_sim.exists():
        ui.error(f"CSV introuvable: {p_sim}\nGénère-le d'abord via --mode simu (save_sim_detail).")
        return

    # chemin CSV de la prod/conso actuelle
    base_csv_path = cfg.get("PLOT_BASE_CSV", "ha_energy_import_export_hourly.csv")
    p_base = Path(base_csv_path)
    if not p_base.exists():
        ui.error(f"CSV introuvable")
        return
    
    # vérifie que le jour est dans le CSV
    csv_path_detail = str(p_sim)
    days_csv = csv_available_days(csv_path_detail)
    if (not days_csv) or (day not in days_csv):
        # message clair + quelques suggestions
        hint = None
        if days_csv:
            hint = f"Choisis un jour parmi les dates présentes dans {csv_path_detail}."
        ui.show_day_not_found(day or "(non fourni)", days_csv, hint=hint)
        return
    
    max_kwh = float(getattr(args, "max_kwh", 5.0) or 5.0)
    
    context = {
        "scenario": cfg.get("SELECTED_SCENARIO", "PV x{:.1f}, Batt {} kWh".format(cfg.get("LAST_PV_FACTOR",1.0), cfg.get("LAST_BATT_KWH",0))),
        "pv_kwc": cfg.get("PV_ACTUAL_KW", 0.0),
        "pv_factor": cfg.get("LAST_PV_FACTOR", 1.0),
        "batt_kwh": cfg.get("LAST_BATT_KWH", 0),
        "eff": cfg.get("BATTERY_EFF", 0.90),
        "initial_soc": cfg.get("INITIAL_SOC", 0.0),
        "grid_hours": cfg.get("GRID_HOURS", []),
        "grid_target_soc": cfg.get("GRID_TARGET_SOC", None),
    }

    # Affichage des barres
    ui.plot_day_cli_bipolar_compare(
        base_csv_path=str(p_base),
        sim_csv_path=str(p_sim),
        day=day,
        days=days,
        stack_when_multi=False, # empiler si days>1
        max_kwh=None,           # autoscale commun
        step_kwh=0.2,
        col_width=2,
        gap=1,
        context=context,
        titles=("Actuel", "Simulé")
    )

# =========================
# CLI
# =========================
def main():
    """ 
    Point d'entrée principal du script.
    Parse les arguments, charge la config et lance le mode demandé.

    Args:
        None
    Returns:
        None
    Raises:
        SystemExit: en cas d'erreur de parsing ou d'exécution
    """
    ap = argparse.ArgumentParser(description="PV/Load report & simulation (HA + Sizing)")
    ap.add_argument("--mode", choices=["report","simu","plot"], required=True, help="report: fetch & compute; simu: run combos on hourly CSV; plot: bar charts in console")
    ap.add_argument("--config", default="pv_config.json", help="chemin du JSON de config (défaut: pv_config.json)")
    # --- options pour le mode report ---
    ap.add_argument("--source", choices=["ha_ws","csv","enlighten"], default="ha_ws",help="source de données pour --mode report")
    # --- options pour le mode simu ---
    ap.add_argument("--override", type=bool, default=False,
                    help="Force la simulation avec les paramètres définis dans le JSON (sinon utilise les derniers paramètres retenus)")
    # --- options pour le mode plot ---
    ap.add_argument("--day", help="Jour à afficher (YYYY-MM-DD) pour --mode plot")
    ap.add_argument("--days", type=int, default=1,
                    help="Nombre de jours à tracer en mode plot (1 par défaut, 2 pour 48h)")
    ap.add_argument("--max-kwh", type=float, default=5.0,
                    help="Échelle verticale (kWh) pour les barres en --mode plot (défaut 5.0)")
    ap.add_argument("--csv", help="Chemin du CSV horaire détaillé (sinon OUT_CSV_SIM_DETAIL du JSON)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))

    if args.mode == "report":
        run_report(cfg, args)
    elif args.mode == "simu":
        run_simu(cfg, args)
    else:
        run_plot(cfg, args)

if __name__ == "__main__":
    main()
