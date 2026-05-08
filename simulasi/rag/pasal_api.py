import os
import httpx
import logging
import urllib.parse
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load env variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)

class PasalAPI:
    """
    Client wrapper untuk https://pasal.id/api
    Digunakan untuk mencari dan memuat naskah Undang-Undang secara real-time.
    """
    BASE_URL = "https://pasal.id/api/v1"
    
    def __init__(self):
        self.token = os.getenv("PASAL_API_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        
    async def search(self, query: str, law_type: str = "UU", limit: int = 5) -> Dict[str, Any]:
        """Cari peraturan berdasarkan keyword."""
        if not self.token:
            logger.warning("PASAL_API_TOKEN tidak ditemukan di .env!")
            return {"error": "Token missing", "results": []}
            
        url = f"{self.BASE_URL}/search"
        params = {
            "q": query,
            "type": law_type,
            "limit": limit
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            logger.error(f"Timeout pada PasalAPI.search untuk query {query[:120]!r}: {repr(e)}")
            return {"error": "timeout saat menghubungi Pasal.id", "results": []}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:300] if e.response is not None else ""
            logger.error(f"HTTP error PasalAPI.search status={status}, body={body}")
            return {"error": f"HTTP {status} dari Pasal.id", "results": []}
        except Exception as e:
            logger.error(f"Error pada PasalAPI.search: {repr(e)}")
            return {"error": str(e), "results": []}

    async def get_law(self, frbr_uri: str) -> Dict[str, Any]:
        """Ambil detail peraturan beserta pasal lengkap untuk UI referensi."""
        if not self.token:
            logger.warning("PASAL_API_TOKEN tidak ditemukan di .env!")
            return {"error": "Token missing"}

        clean_uri = str(frbr_uri or "").strip()
        if not clean_uri:
            return {"error": "frbr_uri kosong"}

        url = f"{self.BASE_URL}/laws/{clean_uri.lstrip('/')}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=15.0)
                if response.status_code == 404:
                    encoded_uri = urllib.parse.quote(clean_uri, safe="")
                    response = await client.get(
                        f"{self.BASE_URL}/laws/{encoded_uri}",
                        headers=self.headers,
                        timeout=15.0,
                    )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            logger.error(f"Timeout pada PasalAPI.get_law untuk {clean_uri!r}: {repr(e)}")
            return {"error": "timeout saat mengambil detail Pasal.id"}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:300] if e.response is not None else ""
            logger.error(f"HTTP error PasalAPI.get_law status={status}, body={body}")
            return {"error": f"HTTP {status} dari Pasal.id"}
        except Exception as e:
            logger.error(f"Error pada PasalAPI.get_law: {repr(e)}")
            return {"error": str(e)}

# Singleton instance
pasal_api = PasalAPI()
