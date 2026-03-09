import httpx
import pandas as pd
from typing import List, Dict, Optional, Any

class RViewerClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url

    async def get_health(self) -> Dict[str, Any]:
        """Check if the backend server is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/health")
                return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_events(
        self, 
        channel: Optional[str] = None, 
        level: Optional[str] = None, 
        limit: int = 50,
        days_ago: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query event logs from the backend."""
        params = {"limit": limit}
        if channel:
            params["channel"] = channel
        if level:
            params["level"] = level
        if days_ago is not None:
            params["days_ago"] = days_ago

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/events", params=params)
                data = response.json()
                if data.get("success"):
                    return data.get("data", [])
                else:
                    print(f"API Error: {data.get('error')}")
                    return []
        except Exception as e:
            print(f"Connection Error: {e}")
            return []

    async def ingest_logs(self, channel: str, limit: int = 100) -> Dict[str, Any]:
        """Trigger ingestion of Windows Event Logs."""
        payload = {"channel": channel, "limit": limit}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/ingest", 
                    json=payload,
                    timeout=30.0  # Ingestion can take a moment
                )
                return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

def format_events_to_df(events: List[Dict[str, Any]]) -> pd.DataFrame:
    """Helper to convert API response data to a clean Pandas DataFrame."""
    if not events:
        return pd.DataFrame(columns=["Time", "Level", "Source", "ID", "Message", "Channel"])
    
    df = pd.DataFrame(events)
    
    # Rename and reorder columns for better UI display if they exist
    column_mapping = {
        "time": "Time",
        "level": "Level",
        "source": "Source",
        "event_id": "ID",
        "message": "Message",
        "channel": "Channel"
    }
    
    df = df.rename(columns=column_mapping)
    
    # Format Time for better readability (Mar 07, 19:15)
    if "Time" in df.columns:
        try:
            # SurrealDB datetime is often in ISO format
            df["Time"] = pd.to_datetime(df["Time"]).dt.strftime('%b %d, %H:%M:%S')
        except:
            pass # Keep original if parsing fails
            
    # Ensure all expected columns are present
    expected_cols = ["Time", "Level", "Source", "ID", "Message", "Channel"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = ""
            
    return df[expected_cols]
