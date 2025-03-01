import logging
import secrets
import time
from urllib.parse import urlencode, parse_qs

from dash import html
from flask import request, session
from stravalib import Client

logger = logging.getLogger(__name__)

class StravaAuth:
    def __init__(self, server_config):
        self.config = server_config
        
    def create_login_layout(self):
        """Generate the login page layout."""
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        params = {
            'client_id': self.config['STRAVA_CLIENT_ID'],
            'redirect_uri': request.url_root.rstrip('/') + '/strava-oauth',
            'approval_prompt': 'auto',
            'response_type': 'code',
            'scope': 'read,activity:read_all,profile:read_all',
            'state': state
        }
        auth_url = f"https://www.strava.com/oauth/authorize?{urlencode(params)}"
        logger.debug("Generated auth URL: %s", auth_url)
        
        return html.Div([
            html.H1('Strava Dashboard Login'),
            html.A('Connect with Strava', href=auth_url, className='strava-button')
        ])

    def handle_oauth_callback(self, search):
        """Process OAuth callback and return auth result."""
        query_params = parse_qs(search.lstrip('?'))
        logger.debug("OAuth callback params: %s", query_params)
        
        error = query_params.get('error', [None])[0]
        if error:
            return None, error
            
        code = query_params.get('code', [None])[0]
        received_state = query_params.get('state', [None])[0]
        
        if not received_state or received_state != session.get('oauth_state'):
            return None, "Invalid state parameter"
            
        if not code:
            return None, "No authorization code received"
            
        client = Client()
        try:
            token_response = client.exchange_code_for_token(
                client_id=self.config['STRAVA_CLIENT_ID'],
                client_secret=self.config['STRAVA_CLIENT_SECRET'],
                code=code
            )
            
            session['access_token'] = token_response['access_token']
            session['refresh_token'] = token_response['refresh_token']
            session['expires_at'] = token_response['expires_at']
            
            client.access_token = session['access_token']
            return client, None
            
        except Exception as e:
            logger.exception("OAuth error")
            return None, str(e)

    def refresh_token_if_needed(self):
        """Check and refresh the Strava token if expired."""
        if 'expires_at' not in session or not session.get('refresh_token'):
            return False
            
        if int(session['expires_at']) < time.time():
            logger.debug("Token expired, refreshing...")
            client = Client()
            try:
                refresh_response = client.refresh_access_token(
                    client_id=self.config['STRAVA_CLIENT_ID'],
                    client_secret=self.config['STRAVA_CLIENT_SECRET'],
                    refresh_token=session['refresh_token']
                )
                session['access_token'] = refresh_response['access_token']
                session['refresh_token'] = refresh_response['refresh_token']
                session['expires_at'] = refresh_response['expires_at']
                return True
            except Exception as e:
                logger.error("Error refreshing token: %s", e)
                return False
        return True

    def get_client(self):
        """Get an authenticated Strava client."""
        if 'access_token' not in session:
            return None
            
        if not self.refresh_token_if_needed():
            return None
            
        client = Client()
        client.access_token = session['access_token']
        return client
