import dash
from dash import dcc, html, Input, Output, State, ctx # ctx helps identify trigger
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

# --- Sample Data (Same as before) ---
# In a real Dash app, you might manage state differently (e.g., dcc.Store)
# but for this example, a global variable is simpler to start.
vca_data = [
     {
        "name": "Johnny Smith (OP)",
        "type": "patient",
        "events": [
            {"type": "test", "date": "2019-10-02", "details": "NR RPR"},
            {"type": "exposure", "start_date": "2019-09-03", "end_date": "2020-02-25", "details": "Exposure Period Elicited"},
            {"type": "symptom", "date": "2020-03-05", "details": "Penile Chancre Onset (x3 days by 3/8)"},
            {"type": "test", "date": "2020-03-08", "details": "RPR 1:32, +EIA"},
            {"type": "treatment", "date": "2020-03-10", "details": "Bicillin 2.4mu x1"},
        ]
    },
    { "name": "Heather P1", "type": "partner", "events": [
            {"type": "test", "date": "2020-04-03", "details": "RPR 1:32, +EIA, Vaginal Chancre Present"},
            {"type": "treatment", "date": "2020-04-03", "details": "Preventive Treatment"}, ]},
    { "name": "Samuel P1", "type": "partner", "events": [
            {"type": "symptom", "date": "2020-02-08", "details": "Rectal Chancre Onset (x7 days by 2/15)"},
            {"type": "test", "date": "2020-02-15", "details": "RPR 1:64, +EIA"},
            {"type": "treatment", "date": "2020-02-17", "details": "Bicillin 2.4mu x1"}, ]},
    { "name": "Fran Sisco", "type": "patient", "events": [
            {"type": "test", "date": "2014-10-06", "details": "Volunteer Exam Initiated"},
            {"type": "exposure", "start_date": "2014-10-01", "end_date": "2015-01-14", "details": "Exposure Period Placeholder"},
            {"type": "symptom", "date": "2015-01-04", "details": "Vaginal Symptom (Lesion?)"},
            {"type": "test", "date": "2015-01-14", "details": "RPR 1:2, TPPA+"},
            {"type": "treatment", "date": "2015-01-14", "details": "Rx Bic 2.4"}, ]},
    { "name": "Carson Zittie", "type": "partner", "events": [
            {"type": "test", "date": "2014-08-03", "details": "City Clinic, RPR NP"},
            {"type": "symptom", "date": "2014-12-15", "details": "Lesion"},
            {"type": "test", "date": "2015-01-17", "details": "RPR 1:16, TPPA+"},
            {"type": "treatment", "date": "2015-01-17", "details": "Rx Bic 2.4"}, ]},
    { "name": "Virginia Zittie", "type": "partner", "events": [
            {"type": "symptom", "date": "2014-11-01", "details": "Oral IX"},
            {"type": "symptom", "date": "2014-12-25", "details": "PP Rash"},
            {"type": "test", "date": "2015-01-20", "details": "RPR 1:32, TPPA+"},
            {"type": "treatment", "date": "2015-01-20", "details": "Rx Bic 2.4"}, ]}
]

# --- Helper function to parse dates ---
def parse_date(date_str):
    """Safely parse date strings from various formats, returning datetime object or None."""
    if not date_str:
        return None
    try:
        # Handle both datetime objects and string representations
        if isinstance(date_str, (datetime, date)):
            # If it's already a date/datetime object, ensure it's datetime for consistency if needed,
            # but for strftime, date object is fine. Return as is.
            return date_str
        # Handle YYYY-MM-DD and ISO formats from date pickers by splitting at 'T' if present
        return datetime.strptime(str(date_str).split('T')[0], '%Y-%m-%d')
    except (ValueError, TypeError):
        print(f"Warning: Could not parse date: {date_str}")
        return None

