# cli_output.py
from __future__ import annotations
import csv
import math
from datetime import datetime, timedelta

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
    """ Console output handler with optional rich formatting.
    If 'rich' library is available, uses it for enhanced output; otherwise falls back to plain text.
    1) Title sections
    2) Summary tables
    3) Passing scenarios table
    4) Best scenario highlight
    5) Definitions
    6) No scenario found message
    7) Daily bars for actual vs simulated
    8) Helpers for formatting and reading CSV
    9) Bar chart rendering in console
    10) Column layout helper
    11) Percentage formatting
    12) Day row reading from CSV
    13) Column building for bar charts
    14) X-axis printing for bar charts
    15) Percentage formatting helper
    16) Daily sum calculation
    """

    def __init__(self):
        """ Initializes the ConsoleUI, checking for rich library availability.
        """
        self.has_rich = _HAS_RICH
        self.console = Console() if self.has_rich else None

    # ---------- helpers ----------
    def _fmt_kwh(self,
                 v: float,
                 ) -> str:
        """ 
        Formats a float value as kWh with no decimal places.
        Args:
            v (float): value in kWh
        Returns:
            str: formatted string
        """
        return f"{v:.0f}"

    def _fmt_pct(self,
                 v: float,
                 ) -> str:
        """
        Formats a float value as percentage with one decimal place.
        Args:
            v (float): value in percentage
        Returns:
            str: formatted string
        """
        return f"{v:.1f}"

    # ---------- public API ----------
    def title(self,
              txt: str,
              ) -> None:
        """ Displays a title section in the console.
        Args:
            txt (str): title text
        Returns:
            None
        """
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
                pv_factor=None,
                batt_kw=None,
                ) -> None:
        """ 
        Displays a summary table of energy stats.
        Args:
            title (str): title of the summary
            pv (float): total PV production in kWh
            load (float): total load consumption in kWh
            imp (float): total import from grid in kWh
            exp (float): total export to grid in kWh
            ac (float): autoconsumption percentage
            tc (float): coverage rate percentage
            start (str, optional): start date of the period. Defaults to None.
            end (str, optional): end date of the period. Defaults to None.
            pv_kw (float, optional): installed PV capacity in kWc. Defaults to None.
            pv_factor (float, optional): PV size factor. Defaults to None.
            batt_kw (float, optional): battery capacity in kW. Defaults to None.
        Returns:
            None
        """
        if self.has_rich:
            if start and end:
                table = Table(title=title + " (" + start[:10] + " → " + end[:10] + ")", show_lines=True, box=ROUNDED, border_style="white")
            else:
                table = Table(title=title, show_lines=True, box=ROUNDED, border_style="white")
            if pv_factor and batt_kw is not None:
                table.add_column("PV ×", justify="right")
                table.add_column("Batterie (KW)", justify="right")
            table.add_column("PV (kWh)", justify="right")
            table.add_column("Conso (kWh)", justify="right")
            table.add_column("Import (kWh)", justify="right")
            table.add_column("Export (kWh)", justify="right")
            table.add_column("AC %", justify="right", style="cyan")
            table.add_column("TC %", justify="right", style="magenta")
            if pv_factor and batt_kw is not None:
                table.add_row(
                    f"{pv_factor:g}",
                    f"{batt_kw} kW",
                    self._fmt_kwh(pv),
                    self._fmt_kwh(load),
                    self._fmt_kwh(imp),
                    self._fmt_kwh(exp),
                    self._fmt_pct(ac),
                    self._fmt_pct(tc),
                )
            else:
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
        print(" ")

    def passing(self,
                passing: list[tuple[float, float, dict]],
                target_ac_min: float,
                target_ac_max: float,
                target_tc_min: float,
                limit: int = 10,
                ) -> None:
        """
        Affiche un tableau des scénarios qui passent les seuils AC/TC.
        Si aucun ne passe, affiche un message.
        
        Args
            passing : list of tuples (pv_factor, battery_kWh, stats_dict)
            target_ac_min : float   Autoconsommation minimale (%) visée
            target_ac_max : float   Autoconsommation maximale (%) (plafond)
            target_tc_min : float   Taux de couverture minimal (%) visé
            limit : int  Nombre maximum de lignes à afficher (défaut: 10)
        Returns
            None
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
             best_tuple: tuple,
             pv_act: float,
             ) -> None:
        """
        Affiche le meilleur scénario (tuple) en évidence.
        Args
            best_tuple : tuple (pv_factor, battery_kWh, stats_dict)
            pv_act : float  Puissance PV actuelle (kWc) pour calcul PV total
        Returns
            None
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
        (à appeler après le tableau des scénarios)
        Returns
            None
        """
        msg = (
            "[bold]* Autoconsommation (AC)[/bold] = part de la production PV consommée directement (charges) et/ou via la batterie\n"
            "[bold]* Taux de couverture (TC)[/bold] = part de la consommation totale couverte par ton PV (direct + batterie)"
        )

        if self.has_rich:
            self.console.print(msg)
        else:
            print(msg.replace("[bold]", "").replace("[/bold]", ""))

    def warning(self,
                txt: str,
                ) -> None:
        """ Affiche un message d'avertissement.
        Args:
            txt (str): texte du message
        Returns:
            None
        """
        if self.has_rich:
            self.console.print(Panel.fit(txt, border_style="yellow", title="Attention"))
        else:
            print("\n[Attention] " + txt)

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
        Returns
        -------
            None
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
        """
        Affiche deux panels côte à côte (fallback en pile si largeur insuffisante).
        Args:
            items (list): liste de panels à afficher
        Returns:
            rich.columns.Columns or rich.console.Group
        """
        try:
            from rich.columns import Columns
            return Columns(items, equal=True, expand=True, padding=(0, 2))
        except Exception:
            # Fallback: on empile
            from rich.console import Group
            return Group(*items)

    def _bar_segments(self,
                      parts: list[tuple[float, str, str | None]],
                      width: int=30,
                      ) -> str | Text:
        """
        parts: list of tuples (ratio, char, color or None) ; ratio ∈ [0..1], somme ≤ 1
        width: total width in characters
        Returns a string or rich Text with colored segments.
        1) Clamp ratios to [0..1]
        2) Convert ratios to cell counts
        3) Adjust rounding to fit width
        4) Build the string or Text object
        Args:
            parts (list): list of tuples (ratio, char, color or None)
            width (int): total width in characters
        Returns:
            str or rich.text.Text: formatted bar
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
                   daily_dict: dict,
                   max_days: int|None = None,
                   width: int = 30,
                   ) -> None:
        """
        daily_dict: { 'YYYY-MM-DD': {pv, load, imp, exp, pv_direct, batt_to_load, pv_to_batt} }
        Affiche 2 barres par jour :
        - Couverture conso (100% = load) : [pv_direct | batt_to_load | import]
        - Disposition PV    (100% = pv)   : [pv_direct | pv_to_batt | export]
        Attention : si load ou pv = 0, la barre correspondante est vide.
        Args:
            daily_dict: dict    Dictionnaire des jours et valeurs
            max_days: int|None  Nombre maximum de jours à afficher (défaut: tous)
            width: int          Largeur des barres en caractères (défaut: 30)
        Returns:
            None
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
                    path: str,
                    ) -> str:
        """ Détecte automatiquement le délimiteur CSV (virgule ou point-virgule) en lisant la première ligne.
        Args:
            path (str): chemin du fichier CSV
        Returns:
            str: délimiteur détecté ("," ou ";")
        """
        with open(path, "r", newline="") as f:
            head = f.readline()
            return ";" if head.count(";") > head.count(",") else ","

    def _as_float(self,
                  x,
                  default=0.0,
                  ) -> float:
        """ Convertit une valeur en float, ou retourne une valeur par défaut en cas d'erreur.
        Args:
            x : valeur à convertir
            default (float, optional): valeur par défaut en cas d'erreur. Defaults to 0.0.
        Returns:
            float: valeur convertie ou défaut
        """
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        try:
            return float(x)

        except Exception:
            return default

    def _hour_from(self,
                   ts: str,
                   ) -> int:
        # "YYYY-MM-DD HH:MM" ou ISO "YYYY-MM-DDTHH:MM:SS"
        """ Extrait l'heure (0-23) d'un timestamp.
        Args:
            ts (str): timestamp
        Returns:
            int: heure (0-23) ou -1 en cas d'erreur
        """
        if len(ts) < 13:
            return -1   # trop court
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
        Lecture du fichier CSV en entrée pour en sortir un dictionnaire
        des 24 heures d'une journée donnée.
        Args:
            csv_path (str): chemin du fichier CSV
            day (str): jour au format "YYYY-MM-DD"
            report (bool, optional): si True, on s'attend à un CSV de type
                                     "report" (ex: exporté de PVOutput).
                                     Si False, on s'attend à un CSV de type
                                        "simu" (ex: exporté de la simu).
                                        Defaults to False.
        Returns:
            list of dict: liste de 24 dictionnaires, un par heure,
                          avec les clés:
                          "hour", "pv_direct", "pv_to_batt", "batt_to_load",
                          "import", "export", "pv", "load"
        1) Détection du délimiteur
        2) Lecture du CSV
        3) Filtrage sur le jour demandé
        4) Extraction des colonnes selon le type de CSV
        5) Reconstitution des totaux PV/Load si absents
        6) Garantie d'avoir 24 heures (0-23) dans la sortie
        7) Retour de la liste des dictionnaires
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
                    g2b = self._as_float(r.get("grid_to_batt"))
                    i2l = self._as_float(r.get("imp_to_load"))
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
                        "grid_to_batt": g2b or 0.0,
                        "imp_to_load":  i2l or 0.0,
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
                        "grid_to_batt": 0.0,
                        "imp_to_load":  0.0,
                        "import":       imp,
                        "export":       exp,
                        "pv":           pv,
                        "load":         load,
                    })

        # garantir 24h
        by_h = {r["hour"]: r for r in rows}
        out = []
        for h in range(24):
            out.append(by_h.get(h, 
            {
                "hour": h, 
                "pv_direct": 0.0, 
                "pv_to_batt": 0.0,
                "batt_to_load": 0.0, 
                "grid_to_batt": 0.0,
                "imp_to_load": 0.0,
                "import": 0.0, 
                "export": 0.0
            }))
        out.sort(key=lambda x: x["hour"])
        return out

    def _build_columns(self, 
                       stacks_per_hour: list, 
                       max_kwh: float,
                       step_kwh: float,
                       col_width: int,
                       gap: int = 1,
                       ) -> tuple[list, int]:
        """
        Construit les colonnes empilées pour les 24 heures, avec espacement constant entre les heures.
            Retourne :
            - grid_rows : lignes ASCII/Rich
            - levels    : nb de niveaux verticaux

        1) Calcul du nombre de niveaux verticaux (levels)
        2) Pour chaque heure, conversion des valeurs en nombre de cellules
           en fonction du step_kwh, et ajustement si dépassement de levels
        3) Construction des colonnes avec styles
        4) Construction des lignes de la grille (haut → bas)
        5) Retour des lignes et du nombre de niveaux
        Args:
            stacks_per_hour (list): list of 24 lists of tuples (value_kwh, style_str)
            max_kwh (float): Valeur maximale en kWh (pour échelle Y)
            step_kwh (float): Pas en kWh entre chaque niveau vertical
            col_width (int): Largeur d'une barre par heure
            gap (int, optional): Nombre d'espaces entre heures. Defaults to 1.
        Returns:
            tuple: (grid_rows, levels)
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

    def _print_x_axis(self, 
                      levels: int,
                      col_width: int,
                      gap: int = 1,
                      ) -> None:
        """
        Affiche l'axe X (heures 00..23) sous la grille.
        - levels : nombre de lignes verticales (juste pour aligner le label '0│')
        - col_width : largeur d'une barre par heure
        - gap : nombre d'espaces entre heures (doit correspondre à _build_columns)
        1) Construction de la ligne avec labels centrés
        2) Affichage
        Args:
            levels (int): nombre de lignes verticales
            col_width (int): largeur d'une barre par heure
            gap (int, optional): nombre d'espaces entre heures. Defaults to 1.
        Returns:
            None
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

    def _fmt_pct(self, v: float | str | int | None) -> str:
        """
        Accepte 0.8, '0.8', 80, '80', None → renvoie '80 %' ou '' si None.
        Si v ≤ 1.5, on le considère comme une fraction (0.0..1.5) et on convertit en %.
        Si v > 1.5, on le considère comme un pourcentage (0..1000) et on l'affiche tel quel.
        Si v n'est pas convertible en float, on le renvoie tel quel en str.
        1) Gestion du None
        2) Conversion en float avec gestion d'erreur
        3) Conversion en % si ≤ 1.5
        4) Formatage final
        Args:
            v : valeur à formater
        Returns:
            str: valeur formatée en pourcentage ou chaîne vide
        """
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

    def _sum_day(self, day_rows: list) -> dict:
        """
        Sommes du jour et SoC début/fin (si présent).
        Args:
            day_rows (list): liste des 24 dictionnaires d'une journée
        Returns:
            dict: dictionnaire des totaux et indicateurs:
                  "pv_direct", "pv_to_batt", "batt_to_load",
                  "import", "export", "pv", "load",
                  "soc_start", "soc_end", "ac", "tc"
        1) Initialisation des totaux
        2) Somme des valeurs sur les 24 heures
        3) Calcul des indicateurs AC et TC
        4) Retour du dictionnaire des totaux
        """
        tot = {
            "pv_direct": 0.0,
            "pv_to_batt": 0.0,
            "batt_to_load": 0.0,
            "grid_to_batt": 0.0,
            "imp_to_load": 0.0,
            "import": 0.0,
            "export": 0.0,
            "pv": 0.0,
            "load": 0.0,
            "soc_start": None,
            "soc_end": None
        }
        for i, r in enumerate(day_rows):
            pvd = float(r.get("pv_direct", 0) or 0)
            p2b = float(r.get("pv_to_batt", 0) or 0)
            b2l = float(r.get("batt_to_load", 0) or 0)
            g2b = float(r.get("grid_to_batt", 0) or 0)
            i2l = float(r.get("imp_to_load", 0) or 0)
            imp = float(r.get("import", 0) or 0)
            exp = float(r.get("export", 0) or 0)
            # si ton CSV contient 'pv' et 'load' par heure, prends-les, sinon reconstitue:
            pv  = float(r.get("pv", pvd + p2b + exp) or 0)
            load = float(r.get("load", pvd + b2l + imp) or 0)

            tot["pv_direct"]   += pvd
            tot["pv_to_batt"]  += p2b
            tot["batt_to_load"]+= b2l
            tot["grid_to_batt"]+= g2b
            tot["imp_to_load"] += i2l
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

    def _print_context_panel(self, day: str,
                             ctx: dict,
                             totals: dict,
                             ) -> None:
        """
        Affiche un panneau "Contexte" avec les paramètres de la simulation
        et les totaux du jour.
        1) Construction d'une table avec les paramètres (si présents)
        2) Ajout des totaux du jour
        3) Affichage dans un panneau
        Args:
            day (str): jour au format "YYYY-MM-DD"
            ctx (dict): dictionnaire des paramètres de la simulation
            totals (dict): dictionnaire des totaux du jour
        Returns:
            None
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

    def _build_columns_bipolar(self,
                               stacks_up: list,
                               stacks_dn: list,
                               max_kwh: float,
                               step_kwh: float,
                               col_width: int,
                               gap: int,
                               ) -> tuple[list, int]:
        """
        Graphe bipolaire façon HA :
            - Haut = consommation couverte  (PV direct, Batt→charges, Import)
            - Bas  = disposition production (PV direct, PV→batt, Export)
            Échelle symétrique ; labels du BAS affichés en POSITIF (0..X), mais les barres descendent.
        1) Calcul du nombre de niveaux verticaux (levels)
        2) Pour chaque heure, conversion des valeurs en nombre de cellules
           en fonction du step_kwh, et ajustement si dépassement de levels
        3) Construction des colonnes avec styles (séparément pour haut et bas)
        4) Construction des lignes de la grille (haut → bas, puis bas → haut)
        5) Retour des lignes et du nombre de niveaux
        Args:
            stacks_up (list): list of 24 lists of tuples (value_kwh, style_str) pour la partie haute
            stacks_dn (list): list of 24 lists of tuples (value_kwh, style_str) pour la partie basse
            max_kwh (float): Valeur maximale en kWh (pour échelle Y)
            step_kwh (float): Pas en kWh entre chaque niveau vertical
            col_width (int): Largeur d'une barre par heure
            gap (int, optional): Nombre d'espaces entre heures. Defaults to 1.
        Returns:
            tuple: (grid_rows, levels)
        """
        hours = max(0, min(len(stacks_up), len(stacks_dn))) # devrait être 24 ou 48
        if hours == 0:
            return [], 0
        levels = max(1, int(math.ceil(max_kwh / step_kwh)))  # mêmes niveaux haut/bas

        def build_cols(stacks: list) -> list:
            """ 
            Construit les colonnes empilées pour les 24 heures.
            Retourne une liste de 24 listes de styles (bas->haut).
            
            1) Pour chaque heure, conversion des valeurs en nombre de cellules
               en fonction du step_kwh, et ajustement si dépassement de levels
            2) Construction des colonnes avec styles
            3) Retour des colonnes
            Args:
                stacks (list): list of 24 lists of tuples (value_kwh, style_str)
            Returns:
                list: list of 24 lists of styles (bas->haut)
            """
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
            for h in range(hours):
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
        grid.append(left + dash * hours)

        # ---- PARTIE BASSE : de 0 vers le bas
        # >>> ICI on AFFICHE DES LABELS POSITIFS (0.5, 1.0, …), MAIS on dessine en dessous de 0.
        for lvl in range(levels):
            ylab = f"{(lvl + 1) * step_kwh:>4.1f}│"  # labels POSITIFS
            line = Text(ylab) if self.has_rich else ylab
            for h in range(hours):
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

    def _print_x_axis_bipolar(self,
                              col_width: int, 
                              gap: int = 1,
                              hours: int = 24,
                              ) -> None:
        """
        Affiche l'axe X aligné sous la grille bipolaire. Labels centrés sous chaque (col_width + gap).
        1) Construction de la ligne avec labels centrés
        2) Affichage
        Args:
            col_width (int): largeur d'une barre par heure
            gap (int, optional): nombre d'espaces entre heures. Defaults to 1.
            hours (int, optional): nombre d'heures (24 ou 48). Defaults to 24.
        Returns:
            None
        """
        unit = col_width + gap
        #left = " " * 3 + " │"   # aligne sous les labels Y (4) et le séparateur vertical
        
        # Pas d'espace avant: on commence directement par la barre verticale
        left = "|"
        # Labels horaires: 00..23 pour 24h, répétés si 48h (00..23 00..23)
        parts = []
        for idx in range(hours):
            h = idx % 24
            # rjust pour éviter l'espace initial ajouté par center()
            parts.append(f"{h:02d}".rjust(unit))

        line = left + "".join(parts)
        if self.has_rich:
            self.console.print(line)
        else:
            print(line)

    def _metrics_from_rows(self,
                           rows: list[dict],
                           report: bool,
                           ) -> dict:
        """
        Calcule les métriques clés d'une journée à partir des 24 lignes horaires.
        Args:
            rows (list): liste des 24 dictionnaires d'une journée
            report (bool): si True, on s'attend à un CSV de type
                           "report" (ex: exporté de PVOutput).
                           Si False, on s'attend à un CSV de type
                              "simu" (ex: exporté de la simu).
        Returns:
            dict: dictionnaire des métriques:
                  "pv", "load", "imp", "exp", "ac", "tc", "onsite_ac", "onsite_tc"
        1) Somme des valeurs sur les 24 heures
        2) Calcul des indicateurs AC et TC
        3) Retour du dictionnaire des métriques
        Note : le calcul de "onsite" diffère selon le type de CSV.
        """
        eps  = 1e-9
        pv   = sum(r.get("pv", 0.0) for r in rows)
        load = sum(r.get("load", 0.0) for r in rows)
        imp  = sum(r.get("import", 0.0) for r in rows)
        exp  = sum(r.get("export", 0.0) for r in rows)
        # --- Quantités utiles pour TC ---
        if report:
            # Sans colonnes batterie, la meilleure estimation de la conso couverte
            # est "load - import" (= PV direct + éventuelle batterie, si existait).
            onsite_tc = max(0.0, min(load, load - imp))
        else:
            pv_direct     = sum(float(r.get("pv_direct", 0.0))    for r in rows)
            batt_to_load  = sum(float(r.get("batt_to_load", 0.0)) for r in rows)
            # Couverture de charge (ne peut pas dépasser la conso)
            onsite_tc = max(0.0, min(load, pv_direct + batt_to_load))
            
        # --- Quantité utile pour AC ---
        # AC se calcule par rapport au PV du jour: PV utilisé = PV produit - export
        onsite_ac = max(0.0, pv - exp)  # borné implicitement par pv

        # --- Pourcentages ---
        ac = 100.0 * onsite_ac / max(pv,   eps) if pv   > eps else 0.0
        tc = 100.0 * onsite_tc / max(load, eps) if load > eps else 0.0
        
        # Clamp de sécurité
        ac = max(0.0, min(100.0, ac))
        tc = max(0.0, min(100.0, tc))
        return {"pv": pv,
                "load": load,
                "imp": imp,
                "exp": exp,
                "ac": ac,
                "tc": tc,
                "onsite_ac": onsite_ac, # PV utilisé ce jour (pour AC)
                "onsite_tc": onsite_tc, # Conso couverte ce jour (pour TC)
                }


    def _print_metrics_line(self,
                            title: str,
                            m: dict,
                            ) -> None:
        """
        Affiche une ligne compacte de stats sous un graphe.
        Args:
            title (str): titre à afficher au début
            m (dict): dictionnaire des métriques:
                      "pv", "load", "imp", "exp", "ac", "tc"
        Returns:
            None
        1) Construction de la ligne formatée
        2) Affichage avec Rich ou print()
        3) Exemple de sortie :
           [dim]Jour  PV=12.3 kWh  Conso=8.4 kWh  Import=1.2  Export=3.4  AC=75.0%  TC=90.0%[/dim]
        4) Si Rich n'est pas dispo, on enlève les balises [dim]...[/dim]
        5) Affichage
        6) Retour None
        7) Note : on affiche une décimale partout pour l'alignement.
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
        Args:
            title (str): titre à afficher en haut à gauche
            m (dict): dictionnaire des métriques:
                      "pv", "load", "imp", "exp", "ac", "tc"
            style (str, optional): style de bordure. Defaults to "cyan".
        Returns:
            Panel: panneau Rich prêt à être affiché
        1) Construction d'une table avec les métriques
        2) Retour d'un panneau avec bordure et titre
        3) Exemple de sortie :
           ┌───────────────────────────────────────────────┐
           │ [bold]Résumé jour[/bold]                      │
           │ ┌──────────────────┬────────────────────────┐ │
           │ │ PV : 12.3 kWh    │ Conso : 8.4 kWh        │ │
           │ │ Import : 1.2 kWh │ Export : 3.4 kWh       │ │
           │ │ AC : 75.0 %      │ TC : 90.0 %            │ │
           │ └──────────────────┴────────────────────────┘ │
           └───────────────────────────────────────────────┘
        4) Note : on affiche une décimale partout pour l'alignement.
        5) Retour du panneau (ne pas afficher ici)
        6) Nécessite Rich
        7) Si Rich n'est pas dispo, cette fonction ne doit pas être appelée.
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
        Args:
            left_panel (Panel): panneau de gauche (Rich Panel)
            right_panel (Panel): panneau de droite (Rich Panel)
            col_width (int, optional): largeur d'une barre par heure. Defaults to 2.
            gap (int, optional): nombre d'espaces entre heures. Defaults to 1.
        Returns:
            None
        1) Calcul de la largeur intérieure des panels (24 * col_width + 23 * gap)
        2) Fixation de la largeur des panels (optionnel mais plus propre)
        3) Indentation à gauche de la largeur de l'axe Y
        4) Alignement à gauche dans chaque colonne (Columns centre par défaut)
        5) Affichage dans deux colonnes égales
        6) Nécessite Rich
        7) Si Rich n'est pas dispo, cette fonction ne doit pas être appelée.
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
        right_padded = Padding(right_panel, (0, 39, 0, axis_pad))

        # crucial: left-align inside each column (Columns centers by default)
        left_aligned  = Align.left(left_padded)
        right_aligned = Align.left(right_padded)

        # deux colonnes égales, alignées avec les deux graphes
        self.console.print(Columns([left_aligned, right_aligned], 
                            equal=True,
                            expand=True,
                            padding=(0, 4)))
        
    def _read_day_rows_many(self,
                            csv_path: str,
                            day: str,
                            report: bool,
                            days: int = 1,
                            ) -> list[dict]:
        """
        Concatène days jours (24*days lignes). S’il manque des heures, remplit à 0.

        Args:
            csv_path (str): chemin vers le fichier CSV à lire
            day (str): jour de départ au format "YYYY-MM-DD"
            report (bool): si True, on s'attend à un CSV de type
                           "report" (ex: exporté de PVOutput).
                           Si False, on s'attend à un CSV de type
                              "simu" (ex: exporté de la simu).
            days (int): nombre de jours à concaténer (≥1)
        Returns:
            list: liste des dictionnaires horaires pour les jours demandés
        1) Pour chaque jour, lire les lignes horaires
        2) Si des heures manquent, les remplir avec des zéros
        3) Décaler l'index d'heure pour les axes (0..24*days-1)
        4) Retourner la liste complète (24*days lignes)
        """
        def _one(d):
            """
            Retourne les 24 lignes d’un jour, remplies à 0 si manquant
            Args:
                d (str): jour au format "YYYY-MM-DD"
            Returns:
                list: liste des 24 dictionnaires horaires
            """
            rows = self._read_day_rows(csv_path, d, report=report)
            return rows or [{"hour": h, 
                             "pv_direct":0.0,
                             "pv_to_batt":0.0,
                             "batt_to_load":0.0,
                             "grid_to_batt":0.0,
                             "imp_to_load":0.0,
                             "import":0.0,
                             "export":0.0,
                             "pv":0.0,
                             "load":0.0}
                            for h in range(24)]

        base_dt = datetime.fromisoformat(day)
        out = []
        for i in range(days):
            d = (base_dt + timedelta(days=i)).date().isoformat()
            rows = _one(d)
            # décale l’index d’heure pour les axes (0..24*days-1)
            for h, r in enumerate(rows):
                rr = dict(r)
                rr["hour"] = i*24 + h
                out.append(rr)
        return out  # 24*days lignes


    # ========= vue “axes” =========
    def plot_day_cli(self, 
                     csv_path: str,
                     day: str = None,
                     max_kwh: float = 5.0,
                     step_kwh: float = 0.5,
                     col_width: int = 2,
                     context: dict = None,
                     ) -> None:
        """
        Affiche DEUX graphiques en console avec axes (heures 00..23 en X, kWh en Y).
        Si `day` n'est pas fourni, utilise le premier jour trouvé dans le CSV.
        1) Détection automatique du séparateur CSV (virgule ou point-virgule)
        2) Lecture du CSV pour extraire les dates disponibles
        3) Validation de la date demandée (ou choix du premier jour)
        4) Lecture des lignes horaires pour ce jour uniquement
        5) Extraction du contexte depuis la première ligne du jour, si présent
        6) Calcul des totaux du jour
        7) Affichage du contexte (paramètres + totaux)
        8) Affichage du graphe 1 : consommation couverte (PV direct, Batt→charges, Import)
        9) Affichage du graphe 2 : disposition de la production (PV direct, PV→batt, Export)
        10) Affichage des légendes et des métriques clés sous chaque graphe
        Args:
            context (dict, optional): contexte additionnel à afficher (paramètres de la simu).
                                      Si des clés existent déjà dans le CSV, elles sont prioritaires.
                                      Clés possibles :
                                      - "pv_factor" : facteur de dimensionnement PV (float)
                                      - "batt_kwh" : capacité batterie (float)
                                      - "eff" : rendement batterie (float 0.0..1.0)
                                      - "initial_soc" : SoC initial batterie (float 0.0..1.0)
                                      - "pv_kwc" : puissance PV installée (float)
                                      - "scenario" : nom du scénario (str)
            day (str, optional): jour au format "YYYY-MM-DD". Si None, utilise le premier jour trouvé.
            csv_path (str): chemin vers le fichier CSV  à lire
            max_kwh (float, optional): valeur maximale en kWh pour l'échelle Y. Defaults to 5.0.
            step_kwh (float, optional): pas en kWh entre chaque niveau vertical. Defaults to 0.5.
            col_width (int, optional): largeur d'une barre par heure. Defaults to 2.
        Returns:
            None
        11) Nécessite Rich pour l'affichage amélioré.
        12) Si Rich n'est pas dispo, affiche un message d'erreur.
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

    def plot_day_cli_bipolar(self, 
                             csv_path: str,
                             day: str = None,
                             max_kwh: float = 5.0,
                             step_kwh: float = 0.5,
                             col_width: int = 2,
                             gap: int = 1,
                             context: dict | None = None,
                             ) -> None:
        """
        Un seul graphique bipolaire façon Home Assistant :
        - Haut : consommation couverte (PV direct, Batt→charges, Import)
        - Bas  : disposition production (PV direct, PV→batt, Export)
        Si `day` n'est pas fourni, utilise le premier jour trouvé dans le CSV.
        1) Détection automatique du séparateur CSV (virgule ou point-virgule)
        2) Lecture du CSV pour extraire les dates disponibles
        3) Validation de la date demandée (ou choix du premier jour)
        4) Lecture des lignes horaires pour ce jour uniquement
        5) Extraction du contexte depuis la première ligne du jour, si présent
        6) Calcul des totaux du jour
        7) Affichage du contexte (paramètres + totaux)
        8) Construction des stacks haut (conso couverte) et bas (dispo PV)
        9) Autoscale symétrique si max_kwh non fourni
        10) Construction de la grille bipolaire
        11) Affichage de la grille
        12) Affichage de l'axe X
        13) Affichage de la légende
        Args:
            csv_path (str): chemin vers le fichier CSV  à lire
            day (str, optional): jour au format "YYYY-MM-DD". Si None, utilise le premier jour trouvé.
            max_kwh (float, optional): valeur maximale en kWh pour l'échelle Y. Si None, autoscale. Defaults to 5.0.
            step_kwh (float, optional): pas en kWh entre chaque niveau vertical. Defaults to 0.5.
            col_width (int, optional): largeur d'une barre par heure. Defaults to 2.
            gap (int, optional): nombre d'espaces entre heures. Defaults to 1.
            context (dict, optional): contexte additionnel à afficher (paramètres de la simu).
                                      Si des clés existent déjà dans le CSV, elles sont prioritaires.
                                      Clés possibles :
                                      - "pv_factor" : facteur de dimensionnement PV (float)
                                      - "batt_kwh" : capacité batterie (float)
                                      - "eff" : rendement batterie (float 0.0..1.0)
                                      - "initial_soc" : SoC initial batterie (float 0.0..1.0)
                                      - "pv_kwc" : puissance PV installée (float)
                                      - "scenario" : nom du scénario (str)
        Returns:
            None
        14) Nécessite Rich pour l'affichage amélioré.
        15) Si Rich n'est pas dispo, affiche un message d'erreur.
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

    def plot_day_cli_bipolar_compare(self,
                                     base_csv_path: str,
                                     sim_csv_path: str,
                                     day: str | None = None,
                                     days: int = 1,
                                     stack_when_multi: bool = False,
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
        Si `day` n'est pas fourni, utilise le premier jour trouvé dans le CSV “base”.
        1) Détection automatique du séparateur CSV (virgule ou point-virgule)
        2) Lecture du CSV “base” pour extraire les dates disponibles
        3) Validation de la date demandée (ou choix du premier jour du CSV “base”)
        4) Lecture des lignes horaires pour ce jour dans les deux CSV
        5) Extraction du contexte depuis la première ligne du jour du CSV “simulé”, si présent
        6) Calcul des totaux du jour pour les deux CSV
        7) Affichage du contexte (paramètres + totaux)
        8) Construction des stacks haut (conso couverte) et bas (dispo PV) pour les deux graphes
        9) Autoscale symétrique si max_kwh non fourni
        10) Construction des deux grilles bipolaires
        11) Affichage des deux grilles côte à côte
        12) Affichage de l'axe X sous les deux graphes
        13) Affichage de la légende
        Args:
            base_csv_path (str): chemin vers le fichier CSV “base” (situation actuelle)
            sim_csv_path (str): chemin vers le fichier CSV “simulé” (résultat de la simulation)
            day (str, optional): jour au format "YYYY-MM-DD". Si None, utilise le premier jour trouvé dans le CSV “base”.
            days (int, optional): nombre de jours à afficher en empilant les jours consécutifs.
                                  Si >1, les jours sont empilés verticalement (stack_when_multi=True). Defaults to 1.
            stack_when_multi (bool, optional): si days>1, True pour empiler les jours verticalement,
                                              False pour afficher chaque jour séparément. Defaults to False.
            max_kwh (float, optional): valeur maximale en kWh pour l'échelle Y. Si None, autoscale. Defaults to None.
            step_kwh (float, optional): pas en kWh entre chaque niveau vertical. Defaults to 0.5.
            col_width (int, optional): largeur d'une barre par heure. Defaults to 2.
            gap (int, optional): nombre d'espaces entre heures. Defaults to 1.
            context (dict, optional): contexte additionnel à afficher (paramètres de la simu).
                                      Si des clés existent déjà dans le CSV “simulé”, elles sont prioritaires.
                                      Clés possibles :
                                      - "pv_factor" : facteur de dimensionnement PV (float)
                                      - "batt_kwh" : capacité batterie (float)
                                      - "eff" : rendement batterie (float 0.0..1.0)
                                      - "initial_soc" : SoC initial batterie (float 0.0..1.0)
                                      - "pv_kwc" : puissance PV installée (float)
                                      - "scenario" : nom du scénario (str)
            titles (tuple, optional): titres à afficher au-dessus des deux graphes. Defaults to ("Actuel", "Simulé").
        Returns:
            None
        14) Nécessite Rich pour l'affichage amélioré.
        15) Si Rich n'est pas dispo, affiche un message d'erreur.
        """
        def _first_day(csv_path: str) -> str | None:
            """_summary_

            Args:
                csv_path (str): _description_

            Returns:
                str | None: _description_
            """
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

        # Nombre de jours à empiler
        hours = 24 * days
        # Si days > 1 on force l’empilement vertical, sauf si tu veux garder le contrôle manuel :
        if days > 1:
            stack_when_multi = True

        # Lecture des lignes du jour (ou plusieurs jours) (base + sim)
        if stack_when_multi:
            base_rows = self._read_day_rows_many(base_csv_path, day, report=True,  days=days)
        else:
            base_rows = self._read_day_rows(base_csv_path, day, report = True)
        if not base_rows:
            self.console.print(f"[red]❌ Pas de données 'Actuel' pour {day}[/red]" if self.has_rich else f"❌ Pas de données 'Actuel' pour {day}")
            return
        
        if stack_when_multi:
            sim_rows  = self._read_day_rows_many(sim_csv_path, day, report=False, days=days)
        else:
            sim_rows  = self._read_day_rows(sim_csv_path, day, report=False)
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

        # --- Prépare stacks (haut/bas) et max pour les DEUX graphes ---
        def _stacks_from_rows(rows: list,
                              is_report: bool = False,
                              ) -> tuple[list, list, float, float]:
            """
            Fabrique les piles haut/bas et retourne (up, dn, up_max, dn_max).
                - Si le CSV est 'simu' (avec pv_direct/pv_to_batt/batt_to_load), on les utilise.
                - Si le CSV est 'report' (pv_diff/load_diff/import/export), on déduit pv_direct/import/export.
            Args:
                rows (list): liste des lignes horaires du jour
                is_report (bool, optional): True si le CSV est un rapport (pv_diff/load_diff/import/export).
                                            False si le CSV est une simulation complète (pv_direct/pv_to_batt/batt_to_load).
            Returns:
                tuple: (up, dn, up_max, dn_max)
            1) Parcourt les lignes horaires
            2) Détecte le type de ligne (report ou simu complète)
            3) Construit les stacks haut et bas
            4) Calcule les max haut et bas
            5) Retourne les stacks et max
            6) Note : dans le cas d'un rapport, on affiche séparément la prod PV et la conso totale.
            7) Dans le cas d'une simu complète, on affiche la conso couverte (PV direct + Batt→charges + Import).
            8) Dans les deux cas, on affiche la disposition de la prod PV (PV direct + PV→batt + Export).
            9) Nécessite Rich pour l'affichage amélioré.
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
                    g2b = float(r.get("grid_to_batt", 0) or 0)
                    i2l = float(r.get("imp_to_load", 0) or 0)
                    
                    up.append([(pvd, "[orange1]"), (b2l, "[magenta]"), (imp, "[blue]")])
                    dn.append([(g2b, "[#00BFFF]"), (p2b, "[yellow3]"), (exp, "[grey74]")])

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
        def _title_cell(txt: str,
                        width_chars: int,
                        ) -> Text | str:
            """ 
            Formatte une cellule titre de largeur fixe (pour aligner les deux grilles).
            Args:
                txt (str): texte du titre
                width_chars (int): largeur totale en caractères (incluant le texte)
            Returns:
                Text | str: texte formaté (Rich Text si possible)
            1) Calcule la largeur totale du graphe (axe Y + 24 barres + espaces)
            2) Calcule le padding nécessaire pour atteindre cette largeur
            3) Retourne le texte formaté avec le padding
            4) Nécessite Rich pour l'affichage amélioré.
            5) Si Rich n'est pas dispo, retourne une chaîne simple.
            """
            # Largeur totale d’un graphe : 4(pour Y) + 2(caractères '0│' ou ' x│') + 24*(col_width+gap)
            total = 4 + 2 + 24 * (col_width + gap)
            t = Text(txt, style="bold") if self.has_rich else txt
            pad = max(0, total - len(txt))
            if self.has_rich:
                return t + Text(" " * pad)
            return txt + " " * pad

        if self.has_rich:
            # Contexte sous les titres
            self._print_context_panel(day, ctx, sim_tot)
        # Rendu : côte-à-côte (24h) ou empilé (48h…)
        if not stack_when_multi:
            # Concaténer ligne-à-ligne les deux grilles
            spacer = "    "
            if self.has_rich:
                self.console.print(
                    _title_cell(titles[0], 0) + Text("    ") + _title_cell(titles[1], 0)
                )
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
            left_axis  = " " * 4 + "│" + "".join(f"{h:02d}".ljust(unit) for h in range(24))
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
        else:
            # EMPILÉ (utile pour --days 2, etc.)
            # --- Actuel ---
            if self.has_rich:
                self.console.print(_title_cell(titles[0], 0))
            for line in base_grid:
                self.console.print(line) if self.has_rich else print(line)
            self._print_x_axis_bipolar(col_width, gap, hours=hours)
            m_base = self._metrics_from_rows(base_rows, report=True)
            if self.has_rich:
                p1 = self._print_metrics_panel("Actuel", m_base, style="cyan")
                self.console.print(p1)
            else:
                print(f"[Actuel] PV={m_base['pv']:.1f} | Conso={m_base['load']:.1f} | Imp={m_base['imp']:.1f} | Exp={m_base['exp']:.1f} | AC={m_base['ac']:.1f}% | TC={m_base['tc']:.1f}%")

            # --- Simulé ---
            if self.has_rich:
                self.console.print(_title_cell(titles[1], 0))
            for line in sim_grid:
                self.console.print(line) if self.has_rich else print(line)
            self._print_x_axis_bipolar(col_width, gap, hours=hours)
            m_sim = self._metrics_from_rows(sim_rows, report=False)
            if self.has_rich:
                p2 = self._print_metrics_panel("Simulé", m_sim, style="magenta")
                self.console.print(p2)
            else:
                print(f"[Simulé] PV={m_sim['pv']:.1f} | Conso={m_sim['load']:.1f} | Imp={m_sim['imp']:.1f} | Exp={m_sim['exp']:.1f} | AC={m_sim['ac']:.1f}% | TC={m_sim['tc']:.1f}%")
       
        # Légende (une fois en bas)
        if self.has_rich:
            self.console.print(
                "[dim]Haut : [orange1]PV direct[/], [magenta]Batt→charges[/], [blue]Import[/]   "
                "Bas : [#00BFFF]Grid→batterie[/], [yellow3]PV→batterie[/], [grey74]Export[/][/dim]"
            )

    def show_day_not_found(self,
                           day: str,
                           available_days: list[str],
                           hint: str | None = None) -> None:
        """
        Affiche un message lisible quand le jour demandé n'est pas dans le CSV (mode plot).
        Args:
            day (str): jour demandé (format "YYYY-MM-DD")
            available_days (list): liste des jours disponibles dans le CSV
            hint (str, optional): astuce à afficher (ex : "Vérifie le format AAAA-MM-JJ")
        Returns:
            None
        1) Si Rich n'est pas dispo, affiche un message simple.
        2) Si Rich est dispo, affiche un panneau rouge avec le jour demandé.
        3) Affiche quelques suggestions utiles : le jour le plus proche, les premiers et derniers jours.
        4) Affiche l'astuce si fournie.
        5) Nécessite Rich pour l'affichage amélioré.
        """
        if not self.has_rich:
            print(f"[Jour non trouvé] {day}")
            if available_days:
                print("Jours disponibles (extrait) :", ", ".join(available_days[:10]) + (" …" if len(available_days) > 10 else ""))
            if hint:
                print(hint)
            return

        header = Panel(
            f"[bold red]Jour non trouvé[/]\n[white]Tu as demandé : [bold]{day}[/][/]",
            border_style="red",
            box=box.HEAVY
        )

        tbl = Table.grid(padding=(0, 2))
        tbl.add_row("Jour demandé :", f"[bold]{day}[/]")

        if available_days:
            # quelques suggestions utiles : le plus proche, le premier et le dernier
            try:
                day_dt = datetime.fromisoformat(day)
                days_dt = [datetime.fromisoformat(d) for d in available_days]
                nearest = min(days_dt, key=lambda d: abs(d - day_dt))
                nearest_s = nearest.date().isoformat()
            except Exception:
                nearest_s = available_days[0]

            tbl.add_row("Plus proche :", nearest_s)
            tbl.add_row("Premiers jours :", ", ".join(available_days[:5]))
            if len(available_days) > 5:
                tbl.add_row("Derniers jours  :", ", ".join(available_days[-5:]))

        if hint:
            tbl.add_row("Astuce :", hint)

        self.console.print()
        self.console.print(header)
        self.console.print(Panel(tbl, title="Disponibilité dans le CSV", border_style="cyan", box=box.ROUNDED))
        self.console.print()

