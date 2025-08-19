# cli_output.py
from __future__ import annotations

# Try rich import; graceful fallback to plain prints if unavailable
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.box import ROUNDED
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
            table.add_column("Import", justify="right")
            table.add_column("Export", justify="right")
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

    def best(self, best_tuple):
        """best_tuple = (pv_factor, battery_kWh, stats_dict)"""
        fct, b, st = best_tuple
        msg = (f"➡️  Meilleur compromis\n"
               f"PV ×{fct:g}, Batterie {int(b)} kWh\n"
               f"AC={st['ac']:.1f} %, TC={st['tc']:.1f} %")
        if self.has_rich:
            self.console.print(Panel.fit(msg, border_style="cyan", title="Sélection"))
        else:
            print("\n[Sélection] " + msg)
