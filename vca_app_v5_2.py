# -*- coding: utf-8 -*-
import dash
from dash import dcc, html, Input, Output, State, ctx, callback, ALL, MATCH, Patch
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import uuid # For unique IDs for partners/components if needed later
import math # For midpoint calculations

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

# --- NEW Helper Functions ---
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

# --- App Initialization ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server

# --- Initial Data Structures ---
DEFAULT_PATIENT_DATA = {
    'id': 'patient', 'name': '', 'reason': '', 'diagnosis': None,
    'elicited_exposure_start': None, 'elicited_exposure_end': None, # New
    'labs': [], 'symptoms': [], 'treatments': [], 'ghosted_lesions': [] # New
}
DEFAULT_PARTNER_DATA = {
    'id': None, 'name': '', 'diagnosis': None,
    'first_exposure': None, 'last_exposure': None,
    'frequency_value': None, 'frequency_unit': None, 'sex_types': [],
    'labs': [], 'symptoms': [], 'treatments': [], 'ghosted_lesions': [] # New
}

# --- App Layout ---
app.layout = html.Div([
    html.H1("Syphilis VCA & Ghosting Analysis Tool"),

    # --- Data Stores ---
    dcc.Store(id='patient-data-store', data=DEFAULT_PATIENT_DATA),
    dcc.Store(id='partners-data-store', data=[]),
    dcc.Store(id='current-partner-form-store', data=DEFAULT_PARTNER_DATA),
    dcc.Store(id='duration-visibility-store', data=True),

    # --- Main Content Area ---
    html.Div([ # Main Row Div
        # == Patient Input Section ==
        html.Div([
            html.H2("Patient Information"),
            html.Div([
                html.Label("Optional Name/ID:"),
                dcc.Input(id='patient-name', type='text', placeholder="e.g., OP 123")
            ], className='form-row'),
            html.Div([
                html.Label("Reason for Testing:"),
                dcc.Input(id='patient-reason', type='text', placeholder="e.g., volunteer",style={'width': '80%'})
            ], className='form-row'),
             html.Div([
                html.Label("Diagnosis:"),
                dcc.Dropdown(id='patient-diagnosis', options=DIAGNOSIS_OPTIONS, style={'minWidth': '250px'})
            ], className='form-row'),
            html.H4("Patient's Elicited Exposure Period:"),
            html.H4("Add Last Lab Result:"),
            html.Div([
                dcc.DatePickerSingle(id='patient-lab-date', placeholder="Lab Date"),
                dcc.Input(id='patient-lab-type', placeholder="Lab Type (e.g., RPR)"),
                dcc.Input(id='patient-lab-result', placeholder="Result (e.g., 1:16)"),
                html.Button("Add Lab", id='patient-add-lab-btn', n_clicks=0)
            ], className='form-row-flex'),
             html.Div(id='patient-labs-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
            html.H4("Add Last Symptom:"),
             html.Div([
                dcc.Dropdown(id='patient-symptom-type', options=SYMPTOM_TYPES, placeholder="Symptom Type", style={'minWidth': '180px'}),
                dcc.DatePickerSingle(id='patient-symptom-onset', placeholder="Onset Date"),
                dcc.Input(id='patient-symptom-duration', type='number', placeholder="Duration (days, optional)"),
                 html.Button("Add Symptom", id='patient-add-symptom-btn', n_clicks=0)
            ], className='form-row-flex'),
             html.Div(id='patient-symptoms-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
            html.H4("Add Last Treatment:"),
             html.Div([
                dcc.DatePickerSingle(id='patient-treatment-date', placeholder="Treatment Date"),
                dcc.Input(id='patient-treatment-details', placeholder="Treatment Details (e.g., Bicillin 2.4mu)", style={'width': '50%'}),
                 html.Button("Add Treatment", id='patient-add-treatment-btn', n_clicks=0)
            ], className='form-row-flex'),
            html.Div(id='patient-treatments-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
        ], className='section-box'),

        # == Partner Input Section ==
        html.Div([
             html.H2("Partner Information (Enter One Partner at a Time)"),
            html.Div(id='current-partner-id-display', style={'fontWeight':'bold', 'marginBottom':'10px'}),
            html.Div([
                html.Label("Optional Name/ID:"),
                dcc.Input(id='partner-name', type='text', placeholder="e.g., Partner A")
            ], className='form-row'),
            html.H4("Partner's Report of Exposure w/ Patient:"), # Clarified label
             html.Div([
                 html.Div([
                 html.Label("First Possible Exposure:"), dcc.DatePickerSingle(id='patient-elicited-exposure-start'),
                 html.Label("Last Possible Exposure:"), dcc.DatePickerSingle(id='patient-elicited-exposure-end'),
            ], className='form-row-flex'),
           
                 html.Label("First Exposure:"), dcc.DatePickerSingle(id='partner-first-exposure'),
                 html.Label("Last Exposure:"), dcc.DatePickerSingle(id='partner-last-exposure'),
             ], className='form-row-flex'),
             html.Div([
                 html.Label("Frequency:"),
                 dcc.Input(id='partner-freq-value', type='number', placeholder="Value", min=1, step=1, style={'width': '80px'}),
                 dcc.Dropdown(id='partner-freq-unit', options=FREQUENCY_UNITS, placeholder="Unit", style={'minWidth': '100px'}),
             ], className='form-row-flex'),
             html.Div([
                 html.Label("Sex Type(s):"),
                 dcc.Checklist(id='partner-sex-types', options=SEX_TYPES, inline=True)
             ], className='form-row'),
             html.Div([
                html.Label("Partner Diagnosis:"),
                dcc.Dropdown(id='partner-diagnosis', options=DIAGNOSIS_OPTIONS, style={'minWidth': '250px'})
            ], className='form-row'),
            html.H4("Add Last Partner Lab Result:"),
            html.Div([
                dcc.DatePickerSingle(id='partner-lab-date', placeholder="Lab Date"),
                dcc.Input(id='partner-lab-type', placeholder="Lab Type"),
                dcc.Input(id='partner-lab-result', placeholder="Result"),
                html.Button("Add Partner Lab", id='partner-add-lab-btn', n_clicks=0)
            ], className='form-row-flex'),
            html.Div(id='partner-labs-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
            html.H4("Add Last Partner Symptom:"),
             html.Div([
                 dcc.Dropdown(id='partner-symptom-type', options=SYMPTOM_TYPES, placeholder="Symptom Type", style={'minWidth': '180px'}),
                 dcc.DatePickerSingle(id='partner-symptom-onset', placeholder="Onset Date"),
                 dcc.Input(id='partner-symptom-duration', type='number', placeholder="Duration (days, optional)"),
                 html.Button("Add Partner Symptom", id='partner-add-symptom-btn', n_clicks=0)
            ], className='form-row-flex'),
            html.Div(id='partner-symptoms-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
            html.H4("Add Last Partner Treatment:"),
             html.Div([
                dcc.DatePickerSingle(id='partner-treatment-date', placeholder="Treatment Date"),
                dcc.Input(id='partner-treatment-details', placeholder="Treatment Details", style={'width': '50%'}),
                 html.Button("Add Partner Treatment", id='partner-add-treatment-btn', n_clicks=0)
            ], className='form-row-flex'),
            html.Div(id='partner-treatments-list', style={'marginLeft': '20px', 'fontSize': 'small'}),
            html.Div([
                html.Button("Save Partner to List / Update Selected", id='save-partner-btn', n_clicks=0, style={'marginRight': '10px'}),
                html.Button("Clear Partner Form", id='clear-partner-form-btn', n_clicks=0)
            ], style={'marginTop': '20px'})
        ], className='section-box'),
    ], style={'display': 'flex', 'flexDirection': 'row', 'gap': '20px'}), # End Main Row Div

    # == Saved Partners List & Selection for Edit ==
    html.Div([
        html.H3("Saved Partners"),
        html.Div(id='saved-partners-list-display'),
        dcc.Dropdown(id='edit-partner-select', placeholder="Select Partner to Edit/View", style={'marginTop':'10px'})
    ], className='section-box', style={'marginTop': '20px'}),

    # == VCA Plot ==
    html.Div([
        html.Div([ # Row for title and button
            html.H2("Visual Case Analysis Timeline", style={'display':'inline-block', 'marginRight':'20px'}),
            html.Button("Hide Symptom Durations", id='toggle-duration-btn', n_clicks=0)
        ]),
        dcc.Graph(id='vca-graph')
    ], className='section-box', style={'marginTop': '20px'}),

    # == Ghosting Analysis ==
    html.Div([
        html.H2("Ghosting Analysis"),
        html.Div([
            html.Label("Select Saved Partner to compare with Patient:"),
            dcc.Dropdown(id='ghosting-partner-select') # Options populated by callback
        ], style={'marginBottom': '10px'}),
        html.Button("Run Ghosting Analysis", id='run-ghosting-btn', n_clicks=0),
        html.Div(id='ghosting-result-output', style={'marginTop': '15px', 'whiteSpace': 'pre-wrap', 'border': '1px dashed #ccc', 'padding': '10px', 'backgroundColor': '#f0f0f0', 'fontFamily': 'monospace'})
    ], className='section-box', style={'marginTop': '20px'}),

    # == Clear All Data ==
     html.Div([
         html.Button("Clear All Patient and Partner Data", id='clear-all-data-btn', n_clicks=0, style={'color': 'red', 'marginTop': '30px'})
     ]),

], style={'padding': '20px'})


# --- Callbacks ---

# --- Input Form Callbacks ---
@callback(
    Output('patient-data-store', 'data', allow_duplicate=True),
    Input('patient-name', 'value'), Input('patient-reason', 'value'),
    Input('patient-diagnosis', 'value'), Input('patient-elicited-exposure-start', 'date'),
    Input('patient-elicited-exposure-end', 'date'), State('patient-data-store', 'data'),
    prevent_initial_call=True
)
def update_patient_basic_info(name, reason, diagnosis, elicited_start, elicited_end, patient_data):
    if not isinstance(patient_data, dict): patient_data = DEFAULT_PATIENT_DATA.copy()
    patch = Patch(); patch['name'] = name; patch['reason'] = reason; patch['diagnosis'] = diagnosis
    patch['elicited_exposure_start'] = elicited_start; patch['elicited_exposure_end'] = elicited_end
    return patch

@callback(
    Output('patient-data-store', 'data', allow_duplicate=True),
    Output('patient-labs-list', 'children'), Input('patient-add-lab-btn', 'n_clicks'),
    State('patient-lab-date', 'date'), State('patient-lab-type', 'value'),
    State('patient-lab-result', 'value'), State('patient-data-store', 'data'),
    prevent_initial_call=True
)
def add_patient_lab(n_clicks, date, type, result, patient_data):
    if not isinstance(patient_data, dict): patient_data = DEFAULT_PATIENT_DATA.copy(); patch=Patch()
    else: patch = Patch()
    current_labs = safe_get_list(patient_data, 'labs'); updated_labs_list = current_labs[:]
    if date and type and result: new_lab = {'date': date, 'type': type, 'result': result}; updated_labs_list.append(new_lab); patch['labs'] = updated_labs_list
    display_items = [html.Li(f"{l.get('date','?')}: {l.get('type','?')} - {l.get('result','?')}") for l in updated_labs_list]
    return patch, display_items

@callback(
    Output('patient-data-store', 'data', allow_duplicate=True),
    Output('patient-symptoms-list', 'children'), Input('patient-add-symptom-btn', 'n_clicks'),
    State('patient-symptom-type', 'value'), State('patient-symptom-onset', 'date'),
    State('patient-symptom-duration', 'value'), State('patient-data-store', 'data'),
    prevent_initial_call=True
)
def add_patient_symptom(n_clicks, type, onset, duration, patient_data):
    if not isinstance(patient_data, dict): patient_data = DEFAULT_PATIENT_DATA.copy(); patch=Patch()
    else: patch = Patch()
    current_symptoms = safe_get_list(patient_data, 'symptoms'); updated_symptoms_list = current_symptoms[:]
    onset_date = parse_date(onset)
    if type and onset_date:
        duration_days = int(duration) if duration and str(duration).isdigit() else None
        if duration_days is None:
             if type == 'Primary Chancre': duration_days = SYPHILIS_DURATIONS['primary']['max']
             elif type == 'Secondary Rash/Lesions': duration_days = SYPHILIS_DURATIONS['secondary']['max']
        new_symptom = {'type': type, 'onset': onset, 'duration': duration_days}; updated_symptoms_list.append(new_symptom); patch['symptoms'] = updated_symptoms_list
    display_items = [html.Li(f"{s.get('onset','?')}: {s.get('type','?')} (Duration: {s.get('duration','N/A')} days)") for s in updated_symptoms_list]
    return patch, display_items

@callback(
    Output('patient-data-store', 'data', allow_duplicate=True),
    Output('patient-treatments-list', 'children'), Input('patient-add-treatment-btn', 'n_clicks'),
    State('patient-treatment-date', 'date'), State('patient-treatment-details', 'value'),
    State('patient-data-store', 'data'), prevent_initial_call=True
)
def add_patient_treatment(n_clicks, date, details, patient_data):
    if not isinstance(patient_data, dict): patient_data = DEFAULT_PATIENT_DATA.copy(); patch=Patch()
    else: patch = Patch()
    current_treatments = safe_get_list(patient_data, 'treatments'); updated_treatments_list = current_treatments[:]
    if date and details: new_treatment = {'date': date, 'details': details}; updated_treatments_list.append(new_treatment); patch['treatments'] = updated_treatments_list
    display_items = [html.Li(f"{t.get('date','?')}: {t.get('details','?')}") for t in updated_treatments_list]
    return patch, display_items

@callback(
    Output('current-partner-form-store', 'data'),
    Input('partner-name', 'value'), Input('partner-first-exposure', 'date'),
    Input('partner-last-exposure', 'date'), Input('partner-freq-value', 'value'),
    Input('partner-freq-unit', 'value'), Input('partner-sex-types', 'value'),
    Input('partner-diagnosis', 'value'), State('current-partner-form-store', 'data'),
    prevent_initial_call=True
)
def update_current_partner_form_basic(name, first_exp, last_exp, freq_val, freq_unit, sex_types, diagnosis, current_data):
    if not isinstance(current_data, dict): current_data = DEFAULT_PARTNER_DATA.copy()
    patch = Patch()
    patch['name'] = name; patch['first_exposure'] = first_exp; patch['last_exposure'] = last_exp
    patch['frequency_value'] = freq_val; patch['frequency_unit'] = freq_unit
    patch['sex_types'] = sex_types if sex_types else []; patch['diagnosis'] = diagnosis
    return patch

@callback(
    Output('current-partner-form-store', 'data', allow_duplicate=True),
    Output('partner-labs-list', 'children'), Input('partner-add-lab-btn', 'n_clicks'),
    State('partner-lab-date', 'date'), State('partner-lab-type', 'value'),
    State('partner-lab-result', 'value'), State('current-partner-form-store', 'data'),
    prevent_initial_call=True
)
def add_partner_form_lab(n_clicks, date, type, result, partner_form_data):
    patch = Patch()
    if not isinstance(partner_form_data, dict): partner_form_data = DEFAULT_PARTNER_DATA.copy()
    current_labs = safe_get_list(partner_form_data, 'labs'); updated_labs_list = current_labs[:]
    if date and type and result: new_lab = {'date': date, 'type': type, 'result': result}; updated_labs_list.append(new_lab); patch['labs'] = updated_labs_list
    display_items = [html.Li(f"{l.get('date','?')}: {l.get('type','?')} - {l.get('result','?')}") for l in updated_labs_list]
    return patch, display_items

@callback(
    Output('current-partner-form-store', 'data', allow_duplicate=True),
    Output('partner-symptoms-list', 'children'), Input('partner-add-symptom-btn', 'n_clicks'),
    State('partner-symptom-type', 'value'), State('partner-symptom-onset', 'date'),
    State('partner-symptom-duration', 'value'), State('current-partner-form-store', 'data'),
    prevent_initial_call=True
)
def add_partner_form_symptom(n_clicks, type, onset, duration, partner_form_data):
    patch = Patch()
    if not isinstance(partner_form_data, dict): partner_form_data = DEFAULT_PARTNER_DATA.copy()
    current_symptoms = safe_get_list(partner_form_data, 'symptoms'); updated_symptoms_list = current_symptoms[:]
    onset_date = parse_date(onset)
    if type and onset_date:
        duration_days = int(duration) if duration and str(duration).isdigit() else None
        if duration_days is None:
             if type == 'Primary Chancre': duration_days = SYPHILIS_DURATIONS['primary']['max']
             elif type == 'Secondary Rash/Lesions': duration_days = SYPHILIS_DURATIONS['secondary']['max']
        new_symptom = {'type': type, 'onset': onset, 'duration': duration_days}; updated_symptoms_list.append(new_symptom); patch['symptoms'] = updated_symptoms_list
    display_items = [html.Li(f"{s.get('onset','?')}: {s.get('type','?')} (Duration: {s.get('duration','N/A')} days)") for s in updated_symptoms_list]
    return patch, display_items

@callback(
    Output('current-partner-form-store', 'data', allow_duplicate=True),
    Output('partner-treatments-list', 'children'), Input('partner-add-treatment-btn', 'n_clicks'),
    State('partner-treatment-date', 'date'), State('partner-treatment-details', 'value'),
    State('current-partner-form-store', 'data'), prevent_initial_call=True
)
def add_partner_form_treatment(n_clicks, date, details, partner_form_data):
    patch = Patch()
    if not isinstance(partner_form_data, dict): partner_form_data = DEFAULT_PARTNER_DATA.copy()
    current_treatments = safe_get_list(partner_form_data, 'treatments'); updated_treatments_list = current_treatments[:]
    if date and details: new_treatment = {'date': date, 'details': details}; updated_treatments_list.append(new_treatment); patch['treatments'] = updated_treatments_list
    display_items = [html.Li(f"{t.get('date','?')}: {t.get('details','?')}") for t in updated_treatments_list]
    return patch, display_items

# --- Partner List Management Callbacks ---
@callback(
    Output('partners-data-store', 'data', allow_duplicate=True),
    Output('current-partner-form-store', 'data', allow_duplicate=True), Output('partner-labs-list', 'children', allow_duplicate=True),
    Output('partner-symptoms-list', 'children', allow_duplicate=True), Output('partner-treatments-list', 'children', allow_duplicate=True),
    Output('current-partner-id-display', 'children', allow_duplicate=True), Output('partner-name', 'value', allow_duplicate=True),
    Output('partner-first-exposure', 'date', allow_duplicate=True), Output('partner-last-exposure', 'date', allow_duplicate=True),
    Output('partner-freq-value', 'value', allow_duplicate=True), Output('partner-freq-unit', 'value', allow_duplicate=True),
    Output('partner-sex-types', 'value', allow_duplicate=True), Output('partner-diagnosis', 'value', allow_duplicate=True),
    Input('save-partner-btn', 'n_clicks'), State('current-partner-form-store', 'data'),
    State('partners-data-store', 'data'), prevent_initial_call=True
)
def save_or_update_partner(n_clicks, partner_form_data, partners_list):
    if not isinstance(partner_form_data, dict): partner_form_data = {}
    if not partner_form_data or not (partner_form_data.get('name') or partner_form_data.get('id')): raise dash.exceptions.PreventUpdate
    partners_list = partners_list if partners_list else []
    partner_id = partner_form_data.get('id')
    partner_to_save = partner_form_data.copy()
    for key in ['labs', 'symptoms', 'treatments', 'sex_types', 'ghosted_lesions']:
        if key not in partner_to_save or not isinstance(partner_to_save.get(key), list): partner_to_save[key] = []
    if partner_id: # Update existing
        updated_list = [] ; found = False
        for p in partners_list:
            if p.get('id') == partner_id: updated_list.append(partner_to_save); found = True
            else: updated_list.append(p)
        if not found: partners_list.append(partner_to_save)
        else: partners_list = updated_list
    else: # New partner
        new_id = str(uuid.uuid4()); partner_to_save['id'] = new_id
        partners_list.append(partner_to_save)
    return (partners_list, DEFAULT_PARTNER_DATA.copy(), None, None, None, "", None, None, None, None, None, [], None)

@callback(
    Output('current-partner-form-store', 'data', allow_duplicate=True), Output('partner-labs-list', 'children', allow_duplicate=True),
    Output('partner-symptoms-list', 'children', allow_duplicate=True), Output('partner-treatments-list', 'children', allow_duplicate=True),
    Output('current-partner-id-display', 'children', allow_duplicate=True), Output('partner-name', 'value', allow_duplicate=True),
    Output('partner-first-exposure', 'date', allow_duplicate=True), Output('partner-last-exposure', 'date', allow_duplicate=True),
    Output('partner-freq-value', 'value', allow_duplicate=True), Output('partner-freq-unit', 'value', allow_duplicate=True),
    Output('partner-sex-types', 'value', allow_duplicate=True), Output('partner-diagnosis', 'value', allow_duplicate=True),
    Input('clear-partner-form-btn', 'n_clicks'), prevent_initial_call=True
)
def clear_partner_form(n_clicks):
     return (DEFAULT_PARTNER_DATA.copy(), None, None, None, "", None, None, None, None, None, [], None)

@callback(
    Output('saved-partners-list-display', 'children'), Output('edit-partner-select', 'options'),
    Output('ghosting-partner-select', 'options'), Input('partners-data-store', 'data')
)
def update_saved_partners_display(partners_list):
    partners_list = partners_list if partners_list else []
    if not partners_list: display = html.P("No partners saved yet."); options = []
    else:
        display_items = [] ; options = []
        for p in partners_list:
             p_id = p.get('id', 'UNKNOWN_ID'); name = p.get('name', f"Partner ID: {p_id}")
             display_items.append(html.Li(name)); options.append({'label': name, 'value': p_id})
        display = html.Ul(display_items)
    return display, options, options

@callback(
    Output('current-partner-form-store', 'data', allow_duplicate=True), Output('partner-labs-list', 'children', allow_duplicate=True),
    Output('partner-symptoms-list', 'children', allow_duplicate=True), Output('partner-treatments-list', 'children', allow_duplicate=True),
    Output('current-partner-id-display', 'children', allow_duplicate=True), Output('partner-name', 'value', allow_duplicate=True),
    Output('partner-first-exposure', 'date', allow_duplicate=True), Output('partner-last-exposure', 'date', allow_duplicate=True),
    Output('partner-freq-value', 'value', allow_duplicate=True), Output('partner-freq-unit', 'value', allow_duplicate=True),
    Output('partner-sex-types', 'value', allow_duplicate=True), Output('partner-diagnosis', 'value', allow_duplicate=True),
    Input('edit-partner-select', 'value'), State('partners-data-store', 'data'),
    prevent_initial_call=True
)
def load_partner_for_edit(selected_partner_id, partners_list):
    if not selected_partner_id or not partners_list: raise dash.exceptions.PreventUpdate
    partner_to_load = next((p for p in partners_list if p.get('id') == selected_partner_id), None)
    if not partner_to_load: return (DEFAULT_PARTNER_DATA.copy(), None, None, None, "Error: Partner not found", None, None, None, None, None, [], None)
    if not isinstance(partner_to_load, dict): return (DEFAULT_PARTNER_DATA.copy(), None, None, None, "Error: Invalid partner data found", None, None, None, None, None, [], None)
    labs_display = [html.Li(f"{l.get('date','?')}: {l.get('type','?')} - {l.get('result','?')}") for l in safe_get_list(partner_to_load, 'labs')]
    symptoms_display = [html.Li(f"{s.get('onset','?')}: {s.get('type','?')} (Duration: {s.get('duration','N/A')} days)") for s in safe_get_list(partner_to_load, 'symptoms')]
    treatments_display = [html.Li(f"{t.get('date','?')}: {t.get('details','?')}") for t in safe_get_list(partner_to_load, 'treatments')]
    id_display = f"Editing: {partner_to_load.get('name', selected_partner_id)}"
    return (partner_to_load.copy(), labs_display, symptoms_display, treatments_display, id_display,
            partner_to_load.get('name'), partner_to_load.get('first_exposure'), partner_to_load.get('last_exposure'),
            partner_to_load.get('frequency_value'), partner_to_load.get('frequency_unit'),
            partner_to_load.get('sex_types', []), partner_to_load.get('diagnosis'))


# --- Plotting & Visibility Callbacks ---
@callback(
    Output('duration-visibility-store', 'data'),
    Output('toggle-duration-btn', 'children'),
    Input('toggle-duration-btn', 'n_clicks'),
    State('duration-visibility-store', 'data'),
    prevent_initial_call=True
)
def toggle_duration_visibility(n_clicks, current_visibility):
    new_visibility = not current_visibility
    button_text = "Show Symptom Durations" if not new_visibility else "Hide Symptom Durations"
    return new_visibility, button_text

# **CORRECTED** Callback to Update VCA Plot
@callback(
    Output('vca-graph', 'figure'),
    Input('patient-data-store', 'data'),
    Input('partners-data-store', 'data'),
    Input('duration-visibility-store', 'data') # Trigger redraw when visibility changes
)
def update_vca_plot_main(patient_data, partners_list, show_durations):
    # --- VCA Plot Generation Logic ---
    fig = go.Figure()
    if not isinstance(patient_data, dict): patient_data = DEFAULT_PATIENT_DATA.copy()
    if not isinstance(partners_list, list): partners_list = []
    all_people_data = [patient_data] + partners_list

    all_dates = set() # Use set for efficient unique date collection
    person_names_map = {} # Map ID to display name

    # Collect names and dates
    for person in all_people_data:
        if not isinstance(person, dict): continue
        p_id = person.get('id', f'unknown_{uuid.uuid4()}') # Assign temp id if missing
        name = person.get('name') or p_id
        if p_id == 'patient': name = f"{name} (Patient)"
        person_names_map[p_id] = name

        for key in ['labs', 'symptoms', 'treatments', 'ghosted_lesions']:
            for item in safe_get_list(person, key):
                 if not isinstance(item, dict): continue
                 dt_onset = parse_date(item.get('date') or item.get('onset'))
                 dt_end = parse_date(item.get('end')) # For ghosted lesions
                 if dt_onset: all_dates.add(dt_onset)
                 if dt_end: all_dates.add(dt_end)
                 # Add symptom end dates
                 if key == 'symptoms':
                     duration = item.get('duration')
                     if dt_onset and isinstance(duration, int) and duration > 0:
                          all_dates.add(dt_onset + timedelta(days=duration))

        # Exposure dates
        if p_id != 'patient':
             first_exp = parse_date(person.get('first_exposure'))
             last_exp = parse_date(person.get('last_exposure'))
             if first_exp: all_dates.add(first_exp)
             if last_exp: all_dates.add(last_exp)
        else: # Patient elicited exposure
             elicited_start = parse_date(person.get('elicited_exposure_start'))
             elicited_end = parse_date(person.get('elicited_exposure_end'))
             if elicited_start: all_dates.add(elicited_start)
             if elicited_end: all_dates.add(elicited_end)

    # Add treatment dates to range calculation if they exist
    for person in all_people_data:
         if isinstance(person, dict):
             treatments = safe_get_list(person,'treatments')
             for t in treatments:
                 if isinstance(t, dict):
                    dt = parse_date(t.get('date'))
                    if dt: all_dates.add(dt)

    # Determine plot range
    if not all_dates:
        min_date_dt = date.today() - timedelta(days=180)
        max_date_dt = date.today() + timedelta(days=30)
    else:
        min_date_dt = min(all_dates) - timedelta(days=30)
        max_date_dt = max(all_dates) + timedelta(days=30)

    # Plotting elements
    colors = {'lab': 'blue', 'symptom': 'red', 'treatment': 'black',
              'exposure_partner': '#9370DB', 'exposure_patient': '#FF8C00',
              'interview': '#006400', 'inoculation': '#006400', 'ghosted': '#FFA500'}
    symbols = {'lab': 'circle', 'symptom': 'triangle-up', 'treatment': 'star', 'inoculation':'diamond', 'ghosted':'diamond-open'}
    line_styles = {'symptom':'solid', 'exposure_partner':'dash', 'exposure_patient':'dot', 'interview':'solid', 'ghosted':'dashdot'}
    line_widths = {'symptom': 5, 'exposure_partner': 5, 'exposure_patient': 5, 'interview': 2, 'ghosted': 4}

    plotted_legend_items = set()
    y_axis_order = list(reversed([person_names_map[p['id']] for p in all_people_data if isinstance(p,dict) and 'id' in p]))

    # Draw Interview Period and Inoculation Points (Patient Only)
    patient_display_name = person_names_map.get('patient')
    if patient_display_name and isinstance(patient_data, dict):
        patient_symptoms = safe_get_list(patient_data, 'symptoms'); patient_treatments = safe_get_list(patient_data, 'treatments')
        earliest_inoc = calculate_earliest_inoculation(patient_symptoms)
        earliest_treat = min((parse_date(t.get('date')) for t in patient_treatments if isinstance(t,dict) and parse_date(t.get('date'))), default=None)
        interview_end = earliest_treat if earliest_treat else max_date_dt
        if earliest_inoc and earliest_inoc <= interview_end:
            show_legend = 'interview' not in plotted_legend_items
            fig.add_trace(go.Scatter(
                x=[earliest_inoc, interview_end], y=[patient_display_name]*2, mode='lines',
                line=dict(color=colors['interview'], width=line_widths['interview'], dash=line_styles['interview']),
                name='Interview Period', legendgroup='interview', showlegend=show_legend,
                hoverinfo='text', hovertext=f"<b>{patient_display_name}</b><br>Interview Period<br>Start (Earliest Inoc.): {earliest_inoc:%Y-%m-%d}<br>End: {interview_end:%Y-%m-%d}"
            ))
            if show_legend: plotted_legend_items.add('interview')
            inoc_min, inoc_avg, inoc_max = calculate_inoculation_points(patient_symptoms)
            inoc_dates = []; inoc_labels = []
            if inoc_min and inoc_min >= earliest_inoc: inoc_dates.append(inoc_min); inoc_labels.append("Min Inoc.")
            if inoc_avg and inoc_avg >= earliest_inoc: inoc_dates.append(inoc_avg); inoc_labels.append("Avg Inoc.")
            if inoc_max and inoc_max >= earliest_inoc: inoc_dates.append(inoc_max); inoc_labels.append("Max Inoc.")
            if inoc_dates:
                 show_legend = 'inoculation' not in plotted_legend_items
                 fig.add_trace(go.Scatter(
                     x=inoc_dates, y=[patient_display_name]*len(inoc_dates), mode='markers',
                     marker=dict(color=colors['inoculation'], symbol=symbols['inoculation'], size=12),
                     name='Inoc. Points (Primary)', legendgroup='interview', showlegend=show_legend,
                     hoverinfo='text', hovertext=[f"<b>{patient_display_name}</b><br>{lbl}<br>{dt:%Y-%m-%d}" for lbl, dt in zip(inoc_labels, inoc_dates)]
                 ))
                 if show_legend: plotted_legend_items.add('inoculation')

    # Draw Data for Each Person
    for person_data in all_people_data:
        if not isinstance(person_data, dict): continue
        person_id = person_data.get('id', 'unknown'); y_val = person_names_map.get(person_id, 'Unknown Y')

        # Plot Labs and Treatments
        for event_type in ['lab', 'treatment']:
            # *** CORRECTED ASSIGNMENT ORDER ***
            event_key = 'labs' if event_type == 'lab' else 'treatments'
            items = safe_get_list(person_data, event_key)
            # *** END CORRECTION ***
            date_key = 'date'
            details_key_func = (lambda item: f"{item.get('type','?')} - {item.get('result','?')}") if event_type=='lab' else (lambda item: item.get('details','?'))
            dates = [parse_date(item.get(date_key)) for item in items if isinstance(item,dict)]
            valid_dates = [d for d in dates if d]
            valid_details = [details_key_func(item) for item, dt in zip(items, dates) if dt and isinstance(item,dict)]
            if valid_dates:
                 show_legend = event_type not in plotted_legend_items
                 fig.add_trace(go.Scatter(
                     x=valid_dates, y=[y_val] * len(valid_dates), mode='markers',
                     marker=dict(color=colors[event_type], symbol=symbols[event_type], size=10),
                     name=event_type.capitalize(), legendgroup=event_type, showlegend=show_legend,
                     hoverinfo='text', hovertext=[f"<b>{y_val}</b><br>{event_type.capitalize()}: {dt:%Y-%m-%d}<br>{detail}" for dt, detail in zip(valid_dates, valid_details)]
                 ))
                 if show_legend: plotted_legend_items.add(event_type)

        # Plot Symptoms
        symptoms_items = safe_get_list(person_data, 'symptoms'); symptom_onsets = []; symptom_details_onset = []
        plotted_duration_legend = 'symptom_duration' in plotted_legend_items
        for item in symptoms_items:
            if not isinstance(item, dict): continue
            onset_date = parse_date(item.get('onset')); duration = item.get('duration'); symptom_type = item.get('type', '?')
            if onset_date:
                symptom_onsets.append(onset_date); symptom_details_onset.append(f"{symptom_type} (Onset)")
                if show_durations and isinstance(duration, int) and duration > 0:
                    end_date = onset_date + timedelta(days=duration)
                    show_legend_dur = not plotted_duration_legend
                    fig.add_trace(go.Scatter(
                        x=[onset_date, end_date], y=[y_val, y_val], mode='lines',
                        line=dict(color=colors['symptom'], width=line_widths['symptom'], dash=line_styles['symptom']),
                        name='Symptom Duration', legendgroup='symptom', showlegend=show_legend_dur, hoverinfo='text',
                        hovertext=f"<b>{y_val}</b><br>{symptom_type}<br>Onset: {onset_date:%Y-%m-%d}<br>End: {end_date:%Y-%m-%d}<br>Dur: {duration}d"
                    ))
                    if show_legend_dur: plotted_legend_items.add('symptom_duration'); plotted_duration_legend=True
        if symptom_onsets:
             show_legend_symp = 'symptom_onset' not in plotted_legend_items
             fig.add_trace(go.Scatter(
                 x=symptom_onsets, y=[y_val] * len(symptom_onsets), mode='markers',
                 marker=dict(color=colors['symptom'], symbol=symbols['symptom'], size=10),
                 name='Symptom Onset', legendgroup='symptom', showlegend=show_legend_symp, hoverinfo='text',
                 hovertext=[f"<b>{y_val}</b><br>{detail}: {dt:%Y-%m-%d}" for dt, detail in zip(symptom_onsets, symptom_details_onset)]
             ))
             if show_legend_symp: plotted_legend_items.add('symptom_onset')

        # Plot Exposure Periods
        if person_id == 'patient':
            first_exp = parse_date(person_data.get('elicited_exposure_start')); last_exp = parse_date(person_data.get('elicited_exposure_end'))
            exp_type = 'exposure_patient'; exp_label = "Patient Elicited Exposure"
        else:
            first_exp = parse_date(person_data.get('first_exposure')); last_exp = parse_date(person_data.get('last_exposure'))
            exp_type = 'exposure_partner'; exp_label = "Partner Reported Exposure"
        if first_exp and last_exp and first_exp <= last_exp:
             show_legend = exp_type not in plotted_legend_items
             hover_detail = f"{exp_label}: {first_exp:%Y-%m-%d} to {last_exp:%Y-%m-%d}"
             if person_id != 'patient':
                 freq_val = person_data.get('frequency_value'); freq_unit = person_data.get('frequency_unit'); sex_types = person_data.get('sex_types', [])
                 if freq_val and freq_unit: hover_detail += f"<br>Freq: {freq_val}/{freq_unit}"
                 if sex_types: hover_detail += f"<br>Types: {', '.join(sex_types)}"
             fig.add_trace(go.Scatter(
                x=[first_exp, last_exp], y=[y_val, y_val], mode='lines',
                line=dict(color=colors[exp_type], width=line_widths[exp_type], dash=line_styles[exp_type]),
                name=exp_label, legendgroup=exp_type, showlegend=show_legend, hoverinfo='text',
                hovertext=f"<b>{y_val}</b><br>{hover_detail}"
             ))
             if show_legend: plotted_legend_items.add(exp_type)

        # Plot Ghosted Lesions
        ghosted_lesions = safe_get_list(person_data, 'ghosted_lesions')
        for lesion in ghosted_lesions:
             if not isinstance(lesion, dict): continue
             onset = parse_date(lesion.get('onset')); end = parse_date(lesion.get('end'))
             lesion_type_raw = lesion.get('type', 'ghosted'); partner_id_ref = lesion.get('analysis_partner_id')
             partner_name_ref = person_names_map.get(partner_id_ref, partner_id_ref)
             lesion_label = f"Ghosted {'Source' if 'source' in lesion_type_raw else 'Spread'} Lesion"
             if partner_name_ref: lesion_label += f" (re: {partner_name_ref})"
             if onset and end and onset <= end:
                 show_legend = 'ghosted' not in plotted_legend_items
                 fig.add_trace(go.Scatter(
                     x=[onset, end], y=[y_val, y_val], mode='lines',
                     line=dict(color=colors['ghosted'], width=line_widths['ghosted'], dash=line_styles['ghosted']),
                     name='Ghosted Lesion', legendgroup='ghosted', showlegend=show_legend,
                     hoverinfo='text', hovertext=f"<b>{y_val}</b><br>{lesion_label}<br>Onset: {onset:%Y-%m-%d}<br>End: {end:%Y-%m-%d}"
                 ))
                 fig.add_trace(go.Scatter(x=[onset, end], y=[y_val, y_val], mode='markers', marker=dict(color=colors['ghosted'], symbol=symbols['ghosted'], size=8), showlegend=False, hoverinfo='skip'))
                 if show_legend: plotted_legend_items.add('ghosted')

    # --- Final Layout ---
    fig.update_layout(
        title='VCA Timeline', xaxis_title='Date', yaxis_title='Person',
        xaxis=dict(range=[min_date_dt, max_date_dt], type='date'),
        yaxis=dict(categoryorder='array', categoryarray=y_axis_order),
        hovermode='closest', legend_title_text='Events',
        legend=dict(tracegroupgap=10, y=1.02, x=1, bgcolor='rgba(255,255,255,0.6)', orientation="h"), # Legend above plot
        margin=dict(l=200, r=30, t=80, b=50) # Increase top margin for legend
    )
    for name_y in y_axis_order:
         fig.add_shape(type="line", x0=min_date_dt, y0=name_y, x1=max_date_dt, y1=name_y,
                       line=dict(color="LightGrey", width=1, dash="dot"))

    return fig


# --- Ghosting and Clear Callbacks ---
@callback(
    Output('ghosting-result-output', 'children'),
    Output('patient-data-store', 'data', allow_duplicate=True),
    Output('partners-data-store', 'data', allow_duplicate=True),
    Input('run-ghosting-btn', 'n_clicks'), State('ghosting-partner-select', 'value'),
    State('patient-data-store', 'data'), State('partners-data-store', 'data'),
    prevent_initial_call=True
)
def perform_ghosting_analysis(n_clicks, selected_partner_id, patient_data, partners_list):
    if not selected_partner_id: return "Please select a partner to analyze.", dash.no_update, dash.no_update
    if not isinstance(patient_data, dict): return "Error: Patient data invalid.", dash.no_update, dash.no_update
    if not isinstance(partners_list, list): return "Error: Partner list data invalid.", dash.no_update, dash.no_update
    partner_data = next((p for p in partners_list if isinstance(p, dict) and p.get('id') == selected_partner_id), None)
    if not partner_data: return f"Error: Selected partner (ID: {selected_partner_id}) not found.", dash.no_update, dash.no_update

    p1_data, p2_data, p1_id, p2_id = None, None, None, None; result_log = ["Ghosting Analysis Log:"]
    p1_name = patient_data.get('name') or patient_data.get('id', 'Patient'); p2_name_partner = partner_data.get('name') or partner_data.get('id', 'Partner')
    result_log.append(f"Comparing Patient ({p1_name}) and Partner ({p2_name_partner})")
    patient_symptoms_raw = safe_get_list(patient_data, 'symptoms'); partner_symptoms_raw = safe_get_list(partner_data, 'symptoms')
    patient_symptoms = sorted([s for s in patient_symptoms_raw if isinstance(s,dict)], key=lambda s: get_symptom_rank(s.get('type')))
    partner_symptoms = sorted([s for s in partner_symptoms_raw if isinstance(s,dict)], key=lambda s: get_symptom_rank(s.get('type')))
    p1_symptom = None
    if not patient_symptoms and not partner_symptoms: return "Cannot perform ghosting: Neither has symptoms.", dash.no_update, dash.no_update
    patient_rank = get_symptom_rank(patient_symptoms[0].get('type')) if patient_symptoms else 999
    partner_rank = get_symptom_rank(partner_symptoms[0].get('type')) if partner_symptoms else 999
    if patient_rank <= partner_rank:
        p1_data, p2_data, p1_id, p2_id = patient_data, partner_data, 'patient', selected_partner_id; p1_symptom = patient_symptoms[0]
        result_log.append(f"Step 1: P1 is Patient ({p1_name}) (Symptom: {p1_symptom.get('type', 'N/A')}), P2 is Partner ({p2_name_partner}).")
    else:
        p1_data, p2_data, p1_id, p2_id = partner_data, patient_data, selected_partner_id, 'patient'; p1_symptom = partner_symptoms[0]
        result_log.append(f"Step 1: P1 is Partner ({p2_name_partner}) (Symptom: {p1_symptom.get('type', 'N/A')}), P2 is Patient ({p1_name}).")
    p1_symptom_type = p1_symptom.get('type'); p1_symptom_onset = parse_date(p1_symptom.get('onset'))
    if not p1_symptom_onset: return f"Error: P1's primary symptom has invalid onset date.", dash.no_update, dash.no_update
    d1 = get_avg_inoculation_date(p1_symptom_onset, p1_symptom_type)
    if not d1: return f"Error: Could not calculate P1's avg inoculation date (D1).", dash.no_update, dash.no_update
    result_log.append(f"Step 2: P1's Est. Avg. Inoculation Date (D1) = {d1:%Y-%m-%d}")
    avg_incubation = timedelta(days=SYPHILIS_DURATIONS['incubation']['avg']); avg_primary_duration = timedelta(days=SYPHILIS_DURATIONS['primary']['avg'])
    ghosted_source_onset = d1 + avg_incubation; ghosted_source_end = ghosted_source_onset + avg_primary_duration
    result_log.append(f"Step 3: Est. Ghosted Source Lesion for P2: {ghosted_source_onset:%Y-%m-%d} to {ghosted_source_end:%Y-%m-%d}")
    d2 = None
    if p1_symptom_type == 'Primary Chancre': d2 = get_chancre_midpoint_date(p1_symptom_onset, p1_symptom.get('duration'), p1_symptom_type); result_log.append(f"Step 4a: P1 Primary Chancre. Midpoint (D2) = {d2:%Y-%m-%d if d2 else 'N/A'}")
    elif p1_symptom_type == 'Secondary Rash/Lesions': avg_latency = timedelta(days=SYPHILIS_DURATIONS['latency']['avg']); midpoint_offset_days = avg_primary_duration.days / 2.0; d2_offset = avg_latency + timedelta(days=midpoint_offset_days); d2 = p1_symptom_onset - d2_offset; result_log.append(f"Step 4b: P1 Secondary Symptom. Est. Midpoint (D2) of preceding primary = {d2:%Y-%m-%d if d2 else 'N/A'}")
    if not d2: return f"Error: Could not calculate P1's midpoint date (D2).", dash.no_update, dash.no_update
    midpoint_offset_days = avg_primary_duration.days / 2.0; ghosted_spread_onset = d2 - timedelta(days=midpoint_offset_days); ghosted_spread_end = ghosted_spread_onset + avg_primary_duration
    result_log.append(f"Step 4c: Est. Ghosted Spread Lesion for P2: {ghosted_spread_onset:%Y-%m-%d} to {ghosted_spread_end:%Y-%m-%d}")
    result_log.append("\nStep 5: Evaluating Scenarios...")
    exposure_start, exposure_end = None, None; partner_in_pair_data = None
    if p1_data['id'] == 'patient': partner_in_pair_data = p2_data
    else: partner_in_pair_data = p1_data
    if isinstance(partner_in_pair_data, dict): exposure_start = parse_date(partner_in_pair_data.get('first_exposure')); exposure_end = parse_date(partner_in_pair_data.get('last_exposure'))
    else: result_log.append("WARN: Cannot evaluate exposure - partner data invalid.")
    def check_criteria(lesion_type, lesion_onset, lesion_end, person_data, other_person_data):
        checks = []; passed_count = 0; total_checks = 0
        person_name = person_data.get('name', person_data.get('id', 'Unknown')); lesion_label = f"{lesion_type} Lesion ({person_name})"
        if not isinstance(person_data, dict): return False, ["Error: Invalid person data for criteria check."]
        total_checks += 1 # Exposure Check
        if exposure_start and exposure_end:
            if exposure_start <= lesion_onset <= exposure_end: checks.append(f"  [PASS] Exposure: {lesion_label} onset ({lesion_onset:%Y-%m-%d}) within period ({exposure_start:%Y-%m-%d} to {exposure_end:%Y-%m-%d})."); passed_count += 1
            else: checks.append(f"  [FAIL] Exposure: {lesion_label} onset outside exposure period.")
        else: checks.append(f"  [WARN] Exposure: Cannot check overlap - missing exposure dates.")
        reported_sex_types = partner_in_pair_data.get('sex_types', []) if isinstance(partner_in_pair_data, dict) else []
        if reported_sex_types: checks.append(f"  [INFO] Sex Types: Partner reported {', '.join(reported_sex_types)}. (Manual check needed).")
        else: checks.append(f"  [WARN] Sex Types: Cannot check correspondence - missing partner sex type data.")
        secondary_symptoms_raw = safe_get_list(person_data, 'symptoms'); secondary_symptoms = [s for s in secondary_symptoms_raw if isinstance(s,dict) and s.get('type') == 'Secondary Rash/Lesions']
        if secondary_symptoms: # Latency Check
            total_checks += 1
            earliest_secondary_onset = min((parse_date(s['onset']) for s in secondary_symptoms if parse_date(s['onset'])), default=None)
            if earliest_secondary_onset:
                time_diff = earliest_secondary_onset - lesion_end; min_latency_needed = timedelta(days=SYPHILIS_DURATIONS['latency']['min'])
                if time_diff >= min_latency_needed: checks.append(f"  [PASS] Latency: Sufficient time ({format_timedelta(time_diff)}) between {lesion_label} end and secondary onset ({earliest_secondary_onset:%Y-%m-%d})."); passed_count += 1
                else: checks.append(f"  [FAIL] Latency: Time ({format_timedelta(time_diff)}) between {lesion_label} end and secondary onset is less than minimum ({format_timedelta(min_latency_needed)}).")
            else: checks.append(f"  [WARN] Latency: Cannot check - Secondary symptom onset date invalid.")
        person_treatments_raw = safe_get_list(person_data, 'treatments'); person_treatments = [t for t in person_treatments_raw if isinstance(t,dict)]
        earliest_treatment_date = min((parse_date(t['date']) for t in person_treatments if parse_date(t['date'])), default=None)
        natural_order_passed = True; secondary_check_applicable = False; treatment_check_applicable = False
        if secondary_symptoms: # Order vs Secondary Check
             earliest_secondary_onset = min((parse_date(s['onset']) for s in secondary_symptoms if parse_date(s['onset'])), default=None)
             if earliest_secondary_onset: secondary_check_applicable = True; total_checks += 1
             if earliest_secondary_onset and lesion_onset >= earliest_secondary_onset: checks.append(f"  [FAIL] Order (vs Secondary): {lesion_label} onset ({lesion_onset:%Y-%m-%d}) on/after secondary onset ({earliest_secondary_onset:%Y-%m-%d})."); natural_order_passed = False
        if earliest_treatment_date: # Order vs Treatment Check
            treatment_check_applicable = True; total_checks += 1
            if lesion_onset >= earliest_treatment_date: checks.append(f"  [FAIL] Order (vs Treatment): {lesion_label} onset ({lesion_onset:%Y-%m-%d}) on/after treatment ({earliest_treatment_date:%Y-%m-%d})."); natural_order_passed = False
        if natural_order_passed and (secondary_check_applicable or treatment_check_applicable):
            checks.append(f"  [PASS] Order: {lesion_label} occurs before relevant secondary/treatment.");
            if secondary_check_applicable: passed_count +=1
            if treatment_check_applicable: passed_count +=1
        elif not secondary_check_applicable and not treatment_check_applicable: checks.append(f"  [N/A] Order: No relevant secondary/treatment found.")
        scenario_passes = (passed_count == total_checks) and total_checks > 0
        return scenario_passes, checks

    source_scenario_passed, source_checks = check_criteria("Ghosted Source", ghosted_source_onset, ghosted_source_end, p2_data, p1_data)
    result_log.append(f"\n--- Scenario: P1 ({p1_data.get('name')}) as Source ---"); result_log.extend(source_checks); result_log.append(f"Source Scenario Passed Checks: {source_scenario_passed}")
    spread_scenario_passed, spread_checks = check_criteria("Ghosted Spread", ghosted_spread_onset, ghosted_spread_end, p2_data, p1_data)
    result_log.append(f"\n--- Scenario: P2 ({p2_data.get('name')}) as Source ---"); result_log.extend(spread_checks); result_log.append(f"Spread Scenario Passed Checks: {spread_scenario_passed}")
    final_conclusion = "Result: Unrelated Infections (Neither scenario passed checks)."; p1_display_name = p1_data.get('name') or p1_data.get('id'); p2_display_name = p2_data.get('name') or p2_data.get('id')
    if source_scenario_passed and not spread_scenario_passed: final_conclusion = f"Result: {p1_display_name} is likely the SOURCE for {p2_display_name}."
    elif spread_scenario_passed and not source_scenario_passed: final_conclusion = f"Result: {p2_display_name} is likely the SOURCE for {p1_display_name}.\n(i.e., {p1_display_name} is likely a SPREAD from {p2_display_name})."
    elif source_scenario_passed and spread_scenario_passed: final_conclusion = "Result: Ambiguous - Both Source and Spread scenarios fit criteria."
    result_log.append(f"\n--- Conclusion ---"); result_log.append(final_conclusion)

    # --- Add Ghosted Lesions to Stores ---
    patient_patch = Patch(); partner_list_patch = Patch() # Use Patch for partner list modification
    updated_partners_list = partners_list[:] # Copy list

    ghosted_source_lesion_data = {'type': 'ghosted_source', 'onset': ghosted_source_onset.strftime('%Y-%m-%d'), 'end': ghosted_source_end.strftime('%Y-%m-%d'), 'analysis_partner_id': p1_id}
    ghosted_spread_lesion_data = {'type': 'ghosted_spread', 'onset': ghosted_spread_onset.strftime('%Y-%m-%d'), 'end': ghosted_spread_end.strftime('%Y-%m-%d'), 'analysis_partner_id': p1_id}
    lesions_to_add = [ghosted_source_lesion_data, ghosted_spread_lesion_data]

    if p2_id == 'patient':
         current_ghosted = safe_get_list(p2_data, 'ghosted_lesions')
         patient_patch['ghosted_lesions'] = current_ghosted + lesions_to_add
         partner_list_output = dash.no_update # No change to partner list structure
    else: # p2 is the partner
         found_partner_index = -1
         for i, p in enumerate(updated_partners_list):
             if isinstance(p, dict) and p.get('id') == p2_id: found_partner_index = i; break
         if found_partner_index != -1:
             partner_to_update = updated_partners_list[found_partner_index]
             if not isinstance(partner_to_update, dict): partner_to_update = DEFAULT_PARTNER_DATA.copy() # Safety
             current_ghosted = safe_get_list(partner_to_update, 'ghosted_lesions')
             # Update the specific partner in the copied list
             partner_to_update['ghosted_lesions'] = current_ghosted + lesions_to_add
             updated_partners_list[found_partner_index] = partner_to_update # Put updated dict back
             patient_data_output = dash.no_update
             partner_list_output = updated_partners_list # Return the modified list
         else:
              result_log.append("\nERROR: Could not find partner in list to add ghosted lesions.")
              patient_data_output = dash.no_update; partner_list_output = dash.no_update

    return "\n".join(result_log), patient_patch, partner_list_output

@callback(
    Output('patient-data-store', 'data', allow_duplicate=True), Output('partners-data-store', 'data', allow_duplicate=True),
    Output('current-partner-form-store', 'data', allow_duplicate=True), Output('patient-name', 'value', allow_duplicate=True),
    Output('patient-reason', 'value', allow_duplicate=True), Output('patient-diagnosis', 'value', allow_duplicate=True),
    Output('patient-elicited-exposure-start', 'date', allow_duplicate=True), Output('patient-elicited-exposure-end', 'date', allow_duplicate=True),
    Output('patient-labs-list', 'children', allow_duplicate=True), Output('patient-symptoms-list', 'children', allow_duplicate=True),
    Output('patient-treatments-list', 'children', allow_duplicate=True), Output('saved-partners-list-display', 'children', allow_duplicate=True),
    Output('edit-partner-select', 'options', allow_duplicate=True), Output('edit-partner-select', 'value', allow_duplicate=True),
    Output('ghosting-partner-select', 'options', allow_duplicate=True), Output('ghosting-partner-select', 'value', allow_duplicate=True),
    Output('ghosting-result-output', 'children', allow_duplicate=True), Output('vca-graph', 'figure', allow_duplicate=True),
    Output('partner-labs-list', 'children', allow_duplicate=True), Output('partner-symptoms-list', 'children', allow_duplicate=True),
    Output('partner-treatments-list', 'children', allow_duplicate=True), Output('current-partner-id-display', 'children', allow_duplicate=True),
    Output('partner-name', 'value', allow_duplicate=True), Output('partner-first-exposure', 'date', allow_duplicate=True),
    Output('partner-last-exposure', 'date', allow_duplicate=True), Output('partner-freq-value', 'value', allow_duplicate=True),
    Output('partner-freq-unit', 'value', allow_duplicate=True), Output('partner-sex-types', 'value', allow_duplicate=True),
    Output('partner-diagnosis', 'value', allow_duplicate=True), Input('clear-all-data-btn', 'n_clicks'),
    prevent_initial_call=True
)
def clear_all_data(n_clicks):
    empty_figure = go.Figure(); empty_figure.update_layout(title='VCA Timeline - Data Cleared', xaxis={'visible':False}, yaxis={'visible':False})
    return (DEFAULT_PATIENT_DATA.copy(), [], DEFAULT_PARTNER_DATA.copy(), None, None, None, None, None, None, None, None, None, [], None, [], None, None, empty_figure, None, None, None, "", None, None, None, None, None, [], None)


# --- Run the App ---
if __name__ == '__main__':
    app.index_string = '''
    <!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
    <style>
        .section-box { border: 1px solid #ccc; padding: 15px; margin-bottom: 15px; border-radius: 5px; background-color: #f9f9f9; }
        .form-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
        .form-row label { font-weight: bold; min-width: 120px; margin-right: 5px;}
        .form-row-flex { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
        .form-row .dash-dropdown { flex-grow: 1; } .form-row-flex .dash-dropdown { flex-grow: 1; }
        .dash-input { padding: 6px; }
    </style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>
    '''
    app.run(debug=True)
