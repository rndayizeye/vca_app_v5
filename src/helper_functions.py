from datetime import datetime, timedelta, date
#___ Importing constants and helper functions
from src.constants import SYPHILIS_DURATIONS, DIAGNOSIS_OPTIONS, SYMPTOM_TYPES, FREQUENCY_UNITS, SEX_TYPES
# --- Helper Functions ---

def parse_date(date_str):
    """Safely parse date strings, returning date object or None."""
    if not date_str: return None
    try:
        if isinstance(date_str, date): return date_str # Already date object
        return datetime.strptime(str(date_str).split('T')[0], '%Y-%m-%d').date()
    except (ValueError, TypeError): return None

def safe_get_list(data, key):
    """Safely get a list from a dict, returning empty list if key missing or not list."""
    if not isinstance(data, dict): return [] # Handle cases where data might not be a dict initially
    val = data.get(key, [])
    return val if isinstance(val, list) else []

def format_timedelta(td):
    """Format timedelta into a human-readable string"""
    if not isinstance(td, timedelta): return ""
    days = td.days
    if days >= 7:
        weeks = days // 7
        rem_days = days % 7
        return f"{weeks}w" + (f",{rem_days}d" if rem_days else "") # Shorter format
    return f"{days}d"

## to do: add symptom_type == 'Ghosted Primary Chancre' and 'Ghosted Secondary Rash/Lesions' cases
def get_symptom_rank(symptom_type):
    """Assigns rank based on ghosting hierarchy"""
    if symptom_type == 'Primary Chancre': return 1 # Existing primary is highest
    elif symptom_type == 'Secondary Rash/Lesions': return 4
    return 99 # Lowest rank for others

def get_avg_inoculation_date(symptom_onset, symptom_type):
    """Calculate the average estimated inoculation date based on a symptom"""
    onset = parse_date(symptom_onset)
    if not onset: return None
    avg_incubation = timedelta(days=SYPHILIS_DURATIONS['incubation']['avg'])
    avg_primary_duration = timedelta(days=SYPHILIS_DURATIONS['primary']['avg'])
    avg_latency = timedelta(days=SYPHILIS_DURATIONS['latency']['avg'])
    if symptom_type == 'Primary Chancre': return onset - avg_incubation
    elif symptom_type == 'Secondary Rash/Lesions':
        avg_secondary_onset_from_inoc = avg_incubation + avg_primary_duration + avg_latency
        return onset - avg_secondary_onset_from_inoc
    return None

def get_chancre_midpoint_date(symptom_onset, symptom_duration_days, symptom_type):
    """Calculate the midpoint date of a primary chancre (real or ghosted)"""
    onset = parse_date(symptom_onset)
    if not onset or symptom_type != 'Primary Chancre': return None
    duration = symptom_duration_days if isinstance(symptom_duration_days, int) and symptom_duration_days > 0 else SYPHILIS_DURATIONS['primary']['avg']
    return onset + timedelta(days=duration / 2.0) # Use float division

def calculate_inoculation_points(symptoms):
    """Calculates min, avg, max inoculation dates based on PRIMARY symptoms"""
    primary_symptoms = [s for s in symptoms if isinstance(s, dict) and s.get('type') == 'Primary Chancre']
    if not primary_symptoms: return None, None, None

    min_inoc_date, avg_inoc_date, max_inoc_date = None, None, None
    earliest_onset = None

    for symp in primary_symptoms:
        onset = parse_date(symp.get('onset'))
        if not onset: continue

        # Keep track of the earliest onset for avg/max calculation basis
        if earliest_onset is None or onset < earliest_onset:
            earliest_onset = onset

        current_min = onset - timedelta(days=SYPHILIS_DURATIONS['incubation']['max'])
        if min_inoc_date is None or current_min < min_inoc_date: min_inoc_date = current_min

    # Calculate avg/max based on the single earliest primary symptom's onset
    if earliest_onset:
        avg_inoc_date = earliest_onset - timedelta(days=SYPHILIS_DURATIONS['incubation']['avg'])
        max_inoc_date = earliest_onset - timedelta(days=SYPHILIS_DURATIONS['incubation']['min'])

    return min_inoc_date, avg_inoc_date, max_inoc_date

def calculate_earliest_inoculation(symptoms):
    """Calculates the earliest possible inoculation date based on ALL symptoms"""
    earliest_overall = None
    if not isinstance(symptoms, list): return None

    for symp in symptoms:
         if not isinstance(symp, dict): continue
         onset = parse_date(symp.get('onset'))
         symp_type = symp.get('type')
         if not onset or not symp_type: continue

         current_earliest = None
         if symp_type == 'Primary Chancre':
             # Earliest inoculation = onset - max incubation time
             current_earliest = onset - timedelta(days=SYPHILIS_DURATIONS['incubation']['max'])
         elif symp_type == 'Secondary Rash/Lesions':
             # Earliest inoculation = onset - max time from inoculation to secondary onset
             max_total_offset = timedelta(days=SYPHILIS_DURATIONS['incubation']['max'] +
                                               SYPHILIS_DURATIONS['primary']['max'] +
                                               SYPHILIS_DURATIONS['latency']['max'])
             current_earliest = onset - max_total_offset

         if current_earliest and (earliest_overall is None or current_earliest < earliest_overall):
             earliest_overall = current_earliest

    return earliest_overall