# --- Plotting Function (Modified slightly for Dash - returns figure object) ---
def create_vca_plot(data):
    """Generates an interactive Plotly VCA chart figure."""
    fig = go.Figure()

    all_dates = []
    # Ensure unique names and preserve order somewhat based on original list (OP often first)
    person_names = list(dict.fromkeys([p['name'] for p in data]))


    # Collect all valid dates to determine range
    for person in data:
        for event in person['events']:
            if event['type'] == 'exposure':
                start = parse_date(event.get('start_date'))
                end = parse_date(event.get('end_date'))
                if start: all_dates.append(start)
                if end: all_dates.append(end)
            else:
                dt = parse_date(event.get('date'))
                if dt: all_dates.append(dt)

    if not all_dates: # Handle case with no valid dates
        min_date_dt = datetime.now() - timedelta(days=365)
        max_date_dt = datetime.now()
    else:
        min_date_dt = min(all_dates) - timedelta(days=30) # Add padding
        max_date_dt = max(all_dates) + timedelta(days=30) # Add padding

    # Define colors and symbols
    colors = {'exposure': 'blue', 'symptom': 'red', 'test': 'black', 'treatment': 'green'}
    symbols = {'exposure': 'line-ns', 'symptom': 'triangle-up', 'test': 'circle', 'treatment': 'star'}
    sizes = {'exposure': 8, 'symptom': 12, 'test': 10, 'treatment': 12}

    # Plot data for each person (reverse order to get OP/index case potentially higher on y-axis)
    plotted_legend_items = set() # To show legend only once per type

    # Create a mapping for consistent y-axis placement even if list order changes
    person_y_mapping = {name: i for i, name in enumerate(reversed(person_names))}


    for person_data in data: # Iterate through original data to process
        person_name = person_data['name']
        y_val = person_name # Use name directly for y-axis category

        event_dates = {'exposure': [], 'symptom': [], 'test': [], 'treatment': []}
        event_details = {'exposure': [], 'symptom': [], 'test': [], 'treatment': []}
        event_exposures = []

        for event in person_data['events']:
            event_type = event['type']

            if event_type == 'exposure':
                start = parse_date(event.get('start_date'))
                end = parse_date(event.get('end_date'))
                if start and end:
                     event_exposures.append({'start': start, 'end': end, 'details': event.get('details', 'Exposure')})
            else:
                dt = parse_date(event.get('date'))
                if dt and event_type in event_dates:
                    event_dates[event_type].append(dt)
                    event_details[event_type].append(event.get('details', event_type.capitalize()))

        # Plot Exposure Periods as Lines
        for exp in event_exposures:
            show_legend_exp = 'exposure' not in plotted_legend_items
            fig.add_trace(go.Scatter(
                x=[exp['start'], exp['end']], y=[y_val, y_val], mode='lines',
                line=dict(color=colors['exposure'], width=6), name='Exposure Period',
                legendgroup='exposure', showlegend=show_legend_exp, hoverinfo='text',
                hovertext=f"<b>{person_name}</b><br>Exposure: {exp['start']:%Y-%m-%d} to {exp['end']:%Y-%m-%d}<br>{exp['details']}"
            ))
            # Add caps
            fig.add_trace(go.Scatter(
                 x=[exp['start'], exp['end']], y=[y_val, y_val], mode='markers',
                 marker=dict(color=colors['exposure'], size=10, symbol='line-ns'),
                 showlegend=False, hoverinfo='skip'
             ))
            if show_legend_exp: plotted_legend_items.add('exposure')


        # Plot other events as markers
        for event_type in ['symptom', 'test', 'treatment']:
            if event_dates[event_type]:
                show_legend_marker = event_type not in plotted_legend_items
                fig.add_trace(go.Scatter(
                    x=event_dates[event_type], y=[y_val] * len(event_dates[event_type]),
                    mode='markers', marker=dict(color=colors[event_type], symbol=symbols[event_type], size=sizes[event_type]),
                    name=event_type.capitalize(), legendgroup=event_type, showlegend=show_legend_marker,
                    hoverinfo='text',
                    hovertext=[f"<b>{person_name}</b><br>{event_type.capitalize()}: {dt:%Y-%m-%d}<br>{detail}"
                               for dt, detail in zip(event_dates[event_type], event_details[event_type])]
                ))
                if show_legend_marker: plotted_legend_items.add(event_type)

    # Layout
    fig.update_layout(
        title='Visual Case Analysis Timeline (Dash)', xaxis_title='Date', yaxis_title='Person',
        xaxis=dict(range=[min_date_dt, max_date_dt], type='date'),
        # Order Y axis based on the reversed list used for plotting
        yaxis=dict(categoryorder='array', categoryarray=list(reversed(person_names))),
        hovermode='closest', legend_title_text='Event Types', legend=dict(tracegroupgap=20),
        margin=dict(l=150, r=20, t=50, b=50) # Adjust margins
    )

    # Add horizontal lines based on the final person_names list
    for name in person_names:
         fig.add_shape(type="line", x0=min_date_dt, y0=name, x1=max_date_dt, y1=name,
                       line=dict(color="LightGrey", width=1, dash="dot"))

    return fig


# --- Initialize the Dash App ---
app = dash.Dash(__name__, suppress_callback_exceptions=True) # Suppress warnings for dynamically shown inputs
server = app.server # Expose Flask server for potential deployment

