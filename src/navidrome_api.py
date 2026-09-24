import hashlib
import secrets
import string
import httpx

class NavidromeClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.client_name = "MediaRequestPortal"
        self.subsonic_version = "1.16.1"

    def _generate_auth_params(self):
        # API Subsonic richiede un salt randomico e un token md5(password + salt)
        salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
        token = hashlib.md5((self.password + salt).encode('utf-8')).hexdigest()
        
        return {
            'u': self.username,
            't': token,
            's': salt,
            'v': self.subsonic_version,
            'c': self.client_name,
            'f': 'json'
        }

    async def start_scan(self) -> bool:
        endpoint = f"{self.base_url}/rest/startScan"
        params = self._generate_auth_params()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(endpoint, params=params)
            
            if response.status_code != 200:
                raise Exception(f"Navidrome API error: {response.status_code} - {response.text}")
                
            data = response.json()
            if data.get('subsonic-response', {}).get('status') != 'ok':
                raise Exception(f"Navidrome API returned error: {data}")
                
            return True
