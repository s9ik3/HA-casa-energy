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
2. Follow the 4 guided steps:
   - **Instance name**: a label for this configuration (useful if you want to track multiple meters/homes separately in the future)
   - **Energy sensors**: select one or more sensors with `device_class: energy` you want history for
   - **Tariff**: energy price (currency/kWh), fixed monthly costs, any extra fees, tax rate — always double-check these against your real bill
   - **Instant power**: total power sensor, your meter/system's maximum power, alert thresholds (as percentages)
3. Optional: add one or more "loads" to monitor individually (name + power sensor)

## Changing the configuration after installation

Settings → Devices & services → Casa Energy → **Configure**. You can edit sensors, tariff, thresholds, and manage (add/remove) monitored loads at any time, without reinstalling anything.

## Entities created

For each configured instance, the integration creates:

| Entity | Description |
|---|---|
| `sensor.<name>_monthly_energy_history` | State: number of months available in the history. Attribute `mesi`: array of `{mese, kwh, costo}` for each month |
| `sensor.<name>_power_status` | State: current power in W. Attributes: `status` (`ok`/`warning`/`critical`), `percent_of_max`, `max_power`, `warning_threshold_pct`, `critical_threshold_pct`, `loads` (array of `{name, value}`) |

## Example Lovelace card

The repository includes, in the [`examples_virtual_sensors/`](examples_virtual_sensors/) folder, the file `energy_summary_card_integration.yaml`: a ready-to-use card built specifically for the two entities this integration generates (only two entity IDs to replace, everything else already lives in the attributes).

## Technical notes

- The monthly history is recalculated every 15 minutes using Home Assistant's native statistics API (not direct SQL queries), so it works identically on installations using SQLite, MariaDB, or PostgreSQL as the recorder database.
- Instant power updates in real time (based on the source sensor's state-change events), not on the 15-minute interval.
- Thresholds and tariff are per-instance: if you configure multiple instances (e.g. Home and Office), each has its own independent values.