# --- App Layout ---
app.layout = html.Div([
    html.H1("Visual Case Analysis Tool (Dash)"),

    # Graph Display
    dcc.Graph(id='vca-graph', figure=create_vca_plot(vca_data)), # Initial plot

    # Input Form Section
    html.Div([
        html.H2("Add New Event"),

        # Person Selection/Addition
        html.Div([
            html.Div([
                html.Label("Select Existing Person:", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='person-select-dropdown',
                    # Use sorted unique names for options
                    options=[{'label': name, 'value': name} for name in sorted(list(dict.fromkeys([p['name'] for p in vca_data])))],
                    placeholder="-- Select --",
                    style={'width': '95%'}
                ),
            ], style={'flex': '1'}), # Column 1
            html.Div([
                 html.Label("Or Add New Person:", style={'fontWeight': 'bold'}),
                 dcc.Input(
                    id='person-input-new',
                    type='text',
                    placeholder="Enter name if new",
                    style={'width': '95%', 'padding': '6px'} # Adjust padding
                 ),
            ], style={'flex': '1'}), # Column 2
        ], style={'display': 'flex', 'gap': '15px', 'marginBottom': '15px'}), # Row for person input


        # Event Type and Date Row
         html.Div([
             html.Div([
                 html.Label("Event Type:", style={'fontWeight': 'bold'}),
                 dcc.Dropdown(
                    id='event-type-dropdown',
                    options=[
                        {'label': 'Symptom', 'value': 'symptom'},
                        {'label': 'Test', 'value': 'test'},
                        {'label': 'Treatment', 'value': 'treatment'},
                        {'label': 'Exposure Period', 'value': 'exposure'},
                    ],
                    placeholder="-- Select Type --",
                    style={'width': '95%'},
                    # required=True, # Removed - validation handled in callback
                 ),
            ], style={'flex': '1'}), # Event Type Column

            # Container for Single Date Picker (shown/hidden by callback)
            html.Div([
                html.Label("Date:", style={'fontWeight': 'bold'}),
                dcc.DatePickerSingle(
                    id='event-date-picker',
                    display_format='YYYY-MM-DD',
                    style={'width': '95%'}
                ),
            ], id='single-date-div', style={'flex': '1', 'display': 'none'}), # Hidden initially

            # Container for Date Range Picker (shown/hidden by callback)
            html.Div([
                 html.Label("Date Range:", style={'fontWeight': 'bold'}),
                 dcc.DatePickerRange(
                    id='exposure-date-range-picker',
                    display_format='YYYY-MM-DD',
                    start_date_placeholder_text="Start Date",
                    end_date_placeholder_text="End Date",
                    style={'width': '100%'} # Let it fill the container
                 ),
            ], id='range-date-div', style={'flex': '1', 'display': 'none'}), # Hidden initially

         ], style={'display': 'flex', 'gap': '15px', 'marginBottom': '15px'}), # Row for type/date


        # Details Textarea
        html.Div([
            html.Label("Details:", style={'fontWeight': 'bold'}),
            dcc.Textarea(
                id='details-input',
                placeholder="e.g., RPR 1:16, Penile Chancre, Bicillin 2.4mu",
                style={'width': '97%', 'height': 60}
            ),
        ], style={'marginBottom': '15px'}),

        # Submit Button
        html.Button('Add Event', id='add-event-button', n_clicks=0),

        # Status message area
        html.Div(id='callback-status', style={'marginTop': '15px', 'color': 'red', 'fontWeight': 'bold'}) # Changed color to red for errors

    ], style={'border': '1px solid #eee', 'padding': '20px', 'backgroundColor': '#f9f9f9', 'marginTop': '30px'}),

], style={'fontFamily': 'sans-serif', 'margin': '20px'})


# --- Callbacks ---

# Callback 1: Toggle Date Picker Visibility based on Event Type
@app.callback(
    Output('single-date-div', 'style'),
    Output('range-date-div', 'style'),
    # No need to manage required here, handled in add callback
    Input('event-type-dropdown', 'value')
)
def toggle_date_pickers(event_type):
    single_style = {'flex': '1', 'display': 'none'}
    range_style = {'flex': '1', 'display': 'none'}

    if event_type == 'exposure':
        range_style = {'flex': '1', 'display': 'block'}
    elif event_type in ['symptom', 'test', 'treatment']:
        single_style = {'flex': '1', 'display': 'block'}

    return single_style, range_style


