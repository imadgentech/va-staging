import sys
import os
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import dash_bootstrap_components as dbc
from datetime import datetime
from dotenv import load_dotenv
import re

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from src.core.airtable_client import AirtableManager

load_dotenv()

# --- INITIALIZATION ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG]) # Dark Theme
app.title = "AI Voice Analytics"

# Initialize Manager Safely
try:
    manager = AirtableManager()
except Exception:
    manager = None

# --- HELPER FUNCTIONS ---
def normalize_phone(phone_str):
    """Strips everything except digits for robust comparison"""
    if not phone_str: return ""
    return re.sub(r'\D', '', str(phone_str))

def fetch_data():
    """Fetches and processes data from Airtable"""
    if not manager:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    try:
        # 1. Fetch Logs
        logs = manager.get_all_logs()
        df_logs = pd.DataFrame([r['fields'] for r in logs]) if logs else pd.DataFrame()
        
        # 2. Fetch Reservations
        res = manager.get_all_reservations()
        df_res = pd.DataFrame([r['fields'] for r in res]) if res else pd.DataFrame()
        
        # 3. Fetch Restaurants
        rests = manager.get_all_restaurants()
        df_rests = pd.DataFrame([r['fields'] for r in rests]) if rests else pd.DataFrame()
        
        return df_logs, df_res, df_rests
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- LAYOUT COMPONENTS ---
def create_card(title, value, subtitle="", color="primary"):
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="card-subtitle text-muted"),
            html.H2(value, className=f"card-title text-{color}"),
            html.Small(subtitle, className="text-muted")
        ]),
        className="mb-4 shadow-sm"
    )

def create_gauge(value, title):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = value,
        title = {'text': title},
        gauge = {
            'axis': {'range': [None, 5], 'tickwidth': 1},
            'bar': {'color': "#00cc96"},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "#333",
            'steps': [{'range': [0, 5], 'color': '#1a1a1a'}]
        }
    ))
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"}, height=250)
    return fig

# --- APP LAYOUT ---
app.layout = dbc.Container([
    # 1. Header & Filters
    dbc.Row([
        dbc.Col(html.H2("AI Voice Front Desk Analytics", className="text-white mt-4 mb-4"), width=8),
        dbc.Col(
            dcc.Dropdown(
                id='restaurant-filter',
                options=[], # Populated by callback
                value='ALL', # Default value set here
                placeholder="Select Location",
                className="mt-4 text-dark"
            ), width=4
        )
    ]),

    # 2. KPIs Row
    dbc.Row([
        dbc.Col(id='card-interactions', width=3),
        dbc.Col(id='card-avg-time', width=3),
        dbc.Col(id='card-orders', width=3),
        dbc.Col(id='card-engagement', width=3),
    ]),

    # 3. Charts Row
    dbc.Row([
        # Line Chart (Interactions)
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id='line-chart', config={'displayModeBar': False})
            ])), width=8
        ),
        # Gauge Chart (Satisfaction/Completion)
        dbc.Col(
            dbc.Card(dbc.CardBody([
                dcc.Graph(id='gauge-chart', config={'displayModeBar': False})
            ])), width=4
        ),
    ], className="mb-4"),

    # 4. Data Refresh Timer (Every 30s)
    dcc.Interval(id='interval-component', interval=30*1000, n_intervals=0)

], fluid=True, style={'backgroundColor': '#000000', 'minHeight': '100vh'})


# --- CALLBACKS (LOGIC) ---
@app.callback(
    Output('restaurant-filter', 'options'),
    [Input('interval-component', 'n_intervals')]
)
def update_dropdown(n):
    # Fetch data
    _, _, df_rests = fetch_data()
    
    # Default Option
    default_options = [{'label': 'All Locations', 'value': 'ALL'}]
    
    if df_rests.empty:
        return default_options
    
    # Ensure columns exist
    if 'name' not in df_rests.columns or 'phone_number' not in df_rests.columns:
        return default_options

    # Filter out bad rows
    valid_rests = df_rests.dropna(subset=['name', 'phone_number'])
    
    # Build list
    dynamic_options = [
        {'label': str(r['name']), 'value': str(r['phone_number'])} 
        for _, r in valid_rests.iterrows()
    ]
    
    return default_options + dynamic_options

@app.callback(
    [Output('card-interactions', 'children'),
     Output('card-avg-time', 'children'),
     Output('card-orders', 'children'),
     Output('card-engagement', 'children'),
     Output('line-chart', 'figure'),
     Output('gauge-chart', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('restaurant-filter', 'value')]
)
def update_metrics(n, selected_location):
    df_logs, df_res, _ = fetch_data()
    
    # --- FILTERING ---
    if selected_location and selected_location != 'ALL':
        if not df_logs.empty and 'restaurant_number' in df_logs.columns:
            # 1. Normalize the selection (strip +1, dashes, etc)
            clean_selection = normalize_phone(selected_location)
            
            # 2. Normalize the column data to match
            # Create a temp column for safe comparison
            df_logs['clean_number'] = df_logs['restaurant_number'].apply(normalize_phone)
            
            # 3. Filter
            df_logs = df_logs[df_logs['clean_number'] == clean_selection]
        
    # --- KPI CALCS ---
    total_calls = len(df_logs) if not df_logs.empty else 0
    total_orders = len(df_res) if not df_res.empty else 0
    
    # Mock Data for demo purposes
    avg_time = "1m 20s" 
    engagement = "85%"

    # --- CHARTS ---
    # 1. Line Chart (Calls over time)
    fig_line = go.Figure()
    if not df_logs.empty and 'timestamp' in df_logs.columns:
        try:
            df_logs['timestamp'] = pd.to_datetime(df_logs['timestamp'])
            df_grouped = df_logs.resample('D', on='timestamp').size().reset_index(name='count')
            
            fig_line.add_trace(go.Scatter(
                x=df_grouped['timestamp'], y=df_grouped['count'],
                mode='lines+markers',
                line=dict(color='#00cc96', width=3),
                fill='tozeroy'
            ))
        except Exception as e:
            print(f"Chart Error: {e}")
    
    fig_line.update_layout(
        title="Daily Voice Interactions",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#333')
    )

    # 2. Gauge Chart
    fig_gauge = create_gauge(4.8, "Guest Satisfaction")

    return (
        create_card("Total Interactions", total_calls),
        create_card("Avg Response Time", avg_time, "Target: <10s"),
        create_card("Voice Reservations", total_orders, "Converted from calls"),
        create_card("Engagement Rate", engagement, "Call completion > 30s"),
        fig_line,
        fig_gauge
    )

# --- RUN SERVER ---
if __name__ == '__main__':
    app.run(debug=True, port=8050)