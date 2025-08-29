#!/usr/bin/env python3
import json, os, sys, ssl, csv, argparse
from pathlib import Path
import csv
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
    "OUT_CSV_DETAIL": "ha_energy_import_export_hourly.csv",
    "OUT_CSV_DAILY":  "ha_energy_import_export_daily.csv",
    "OUT_CSV_SIMU":   "ha_energy_simulation_combos.csv",
    "TARGET_AC_MIN":  85.0,
    "TARGET_AC_MAX":  100.0,   # 100 = pas de plafond
    "TARGET_TC_MIN":  80.0,
    "BATTERY_SIZES":  [0,5,10,12,14,16,18,20,22,24,26,28,30],
    "PV_FACTORS":     [1.0,1.2,1.5,1.8,2.0,2.2,2.4,2.6,3.0],
    "BATTERY_EFF":    0.90,
    "PV_ACTUAL_KW":   4.0,
    "INITIAL_SOC":    0.0,    # 0% par défaut
}

ui = ConsoleUI()

def save_sim_detail(csv_path: str, sim_rows: list, date_key: str = "date", context=None) -> None:
    """
        Écrit un CSV horaire détaillé pour un scénario unique.
        `sim_rows` est la liste de dicts renvoyée par `simulate_battery(...)`,
        chaque élément devant contenir au minimum :
            date, pv, load, pv_direct, pv_to_batt, batt_to_load, import, export, soc
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
    """
    fields = [
        "date", "pv", "load", "pv_direct", "pv_to_batt",
        "batt_to_load", "import", "export", "soc"
    ]

    meta_fields = ["pv_factor","batt_kwh","eff","initial_soc","pv_kwc","scenario"]
    all_fields = fields + meta_fields
    
    def _fmt_date(dt):
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

def aggregate_daily(sim_rows):
    """
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

def _as_float(x, name):
    """
    """
    try: return float(x)
    except: raise ValueError(f"Paramètre '{name}' doit être un nombre (float), reçu: {x!r}")

def _as_list_float(x, name):
    """
    """
    if not isinstance(x, list):
        raise ValueError(f"Paramètre '{name}' doit être une liste de nombres")
    return [float(v) for v in x]

def load_config(path: Path) -> dict:
    """
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


