# Energy Tool

[![License](https://img.shields.io/github/license/sinseman44/energy_tool?style=for-the-badge)](https://github.com/sinseman44/energy_tool/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sinseman44/energy_tool?style=for-the-badge)](https://github.com/sinseman44/energy_tool/releases)
<br />

## Contexte

Dans le but de tendre vers une indépendance énergetique (partielle ou totale) de mon logement, j'ai réalisé ce simulateur d'energie permettant de quantifier _au plus juste_ mon besoin en production solaire et stockage d'énergie.<br />
Mon logement étant déjà équipé de panneaux photovoltaiques en autoconsommation avec revente de surplus, je me suis servi des données agrégées, au fil des mois, par mon système domotique (Home Assistant) pour créer ce simulateur.<br />
<br />Cet outil a pour but :
* de **récolter les données** de mon système domotique sur _une période de temps limitée_ (période d'étude).
* Sur cette période d'étude, de **définir le meilleur compromis** en terme d'ajout de _production solaire_ et _stockage d'énergie_ en fonction de mes objectifs en _autoconsommation_ et _taux de couverture_ (autosuffisance).
* Sur cette même période d'étude, de simuler ce scénario (meilleur compromis) ou un scénario forcé sur les données récoltées de mon système domotique.
* D'afficher les résultats sous forme de graphes avec un Avant (valeurs actuelles)/Après (valeurs simulées).

> [!WARNING]
> Cet outil doit être utilisé à titre informatif et ne peux pas répondre avec une grande précision aux besoins exprimés.

# Support

<a href="https://www.buymeacoffee.com/sinseman44" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 145px !important;" ></a>

# Todo 📃 and Bug report 🐞

See [Github To Do & Bug List](https://github.com/sinseman44/energy_tool/issues)

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
> Part de la consommation couverte par le PV.<br />
> Plus cette valeur tend vers 100%, moins nous sommes dépendants du réseau électrique.

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
![ha_long_lived_token](assets/HA_long_lived_token.png)
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

  "ALLOW_DISCHARGE_IN_HC": true,
  "GRID_CHARGE_IN_HC": true,
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
* **BASE_URL/TOKEN**: connexion Home Assistant (mode `report` avec la source `ha_ws`).
* **PV_ENTITY/LOAD_ENTITY**: L'entité de production totale et de consommation totale d'Home Assistant (mode `report` avec la source `ha_ws`).
* **START/END**: fenêtre d'étude (ISO local sans `Z` pour éviter les décalages).
* **TARGET_AC_MIN/TARGET_AC_MAX/TARGET_TC_MIN**: objectifs de sélection des scénarios pour l'autoconsommation et le taux de couverture (mode `simu`).
* **BATTERY_EFF/BATTERY_SIZES/PV_FACTORS**: grille de recherche de scénarios (mode `simu`).
* **ALLOW_DISCHARGE_IN_HC**: autorise la décharge de la batterie en heures creuses (mode `simu`).
* **GRID_CHARGE_IN_HC**: autorise la charge de la batterie en heures creuses (mode `simu`).
* **GRID_HOURS**: heures creuses (mode `simu`).
* **GRID_TARGET_SOC**: Jusqu'à quel niveau de charge, on souhaite remonter la batterie (mode `simu`).
* **GRID_CHARGE_LIMIT**: La puissance maximale de recharge par heure, en kWh (mode `simu`).
* **INITIAL_SOC**: état de charge initial de la batterie pour la période d'étude.
* **BATT_MIN_SOC**: réserve non déchargeable de la batterie.
* **DISCHARGE_KW_PER_HOUR**: limites (kWh par pas horaire). `0` = illimité

> [!NOTE]
> Vous pouvez forcer le scénario de simulation (PV et batterie) via le JSON en posant par ex. `SIM_OVERRIDE: {"pv_factor": 2.4, "batt_kwh": 24}`.

# Lancer l'outil
## Rapport (extraction et calculs)
```bash
python3 energy_tool.py --mode report --config pv_config.json --source ha_ws
```
ou depuis un CSV déjà exporté :
```bash
python3 energy_tool.py --mode report --config pv_config.json --source csv
```
Exemple d'affichage :<br />
![example_report](assets/energy_tool_report_example.png)

## Simulation (sélectionne les scénarios qui atteignent vos objectifs)
```bash
python3 energy_tool.py --mode simu --config pv_config.json
```
Exemple d'affichage :<br />
![example_simu](assets/energy_tool_simu_example.png)

## Graphes (plot)
* Bipolaire simple (un CSV, un jour):
```bash
python3 energy_tool.py --mode plot --config pv_config.json --day 2025-06-01
```
Exemple d'affichage :<br />
![example_plot](assets/energy_tool_plot_example.png)

* Comparatif Avant/Après
```bash
python3 energy_tool.py --mode plot --config pv_config.json --day 2025-06-01 --days 2
```
Exemple d'affichage :<br />
![example_plot_48h_1](assets/energy_tool_plot_48h_example_1.png)
![example_plot_48h_2](assets/energy_tool_plot_48h_example_2.png)

> [!NOTE]
> Les graphes utilisent `Rich` : couleurs, panneaux de contexte (puissance PV, scénario, SoC initial, AC/TC, etc.).

# Sorties générées
TODO

# Modèle de simulation
Pour chaque heure h :
1. PV → charges directes : `pv_direct = min(pv[h], load[h])`
2. Batterie → charges : borné par SoC – réserve et `MAX_DISCHARGE_KW_PER_HOUR`
3. Import = reste de charge si non couvert
4. PV → batterie (stockage) : borné par capacité restante et `MAX_CHARGE_KW_PER_HOUR`
5. Export = surplus PV non stocké/consommé
6. Recharge réseau (HC) si activée, vers `GRID_TARGET_SOC` sans dépasser `GRID_CHARGE_LIMIT` (kWh)

Paramètres clés :
* Rendement unique `BATTERY_EFF` pour charge/décharge.
* `BATT_MIN_SOC` (réserve) : fraction non déchargeable.
* `INITIAL_SOC` : SoC initial au début de la fenêtre (pas de reset journalier).
* Limites charge/décharge (kWh/h) optionnelles.

## Scénarios envisagés pour la Charge/Décharge de la batterie en Heures Creuses

| `ALLOW_DISCHARGE_IN_HC` | `GRID_CHARGE_IN_HC` | Comportement |
|:-----------------------:|:-------------------:|--------------|
| **FALSE**               | **FALSE**           | **Ni charge, ni décharge** en HC -> tout vient du réseau             |
| **FALSE**               | **TRUE**            | **Recharge autorisée**, mais pas de décharge -> on remplit la batterie avec le réseau, toute la conso vient du réseau             |
| **TRUE**                | **FALSE**           | **Décharge autorisée**, mais pas de recharge -> la batterie allimente le load si disponible             |
| **TRUE**                | **TRUE**            | **Recharge et décharge autorisée**, priorité à la recharge             |

Dans une stratégie d'optimisation de l'autoconsommation pour les tarifs HC/HP:
* On met `GRID_CHARGE_IN_HC = true` pour profiter des HC pour charger avec le réseau et alimenter l'habitation avec le réseau.
* On met `ALLOW_DISCHARGE_IN_HC = false` pour éviter de vider la batterie en HC et maximiser l'autoconsommation.

# Graphes et console
