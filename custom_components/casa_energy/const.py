"""Costanti per l'integrazione Casa Energy."""

DOMAIN = "casa_energy"

# --- Step 1: sensori energy per lo storico ---
CONF_ENERGY_SENSORS = "energy_sensors"

# --- Step 2: tariffa ---
CONF_PRICE_PER_KWH = "price_per_kwh"
CONF_FIXED_MONTHLY_COST = "fixed_monthly_cost"
CONF_EXTRA_CHARGES_PER_KWH = "extra_charges_per_kwh"
CONF_VAT_RATE = "vat_rate"

# --- Voci di tariffa avanzate (opzionali): per bollette con struttura più
# articolata di prezzo/costo fisso/oneri/IVA semplici (es. più oneri di
# sistema distinti, componenti stagionali, voci senza IVA). Si sommano ai
# quattro campi semplici sopra, non li sostituiscono. ---
CONF_TARIFF_LINE_ITEMS = "tariff_line_items"
CONF_LINE_ITEM_NAME = "name"
CONF_LINE_ITEM_TYPE = "type"  # "per_kwh" oppure "fixed"
CONF_LINE_ITEM_VALUE = "value"
CONF_LINE_ITEM_APPLY_VAT = "apply_vat"
CONF_LINE_ITEM_MONTH_FROM = "month_from"  # 1-12, opzionale (assente = tutto l'anno)
CONF_LINE_ITEM_MONTH_TO = "month_to"  # 1-12, opzionale
LINE_ITEM_TYPE_PER_KWH = "per_kwh"
LINE_ITEM_TYPE_FIXED = "fixed"

# --- Step 3: potenza istantanea ---
CONF_TOTAL_POWER_SENSOR = "total_power_sensor"
CONF_MAX_POWER = "max_power"
CONF_WARNING_THRESHOLD_PCT = "warning_threshold_pct"
CONF_CRITICAL_THRESHOLD_PCT = "critical_threshold_pct"

# --- Step 4: carichi monitorati (auto-derivati dai sensori energy, entrano nel calcolo totale) ---
CONF_LOADS = "loads"
CONF_LOAD_NAME = "name"
CONF_LOAD_ENTITY = "entity"
CONF_LOAD_ENERGY_ENTITY = "energy_entity"  # sensore energy da cui questo carico è stato derivato

# --- Flag per bypassare l'errore bloccante quando un device non ha un
# sensore power abbinato al suo sensore energy (l'utente accetta il rischio
# che quel carico non venga conteggiato nella potenza istantanea) ---
CONF_IGNORE_UNMATCHED = "ignore_unmatched_power"

# --- Reset delle tariffe congelate sui mesi già chiusi (Opzioni → Tariffa) ---
CONF_RESET_FROZEN_TARIFFS = "reset_frozen_tariffs"

# --- Nome istanza (per supportare più config entry, es. Casa / Ufficio) ---
CONF_INSTANCE_NAME = "instance_name"

# --- Default ragionevoli, precompilati nel form ---
DEFAULT_VAT_RATE = 22.0
DEFAULT_WARNING_THRESHOLD_PCT = 75
DEFAULT_CRITICAL_THRESHOLD_PCT = 90
DEFAULT_MAX_POWER = 3300

# --- Intervallo di aggiornamento del coordinator (minuti) ---
UPDATE_INTERVAL_MINUTES = 15
