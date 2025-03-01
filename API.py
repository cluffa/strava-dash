import logging
from functools import lru_cache
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import html, dcc
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class StravaAPI:
    @staticmethod
    def get_activities_data(client, limit=100, before=None, after=None):
        """Fetch and process activities from Strava."""
        try:
            # Calculate date range if not provided
            if not after:
                after = datetime.now() - timedelta(days=90)  # Last 90 days by default
            if not before:
                before = datetime.now()

            logger.info("Fetching activities between %s and %s", after, before)
            
            # Get activities iterator
            activities_iter = client.get_activities(
                before=before,
                after=after,
                limit=limit
            )
            
            activities_data = []
            for activity in activities_iter:
                activity_dict = {
                    'id': activity.id,
                    'name': activity.name,
                    'type': str(activity.type),
                    'start_date': activity.start_date_local,
                    'kudos': activity.kudos_count,
                    'distance': str(activity.distance),
                    'moving_time': str(activity.moving_time),
                    'elapsed_time': str(activity.elapsed_time),
                    'total_elevation_gain': str(activity.total_elevation_gain),
                    'average_speed': str(activity.average_speed),
                }
                
                # Add optional attributes if they exist
                for attr in ['max_speed', 'average_watts', 'max_watts', 'average_heartrate', 'max_heartrate']:
                    try:
                        val = getattr(activity, attr)
                        activity_dict[attr] = str(val) if val is not None else 'N/A'
                    except:
                        activity_dict[attr] = 'N/A'
                
                activities_data.append(activity_dict)
                
                if len(activities_data) >= limit:
                    break
            
            logger.info("Successfully fetched %d activities", len(activities_data))
            return pd.DataFrame(activities_data)
            
        except Exception as e:
            logger.exception("Error fetching activities")
            return None

    @staticmethod
    @lru_cache(maxsize=100)  # Cache stream data to reduce API calls
    def get_activity_streams(client, activity_id):
        """Fetch detailed stream data for an activity."""
        try:
            streams = client.get_activity_streams(
                activity_id,
                types=['time', 'distance', 'altitude', 'velocity_smooth', 'heartrate'],
                resolution='medium'
            )
            
            if not streams:
                return None
                
            # Convert to simple dict structure
            stream_data = {}
            for stream_type in streams.keys():
                try:
                    data = streams[stream_type].data
                    stream_data[stream_type] = [float(x) if hasattr(x, 'real') else x for x in data]
                except Exception as e:
                    logger.warning(f"Could not process stream {stream_type}: {e}")
                    
            return stream_data
            
        except Exception as e:
            logger.exception(f"Error fetching streams for activity {activity_id}")
            return None

    @staticmethod
    def create_activity_details(df, client, activity_id):
        """Create detailed view for a single activity."""
        if activity_id is None:
            return html.Div()
            
        # Get activity details
        activity = df[df['id'] == activity_id].iloc[0]
        streams = StravaAPI.get_activity_streams(client, activity_id)
        
        if not streams:
            return html.Div([
                html.H3(activity['name']),
                html.P("No detailed data available for this activity")
            ])
            
        # Create elevation profile
        elevation_fig = go.Figure()
        if 'altitude' in streams and 'distance' in streams:
            elevation_fig.add_trace(go.Scatter(
                x=streams['distance'],
                y=streams['altitude'],
                name='Elevation',
                fill='tozeroy'
            ))
            elevation_fig.update_layout(
                title='Elevation Profile',
                xaxis_title='Distance (m)',
                yaxis_title='Elevation (m)'
            )
            
        # Create speed profile
        speed_fig = go.Figure()
        if 'velocity_smooth' in streams and 'distance' in streams:
            speed_fig.add_trace(go.Scatter(
                x=streams['distance'],
                y=streams['velocity_smooth'],
                name='Speed'
            ))
            speed_fig.update_layout(
                title='Speed Profile',
                xaxis_title='Distance (m)',
                yaxis_title='Speed (m/s)'
            )
            
        # Create heart rate profile if available
        hr_fig = None
        if 'heartrate' in streams and 'distance' in streams:
            hr_fig = go.Figure()
            hr_fig.add_trace(go.Scatter(
                x=streams['distance'],
                y=streams['heartrate'],
                name='Heart Rate'
            ))
            hr_fig.update_layout(
                title='Heart Rate Profile',
                xaxis_title='Distance (m)',
                yaxis_title='Heart Rate (bpm)'
            )
            
        graphs = [
            html.Div([
                dcc.Graph(figure=fig)
            ]) for fig in [elevation_fig, speed_fig, hr_fig] if fig is not None
        ]
            
        return html.Div([
            html.H3(activity['name']),
            html.Div(graphs, style={'display': 'flex', 'flexWrap': 'wrap'})
        ])

    @staticmethod
    def create_dashboard(df, client=None):
        """Create dashboard layout with activity statistics."""
        if df is None or df.empty:
            return html.Div([
                html.H2('No Data Available'),
                html.P('Unable to fetch activity data from Strava.')
            ])

        # Create activity type visualization
        activity_counts = df['type'].value_counts().reset_index()
        activity_counts.columns = ['type', 'count']
        
        type_fig = px.bar(activity_counts, 
                         x='type', 
                         y='count',
                         title='Activities by Type')
        
        # Add activity summary statistics
        if not df.empty:
            total_activities = len(df)
            activity_types = df['type'].value_counts()
            
            summary_stats = html.Div([
                html.H3('Activity Summary'),
                html.P(f'Total Activities: {total_activities}'),
                html.P(f'Activity Types: {", ".join(activity_types.index[:5])}'),
                html.P(f'Date Range: {df["start_date"].min()} to {df["start_date"].max()}'),
            ])
            
            dashboard_content = [
                html.H1('Your Strava Dashboard'),
                summary_stats,
                html.Div([
                    dcc.Graph(id='activity-types', figure=type_fig)
                ]),
                html.Div([
                    html.H3('Activity Details'),
                    dcc.Dropdown(
                        id='activity-selector',
                        options=[{'label': f"{row['start_date']} - {row['name']}", 
                                'value': row['id']} for _, row in df.iterrows()],
                        placeholder="Select an activity to view details"
                    ),
                    html.Div(id='activity-details')
                ]),
                html.Div([
                    html.H3('Recent Activities'),
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
            ]
            
            return html.Div(dashboard_content)
        else:
            return html.Div([
                html.H1('Your Strava Dashboard'),
                html.Div([
                    dcc.Graph(id='activity-types', figure=type_fig)
                ]),
                html.Div([
                    html.H3('Recent Activities'),
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
