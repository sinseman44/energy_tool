# cli_output.py
from __future__ import annotations
import csv
import math

# Try rich import; graceful fallback to plain prints if unavailable
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.box import ROUNDED
    from rich.text import Text
    from rich.bar import Bar
    from rich.rule import Rule
    _HAS_RICH = True
except Exception:
    _HAS_RICH = False

class ConsoleUI:
    """
    Simple CLI UI for energy_tool.py
    - Pretty output if 'rich' is installed
    - Clean text fallback otherwise
    """

    def __init__(self):
        self.has_rich = _HAS_RICH
        self.console = Console() if self.has_rich else None

    # ---------- helpers ----------
    def _fmt_kwh(self, v: float) -> str:
        return f"{v:.0f}"

    def _fmt_pct(self, v: float) -> str:
        return f"{v:.1f}"

    # ---------- public API ----------
    def title(self, txt: str):
        if self.has_rich:
            self.console.print(Panel.fit(txt, border_style="cyan", title=""))
        else:
            print(f"\n=== {txt} ===")

    def summary(self, title: str, pv: float, load: float, imp: float, exp: float, ac: float, tc: float, start=None, end=None, pv_kw=None):
        if self.has_rich:
            if start and end:
                table = Table(title=title + " (" + start[:10] + " → " + end[:10] + ")", show_lines=True, box=ROUNDED, border_style="white")
            else:
                table = Table(title=title, show_lines=True, box=ROUNDED, border_style="white")
            table.add_column("PV (kWh)", justify="right")
            table.add_column("Conso (kWh)", justify="right")
            table.add_column("Import (kWh)", justify="right")
            table.add_column("Export (kWh)", justify="right")
            table.add_column("AC %", justify="right", style="cyan")
            table.add_column("TC %", justify="right", style="magenta")
            table.add_row(
                self._fmt_kwh(pv),
                self._fmt_kwh(load),
                self._fmt_kwh(imp),
                self._fmt_kwh(exp),
                self._fmt_pct(ac),
                self._fmt_pct(tc),
            )
            self.console.print(table)

            # Affichage de la puissance installée si dispo
            if pv_kw:
                self.console.print(f"[cyan]Installation PV présente: {pv_kw:.1f} kWc[/cyan]")
        else:
            if start and end:
                print(f"Situation actuelle ({start[:10]} → {end[:10]})")
            else:
                print(f"{title}")
            print(f"PV={pv:.0f} kWh, Load={load:.0f} kWh, Import={imp:.0f} kWh, Export={exp:.0f} kWh, "
                  f"AC={ac:.1f} %, TC={tc:.1f} %")

    def passing(self, passing, target_ac_min: float, target_ac_max: float, target_tc_min: float, limit: int = 10):
        """
            passing: list of tuples (pv_factor, battery_kWh, stats_dict)
            stats_dict keys: 'pv_tot','load_tot','import_tot','export_tot','ac','tc'
        """
        if not passing:
            msg = (f"Aucun scénario ne passe\n"
                   f"(AC dans [{target_ac_min:.0f} → {target_ac_max:.0f}] %, TC ≥ {target_tc_min:.0f} %)")
            if self.has_rich:
                self.console.print(Panel.fit(msg, border_style="red", title="Résultats"))
            else:
                print("\n[Résultats] " + msg)
            return

        hdr = (f"Scénarios valides: AC ∈ [{target_ac_min:.0f} → {target_ac_max:.0f}] %, "
               f"TC ≥ {target_tc_min:.0f} %")
        if self.has_rich:
            self.console.print(Panel.fit(hdr, border_style="green", title="Résultats"))
            table = Table(show_lines=True, box=ROUNDED, border_style="white")
            table.add_column("PV ×", justify="center")
            table.add_column("Batterie", justify="right")
            table.add_column("PV (kWh)", justify="right")
            table.add_column("Conso (kWh)", justify="right")
            table.add_column("Import (kWh)", justify="right")
            table.add_column("Export (kWh)", justify="right")
            table.add_column("AC %", justify="right", style="cyan")
            table.add_column("TC %", justify="right", style="magenta")
            for fct, b, st in passing[:limit]:
                table.add_row(
                    f"{fct:g}",
                    f"{int(b)} kWh",
                    self._fmt_kwh(st["pv_tot"]),
                    self._fmt_kwh(st["load_tot"]),
                    self._fmt_kwh(st["import_tot"]),
                    self._fmt_kwh(st["export_tot"]),
                    self._fmt_pct(st["ac"]),
                    self._fmt_pct(st["tc"]),
                )
            self.console.print(table)
        else:
            print("\n[Résultats] " + hdr)
            print(" PV× | Batt(kWh) |   PV  | Load | Imp | Exp |  AC% |  TC% ")
            print("-----+-----------+-------+------+-----+-----+------+------")
            for fct, b, st in passing[:limit]:
                print(f"{fct:>4g} | {int(b):>9} | {st['pv_tot']:>5.0f} | {st['load_tot']:>4.0f} | "
                      f"{st['import_tot']:>3.0f} | {st['export_tot']:>3.0f} | "
                      f"{st['ac']:>5.1f} | {st['tc']:>5.1f}")

    def best(self, best_tuple, pv_act):
        """
            best_tuple = (pv_factor, battery_kWh, stats_dict)
        """
        fct, b, st = best_tuple
        msg = (f"➡️  Meilleur compromis\n"
               f"PV ×{fct:g} = {fct * pv_act} kWc, Batterie {int(b)} kWh\n"
               f"AC={st['ac']:.1f} %, TC={st['tc']:.1f} %")
        if self.has_rich:
            self.console.print(Panel.fit(msg, border_style="cyan", title="Sélection"))
        else:
            print("\n[Sélection] " + msg)
            
    def definitions(self):
        """ 
            Definitions
        """
        msg = (
            "[bold]* Autoconsommation (AC)[/bold] = part de la production PV consommée directement (charges) et/ou via la batterie\n"
            "[bold]* Taux de couverture (TC)[/bold] = part de la consommation totale couverte par ton PV (direct + batterie)"
        )

        if self.has_rich:
            self.console.print(msg)
        else:
            print(msg.replace("[bold]", "").replace("[/bold]", ""))
            
    def _bar_segments(self, parts, width=30):
        """
            parts: list of tuples (ratio, char, color or None) ; ratio ∈ [0..1], somme ≤ 1
        """
        total = sum(p[0] for p in parts)

        # clamp
        ratios = [max(0.0, min(1.0, r)) for r,_,_ in parts]
        # convert to cells
        cells = [int(round(r * width)) for r in ratios]
        # adjust rounding to fit width
        diff = width - sum(cells)
        if diff != 0 and cells:
            cells[0] += diff  # petite correction simple

        if not self.has_rich:
            # fallback: concat chars
            return "".join(ch * n for n,(_,ch,_) in zip(cells, parts))

        t = Text()
        for n,(r,ch,color) in zip(cells, parts):
            if n <= 0: 
                continue
            seg = ch * n
            if color:
                t.append(seg, style=color)
            else:
                t.append(seg)
        return t

    def daily_bars(self, daily_dict, max_days=None, width=30):
        """
            daily_dict: { 'YYYY-MM-DD': {pv, load, imp, exp, pv_direct, batt_to_load, pv_to_batt} }
            Affiche 2 barres par jour :
            - Couverture conso (100% = load) : [pv_direct | batt_to_load | import]
            - Disposition PV    (100% = pv)   : [pv_direct | pv_to_batt | export]
        """
        days = list(daily_dict.items())
        if max_days:
            days = days[:max_days]

        title = "Profils journaliers (barres = 100%)"
        if self.has_rich:
            self.console.rule(title)
        else:
            print("\n" + title)

        for d, v in days:
            load = v["load"]; pv = v["pv"]
            pv_direct = v["pv_direct"]; batt_to_load = v["batt_to_load"]; imp = v["imp"]
            pv_to_batt = v["pv_to_batt"]; exp = v["exp"]

            # Barres en % (éviter /0)
            if load > 0:
                parts_load = [
                    (pv_direct / load, "█", "green"),
                    (batt_to_load / load, "█", "magenta"),
                    (imp / load, "█", "red"),
                ]
            else:
                parts_load = [(0," ",""),(0," ",""),(0," ","")]

            if pv > 0:
                parts_pv = [
                    (pv_direct / pv, "█", "green"),
                    (pv_to_batt / pv, "█", "yellow"),
                    (exp / pv, "█", "bright_black"),
                ]
            else:
                parts_pv = [(0," ",""),(0," ",""),(0," ","")]

            bar_load = self._bar_segments(parts_load, width=width)
            bar_pv   = self._bar_segments(parts_pv, width=width)
            if self.has_rich:
                self.console.print(f"[bold]{d}[/bold]  "
                                   f"[green]Conso[/green]: {bar_load} "
                                   f"[green]{(pv_direct/load*100 if load else 0):.0f}%[/green]/"
                                   f"[magenta]{(batt_to_load/load*100 if load else 0):.0f}%[/magenta]/"
                                   f"[red]{(imp/load*100 if load else 0):.0f}%[/red]")
                self.console.print(f"            "
                                   f"[cyan]PV   [/cyan]: {bar_pv} "
                                   f"[green]{(pv_direct/pv*100 if pv else 0):.0f}%[/green]/"
                                   f"[yellow]{(pv_to_batt/pv*100 if pv else 0):.0f}%[/yellow]/"
                                   f"[bright_black]{(exp/pv*100 if pv else 0):.0f}%[/bright_black]")
            else:
                print(f"{d}  Conso: {bar_load}  "
                      f"{(pv_direct/load*100 if load else 0):.0f}%/"
                      f"{(batt_to_load/load*100 if load else 0):.0f}%/"
                      f"{(imp/load*100 if load else 0):.0f}%")
                print(f"        PV   : {bar_pv}  "
                      f"{(pv_direct/pv*100 if pv else 0):.0f}%/"
                      f"{(pv_to_batt/pv*100 if pv else 0):.0f}%/"
                      f"{(exp/pv*100 if pv else 0):.0f}%")


    # --- petits helpers internes ---
    def _auto_delim(self, path):
        with open(path, "r", newline="") as f:
            head = f.readline()
            return ";" if head.count(";") > head.count(",") else ","

    def _as_float(self, x, default=0.0):
        try:
            return float(x)

        except Exception:
            return default

    def _hour_from(self, ts: str) -> int:
        # "YYYY-MM-DD HH:MM" ou ISO "YYYY-MM-DDTHH:MM:SS"
        try:
            return int(ts[11:13])

        except Exception:
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z","")).hour
            except Exception:
                return -1

    def _read_day_rows(self, csv_path: str, day: str):
        import csv
        delim = self._auto_delim(csv_path)
        rows = []

        with open(csv_path, "r", newline="") as f:
            rdr = csv.DictReader(f, delimiter=delim)
            for r in rdr:
                ts = str(r.get("date",""))
                if not ts.startswith(day):
                    continue
                h = self._hour_from(ts)
                if h < 0: 
                    continue

                rows.append({
                    "hour": h,
                    "pv_direct":    self._as_float(r.get("pv_direct")),
                    "pv_to_batt":   self._as_float(r.get("pv_to_batt")),
                    "batt_to_load": self._as_float(r.get("batt_to_load")),
                    "import":       self._as_float(r.get("import")),
                    "export":       self._as_float(r.get("export")),
                })

        # garantir 24h
        by_h = {r["hour"]: r for r in rows}
        out = []
        for h in range(24):
            out.append(by_h.get(h, {
                "hour": h, "pv_direct": 0.0, "pv_to_batt": 0.0,
                "batt_to_load": 0.0, "import": 0.0, "export": 0.0
            }))
        out.sort(key=lambda x: x["hour"])
        return out

    def _build_columns(self, stacks_per_hour, max_kwh: float, step_kwh: float, col_width: int, gap: int = 1):
        """
            Construit les colonnes empilées pour les 24 heures, avec espacement constant entre les heures.
            Retourne :
            - grid_rows : lignes ASCII/Rich
            - levels    : nb de niveaux verticaux
        """
        levels = max(1, int(math.ceil(max_kwh / step_kwh)))

        cols = []
        for hour_stack in stacks_per_hour:
            cells_per_seg = [int(round((v or 0.0) / step_kwh)) for (v, _style) in hour_stack]
            total_cells = sum(cells_per_seg)

            if total_cells > levels and cells_per_seg:
                excess = total_cells - levels
                i_max = max(range(len(cells_per_seg)), key=lambda i: cells_per_seg[i])
                cells_per_seg[i_max] = max(0, cells_per_seg[i_max] - excess)

            col_styles = []
            for n, (_v, style) in zip(cells_per_seg, hour_stack):
                if n > 0:
                    col_styles.extend([style] * n)
            if len(col_styles) < levels:
                col_styles.extend([""] * (levels - len(col_styles)))

            cols.append(col_styles[:levels])

        # Construit les lignes haut -> bas
        grid_rows = []
        for lvl in reversed(range(levels)):
            y_label = f"{(lvl + 1) * step_kwh:>4.1f}│"
            line = Text(y_label) if self.has_rich else y_label

            for h in range(24):
                style = cols[h][lvl]
                block = "█" * col_width if style else " " * col_width
                sep = " " * gap

                if self.has_rich:
                    if style:
                        line.append(block, style=style.strip("[]"))
                    else:
                        line.append(block)
                    line.append(sep)
                else:
                    line += block + sep

            grid_rows.append(line)

        return grid_rows, levels

    def _print_x_axis(self, levels: int, col_width: int, gap: int = 1):
        """
            Affiche l'axe X (heures 00..23) sous la grille.
            - levels : nombre de lignes verticales (juste pour aligner le label '0│')
            - col_width : largeur d'une barre par heure
            - gap : nombre d'espaces entre heures (doit correspondre à _build_columns)
        """
        total_left = " " * 3 + "0│"  # espace pour l'axe Y
        unit = col_width + gap

        labels = ""
        for h in range(24):
            # Place le label pile au centre du bloc (barre + gap)
            labels += f" {h:02d} ".center(unit)

        line = total_left + labels

        if self.has_rich:
            self.console.print(line)
        else:
            print(line)

    # ========= vue “axes” =========
    def plot_day_cli(self, csv_path: str, day: str = None, max_kwh: float = 5.0, step_kwh: float = 0.5, col_width: int = 2):
        """
            Affiche DEUX graphiques en console avec axes (heures 00..23 en X, kWh en Y).
            Si `day` n'est pas fourni, utilise le premier jour trouvé dans le CSV.

            csv_path: CSV horaire avec colonnes:
                date,pv,load,pv_direct,pv_to_batt,batt_to_load,import,export,soc
                max_kwh: hauteur max de l'axe Y (kWh)
                step_kwh: pas de graduation Y (kWh)
                col_width: largeur (caractères) par heure
        """
        # Auto-détection du séparateur
        delim = self._auto_delim(csv_path)
        all_dates = set()
        with open(csv_path, "r", newline="") as f:
            rdr = csv.DictReader(f, delimiter=delim)
            for row in rdr:
                ts = str(row.get("date", ""))
                if len(ts) >= 10:
                    all_dates.add(ts[:10])

        if not all_dates:
            msg = f"Aucune donnée trouvée dans {csv_path}"
            if self.has_rich:
                self.console.print(f"[red]❌ {msg}[/red]")
            else:
                print("❌ " + msg)
            return

        # Déterminer la date à tracer
        dates_sorted = sorted(list(all_dates))
        if not day:
            day = dates_sorted[0]  # par défaut : premier jour trouvé
        elif day not in all_dates:
            msg = f"La date {day} n'existe pas dans {csv_path}. Disponibles: {', '.join(dates_sorted)}"
            if self.has_rich:
                self.console.print(f"[red]❌ {msg}[/red]")
            else:
                print("❌ " + msg)
            return

        # Lecture des lignes pour ce jour uniquement
        day_rows = self._read_day_rows(csv_path, day)
        if not day_rows:
            msg = f"Aucune donnée trouvée pour {day} dans {csv_path}"
            if self.has_rich:
                self.console.print(f"[red]❌ {msg}[/red]")
            else:
                print("❌ " + msg)
            return

        # --------- 1) Consommation couverte ---------
        if self.has_rich:
            self.console.print(Panel.fit(f"[bold cyan]Consommation d'électricité[/bold cyan]\n{day}"))
        else:
            print(f"\nConsommation d'électricité — {day}")
            
        conso_stacks = []
        for r in day_rows:
            pvd = r["pv_direct"]; b2l = r["batt_to_load"]; imp = r["import"]
            conso_stacks.append([
                (pvd, "[orange1]"),
                (b2l, "[magenta]"),
                (imp, "[blue]"),
            ])

        grid_rows, levels = self._build_columns(conso_stacks, max_kwh, step_kwh, col_width + 1)

        for line in grid_rows:
            if self.has_rich: self.console.print(line)
            else: print(line)

        self._print_x_axis(levels, col_width)

        if self.has_rich:
            self.console.print("[dim]Légende : [orange1]PV direct[/], [magenta]Batterie→charges[/], [blue]Import[/][/dim]")
            self.console.print(Rule())

        # --------- 2) Disposition de la production ---------
        if self.has_rich:
            self.console.print(Panel.fit(f"[bold green]Production solaire[/bold green]\n{day}"))
        else:
            print(f"\nProduction solaire — {day}")

        pv_stacks = []
        for r in day_rows:
            pvd = r["pv_direct"]; p2b = r["pv_to_batt"]; exp = r["export"]
            pv_stacks.append([
                (pvd, "[orange1]"),
                (p2b, "[yellow3]"),
                (exp, "[grey74]"),
            ])

        grid_rows, levels = self._build_columns(pv_stacks, max_kwh, step_kwh, col_width + 1)

        for line in grid_rows:
            if self.has_rich: self.console.print(line)
            else: print(line)

        self._print_x_axis(levels, col_width)
        if self.has_rich:
            self.console.print("[dim]Légende : [orange1]PV direct[/], [yellow3]PV→batterie[/], [grey74]Export[/][/dim]")