# Callback 2: Add Event and Update Graph
@app.callback(
    Output('vca-graph', 'figure'),
    Output('person-select-dropdown', 'options'), # Update dropdown options too
    Output('callback-status', 'children'), # Feedback message
    # Reset form fields after submission
    Output('person-select-dropdown', 'value'),
    Output('person-input-new', 'value'),
    Output('event-type-dropdown', 'value'),
    Output('event-date-picker', 'date'),
    Output('exposure-date-range-picker', 'start_date'),
    Output('exposure-date-range-picker', 'end_date'),
    Output('details-input', 'value'),
    Input('add-event-button', 'n_clicks'),
    State('person-select-dropdown', 'value'),
    State('person-input-new', 'value'),
    State('event-type-dropdown', 'value'),
    State('event-date-picker', 'date'),
    State('exposure-date-range-picker', 'start_date'),
    State('exposure-date-range-picker', 'end_date'),
    State('details-input', 'value'),
    prevent_initial_call=True # Don't run on page load
)
def add_event_and_update(n_clicks, selected_person, new_person_name,
                         event_type, event_date, start_date, end_date, details):
    global vca_data # Modify the global data (better alternatives exist for complex apps)

    status_message = ""
    status_color = 'green' # Default to green for success

    # --- VALIDATION CHECKS ---
    person_name = None
    is_new = False
    if new_person_name and new_person_name.strip():
        person_name = new_person_name.strip()
        is_new = True
        # Check if 'new' name already exists
        if any(p['name'] == person_name for p in vca_data):
            is_new = False # It's actually an existing person specified via the text box
    elif selected_person:
        person_name = selected_person

    if not person_name:
        status_message = "Error: Please select or enter a person's name."
    elif not event_type:
        status_message = "Error: Please select an Event Type."

    if status_message: # If basic validation failed
        status_color = 'red'
        updated_fig = create_vca_plot(vca_data) # No change to data
        updated_options = [{'label': name, 'value': name} for name in sorted(list(dict.fromkeys([p['name'] for p in vca_data])))]
        # Keep original values in form
        return (updated_fig, updated_options, status_message,
                selected_person, new_person_name, event_type, event_date,
                start_date, end_date, details)
    # --- END BASIC VALIDATION ---

    # --- DATE VALIDATION and EVENT CREATION ---
    new_event = {'type': event_type, 'details': details if details else ""}
    valid_date = True

    if event_type == 'exposure':
        parsed_start = parse_date(start_date)
        parsed_end = parse_date(end_date)
        if not (parsed_start and parsed_end):
            status_message = "Error: Please provide valid start and end dates for exposure."
            valid_date = False
        elif parsed_start > parsed_end:
             status_message = "Error: Exposure start date cannot be after end date."
             valid_date = False
        else:
            new_event['start_date'] = parsed_start.strftime('%Y-%m-%d')
            new_event['end_date'] = parsed_end.strftime('%Y-%m-%d')

    else: # Single date event types
        parsed_event_date = parse_date(event_date)
        if not parsed_event_date:
             status_message = f"Error: Please provide a valid date for {event_type}."
             valid_date = False
        else:
             new_event['date'] = parsed_event_date.strftime('%Y-%m-%d')

    if not valid_date:
        status_color = 'red'
        updated_fig = create_vca_plot(vca_data) # No change to data
        updated_options = [{'label': name, 'value': name} for name in sorted(list(dict.fromkeys([p['name'] for p in vca_data])))]
         # Keep original values in form
        return (updated_fig, updated_options, status_message,
                selected_person, new_person_name, event_type, event_date,
                start_date, end_date, details)
    # --- END DATE VALIDATION ---


    # --- ADD DATA if all validation passed ---
    person_found = False
    for person in vca_data:
        if person['name'] == person_name:
            person['events'].append(new_event)
            person_found = True
            break

    if not person_found and is_new:
         vca_data.append({
             "name": person_name,
             "type": "partner", # Default new people to partner
             "events": [new_event]
         })
    elif not person_found and not is_new:
         # This case should ideally not happen if dropdown is populated correctly
         # but could occur if data changes elsewhere without dropdown update
         status_message = f"Error: Selected person '{person_name}' not found in data (internal issue)."
         status_color = 'red'


    if not status_message.startswith("Error"): # If no errors so far
         status_message = f"Success: Event added for {person_name}."
         status_color = 'green'
         # Clear form fields on success by returning None/empty string for their value props
         reset_select = None
         reset_new = ""
         reset_type = None
         reset_date = None
         reset_start = None
         reset_end = None
         reset_details = ""
    else: # An error occurred during data addition phase (like person not found)
        status_color = 'red'
        reset_select = selected_person
        reset_new = new_person_name
        reset_type = event_type
        reset_date = event_date
        reset_start = start_date
        reset_end = end_date
        reset_details = details


    # Regenerate the plot with potentially updated data
    updated_fig = create_vca_plot(vca_data)

    # Update dropdown options to include any newly added person
    updated_options = [{'label': name, 'value': name} for name in sorted(list(dict.fromkeys([p['name'] for p in vca_data])))]

    # Return updated figure, options, status, and reset values
    # Note: We also need to update the style of the status message for color
    status_output = html.Div(status_message, style={'color': status_color, 'marginTop': '15px', 'fontWeight': 'bold'})

    return (updated_fig, updated_options, status_output,
            reset_select, reset_new, reset_type, reset_date, reset_start, reset_end, reset_details)


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True) # Use app.run for Dash 2.0 and later
