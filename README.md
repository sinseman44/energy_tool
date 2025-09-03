# Energy Tool

[![License](https://img.shields.io/github/license/sinseman44/energy_tool?style=for-the-badge)](https://github.com/sinseman44/energy_tool/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sinseman44/energy_tool?style=for-the-badge)](https://github.com/sinseman44/energy_tool/releases)
<br />

## Contexte

Un simulateur d'energie d'une habitation avec des panneaux solaires et batteries

# Support

<a href="https://www.buymeacoffee.com/sinseman44" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 145px !important;" ></a>

# Todo 📃 and Bug report 🐞

See [Github To Do & Bug List](https://github.com/sinseman44/energy_tool/issues)

# Fonctionnalités
* **Report** (mode `report`) : récupère l’historique PV/Conso, calcule import/export horaire et journalier.
* **Simulation** (mode `simu`) : parcourt un espace de scénarios PV × batteries selon vos objectifs (AC/TC), et produit le meilleur compromis.
* **Plot** (mode `plot`) :
  * graphe horaire bipolaire (consommation en haut / production en bas),
  * comparatif Avant/Après pour un jour donné,
  * affichage multi-jours (24 h / 48 h …) avec empilement vertical.

# Prérequis
* Python 3.10+
* Home Assistant (optionnel, si vous utilisez la source `ha_ws`)
* Un _long-lived access token_ Home Assistant (si vous utilisez la source `ha_ws`)
* Paquets Python:
  * `websocket-client`, `rich`

```bash
pip install websocket-client rich
```

# Installation
Placez les fichiers dans un dossier de travail, par exemple :
```bash
energy_tool.py
cli_output.py
ha_ws_api.py
pv_config.json
```

# Configuration
Tout passe par un unique JSON (ex. `pv_config.json`)
<br />
Exemple minimal à adapter à vos valeurs :
```json
{
  "BASE_URL": "wss://votre-ha/api/websocket",
  "TOKEN": "XXXXXXXX",
  "PV_ENTITY": "sensor.envoy_xxx_production_d_energie_totale",
  "LOAD_ENTITY": "sensor.envoy_xxx_consommation_d_energie_totale",

  "START": "2025-03-01T00:00:00",
  "END":   "2025-04-01T00:00:00",

  "OUT_CSV_DETAIL": "ha_energy_import_export_hourly.csv",
  "OUT_CSV_DAILY":  "ha_energy_import_export_daily.csv",
  "OUT_CSV_SIMU":   "ha_energy_simulation_combos.csv",

  "PV_ACTUAL_KW": 4.0,

  "TARGET_AC_MIN": 85.0,
  "TARGET_AC_MAX": 95.0,
  "TARGET_TC_MIN": 75.0,

  "BATTERY_EFF": 0.90,
  "BATTERY_SIZES": [0,5,10,12,14,16,18,20,22,24,26,28,30],
  "PV_FACTORS":   [1.0,1.2,1.5,1.8,2.0,2.2,2.4,2.6,3.0],

  "GRID_CHARGE": true,
  "GRID_HOURS": [22,23,0,1,2,3,4,5],
  "GRID_TARGET_SOC": 0.80,
  "GRID_CHARGE_LIMIT": 3.0,

  "INITIAL_SOC": 0.50,
  "BATT_MIN_SOC": 0.10,

  "MAX_CHARGE_KW_PER_HOUR": 0.0,
  "MAX_DISCHARGE_KW_PER_HOUR": 0.0
}
```
## Champs importants
* BASE_URL/TOKEN/_ENTITY: connexion Home Assistant (mode `report`).
* START/END: fenêtre d'étude (ISO local sans `Z` pour éviter les décalages).
* TARGET_*: objectifs de sélection des scénarios (autoconsommation et couverture).
* BATTERY_/PV_FACTORS: grille de recherche de scénarios.
* GRID_*: recharge en heures creuses coté réseau (optionnel).
* INITIAL_SOC: état de charge initial de la batterie
* BATT_MIN_SOC: réserve non déchargeable de la batterie
* MAX_CHARGE/DISCHARGE_KW_PER_HOUR: limites (kWh par pas horaire). `0` = illimité

> [!NOTE]
> Vous pouvez overrider le scénario de simulation (PV et batterie) via le JSON en posant par ex. `SIM_OVERRIDE: {"pv_factor": 2.4, "batt_kwh": 24}` (si implémenté dans votre `energy_tool.py`).

# Lancer l'outil
## Rapport (extraction et calculs)
```bash
python3 energy_tool.py --mode report --config pv_config.json --source ha_ws
```
ou depuis un CSV déjà exporté :
```bash
python3 energy_tool.py --mode report --config pv_config.json --source csv
```
## Simulation (sélectionne les scénarios qui atteignent vos objectifs)
```bash
python3 energy_tool.py --mode simu --config pv_config.json
```
## Graphes (plot)
* Bipolaire simple (un CSV, un jour):
```bash
python3 energy_tool.py --mode plot --config pv_config.json --day 2025-06-01
```
* Comparatif Avant/Après
```bash
python3 energy_tool.py --mode plot --config pv_config.json --day 2025-06-01 --days 2
```
> [!NOTE]
> Les graphes utilisent `Rich` : couleurs, panneaux de contexte (puissance PV, scénario, SoC initial, AC/TC, etc.).

# Sorties générées
TODO
# Définitions et formules
## Autoconsommation (AC)
> [!NOTE]
> Part de la production PV consommée sur place.

<br />C'est le pourcentage de la production PV **directement utilisée** pour couvrir la consommation locale, **sans passer par l'export réseau**.

### Formule
$AC\ =\ (PV\ utilisée\ sur\ place / PV\ totale)\ *\ 100$
<br />
* **PV totale** = somme de toute la production PV sur la période.
* **PV utilisée sur place** dépend du mode :
  * **En mode report (réel)** :<br />
$PV\ utilisée\ =\ PV\ totale\ -\ Export$
  * **En mode simulation** :<br />
$PV utilisée\ =\ \sum(pv\\_direct + batt\\_to\\_load)$

### Valeur attendue
* Toujours comprise entre **0%** et **100%**

## Taux de couverture (TC)
> [!NOTE]
> Part de la consommation couverte par le PV.

<br />C'est le pourcentage de la consommation locale qui **provient de la production photovoltaique** (directement ou via batterie).

### Formule
$TC\ =\ (PV\ utilisée\ sur\ place / Consommation\ totale)\ *\ 100$
<br />
* **Consommation totale** = somme de la demande énergétique sur la période.
* **PV utilisée sur place** = identique à celle utilisée pour le calcul de l'AC:
  * **En mode report (réel)** :<br />
$PV\ utilisée\ =\ PV\ totale\ -\ Export$
  * **En mode simulation** :<br />
$PV utilisée\ =\ \sum(pv\\_direct + batt\\_to\\_load)$
 
### Valeur attendue
* Toujours comprise entre **0%** et **100%**

## Import
électricité prise au réseau

## Export
surplus injecté au réseau

# Modèle de simulation
Pour chaque heure h :
1. PV → charges directes : `pv_direct = min(pv[h], load[h])`
2. PV → batterie (stockage) : borné par capacité restante et `MAX_CHARGE_KW_PER_HOUR`
3. Batterie → charges : borné par SoC – réserve et `MAX_DISCHARGE_KW_PER_HOUR`
4. Import = reste de charge si non couvert
5. Export = surplus PV non stocké/consommé
6. Recharge réseau (HC) si activée, vers `GRID_TARGET_SOC` sans dépasser `GRID_CHARGE_LIMIT` (kWh/h)

Paramètres clés :
* Rendement unique `BATTERY_EFF` pour charge/décharge.
* `BATT_MIN_SOC` (réserve) : fraction non déchargeable.
* `INITIAL_SOC` : SoC initial au début de la fenêtre (pas de reset journalier).
* Limites charge/décharge (kWh/h) optionnelles.

# Graphes et console
