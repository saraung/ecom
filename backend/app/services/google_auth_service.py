import warnings

try:
    from google.oauth2 import id_token
    from google.auth.transport import requests
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    warnings.warn("Google Auth not available. Install: uv add google-auth requests")

from app.schemas.google_auth import GoogleUserInfo
from app.core.config import settings


class GoogleAuthService:
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        
        # Debug prints
        print(f"Google Auth Available: {GOOGLE_AUTH_AVAILABLE}")
        print(f"Google Client ID configured: {bool(self.client_id)}")
        print(f"Google Client Secret configured: {bool(self.client_secret)}")
        
        if self.client_id:
            print(f"Client ID: {self.client_id[:30]}...")
    
    def verify_id_token(self, id_token_str: str) -> GoogleUserInfo | None:
        """Verify Google ID token and extract user info"""
        if not GOOGLE_AUTH_AVAILABLE:
            print("ERROR: Google Auth library not installed")
            return None
        
        if not self.client_id:
            print("ERROR: GOOGLE_CLIENT_ID not configured in .env")
            return None
        
        try:
            # Verify the token
            info = id_token.verify_oauth2_token(
                id_token_str,
                requests.Request(),
                self.client_id
            )
            
            print(f"Token verified successfully for: {info.get('email')}")
            
            # Check if the token is for this app
            if info.get("aud") not in [self.client_id]:
                print(f"Invalid audience: {info.get('aud')}")
                return None
            
            return GoogleUserInfo(
                id=info.get("sub"),
                email=info.get("email"),
                name=info.get("name"),
                given_name=info.get("given_name"),
                family_name=info.get("family_name"),
                picture=info.get("picture"),
                verified_email=info.get("email_verified", False),
            )
        except Exception as e:
            print(f"Google token verification failed: {str(e)}")
            return None


google_auth_service = GoogleAuthService()