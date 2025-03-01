from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from flask import request, session
from stravalib import Client, unit_helper
import os
from urllib.parse import urlencode, parse_qs
import logging
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import secrets
import time

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize the Dash app with session support
app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server  # Expose Flask server for config
server.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')  # Add this line

# Load config from environment
server.config['STRAVA_CLIENT_ID'] = os.environ.get('STRAVA_CLIENT_ID')
server.config['STRAVA_CLIENT_SECRET'] = os.environ.get('STRAVA_CLIENT_SECRET')

# Define the layout
app.layout = html.Div([
    dcc.Location(id='url', refresh=True),
    html.Div(id='page-content')
])

def login_layout():
    client = Client()
    # Generate a unique state token and store it in session
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    params = {
        'client_id': server.config['STRAVA_CLIENT_ID'],
        'redirect_uri': request.url_root.rstrip('/') + '/strava-oauth',  # Use dynamic URL
        'approval_prompt': 'auto',
        'response_type': 'code',
        'scope': 'read,activity:read_all,profile:read_all',  # Add required scopes
        'state': state  # Add state for security
    }
    auth_url = f"https://www.strava.com/oauth/authorize?{urlencode(params)}"
    logger.debug(f"Generated auth URL: {auth_url}")
    
    return html.Div([
        html.H1('Strava Dashboard Login'),
        html.A('Connect with Strava', href=auth_url, className='strava-button')
    ])

def dashboard_layout(client):
    # Fetch recent activities and show raw data
    activities = list(client.get_activities(limit=30))
    
    # Create a simplified data structure
    activities_data = []
    for activity in activities:
        # Get all available attributes
        activity_dict = {
            'id': activity.id,
            'name': activity.name,
            'type': str(activity.type),  # Convert type to string
            'start_date': activity.start_date_local,
            'kudos': activity.kudos_count,
        }
        
        # Add any available numeric attributes
        for attr in ['distance', 'moving_time', 'elapsed_time', 'total_elevation_gain', 
                    'average_speed', 'max_speed', 'average_watts', 'max_watts']:
            try:
                val = getattr(activity, attr)
                activity_dict[attr] = str(val)  # Convert to string to handle all types
            except:
                activity_dict[attr] = 'N/A'
        
        activities_data.append(activity_dict)
    
    # Convert to DataFrame for easy handling
    df = pd.DataFrame(activities_data)
    
    # Create a simple bar chart of activity counts by type using string values
    activity_counts = df['type'].value_counts().reset_index()
    activity_counts.columns = ['type', 'count']
    
    type_fig = px.bar(activity_counts, 
                      x='type', 
                      y='count',
                      title='Activities by Type')
    
    return html.Div([
        html.H1('Your Strava Dashboard'),
        html.Div([
            dcc.Graph(id='activity-types', figure=type_fig)
        ]),
        html.Div([
            html.H3('Recent Activities (Raw Data)'),
            # Show all available columns in the table
            html.Table([
                html.Thead(html.Tr([html.Th(col) for col in df.columns])),
                html.Tbody([
                    html.Tr([
                        html.Td(str(df.iloc[i][col])) 
                        for col in df.columns
                    ]) for i in range(min(10, len(df)))
                ])
            ], className='activities-table')
        ])
    ])

def refresh_token_if_needed():
    if 'expires_at' not in session or not session.get('refresh_token'):
        return False
        
    if int(session['expires_at']) < time.time():
        logger.debug("Token expired, refreshing...")
        client = Client()
        try:
            refresh_response = client.refresh_access_token(
                client_id=server.config['STRAVA_CLIENT_ID'],
                client_secret=server.config['STRAVA_CLIENT_SECRET'],
                refresh_token=session['refresh_token']
            )
            session['access_token'] = refresh_response['access_token']
            session['refresh_token'] = refresh_response['refresh_token']
            session['expires_at'] = refresh_response['expires_at']
            return True
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False
    return True

@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname'),
    Input('url', 'search')
)
def display_page(pathname, search):
    logger.debug(f"Pathname: {pathname}, Search: {search}")
    
    # Check if we have a valid session and try to refresh token
    if pathname != '/' and 'access_token' in session:
        if not refresh_token_if_needed():
            return login_layout()
    
    if pathname == '/':
        return login_layout()
    elif pathname == '/strava-oauth':
        # Parse the query string
        query_params = parse_qs(search.lstrip('?'))
        logger.debug(f"Query params: {query_params}")
        
        error = query_params.get('error', [None])[0]
        if error:
            return html.Div([
                html.H2('Login Error'),
                html.P(f'Error: {error}'),
                html.A('Try Again', href='/', className='strava-button')
            ])
        
        code = query_params.get('code', [None])[0]
        received_state = query_params.get('state', [None])[0]
        
        # Verify state to prevent CSRF
        if not received_state or received_state != session.get('oauth_state'):
            return html.Div([
                html.H2('Security Error'),
                html.P('Invalid state parameter'),
                html.A('Try Again', href='/', className='strava-button')
            ])
        
        if not code:
            return html.Div([
                html.H2('Authentication Error'),
                html.P('No authorization code received'),
                html.A('Try Again', href='/', className='strava-button')
            ])
            
        logger.debug(f"Received code: {code}")
        client = Client()
        
        try:
            token_response = client.exchange_code_for_token(
                client_id=server.config['STRAVA_CLIENT_ID'],
                client_secret=server.config['STRAVA_CLIENT_SECRET'],
                code=code
            )
            logger.debug(f"Token response: {token_response}")
            
            # Store tokens in session
            session['access_token'] = token_response['access_token']
            session['refresh_token'] = token_response['refresh_token']
            session['expires_at'] = token_response['expires_at']
            
            # Set up client with access token
            client.access_token = session['access_token']
            
            # Return dashboard instead of welcome message
            return dashboard_layout(client)
        except Exception as e:
            import traceback
            logger.error(f"Authentication error: {e}")
            return html.Div([
                html.H2('Authentication Error'),
                html.P('Failed to authenticate with Strava. Please try again.'),
                html.Pre(str(e)),
                html.A('Try Again', href='/', className='strava-button')
            ])
    
    return '404'

if __name__ == '__main__':
    app.run_server(debug=True)