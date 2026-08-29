import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def get_supabase():
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: Missing Supabase credentials.")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def run_cleanup():
    supabase = get_supabase()
    if not supabase:
        print("Cannot run cleanup, missing supabase credentials")
        return
        
    print(f"[{datetime.now()}] Starting 30-day auto-deletion cleanup...")
    
    # 1. Fetch labs that do NOT have extended_storage = true
    labs_res = supabase.table("labs").select("id, extended_storage").execute()
    labs = labs_res.data or []
    
    labs_to_clean = [lab['id'] for lab in labs if not lab.get('extended_storage')]
    
    if not labs_to_clean:
        print("No labs require cleanup. Exiting.")
        return

    # Calculate the cutoff date (30 days ago)
    cutoff_date = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    # Process labs
    total_deleted = 0
    for lab_id in labs_to_clean:
        # Fetch old patients for this lab
        patients_res = (
            supabase.table("patients")
            .select("id, report_link")
            .eq("lab_id", lab_id)
            .lt("created_at", cutoff_date)
            .execute()
        )
        
        old_patients = patients_res.data or []
        if not old_patients:
            continue
            
        print(f"Found {len(old_patients)} old records for lab {lab_id}")
        
        storage_paths_to_delete = []
        patient_ids_to_delete = []
        
        for p in old_patients:
            patient_ids_to_delete.append(p['id'])
            link = p.get('report_link')
            if link and 'reports/' in link:
                filename = link.split('reports/')[-1]
                storage_paths_to_delete.append(filename)
                
        # 1. Delete from Storage
        if storage_paths_to_delete:
            try:
                supabase.storage.from_("reports").remove(storage_paths_to_delete)
                print(f"Deleted {len(storage_paths_to_delete)} PDFs from storage.")
            except Exception as e:
                print(f"Error deleting storage for lab {lab_id}: {e}")
                
        # 2. Delete from Database
        if patient_ids_to_delete:
            try:
                supabase.table("patients").delete().in_("id", patient_ids_to_delete).execute()
                print(f"Deleted {len(patient_ids_to_delete)} patient records from DB.")
                total_deleted += len(patient_ids_to_delete)
            except Exception as e:
                print(f"Error deleting db records for lab {lab_id}: {e}")
                
    print(f"[{datetime.now()}] Cleanup complete. Total records deleted: {total_deleted}")

if __name__ == "__main__":
    run_cleanup()
