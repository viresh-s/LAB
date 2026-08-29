from supabase import create_client, Client
# Import the settings from the config file you showed me
from app.core.config import settings

# Use the service-role key for backend/admin operations (bypasses RLS)
_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY

if settings.SUPABASE_URL and _key:
    supabase: Client = create_client(settings.SUPABASE_URL, _key)
else:
    supabase = None

# This 'supabase' object is what you will import into your LangGraph nodes
# to read and write data.