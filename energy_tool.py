#!/usr/bin/env python3
import json, os, sys, ssl, csv, argparse
from pathlib import Path
import csv
from datetime import datetime
from sources.ha_ws_api import HAWebSocketSource
from sources.csv_file_api import CSVSource
from sources.enlighten_api import EnlightenSource  # prêt pour plus tard

from cli_output import ConsoleUI
from collections import defaultdict

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

def save_sim_detail(csv_path: str, sim_rows: list, date_key: str = "date") -> None:
    """
        Écrit un CSV horaire détaillé pour un scénario unique.
        `sim_rows` est la liste de dicts renvoyée par `simulate_battery(...)`,
        chaque élément devant contenir au minimum :
            date, pv, load, pv_direct, pv_to_batt, batt_to_load, import, export, soc

        - date peut être str ("YYYY-MM-DD HH:MM") ou datetime -> converti en ISO minutes
        - les valeurs sont arrondies proprement
    """
    fields = [
        "date", "pv", "load", "pv_direct", "pv_to_batt",
        "batt_to_load", "import", "export", "soc"
    ]

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

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
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
            }
            w.writerow(row)


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

def simulate_battery(rows, batt_kwh, eff,
                     charge_limit=None, discharge_limit=None,
                     grid_charge=False, grid_hours=None,
                     grid_target_soc=0.8, grid_charge_limit=3.0,
                     soc_reserve=0.10,
                     initial_soc=0.0):
    """
        Simule l'utilisation d'une batterie sur une période entière
        en partant d'un SoC initial, sans remise à zéro quotidienne.

        rows          : liste des mesures horaires [{'date', 'pv', 'load'}]
        batt_kwh      : capacité totale de la batterie (kWh)
        eff           : rendement de charge/décharge (0-1)
        initial_soc   : fraction initiale de charge (0.0 → 0%, 1.0 → 100%)
        soc_reserve   : pourcentage minimal de SoC non déchargeable
        grid_charge   : autoriser la recharge sur le réseau en heures creuses
        grid_hours    : liste des heures creuses [0..23]
    """
    if batt_kwh <= 0:
        out=[]
        for r in rows:
            pv, ld = float(r["pv"]), float(r["load"])
            pv_direct = min(pv, ld)
            export = max(0.0, pv - pv_direct)
            imp = max(0.0, ld - pv_direct)
            out.append({
                "date": r["date"], "pv": pv, "load": ld,
                "export": export, "import": imp, "soc": 0.0,
                "pv_direct": pv_direct, "batt_to_load": 0.0, "pv_to_batt": 0.0
            })
        return out

    grid_hours = set(grid_hours or [])
    soc_min = batt_kwh * soc_reserve
    soc_max = batt_kwh
    soc = batt_kwh * max(0.0, min(1.0, initial_soc))

    out=[]
    for r in rows:
        pv = float(r["pv"]); load = float(r["load"])
        available_pv = pv
        remaining_load = load

        # 1) PV → charges direct
        pv_direct = min(available_pv, remaining_load)
        available_pv -= pv_direct
        remaining_load -= pv_direct

        # 2) PV → batterie (stockage), borné par capacité restante
        pv_in_limit = available_pv if charge_limit is None else min(available_pv, charge_limit)
        can_store = (soc_max - soc) / eff if eff > 0 else 0.0
        charge_from_pv_in = min(pv_in_limit, max(0.0, can_store))
        pv_to_batt = charge_from_pv_in                     # côté entrée (kWh PV)
        soc += pv_to_batt * eff
        available_pv -= pv_to_batt

        # 3) Batterie → charges (décharge)
        batt_avail_out = max(0.0, soc - soc_min) * eff
        batt_out_limit = remaining_load if discharge_limit is None else min(remaining_load, discharge_limit)
        batt_to_load = min(batt_out_limit, batt_avail_out)
        soc -= batt_to_load / (eff if eff > 0 else 1.0)
        remaining_load -= batt_to_load

        # 4) Import pour le reste de charge
        imp = max(0.0, remaining_load)

        # 5) Export du surplus PV
        exp = max(0.0, available_pv)

        # 6) Recharge réseau en HC (optionnelle)
        try:
            hour_local = int(str(r["date"])[11:13])
        except:
            hour_local = -1
        if grid_charge and hour_local in grid_hours:
            target_soc = batt_kwh * grid_target_soc
            if soc < target_soc:
                need = target_soc - soc
                # quantité entrée batterie (côté entrée réseau)
                grid_in = min(need / (eff if eff > 0 else 1.0), grid_charge_limit)
                soc += grid_in * eff
                imp += grid_in

        # clamp SoC
        soc = max(soc_min, min(soc_max, soc))

        out.append({
            "date": r["date"], "pv": pv, "load": load,
            "export": exp, "import": imp, "soc": soc,
            "pv_direct": pv_direct, "batt_to_load": batt_to_load, "pv_to_batt": pv_to_batt
        })
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
    INITIAL_SOC = float(cfg.get("INITIAL_SOC", 0.0))

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
        batt_kwh=0.0,          # pas de batterie
        eff=EFF,               # pas utilisé mais requis
        initial_soc=0.0        # SoC ignoré
    )
    base_stats = compute_stats(base_no_batt)

    ui.summary("Situation actuelle", base_stats["pv_tot"], base_stats["load_tot"],
           base_stats["import_tot"], base_stats["export_tot"],
           base_stats["ac"], base_stats["tc"], START, END, PV_ACTUAL_KW)

    # combinaisons
    results=[]
    for fct in PV_FACTORS:
        scaled = simulate_pv_scale(rows, fct)
        for batt_kwh in BATTERY_SIZES:
            sim = simulate_battery(
                rows=scaled,
                batt_kwh=batt_kwh,          # batterie utilisée
                eff=EFF,                    # Batterie efficiency
                initial_soc=INITIAL_SOC     # batterie avec un pourcentage de départ
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
    
    # on prend le premier qui passe (ou trie si tu veux un critère)
    pv_factor, batt_kwh, st = passing[0]

    # applique le facteur PV aux rows (copie légère)
    scaled_rows = [
        {"date": r["date"], "pv": float(r["pv"]) * pv_factor, "load": float(r["load"])}
        for r in rows
    ]
    
    sim = simulate_battery(
        rows=scaled_rows,
        batt_kwh=batt_kwh,     # batterie utilisée
        eff=EFF,                    # Batterie efficiency
        initial_soc=INITIAL_SOC     # batterie avec un pourcentage de départ
    )
    # chemin de sortie configurable (ajoute la clé dans ton JSON)
    csv_detail_path = cfg.get("OUT_CSV_SIM_DETAIL", "ha_energy_sim_detail.csv")
    save_sim_detail(csv_detail_path, sim)
    print(f"OK -> CSV horaire détaillé écrit dans {csv_detail_path}")
    
    # Affichage
    ui.passing(passing, TARGET_AC_MIN, TARGET_AC_MAX, TARGET_TC_MIN, limit=10)
    if passing:
        # déjà triés dans ton script : passer passing[0]
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

    # chemin CSV
    csv_path = None
    if args and getattr(args, "csv", None):
        csv_path = args.csv
    else:
        csv_path = cfg.get("OUT_CSV_SIM_DETAIL") or cfg.get("OUT_CSV_DETAIL") or "ha_energy_sim_detail.csv"

    p = Path(csv_path)
    if not p.exists():
        ui.error(f"CSV introuvable: {p}\nGénère-le d'abord via --mode simu (save_sim_detail).")
        return

    max_kwh = float(getattr(args, "max_kwh", 5.0) or 5.0)
    # Affiche
    ui.plot_day_cli(str(p))

# =========================
# CLI
# =========================
def main():
    ap = argparse.ArgumentParser(description="PV/Load report & simulation (HA + Sizing)")
    ap.add_argument("--mode", choices=["report","simu","plot"], required=True, help="report: fetch & compute; simu: run combos on hourly CSV; plot: bar charts in console")
    ap.add_argument("--config", default="pv_config.json", help="chemin du JSON de config (défaut: pv_config.json)")
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
