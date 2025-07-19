# --- Constants ---
SYPHILIS_DURATIONS = {
    # Durations in days
    'incubation': {'min': 10, 'avg': 21, 'max': 90},
    'primary': {'min': 7, 'avg': 21, 'max': 35}, # Chancre duration
    'latency': {'min': 0, 'avg': 28, 'max': 70}, # Between primary and secondary
    'secondary': {'min': 14, 'avg': 28, 'max': 42} # Symptom duration
}

SEX_TYPES = ['Oral', 'Anal', 'Vaginal']
DIAGNOSIS_OPTIONS = ['Primary Syphilis', 'Secondary Syphilis', 'Early Latent Syphilis', 'Late Latent Syphilis']
SYMPTOM_TYPES = ['Primary Chancre', 'Secondary Rash/Lesions'] # Simplified symptom types
FREQUENCY_UNITS = ['Day', 'Week', 'Month']