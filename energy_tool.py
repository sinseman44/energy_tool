#!/usr/bin/env python3
import json, os, sys, ssl, csv, argparse
from pathlib import Path

from sources.ha_ws_api import HAWebSocketSource
from sources.csv_file_api import CSVSource
from sources.enlighten_api import EnlightenSource  # prêt pour plus tard

from cli_output import ConsoleUI

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
    "PV_ACTUAL_KW":   4.0
}

ui = ConsoleUI()

def _as_float(x, name):
    try: return float(x)
    except: raise ValueError(f"Paramètre '{name}' doit être un nombre (float), reçu: {x!r}")

def _as_list_float(x, name):
    if not isinstance(x, list):
        raise ValueError(f"Paramètre '{name}' doit être une liste de nombres")
    return [float(v) for v in x]

def load_config(path: Path) -> dict:
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
    series = src.get_hourly_pv_load(cfg["START"], cfg["END"])

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

def simulate_battery(rows, batt_kwh, eff, charge_limit=None, discharge_limit=None):
    if batt_kwh <= 0:
        out=[]
        for r in rows:
            pv, ld = r["pv"], r["load"]
            self_used = min(pv, ld)
            out.append({"date":r["date"], "pv":pv, "load":ld,
                        "export":max(0.0,pv-self_used), "import":max(0.0,ld-self_used), "soc":0.0})
        return out
    soc=0.0; out=[]
    for r in rows:
        pv, ld = r["pv"], r["load"]; surplus = pv - ld
        if surplus >= 0:
            room = batt_kwh - soc
            if charge_limit is not None:
                storable_from_surplus = min(surplus, charge_limit) * eff
            else:
                storable_from_surplus = surplus * eff
            stored = max(0.0, min(room, storable_from_surplus))
            soc += stored
            exported = surplus - (stored / eff if eff>0 else 0.0)
            out.append({"date":r["date"], "pv":pv, "load":ld, "export":max(0.0,exported), "import":0.0, "soc":soc})
        else:
            demand = -surplus
            if discharge_limit is not None:
                deliverable = min(soc*eff, discharge_limit)
            else:
                deliverable = soc*eff
            used_from_batt = min(demand, deliverable)
            soc -= (used_from_batt / (eff if eff>0 else 1.0))
            imported = demand - used_from_batt
            out.append({"date":r["date"], "pv":pv, "load":ld, "export":0.0, "import":max(0.0,imported), "soc":max(0.0,min(batt_kwh,soc))})
        soc = max(0.0, min(batt_kwh, soc))
    return out

def run_simu(cfg: dict):
    IN_CSV = cfg["OUT_CSV_DETAIL"]   # on lit le CSV horaire produit par report
    OUT_CSV = cfg["OUT_CSV_SIMU"]
    TARGET_AC_MIN = cfg["TARGET_AC_MIN"]
    TARGET_AC_MAX = cfg["TARGET_AC_MAX"]
    TARGET_TC_MIN = cfg["TARGET_TC_MIN"]
    BATTERY_SIZES = cfg["BATTERY_SIZES"]
    PV_FACTORS = cfg["PV_FACTORS"]
    EFF = cfg["BATTERY_EFF"]
    START = cfg["START"]
    END = cfg["END"]
    PV_ACTUAL_KW = cfg["PV_ACTUAL_KW"]

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
    base_no_batt = simulate_battery(rows, 0.0, EFF)
    base_stats = compute_stats(base_no_batt)

    ui.summary("Situation actuelle", base_stats["pv_tot"], base_stats["load_tot"],
           base_stats["import_tot"], base_stats["export_tot"],
           base_stats["ac"], base_stats["tc"], START, END, PV_ACTUAL_KW)

    # combinaisons
    results=[]
    for fct in PV_FACTORS:
        scaled = simulate_pv_scale(rows, fct)
        for b in BATTERY_SIZES:
            sim = simulate_battery(scaled, b, EFF)
            st  = compute_stats(sim)
            results.append((fct, b, st))

    # CSV
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pv_factor","battery_kWh","pv_tot_kWh","load_tot_kWh","import_kWh","export_kWh","AC_%","TC_%"])
        for fct, b, st in results:
            w.writerow([fct, b, st["pv_tot"], st["load_tot"], st["import_tot"], st["export_tot"], st["ac"], st["tc"]])

    # filtrage selon seuils
    passing = [(fct,b,st) for (fct,b,st) in results if (TARGET_AC_MIN <= st["ac"] <= TARGET_AC_MAX) and (st["tc"] >= TARGET_TC_MIN)]

    ui.passing(passing, TARGET_AC_MIN, TARGET_AC_MAX, TARGET_TC_MIN, limit=10)
    if passing:
        # déjà triés dans ton script : passer passing[0]
        ui.best(passing[0], cfg["PV_ACTUAL_KW"])
    ui.definitions()

# =========================
# CLI
# =========================
def main():
    ap = argparse.ArgumentParser(description="PV/Load report & simulation (HA + Sizing)")
    ap.add_argument("--mode", choices=["report","simu"], required=True, help="report: fetch & compute; simu: run combos on hourly CSV")
    ap.add_argument("--config", default="pv_config.json", help="chemin du JSON de config (défaut: pv_config.json)")
    ap.add_argument("--source", choices=["ha_ws","csv","enlighten"], default="ha_ws",help="source de données pour --mode report")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))

    if args.mode == "report":
        run_report(cfg, args)
    else:
        run_simu(cfg)

if __name__ == "__main__":
    main()
