"""
Twitch OAuth2 Authentication for !Clipit
Implements Authorization Code Grant flow with automatic token refresh
"""
import asyncio
import aiohttp
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
from datetime import datetime
from logs import get_logger; log = get_logger(__name__)


class AuthHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback"""
    
    def __init__(self, *args, auth_queue=None, **kwargs):
        self.auth_queue = auth_queue
        # Set timeout to prevent hanging
        self.timeout = 1
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle OAuth callback"""
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        if 'code' in query_params:
            auth_code = query_params['code'][0]
            if self.auth_queue:
                self.auth_queue.put(auth_code)
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b'<html><body><h1>Authentication successful!</h1>'
                b'<p>You can close this window and return to the application.</p></body></html>'
            )
        elif 'error' in query_params:
            error = query_params['error'][0]
            error_description = query_params.get('error_description', [b'Unknown error'])[0]
            log.error(f"OAuth error: {error} - {error_description}")
            if self.auth_queue:
                self.auth_queue.put(None)
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b'<html><body><h1>Authentication failed</h1></body></html>'
            )
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b'<html><body><h1>Authentication failed</h1></body></html>'
            )

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


def create_handler_class(auth_queue):
    """Create a handler class with the auth_queue"""
    class Handler(AuthHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, auth_queue=auth_queue, **kwargs)
    return Handler


class TwitchAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = "http://localhost:3000"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = "https://id.twitch.tv/oauth2"
        self.api_url = "https://api.twitch.tv/helix"

    def get_auth_url(self, scopes: list = None) -> str:
        """Generate OAuth authorization URL"""
        if scopes is None:
            scopes = [
                "clips:edit",
                "chat:read",
                "chat:edit",
                "moderator:read:chatters"
            ]

        scope_string = "+".join(scopes)
        return (
            f"{self.base_url}/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope={scope_string}"
        )


    async def get_auth_code(self) -> Optional[str]:
        """Open browser and wait for OAuth callback"""
        import queue
        
        auth_url = self.get_auth_url()
        log.info(f"Opening browser for authentication.")
        log.info(f"If your browser does not automatically open, hit this URL manually: {auth_url}")
        log.info("Waiting for you to authorize the application in your browser...")

        # Create queue for communication between server thread and async code
        auth_queue = queue.Queue()
        
        # Create handler class with queue
        HandlerClass = create_handler_class(auth_queue)
        
        # Start local HTTP server in a separate thread
        server = HTTPServer(('localhost', 3000), HandlerClass)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.daemon = True
        server_thread.start()
        log.info("Local server started on http://localhost:3000")

        try:
            # Open browser
            webbrowser.open(auth_url)

            # Wait for callback with timeout (2 minute)
            timeout = 120
            start_time = datetime.now()

            # Poll the queue periodically
            while True:
                elapsed = (datetime.now() - start_time).total_seconds()

                if elapsed > timeout:
                    log.error("Authentication timeout - no response received within 2 minutes")
                    return None
                # Check if auth code is in queue (non-blocking)
                try:
                    auth_code = auth_queue.get_nowait()
                    if auth_code:
                        log.info("Authentication code received successfully")
                        return auth_code
                    else:
                        log.error("Authentication failed (error in callback)")
                        return None
                except queue.Empty:
                    # No code yet, wait a bit and check again
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.error(f"Error retrieving auth code from queue: {e}")
                    return None

        except Exception as e:
            log.error(f"Error waiting for authentication: {e}")
            return None
        finally:
            # Shutdown server
            try:
                log.debug("Calling shutdown")
                server.shutdown()
                log.debug("Calling server_close")
                server.server_close()
                log.debug("Local server shut down")
            except Exception as e:
                log.error(f"Error shutting down server: {e}")

    async def exchange_code_for_tokens(self, auth_code: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens"""
        url = f"{self.base_url}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    expires_at = int(datetime.now().timestamp()) + token_data['expires_in']
                    return {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data['refresh_token'],
                        'expires_at': expires_at
                    }
                else:
                    error_text = await response.text()
                    log.error(f"Token exchange failed: {response.status} - {error_text} - URL: {url} - data: {data} - token_data: {token_data}")
                    raise Exception(f"Failed to exchange code for tokens: {error_text}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        url = f"{self.base_url}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    expires_at = int(datetime.now().timestamp()) + token_data['expires_in']
                    return {
                        'access_token': token_data['access_token'],
                        'refresh_token': token_data.get('refresh_token', refresh_token),
                        'expires_at': expires_at
                    }
                else:
                    error_text = await response.text()
                    log.error(f"Token refresh failed: {response.status} - {error_text}")
                    raise Exception(f"Failed to refresh token: {error_text}")

    async def validate_token(self, access_token: str) -> bool:
        """Validate if access token is still valid"""
        url = f"{self.base_url}/validate"
        headers = {"Authorization": f"OAuth {access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                return response.status == 200

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get authenticated user information"""
        url = f"{self.api_url}/users"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": self.client_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('data', [{}])[0] if data.get('data') else {}
                else:
                    log.error(f"Failed to get user info: {response.status}")
                    return {}
