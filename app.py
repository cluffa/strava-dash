import logging
import os
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from flask import session

from auth import StravaAuth
from API import StravaAPI

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize the Dash app
app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server
server.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')

# Load config from environment
server.config['STRAVA_CLIENT_ID'] = os.environ.get('STRAVA_CLIENT_ID')
server.config['STRAVA_CLIENT_SECRET'] = os.environ.get('STRAVA_CLIENT_SECRET')

# Initialize auth handler
auth_handler = StravaAuth(server.config)

# Define the layout
app.layout = html.Div([
    dcc.Location(id='url', refresh=True),
    html.Div(id='page-content')
])

@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'),
     Input('url', 'search')]
)
def display_page(pathname, search):
    """Handle page routing and display appropriate content."""
    logger.debug("Page requested - Path: %s, Search: %s", pathname, search)
    
    if pathname == '/':
        return auth_handler.create_login_layout()
        
    elif pathname == '/strava-oauth':
        client, error = auth_handler.handle_oauth_callback(search)
        if error:
            return html.Div([
                html.H2('Authentication Error'),
                html.P(error),
                html.A('Try Again', href='/', className='strava-button')
            ])
            
        df = StravaAPI.get_activities_data(client)
        return StravaAPI.create_dashboard(df)
        
    elif 'access_token' in session:
        client = auth_handler.get_client()
        if client:
            df = StravaAPI.get_activities_data(client)
            return StravaAPI.create_dashboard(df)
    
    return html.Div([
        html.H2('404 - Page Not Found'),
        html.A('Go Home', href='/', className='strava-button')
    ])

@app.callback(
    Output('activity-details', 'children'),
    [Input('activity-selector', 'value')],
    [State('page-content', 'children')]
)
def update_activity_details(activity_id, current_page):
    """Update the activity details when an activity is selected."""
    if not activity_id:
        return html.Div()
        
    client = auth_handler.get_client()
    if not client:
        return html.Div("Please log in again")
        
    df = StravaAPI.get_activities_data(client)
    return StravaAPI.create_activity_details(df, client, activity_id)

if __name__ == '__main__':
    app.run_server(debug=True)