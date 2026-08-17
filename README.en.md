# Casa Energy

*[Leggi questo in italiano](README.md)*

A Home Assistant integration, installable via HACS, that calculates and monitors:

- **Monthly energy consumption history** (kWh) and estimated bill cost, from the long-term statistics Home Assistant already records for one or more "energy" sensors
- **Instant power** with automatic threshold status (`ok` / `warning` / `critical`), percentage relative to your meter's maximum power, and a list of the main monitored loads

All configuration happens through a graphical interface — no YAML to write, no SQL query to edit.

## Installation

### Via HACS (custom repository)

1. HACS → Integrations → menu (⋮) top right → **Custom repositories**
2. Add this repository's URL, category **Integration**
3. Search "Casa Energy" in the HACS list → Download
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/casa_energy/` folder to `/config/custom_components/`
2. Restart Home Assistant

## Configuration

After installing and restarting:

1. Settings → Devices & services → Add integration → search **Casa Energy**
2. Follow the guided steps:
   - **Instance name**: a label for this configuration (useful if you want to track multiple meters/homes separately in the future)
   - **Energy sensors**: select one or more sensors with `device_class: energy` you want history for. These are the devices that count toward the total instant power. The power sensor (Watts) of the same device is identified **automatically** (same Home Assistant device): you don't need to select it again. If a device has more than one power sensor, you'll be asked which one to use; if it has none, a blocking warning flags it (with the option to proceed anyway, accepting that device won't be counted)
   - **Tariff**: energy price (currency/kWh), fixed monthly costs, any extra fees, tax rate — always double-check these against your real bill
   - **Instant power**: your meter/system's maximum power, alert thresholds (as percentages)

If you also want to show devices that should **not** count toward the total (e.g. one already included in an aggregated load, or just something you want to keep an eye on), add them directly from the card's editor — see below.

## Changing the configuration after installation

Settings → Devices & services → Casa Energy → **Configure**. You can edit energy sensors, tariff, thresholds, and rename loads at any time, without reinstalling anything. If the energy sensor selection doesn't change, already-resolved loads (including any renames) stay unchanged.

## Included Lovelace card

The integration ships with a dedicated card (`Casa Energy Card`), served and **automatically registered** at install time — no file to copy, no resource to add by hand. After configuring the integration, look for it in your dashboard's "Add card" picker.

The card reads directly from the two generated entities: pick `sensor.<name>_power_status` and `sensor.<name>_monthly_energy_history` from the card's visual editor (or write the YAML yourself, if you prefer):

```yaml
type: custom:casa-energy-card
power_entity: sensor.casa_power_status
history_entity: sensor.casa_monthly_energy_history
```

### Display-only devices

From the card's editor you can add extra devices (name + power sensor) to show as separate chips, **excluded from the total**: useful for devices already included in an aggregated load, or just to keep an eye on them without contributing to the sum. Unlike the main loads, these don't go through the integration: they're managed entirely here, with a visual editor (name + entity picker, add/remove). In YAML:

```yaml
type: custom:casa-energy-card
power_entity: sensor.casa_power_status
history_entity: sensor.casa_monthly_energy_history
extra_devices:
  - name: "Server"
    entity: sensor.server_power
  - name: "Dishwasher"
    entity: sensor.dishwasher_power
```

### Reordering and renaming chips

From the card's editor you can drag (handle "☰") both the main loads and the display-only devices to change the order they appear in. On each row, the "✎" button opens a dedicated screen to rename that single chip: for main loads this doesn't touch the name configured in the integration, it only overrides the label shown in this card (saved in `load_labels`); for display-only devices it renames the entry in `extra_devices` directly.

**Note**: automatic Lovelace resource registration requires your dashboard to be in "storage" mode (the default for most installations). If you use a fully YAML-configured dashboard, auto-registration may not succeed — in that case a log message tells you to add the resource manually (Settings → Dashboards → Resources → URL `/casa_energy_static/casa-energy-card.js`, type JavaScript module). The integration remains fully functional either way: only the automatic card step might need a small manual step on this kind of setup.

If you configure multiple instances (e.g. Home and Office), the card is registered only once and stays available for all of them; it's removed only when the **last** instance is uninstalled.

## Entities created

For each configured instance, the integration creates:

| Entity | Description |
|---|---|
| `sensor.<name>_monthly_energy_history` | State: number of months available in the history. Attribute `mesi`: array of `{mese, kwh, costo}` for each month |
| `sensor.<name>_power_status` | State: current power in W, sum of the loads configured in the integration. Attributes: `status` (`ok`/`warning`/`critical`), `percent_of_max`, `max_power`, `warning_threshold_pct`, `critical_threshold_pct`, `loads` (array of `{name, value}`) |

## Alternative YAML card (optional)

If you'd rather not use the auto-registered card above, the repository still includes, in the [`examples_virtual_sensors/`](examples_virtual_sensors/) folder, the file `energy_summary_card_integration.yaml`: a more elaborate card (grid of loads, expandable previous-months history) to paste by hand, requiring `button-card` and `card_mod` via HACS.

## Integration icon

The integration ships with a dedicated icon (`custom_components/casa_energy/brand/`), shown automatically on the "Devices & services" page and in the add-integration picker. Requires **Home Assistant 2026.3 or later**: on older versions the icon simply doesn't appear (no error, just the generic icon), everything else keeps working normally.

## Technical notes

- The monthly history is recalculated every 15 minutes using Home Assistant's native statistics API (not direct SQL queries), so it works identically on installations using SQLite, MariaDB, or PostgreSQL as the recorder database.
- Instant power updates in real time (based on the source sensor's state-change events), not on the 15-minute interval.
- Thresholds and tariff are per-instance: if you configure multiple instances (e.g. Home and Office), each has its own independent values.