def make_source(cfg, args):
    """
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
def run_report(cfg: dict, args):
    BASE_URL = cfg["BASE_URL"]
    TOKEN = cfg["TOKEN"]
    PV_ENTITY = cfg["PV_ENTITY"]
    LOAD_ENTITY = cfg["LOAD_ENTITY"]
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
        rows.append({"date": h["date"], "pv_diff": pv, "load_diff": ld, "import": imp, "export": export})

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

    ui.summary("Situation actuelle", pv_tot, load_tot, imp_tot, exp_tot, ac, tc, START, END, PV_ACTUAL_KW)

# =========================
# SIMULATION MODE
# =========================
def compute_stats(rows):
    pv = sum(r["pv"] for r in rows)
    load = sum(r["load"] for r in rows)
    exp = sum(r.get("export",0.0) for r in rows)
    imp = sum(r.get("import",0.0) for r in rows)
    pv_used = pv - exp
    ac = (pv_used / pv * 100) if pv>0 else 0.0
    tc = (pv_used / load * 100) if load>0 else 0.0
    return {"pv_tot":pv, "load_tot":load, "import_tot":imp, "export_tot":exp, "ac":ac, "tc":tc}

def simulate_pv_scale(rows, factor):
    return [{"date": r["date"], "pv": r["pv"]*factor, "load": r["load"]} for r in rows]

def _hour_from_iso(ts_str: str) -> int:
    """
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
                     ):
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
    """
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

    grid_hours = set(grid_hours or [])
    soc_min = batt_kwh * max(0.0, min(1.0, soc_reserve))
    soc_max = batt_kwh
    soc = batt_kwh * max(0.0, min(1.0, initial_soc))

    out=[]
    for r in rows:
        pv = float(r["pv"])
        load = float(r["load"])
        hour_local = _hour_from_iso(r["date"])
        in_hc = grid_charge and (hour_local in grid_hours)
        available_pv = pv
        remaining_load = load

        # 1) PV → charges direct
        pv_direct = min(available_pv, remaining_load)
        available_pv -= pv_direct
        remaining_load -= pv_direct

        # 2) Batterie -> load (décharge), y compris en HC si autorisée
        batt_out_limit = remaining_load if discharge_limit is None else min(remaining_load, discharge_limit)
        batt_can_out = max(0.0, soc - soc_min) # kWh *côté batterie*
        batt_to_load = 0.0
        if batt_out_limit > 0 and (allow_discharge_in_hc or not in_hc):
            # énergie restituée au load = retiré_du_SoC * eff
            batt_to_load = min(batt_out_limit, batt_can_out * eff)
            if batt_to_load > 0:
                soc -= batt_to_load / (eff if eff > 0 else 1.0)
                remaining_load -= batt_to_load

        # 3) Le reste du load est à importer
        imp_load = max(0.0, remaining_load)

        # 4) PV -> batterie (stockage) limité par capacité restante + limite horaire
        pv_in_limit = available_pv if charge_limit is None else min(available_pv, charge_limit)
        can_store_in = (soc_max - soc) / (eff if eff > 0 else 1.0)  # kWh côté entrée PV
        pv_to_batt = min(pv_in_limit, max(0.0, can_store_in))
        if pv_to_batt > 0:
            soc += pv_to_batt * eff
            available_pv -= pv_to_batt
            
        # 5) Surplus PV restant = export
        export = max(0.0, available_pv)
        
        # 6) Charge réseau en HC pour atteindre la cible (séparée du load)
        imp_grid = 0.0
        if in_hc and grid_charge:
            target_soc = batt_kwh * max(0.0, min(1.0, grid_target_soc))
            if soc < target_soc:
                need_batt_side = target_soc - soc                              # kWh côté batterie
                grid_in = min(need_batt_side / (eff if eff > 0 else 1.0),      # kWh côté réseau
                              max(0.0, grid_charge_limit))
                if grid_in > 0:
                    soc += grid_in * eff
                    imp_grid += grid_in

        # 7) Clamp SoC
        soc = max(soc_min, min(soc_max, soc))

        # 2) PV → batterie (stockage), borné par capacité restante
        #pv_in_limit = available_pv if charge_limit is None else min(available_pv, charge_limit)
        #can_store = (soc_max - soc) / eff if eff > 0 else 0.0
        #charge_from_pv_in = min(pv_in_limit, max(0.0, can_store))
        #pv_to_batt = charge_from_pv_in                     # côté entrée (kWh PV)
        #soc += pv_to_batt * eff
        #available_pv -= pv_to_batt

        # 3) Batterie → charges (décharge)
        #batt_avail_out = max(0.0, soc - soc_min) * eff
        #batt_out_limit = remaining_load if discharge_limit is None else min(remaining_load, discharge_limit)
        #batt_to_load = min(batt_out_limit, batt_avail_out)
        #soc -= batt_to_load / (eff if eff > 0 else 1.0)
        #remaining_load -= batt_to_load

        # 4) Import pour le reste de charge
        #imp = max(0.0, remaining_load)

        # 5) Export du surplus PV
        #exp = max(0.0, available_pv)

        # 6) Recharge réseau en HC (optionnelle)
        #try:
        #    hour_local = int(str(r["date"])[11:13])
        #except:
        #    hour_local = -1
        #if grid_charge and hour_local in grid_hours:
        #    target_soc = batt_kwh * grid_target_soc
        #    if soc < target_soc:
        #        need = target_soc - soc
        #        # quantité entrée batterie (côté entrée réseau)
        #        grid_in = min(need / (eff if eff > 0 else 1.0), grid_charge_limit)
        #        soc += grid_in * eff
        #        imp += grid_in
#
        ## clamp SoC
        #soc = max(soc_min, min(soc_max, soc))
#
        out.append({
            "date": r["date"],
            "pv": pv,
            "load": load,
            "export": export,
            "import": imp_load + imp_grid,
            "soc": soc,
            "pv_direct": pv_direct,
            "batt_to_load": batt_to_load,
            "pv_to_batt": pv_to_batt
        })
    return out


def run_simu(cfg: dict) -> None:
    """
        Lancement de la simulation
    """
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

    if not Path(IN_CSV).exists():
        print(f"[ERREUR] Fichier horaire introuvable: {IN_CSV}\nLance d'abord --mode report.")
        sys.exit(1)

    # charge data horaire
    rows=[]
    with open(IN_CSV) as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append({"date": r["date"], "pv": float(r["pv_diff"]), "load": float(r["load_diff"])})

    # base
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

    # combinaisons
    results=[]
    for fct in PV_FACTORS:
        scaled = simulate_pv_scale(rows, fct)
        for batt_kwh in BATTERY_SIZES:
            sim = simulate_battery(
                rows=scaled,
                grid_hours=[0,1,2,3,4,5,22,23],                 # Heures creuses
                batt_kwh=batt_kwh,                              # batterie utilisée
                eff=EFF,                                        # Batterie efficiency
                soc_reserve=BATT_MIN_SOC,                       # minimum de capacité pour la batterie
                initial_soc=INITIAL_SOC,                        # batterie avec un pourcentage de départ
                discharge_limit=MAX_DISCHARGE_KW_PER_HOUR,      # décharge limite de batterie
                allow_discharge_in_hc=ALLOW_DISCHARGE_IN_HC     # Permet la décharge en heure creuse
            )
            daily = aggregate_daily(sim)
            st  = compute_stats(sim)
            results.append((fct, batt_kwh, st))

    # CSV
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pv_factor","battery_kWh","pv_tot_kWh","load_tot_kWh","import_kWh","export_kWh","AC_%","TC_%"])
        for fct, b, st in results:
            w.writerow([fct, b, st["pv_tot"], st["load_tot"], st["import_tot"], st["export_tot"], st["ac"], st["tc"]])

    # filtrage selon seuils
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
    
    sim = simulate_battery(
        rows=scaled_rows,
        grid_hours=[0,1,2,3,4,5,22,23],                 # Heures creuses
        batt_kwh=batt_kwh,                              # batterie utilisée
        eff=EFF,                                        # Batterie efficiency
        soc_reserve=BATT_MIN_SOC,                       # minimum de capacité pour la batterie
        initial_soc=INITIAL_SOC,                        # batterie avec un pourcentage de départ
        discharge_limit=MAX_DISCHARGE_KW_PER_HOUR,      # décharge limite de batterie
        allow_discharge_in_hc=ALLOW_DISCHARGE_IN_HC     # Permet la décharge en heure creuse
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
    save_sim_detail(csv_detail_path, sim, context=context)
    
    # Affichage
    ui.passing(passing, TARGET_AC_MIN, TARGET_AC_MAX, TARGET_TC_MIN, limit=10)
    if passing:
        # déjà triés : passer passing[0]
        ui.best(passing[0], cfg["PV_ACTUAL_KW"])

    ui.definitions()

def run_plot(cfg: dict, args=None):
    """
        Affiche en console les barres horaires (import/batterie/PV et export)
        pour un jour donné à partir d'un CSV de simulation horaire.
        Le CSV doit contenir: date,pv,load,pv_direct,pv_to_batt,batt_to_load,import,export,soc
    """

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

    # chemin CSV de la simulation
    sim_csv_path = None
    if args and getattr(args, "csv", None):
        sim_csv_path = args.csv
    else:
        sim_csv_path = cfg.get("OUT_CSV_SIM_DETAIL") or cfg.get("OUT_CSV_DETAIL") or "ha_energy_sim_detail.csv"

    p_sim = Path(sim_csv_path)
    if not p_sim.exists():
        ui.error(f"CSV introuvable: {p}\nGénère-le d'abord via --mode simu (save_sim_detail).")
        return

    # chemin CSV de la prod/conso actuelle
    base_csv_path = cfg.get("PLOT_BASE_CSV", "ha_energy_import_export_hourly.csv")
    p_base = Path(base_csv_path)
    if not p_base.exists():
        ui.error(f"CSV introuvable")
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

    # Affichage
    ui.plot_day_cli_bipolar_compare(
        base_csv_path=str(p_base),
        sim_csv_path=str(p_sim),
        day=day,
        max_kwh=None,       # autoscale commun
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
    ap = argparse.ArgumentParser(description="PV/Load report & simulation (HA + Sizing)")
    ap.add_argument("--mode", choices=["report","simu","plot"], required=True, help="report: fetch & compute; simu: run combos on hourly CSV; plot: bar charts in console")
    ap.add_argument("--config", default="pv_config.json", help="chemin du JSON de config (défaut: pv_config.json)")
    # --- options pour le mode report ---
    ap.add_argument("--source", choices=["ha_ws","csv","enlighten"], default="ha_ws",help="source de données pour --mode report")
    # --- options pour le mode plot ---
    ap.add_argument("--day", help="Jour à afficher (YYYY-MM-DD) pour --mode plot")
    ap.add_argument("--max-kwh", type=float, default=5.0,
                    help="Échelle verticale (kWh) pour les barres en --mode plot (défaut 5.0)")
    ap.add_argument("--csv", help="Override: chemin du CSV horaire détaillé (sinon OUT_CSV_SIM_DETAIL du JSON)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))

    if args.mode == "report":
        run_report(cfg, args)
    elif args.mode == "simu":
        run_simu(cfg)
    else:
        run_plot(cfg, args)

if __name__ == "__main__":
    main()
