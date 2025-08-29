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
    from rich import box
    from rich.columns import Columns
    from rich.padding import Padding
    from rich.align import Align
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
    def _fmt_kwh(self,
                 v: float,
                 ) -> str:
        return f"{v:.0f}"

    def _fmt_pct(self,
                 v: float,
                 ) -> str:
        return f"{v:.1f}"

    # ---------- public API ----------
    def title(self,
              txt: str,
              ) -> None:
        if self.has_rich:
            self.console.print(Panel.fit(txt, border_style="cyan", title=""))
        else:
            print(f"\n=== {txt} ===")

    def summary(self,
                title: str,
                pv: float,
                load: float,
                imp: float,
                exp: float,
                ac: float,
                tc: float,
                start=None,
                end=None,
                pv_kw=None,
                ) -> None:
        """
        """
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

    def passing(self,
                passing,
                target_ac_min: float,
                target_ac_max: float,
                target_tc_min: float,
                limit: int = 10,
                ) -> None:
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

    def best(self,
             best_tuple,
             pv_act,
             ) -> None:
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
            
    def definitions(self) -> None:
        """ 
            Affichage des définitions
        """
        msg = (
            "[bold]* Autoconsommation (AC)[/bold] = part de la production PV consommée directement (charges) et/ou via la batterie\n"
            "[bold]* Taux de couverture (TC)[/bold] = part de la consommation totale couverte par ton PV (direct + batterie)"
        )

        if self.has_rich:
            self.console.print(msg)
        else:
            print(msg.replace("[bold]", "").replace("[/bold]", ""))

    def show_no_scenarios(self,
                          ac_min: float,
                          ac_max: float,
                          tc_min: float,
                          best: dict | None = None):
        """
            Affiche un message (rich) lorsqu'aucune combinaison simulée n'atteint les objectifs.

            Params
            ------
            ac_min : float   Autoconsommation minimale (%) visée
            ac_max : float   Autoconsommation maximale (%) (plafond)
            tc_min : float   Taux de couverture minimal (%) visé
            best   : dict|None  Optionnel. Un meilleur scénario trouvé (même s'il échoue),
                            ex: {"pv_factor": 2.2, "batt_kwh": 18, "ac": 82.4, "tc": 69.3}
        """
        if not self.has_rich:
            print(
                f"[Aucun scénario ne correspond] Cibles: AC ∈ [{ac_min:.0f};{ac_max:.0f}] %, TC ≥ {tc_min:.0f} %"
            )
            if best:
                print(
                    f"Meilleur obtenu: PV×{best.get('pv_factor')}, Batt {best.get('batt_kwh')} kWh "
                    f"(AC {best.get('ac',0):.1f} %, TC {best.get('tc',0):.1f} %)"
                )
            print(
                "- Assouplir les seuils (augmenter AC max ou diminuer TC min)\n"
                "- Étendre la grille PV_FACTORS / BATTERY_SIZES\n"
                "- Étudier une autre période (météo différente)"
            )
            return

        # Bloc "objectifs"
        t_goal = Table.grid(padding=(0, 1))
        t_goal.add_column(justify="right", style="bold")
        t_goal.add_column(justify="left")
        t_goal.add_row("AC visée :", f"[cyan]{ac_min:.0f}[/]–[cyan]{ac_max:.0f}[/] %")
        t_goal.add_row("TC visé  :", f"[cyan]{tc_min:.0f}[/] %")
        pnl_goal = Panel(t_goal, title="🎯 Objectifs", border_style="cyan", box=box.ROUNDED)

        # Bloc "meilleur obtenu" (optionnel)
        if best:
            t_best = Table.grid(padding=(0, 1))
            t_best.add_column(justify="right", style="bold")
            t_best.add_column(justify="left")
            t_best.add_row("PV ×",       f"[magenta]{best.get('pv_factor')}[/]")
            t_best.add_row("Batterie",   f"[magenta]{best.get('batt_kwh')}[/] kWh")
            t_best.add_row("AC obtenu",  f"[magenta]{best.get('ac',0):.1f}[/] %")
            t_best.add_row("TC obtenu",  f"[magenta]{best.get('tc',0):.1f}[/] %")
            pnl_best = Panel(t_best, title="⭐ Meilleur obtenu (non conforme)", border_style="magenta", box=box.ROUNDED)
        else:
            pnl_best = Panel("—", title="⭐ Meilleur obtenu", border_style="magenta", box=box.ROUNDED)

        # Bloc "pistes"
        tips = (
            "[white]- Élargir la plage d'AC (augmenter AC max) ou abaisser TC min\n"
            "- Ajouter des points dans [bold]PV_FACTORS[/] (ex: 2.7, 2.8…) et [bold]BATTERY_SIZES[/] (ex: +2 kWh)\n"
            "- Simuler une autre période (météo, saison, week-end vs semaine)\n"
            "- Activer charge réseau en HC si pertinent, ou ajuster SoC initial\n"
            "- Vérifier que les limites de puissance batt/charge dégradent pas le résultat[/]"
        )
        pnl_tips = Panel(tips, title="💡 Pistes d’ajustement", border_style="yellow", box=box.ROUNDED)

        # Conteneur principal
        header = Panel(
            Align.center("[bold red]Aucun scénario ne satisfait les objectifs[/]"),
            border_style="red",
            box=box.HEAVY
        )

        self.console.print()
        self.console.print(header)
        self.console.print()
        self.console.print(self._cols([pnl_goal, pnl_best]))  # helper colonne si tu en as un
        self.console.print()
        self.console.print(pnl_tips)
        self.console.print()

    # Si tu n'as pas déjà un helper pour afficher 2 colonnes:
    def _cols(self, items):
        """Affiche deux panels côte à côte (fallback en pile si largeur insuffisante)."""
        try:
            from rich.columns import Columns
            return Columns(items, equal=True, expand=True, padding=(0, 2))
        except Exception:
            # Fallback: on empile
            from rich.console import Group
            return Group(*items)

    def _bar_segments(self,
                      parts,
                      width=30,
                      ) -> str or Text:
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

    def daily_bars(self,
                   daily_dict,
                   max_days=None,
                   width=30,
                   ) -> None:
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
    def _auto_delim(self,
                    path,
                    ) -> str:
        with open(path, "r", newline="") as f:
            head = f.readline()
            return ";" if head.count(";") > head.count(",") else ","

    def _as_float(self,
                  x,
                  default=0.0,
                  ) -> float:
        try:
            return float(x)

        except Exception:
            return default

    def _hour_from(self,
                   ts: str,
                   ) -> int:
        # "YYYY-MM-DD HH:MM" ou ISO "YYYY-MM-DDTHH:MM:SS"
        try:
            return int(ts[11:13])

        except Exception:
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z","")).hour
            except Exception:
                return -1

    def _read_day_rows(self,
                       csv_path: str,
                       day: str,
                       report: bool = False,
                       ):
        """
            Lecture du fichier CSV en entrée pour en sortir un
            dictionnaire
        """
        delim = self._auto_delim(csv_path)
        rows = []
        
        with open(csv_path, "r", newline="") as f:
            rdr = csv.DictReader(f, delimiter=delim)
            # Détection des colonnes dispo
            for r in rdr:
                ts = str(r.get("date",""))
                if not ts.startswith(day):
                    continue
                h = self._hour_from(ts)
                if h < 0: 
                    continue

                if not report:
                    # ===== CSV SIMU =====
                    pvd = self._as_float(r.get("pv_direct"))
                    p2b = self._as_float(r.get("pv_to_batt"))
                    b2l = self._as_float(r.get("batt_to_load"))
                    imp = self._as_float(r.get("import"))
                    exp = self._as_float(r.get("export"))

                    # Reconstitution PV/Load totaux si absents
                    pv_total = self._as_float(r.get("pv"))
                    if pv_total is None:
                        pv_total = (pvd or 0.0) + (p2b or 0.0) + (exp or 0.0)
                    load_total = self._as_float(r.get("load"))
                    if load_total is None:
                        load_total = (pvd or 0.0) + (b2l or 0.0) + (imp or 0.0)

                    rows.append({
                        "hour": h,
                        "pv_direct":    pvd or 0.0,
                        "pv_to_batt":   p2b or 0.0,
                        "batt_to_load": b2l or 0.0,
                        "import":       imp or 0.0,
                        "export":       exp or 0.0,
                        "pv":           pv_total or 0.0,
                        "load":         load_total or 0.0,
                    })
                else:
                    # ===== CSV REPORT (ou mix) =====
                    # On veut voir PV et Load tels quels
                    pv  = self._as_float(r.get("pv_diff"))
                    if pv is None:
                        pv = self._as_float(r.get("pv")) or 0.0
                    load = self._as_float(r.get("load_diff"))
                    if load is None:
                        load = self._as_float(r.get("load")) or 0.0

                    # Import/Export : utiliser colonnes si présentes, sinon calcul
                    imp = self._as_float(r.get("import"))
                    exp = self._as_float(r.get("export"))
                    
                    # production d'énergie consommée (autoconsommée)
                    prod_cons = min(pv, load)

                    if imp is None and exp is None:
                        imp = max(load - pv, 0.0)
                        exp = max(pv - load, 0.0)
                    else:
                        imp = imp or 0.0
                        exp = exp or 0.0

                    rows.append({
                        "hour": h,
                        # pas de batterie en 'actuel'
                        "pv_direct":    0.0,
                        "pv_to_batt":   0.0,
                        "batt_to_load": 0.0,
                        "import":       imp,
                        "export":       exp,
                        "pv":           pv,
                        "load":         load,
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

    def _fmt_pct(self, v):
        """Accepte 0.8, '0.8', 80, '80', None → renvoie '80 %' ou '' si None."""
        if v is None:
            return ""
        try:
            x = float(v)
        except Exception:
            return str(v)
        # Si on pense que c'est une fraction (<=1.5), on convertit en %
        if x <= 1.5:
            return f"{x*100:.0f} %"
        return f"{x:.0f} %"

    def _sum_day(self, day_rows):
        """
            Sommes du jour et SoC début/fin (si présent).
        """
        tot = {
            "pv_direct": 0.0, "pv_to_batt": 0.0, "batt_to_load": 0.0,
            "import": 0.0, "export": 0.0, "pv": 0.0, "load": 0.0,
            "soc_start": None, "soc_end": None
        }
        for i, r in enumerate(day_rows):
            pvd = float(r.get("pv_direct", 0) or 0)
            p2b = float(r.get("pv_to_batt", 0) or 0)
            b2l = float(r.get("batt_to_load", 0) or 0)
            imp = float(r.get("import", 0) or 0)
            exp = float(r.get("export", 0) or 0)
            # si ton CSV contient 'pv' et 'load' par heure, prends-les, sinon reconstitue:
            pv  = float(r.get("pv", pvd + p2b + exp) or 0)
            load = float(r.get("load", pvd + b2l + imp) or 0)

            tot["pv_direct"]   += pvd
            tot["pv_to_batt"]  += p2b
            tot["batt_to_load"]+= b2l
            tot["import"]      += imp
            tot["export"]      += exp
            tot["pv"]          += pv
            tot["load"]        += load

            if "soc" in r and r["soc"] is not None and tot["soc_start"] is None:
                tot["soc_start"] = float(r["soc"])
            if "soc" in r and r["soc"] is not None:
                tot["soc_end"] = float(r["soc"])

        # indicateurs
        ac = 0.0 if tot["pv"]   <= 0 else 100.0 * (tot["pv_direct"] + tot["pv_to_batt"]) / tot["pv"]
        tc = 0.0 if tot["load"] <= 0 else 100.0 * (tot["pv_direct"] + tot["batt_to_load"]) / tot["load"]
        tot["ac"] = ac
        tot["tc"] = tc
        return tot

    def _print_context_panel(self, day: str, ctx: dict, totals: dict):
        """
        """

        t = Table.grid(expand=False)
        t.add_column(justify="right", style="bold dim")
        t.add_column(justify="left")

        if ctx:
            if "scenario" in ctx:   t.add_row("Scénario :", f"{ctx['scenario']}")
            if "pv_kwc" in ctx:     t.add_row("PV installé :", f"{ctx['pv_kwc']} kWc")
            if "pv_factor" in ctx:  t.add_row("Facteur PV :", f"x{ctx['pv_factor']}")
            if "batt_kwh" in ctx:   t.add_row("Batterie :", f"{ctx['batt_kwh']} kWh")
            if "eff" in ctx:
                try:
                    eff = float(ctx["eff"])
                    t.add_row("Rendement batt :", f"{eff*100:.0f} %")
                except Exception:
                    t.add_row("Rendement batt :", str(ctx["eff"]))
            if "initial_soc" in ctx:
                t.add_row("SoC initial :", self._fmt_pct(ctx["initial_soc"]))
            if ctx.get("grid_hours"):
                t.add_row("HC réseau :", ", ".join(f"{int(h):02d}h" for h in ctx["grid_hours"]))
            if "grid_target_soc" in ctx and ctx["grid_target_soc"] is not None:
                t.add_row("Cible SoC HC :", self._fmt_pct(ctx["grid_target_soc"]))

        # Résumé jour
        t.add_row("", "")
        t.add_row("Jour :", day)
        t.add_row("Prod (kWh) :", f"{totals['pv']:.1f} (dir {totals['pv_direct']:.1f} / batt {totals['pv_to_batt']:.1f} / exp {totals['export']:.1f})")
        t.add_row("Conso (kWh) :", f"{totals['load']:.1f} (PVdir {totals['pv_direct']:.1f} / batt {totals['batt_to_load']:.1f} / imp {totals['import']:.1f})")
        if totals.get("soc_start") is not None or totals.get("soc_end") is not None:
            t.add_row("SoC (début→fin) :", f"{totals.get('soc_start','?')} → {totals.get('soc_end','?')}")
        t.add_row("Autoconsommation :", f"{totals['ac']:.1f} %")
        t.add_row("Couverture :", f"{totals['tc']:.1f} %")

        self.console.print(Panel(t, title="[bold]Contexte[/bold]", border_style="cyan"))    

    def _build_columns_bipolar(self, stacks_up, stacks_dn,
                               max_kwh: float, step_kwh: float,
                               col_width: int, gap: int):
        """
            Graphe bipolaire façon HA :
            - Haut = consommation couverte  (PV direct, Batt→charges, Import)
            - Bas  = disposition production (PV direct, PV→batt, Export)
            Échelle symétrique ; labels du BAS affichés en POSITIF (0..X), mais les barres descendent.
        """
        levels = max(1, int(math.ceil(max_kwh / step_kwh)))  # mêmes niveaux haut/bas

        def build_cols(stacks):
            cols = []
            for stack in stacks:
                cells = [int(round((v or 0.0) / step_kwh)) for (v, _s) in stack]
                total = sum(cells)
                if total > levels and cells:
                    # clip sur le plus gros segment
                    i = max(range(len(cells)), key=lambda k: cells[k])
                    cells[i] = max(0, cells[i] - (total - levels))
                col = []
                for n, (_v, style) in zip(cells, stack):
                    if n > 0:
                        col.extend([style] * n)
                if len(col) < levels:
                    col.extend([""] * (levels - len(col)))
                cols.append(col[:levels])  # bas -> haut
            return cols

        cols_up = build_cols(stacks_up)    # bas->haut
        cols_dn = build_cols(stacks_dn)    # bas->haut (on affichera sous 0)

        grid = []

        # ---- PARTIE HAUTE : du haut vers 0 (labels positifs)
        for lvl in range(levels - 1, -1, -1):
            ylab = f"{(lvl + 1) * step_kwh:>4.1f}│"
            line = Text(ylab) if self.has_rich else ylab
            for h in range(24):
                style = cols_up[h][lvl]
                block = "█" * col_width if style else " " * col_width
                sep = " " * gap
                if self.has_rich:
                    line.append(block, style=style.strip("[]") if style else None)
                    line.append(sep)
                else:
                    line += block + sep
            grid.append(line)

        # ---- LIGNE ZÉRO (pointillés)
        left = " " * 3 + "0│"
        dash = "┄" * col_width + " " * gap
        grid.append(left + dash * 24)

        # ---- PARTIE BASSE : de 0 vers le bas
        # >>> ICI on AFFICHE DES LABELS POSITIFS (0.5, 1.0, …), MAIS on dessine en dessous de 0.
        for lvl in range(levels):
            ylab = f"{(lvl + 1) * step_kwh:>4.1f}│"  # labels POSITIFS
            line = Text(ylab) if self.has_rich else ylab
            for h in range(24):
                style = cols_dn[h][lvl]
                block = "█" * col_width if style else " " * col_width
                sep = " " * gap
                if self.has_rich:
                    line.append(block, style=style.strip("[]") if style else None)
                    line.append(sep)
                else:
                    line += block + sep
            grid.append(line)
        return grid, levels


    def _print_x_axis_bipolar(self, col_width: int, gap: int = 1):
        """
            Affiche l'axe X aligné sous la grille bipolaire. Labels centrés sous chaque (col_width+gap).
        """
        unit = col_width + gap
        left = " " * 3 + " │"   # aligne sous les labels Y (4) et le séparateur vertical
        labels = "".join(f"{h:02d}".center(unit) for h in range(24))
        line = left + labels
        if self.has_rich:
            self.console.print(line)
        else:
            print(line)

    def _metrics_from_rows(self,
                           rows: list[dict],
                           report: bool,
                           ) -> dict:
        """
            Calcule PV, Conso, Import, Export, AC%, TC%, Onsite.
        """
        pv   = sum(r.get("pv", 0.0) for r in rows)
        load = sum(r.get("load", 0.0) for r in rows)
        imp  = sum(r.get("import", 0.0) for r in rows)
        exp  = sum(r.get("export", 0.0) for r in rows)
        if report:
            onsite = max(pv - exp, 0.0)
        else:
            onsite = sum((r.get("pv_direct", 0.0) + r.get("batt_to_load", 0.0)) for r in rows)
        ac = (onsite / pv * 100.0)   if pv   > 1e-9 else 0.0
        tc = (onsite / load * 100.0) if load > 1e-9 else 0.0
        return {"pv": pv,
                "load": load,
                "imp": imp,
                "exp": exp,
                "ac": ac,
                "tc": tc,
                "onsite": onsite}


    def _print_metrics_line(self,
                            title: str,
                            m: dict,
                            ):
        """
            Affiche une ligne compacte de stats sous un graphe.
        """
        txt = (f"[dim]{title}  "
               f"PV={m['pv']:.1f} kWh  Conso={m['load']:.1f} kWh  "
               f"Import={m['imp']:.1f}  Export={m['exp']:.1f}  "
               f"AC={m['ac']:.1f}%  TC={m['tc']:.1f}%[/dim]")
        if self.has_rich:
            from rich.text import Text
            self.console.print(Text.from_markup(txt))
        else:
            print(txt.replace("[dim]","").replace("[/dim]",""))

    def _print_metrics_panel(self,
                             title: str,
                             m: dict,
                             style: str = "cyan",
                             ) -> Panel:
        """
            Affiche un encart sous le graphe avec les métriques clés.
        """
        table = Table.grid(padding=(0, 2))
        table.add_row("PV :",     f"{m['pv']:.1f} kWh", "Conso :", f"{m['load']:.1f} kWh")
        table.add_row("Import :", f"{m['imp']:.1f} kWh", "Export :", f"{m['exp']:.1f} kWh")
        table.add_row("AC :",     f"{m['ac']:.1f} %",   "TC :",     f"{m['tc']:.1f} %")
        return Panel(
            table,
            title=title,
            title_align="left",
            border_style=style,
            box=box.ROUNDED
        )

    def _print_side_by_side_panels(self,
                                   left_panel: Panel,
                                   right_panel: Panel,
                                   col_width: int = 2,
                                   gap: int = 1,
                                   ) -> None:
        """
            Aligne les 2 encarts sous les graphes :
            - on indente à gauche de la largeur de l'axe Y (labels + '│')
            - on affiche dans deux colonnes égales
        """
        # largeur d'indentation = exactement ce que tu utilises pour l'axe Y
        # (dans tes graphes tu fais f"{val:>4.1f}│" → 4+1+1 = 6)
        axis_pad = len(f"{0:>4.1f}│")  # == 6

        # largeur intérieure des barres (24 heures) si tu veux fixer la largeur des panels
        plot_inner = 24 * col_width + (23 * gap)
        # on fixe la largeur des panels à la largeur des barres (optionnel mais clean)
        left_panel  = Panel(left_panel.renderable,
                            title=left_panel.title,
                            border_style=left_panel.border_style,
                            box=left_panel.box,
                            width=plot_inner)
        right_panel = Panel(right_panel.renderable,
                            title=right_panel.title,
                            border_style=right_panel.border_style,
                            box=right_panel.box,
                            width=plot_inner)
        
        # indent by the Y-axis width so the panel starts exactly under the bars
        left_padded  = Padding(left_panel,  (0, 0, 0, axis_pad))
        right_padded = Padding(right_panel, (0, 38, 0, axis_pad))

        # crucial: left-align inside each column (Columns centers by default)
        left_aligned  = Align.left(left_padded)
        right_aligned = Align.left(right_padded)

        # deux colonnes égales, alignées avec les deux graphes
        self.console.print(Columns([left_aligned, right_aligned], 
                            equal=True,
                            expand=True,
                            padding=(0, 4)))

    # ========= vue “axes” =========
    def plot_day_cli(self, 
                     csv_path: str,
                     day: str = None,
                     max_kwh: float = 5.0,
                     step_kwh: float = 0.5,
                     col_width: int = 2,
                     context=None):
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

        # ---- extraire contexte depuis la première ligne du jour, si présent ----
        meta_ctx = {}
        try:
            # relire la 1re ligne brute du jour pour attraper les colonnes meta
            delim = self._auto_delim(csv_path)
            with open(csv_path, "r", newline="") as f:
                rdr = csv.DictReader(f, delimiter=delim)
                for r in rdr:
                    ts = str(r.get("date",""))
                    if ts.startswith(day):
                        # colonnes meta si elles existent
                        def _getf(key): 
                            v = r.get(key)
                            try: return float(v) if v not in (None,"") else None
                            except: return v
                        meta_ctx = {
                            "pv_factor": _getf("pv_factor"),
                            "batt_kwh": _getf("batt_kwh"),
                            "eff": _getf("eff"),
                            "initial_soc": _getf("initial_soc"),
                            "pv_kwc": _getf("pv_kwc"),
                            "scenario": r.get("scenario") or None,
                        }
                        break
        except Exception:
            meta_ctx = {}

        # Contexte final = meta du CSV (prioritaire) éventuellement fusionné avec `context=` passé par l'appelant
        ctx = {**(context or {}), **{k: v for k, v in meta_ctx.items() if v is not None}}
        totals = self._sum_day(day_rows)

        # Affiche le contexte AVANT les deux graphes
        if self.has_rich:
            self._print_context_panel(day, ctx, totals)
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

    def plot_day_cli_bipolar(self, csv_path: str, day: str = None,
                             max_kwh: float = 5.0, step_kwh: float = 0.5,
                             col_width: int = 2, gap: int = 1, context: dict | None = None):
        """
            Un seul graphique bipolaire façon Home Assistant :
            - Haut : consommation couverte (PV direct, Batt→charges, Import)
            - Bas  : disposition production (PV direct, PV→batt, Export)
        """
        # auto-sélection du jour si non précisé
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
            self.console.print(f"[red]❌ {msg}[/red]" if self.has_rich else "❌ "+msg)
            return
        dates_sorted = sorted(all_dates)
        if not day:
            day = dates_sorted[0]
        elif day not in all_dates:
            msg = f"La date {day} n'existe pas dans {csv_path}. Disponibles: {', '.join(dates_sorted)}"
            self.console.print(f"[red]❌ {msg}[/red]" if self.has_rich else "❌ "+msg)
            return

        # lecture des lignes jour
        day_rows = self._read_day_rows(csv_path, day)
        if not day_rows:
            msg = f"Aucune donnée trouvée pour {day} dans {csv_path}"
            self.console.print(f"[red]❌ {msg}[/red]" if self.has_rich else "❌ "+msg)
            return

        # méta-contexte depuis 1ère ligne + context param
        meta_ctx = {}
        try:
            with open(csv_path, "r", newline="") as f:
                rdr = csv.DictReader(f, delimiter=delim)
                for r in rdr:
                    ts = str(r.get("date",""))
                    if ts.startswith(day):
                        def _getf(k):
                            v = r.get(k)
                            try: return float(v) if v not in (None,"") else None
                            except: return v
                        meta_ctx = {
                            "pv_factor": _getf("pv_factor"),
                            "batt_kwh": _getf("batt_kwh"),
                            "eff": _getf("eff"),
                            "initial_soc": _getf("initial_soc"),
                            "pv_kwc": _getf("pv_kwc"),
                            "scenario": r.get("scenario") or None,
                        }
                        break
        except Exception:
            meta_ctx = {}
        ctx = {**(context or {}), **{k:v for k,v in meta_ctx.items() if v is not None}}

        # totaux & panneau de contexte
        totals = self._sum_day(day_rows)
        if self.has_rich:
            self._print_context_panel(day, ctx, totals)

        # stacks haut = conso couverte ; bas = disposition PV
        up = []
        dn = []
        up_max, dn_max = 0.0, 0.0
        for r in day_rows:
            pvd = r["pv_direct"]; b2l = r["batt_to_load"]; imp = r["import"]
            p2b = r["pv_to_batt"]; exp = r["export"]
            up.append([
                (pvd, "[orange1]"),
                (b2l, "[magenta]"),
                (imp, "[blue]"),
            ])
            dn.append([
                (p2b, "[yellow3]"),
                (exp, "[grey74]"),
            ])
            up_max = max(up_max, pvd + b2l + imp)
            dn_max = max(dn_max, p2b + exp)

        # Autoscale symétrique si max_kwh non fourni
        if max_kwh is None:
            m = max(up_max, dn_max)
            # arrondit à un multiple de step_kwh (ex : 0.5 → 0.5, 0.8 → 1.0, etc.)
            max_kwh = step_kwh * math.ceil(m / step_kwh)
            if max_kwh == 0: 
                max_kwh = step_kwh

        # construire et afficher la grille bipolaire
        if self.has_rich:
            self.console.print(Panel.fit(f"[bold]Profil horaire[/bold]\n{day}"))

        grid, _levels = self._build_columns_bipolar(up, dn, max_kwh, step_kwh, col_width, gap)
        for line in grid:
            if self.has_rich: self.console.print(line)
            else: print(line)

        self._print_x_axis_bipolar(col_width, gap)

        if self.has_rich:
            self.console.print(
                "[dim]Haut : [orange1]PV direct[/], [magenta]Batt→charges[/], [blue]Import[/]  "
                "Bas : [yellow3]PV→batterie[/], [grey74]Export[/][/dim]"
            )

    def plot_day_cli_bipolar_compare(
        self,
        base_csv_path: str,
        sim_csv_path: str,
        day: str | None = None,
        max_kwh: float | None = None,
        step_kwh: float = 0.5,
        col_width: int = 2,
        gap: int = 1,
        context: dict | None = None,
        titles: tuple[str, str] = ("Actuel", "Simulé"),
    ) -> None:
        """
            Affiche DEUX graphes bipolaires côte à côte (avant / après) avec la même échelle.
            Gauche = 'base_csv_path' (situation actuelle), Droite = 'sim_csv_path' (simulation).
        """
        def _first_day(csv_path: str) -> str | None:
            delim = self._auto_delim(csv_path)
            days = set()
            with open(csv_path, "r", newline="") as f:
                for r in csv.DictReader(f, delimiter=delim):
                    ts = str(r.get("date", ""))
                    if len(ts) >= 10:
                        days.add(ts[:10])
            return sorted(days)[0] if days else None

        # Choix du jour (par défaut : premier jour dispo dans le CSV “base”)
        if not day:
            day = _first_day(base_csv_path)
        if not day:
            self.console.print("[red]❌ Aucun jour détecté dans le CSV de base[/red]" if self.has_rich else "❌ Aucun jour dans le CSV de base")
            return

        # Lecture des lignes du jour (base + sim)
        base_rows = self._read_day_rows(base_csv_path, day, report = True)
        if not base_rows:
            self.console.print(f"[red]❌ Pas de données 'Actuel' pour {day}[/red]" if self.has_rich else f"❌ Pas de données 'Actuel' pour {day}")
            return
        sim_rows  = self._read_day_rows(sim_csv_path, day, report = False)
        if not sim_rows:
            self.console.print(f"[red]❌ Pas de données 'Simulé' pour {day}[/red]" if self.has_rich else f"❌ Pas de données 'Simulé' pour {day}")
            return

        # Totaux + contexte (si tu veux afficher deux panneaux au-dessus)
        base_tot = self._sum_day(base_rows)
        sim_tot  = self._sum_day(sim_rows)

        # Contexte depuis CSV (1re ligne du jour), prioritaire sur context_*
        def _meta_from_csv(csv_path: str, day: str) -> dict:
            try:
                delim = self._auto_delim(csv_path)
                with open(csv_path, "r", newline="") as f:
                    for r in csv.DictReader(f, delimiter=delim):
                        ts = str(r.get("date",""))
                        if ts.startswith(day):
                            def _getf(k):
                                v = r.get(k)
                                try: return float(v) if v not in (None,"") else None
                                except: return v
                            return {
                                "pv_factor": _getf("pv_factor"),
                                "batt_kwh": _getf("batt_kwh"),
                                "eff": _getf("eff"),
                                "initial_soc": _getf("initial_soc"),
                                "pv_kwc": _getf("pv_kwc"),
                                "scenario": r.get("scenario") or "Comparatif horaire",
                            }
            except Exception:
                pass
            return {}

        ctx  = {**(context or {}),  **{k:v for k,v in _meta_from_csv(sim_csv_path, day).items() if v is not None}}

        # Affiche un bandeau titre général
        #if self.has_rich:
        #    self.console.print(Panel.fit(f"[bold]Comparatif horaire[/bold]\n{day}"))

        # --- Prépare stacks (haut/bas) et max pour les DEUX graphes ---
        def _stacks_from_rows(rows, is_report: bool = False):
            """
                Fabrique les piles haut/bas et retourne (up, dn, up_max, dn_max).
                - Si le CSV est 'simu' (avec pv_direct/pv_to_batt/batt_to_load), on les utilise.
                - Si le CSV est 'report' (pv_diff/load_diff/import/export), on déduit pv_direct/import/export.
            """
            up, dn = [], []
            up_max = dn_max = 0.0
            for r in rows:
                # détecte le type de ligne
                if not is_report and "pv_direct" in r:
                    # Simulation complète => on affiche tout
                    pvd = float(r.get("pv_direct", 0) or 0)
                    b2l = float(r.get("batt_to_load", 0) or 0)
                    imp = float(r.get("import", 0) or 0)
                    p2b = float(r.get("pv_to_batt", 0) or 0)
                    exp = float(r.get("export", 0) or 0)
                    
                    up.append([(pvd, "[orange1]"), (b2l, "[magenta]"), (imp, "[blue]")])
                    dn.append([(p2b, "[yellow3]"), (exp, "[grey74]")])

                    up_max = max(up_max, pvd + b2l + imp)
                    dn_max = max(dn_max, p2b + exp)
                else:
                    # CSV report (pv_diff/load_diff/import/export)
                    pv   = float(r.get("pv_diff", 0) or r.get("pv", 0) or 0)
                    load = float(r.get("load_diff", 0) or r.get("load", 0) or 0)
                    imp  = float(r.get("import", max(load - pv, 0)) or 0)
                    exp  = float(r.get("export", max(pv - load, 0)) or 0)

                    prod_cons = min(pv, load)
                    # Ici : on affiche séparément la prod PV et la conso totale
                    #up.append([(pv, "[orange1]"), (load, "[cyan]"), (imp, "[blue]")])
                    up.append([(prod_cons, "[orange1]"), (imp, "[blue]")])
                    dn.append([(exp, "[grey74]")])

                    up_max = max(up_max, pv + imp)
                    dn_max = max(dn_max, exp)

            return up, dn, up_max, dn_max

        base_up, base_dn, base_upmax, base_dnmax = _stacks_from_rows(base_rows, is_report=True)
        sim_up,  sim_dn,  sim_upmax,  sim_dnmax  = _stacks_from_rows(sim_rows, is_report=False)

        # Échelle commune (symétrique)
        if max_kwh is None:
            m = max(base_upmax, base_dnmax, sim_upmax, sim_dnmax)
            if m > 0:
                max_kwh = (step_kwh * math.ceil(m / step_kwh)) + step_kwh
            else:
                step_kwh

        # Construire les deux grilles
        base_grid, _ = self._build_columns_bipolar(base_up, base_dn, max_kwh, step_kwh, col_width, gap)
        sim_grid,  _ = self._build_columns_bipolar(sim_up,  sim_dn,  max_kwh, step_kwh, col_width, gap)

        # Titre colonnes
        def _title_cell(txt: str, width_chars: int):
            # Largeur totale d’un graphe : 4(pour Y) + 2(caractères '0│' ou ' x│') + 24*(col_width+gap)
            total = 4 + 2 + 24 * (col_width + gap)
            t = Text(txt, style="bold") if self.has_rich else txt
            pad = max(0, total - len(txt))
            if self.has_rich:
                return t + Text(" " * pad)
            return txt + " " * pad

        if self.has_rich:
            # Contexte sous les titres (facultatif — commente si tu préfères compact)
            self._print_context_panel(day, ctx, sim_tot)
            self.console.print(
                _title_cell(titles[0], 0) + Text("    ") + _title_cell(titles[1], 0)
            )

        # Concaténer ligne-à-ligne les deux grilles
        spacer = "    "
        for i in range(len(base_grid)):
            left_line = base_grid[i]
            right_line = sim_grid[i]
            if self.has_rich:
                out = Text.assemble(left_line, Text(spacer), right_line)
                self.console.print(out)
            else:
                print(str(left_line) + spacer + str(right_line))

        # Axe des heures (une fois, au centre : on duplique pour l’alignement)
        unit = col_width + gap
        left_axis  = " " * 4 + "│" + "".join(f"{h:02d}".center(unit) for h in range(24))
        right_axis = left_axis
        if self.has_rich:
            self.console.print(Text(left_axis) + Text(spacer) + Text(right_axis))
        else:
            print(left_axis + spacer + right_axis)

        m_base = self._metrics_from_rows(base_rows, report=True)
        m_sim = self._metrics_from_rows(sim_rows, report=False)
        if self.has_rich:
            p1 = self._print_metrics_panel("Actuel", m_base, style="cyan")
            p2 = self._print_metrics_panel("Simulé", m_sim, style="magenta")
            # deux encarts côte à côte
            self._print_side_by_side_panels(p1, p2, col_width=2, gap=0)
        else:
            # fallback simple en mode non-rich
            print(f"[Actuel] PV={m_base['pv']:.1f} kWh | Conso={m_base['load']:.1f} kWh | "
                  f"Import={m_base['imp']:.1f} | Export={m_base['exp']:.1f} | "
                  f"AC={m_base['ac']:.1f}% | TC={m_base['tc']:.1f}%")
            print(f"[Simulé] PV={m_sim['pv']:.1f} kWh | Conso={m_sim['load']:.1f} kWh | "
                  f"Import={m_sim['imp']:.1f} | Export={m_sim['exp']:.1f} | "
                  f"AC={m_sim['ac']:.1f}% | TC={m_sim['tc']:.1f}%")

        # Légende (une fois en bas)
        if self.has_rich:
            self.console.print(
                "[dim]Haut : [orange1]PV direct[/], [magenta]Batt→charges[/], [blue]Import[/]   "
                "Bas : [yellow3]PV→batterie[/], [grey74]Export[/][/dim]"
            )

