-- ============================================================
-- Migration: Twilio Voice + Multi-tenant Lab Support
-- Run this in Supabase SQL Editor
-- ============================================================

-- 1. labs table — your actual schema (already exists, shown for reference)
--    id           → UUID, FK to auth.users(id) — use your Supabase Auth user UUID
--    business_name → TEXT NOT NULL
--    twilio_number → TEXT NOT NULL  (your Twilio number, e.g. "+919876543210")
--
-- The table already exists, so we skip CREATE TABLE.
-- Just ensure twilio_number is unique (run if not already set):
CREATE UNIQUE INDEX IF NOT EXISTS labs_twilio_number_unique ON public.labs (twilio_number);


-- 2. call_sessions table — stores multi-turn voice conversation state
--    Keyed by Twilio CallSid. Serverless-safe: each webhook reads/writes this.
CREATE TABLE IF NOT EXISTS call_sessions (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    call_sid       TEXT UNIQUE NOT NULL,         -- Twilio CallSid
    lab_id         TEXT NOT NULL,                -- which lab this call is for
    patient_data   JSONB DEFAULT '{}',           -- PatientData collected so far
    missing_fields TEXT[] DEFAULT ARRAY[]::TEXT[], -- fields still needed
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql' SET search_path = '';

DROP TRIGGER IF EXISTS update_call_sessions_updated_at ON call_sessions;
CREATE TRIGGER update_call_sessions_updated_at
    BEFORE UPDATE ON call_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- 3. Insert your test lab
--    ⚠️  IMPORTANT: id must be a real UUID from auth.users (Supabase Auth).
--    Go to Supabase → Authentication → Users → copy your user UUID and paste below.
--    Replace YOUR_AUTH_USER_UUID and YOUR_TWILIO_NUMBER before running.
INSERT INTO public.labs (id, business_name, twilio_number)
VALUES (
    'YOUR_AUTH_USER_UUID',   -- e.g. 'a1b2c3d4-...' from Supabase Auth
    'Test Lab (Dev)',
    '+91XXXXXXXXXX'          -- your actual Twilio number
)
ON CONFLICT (id) DO UPDATE
    SET business_name = EXCLUDED.business_name,
        twilio_number = EXCLUDED.twilio_number;


-- 4. Create Supabase Storage bucket for TTS audio
--    Run this separately or via the Supabase Dashboard → Storage → New Bucket
--    Name: tts-audio, Public: true
-- insert into storage.buckets (id, name, public) values ('tts-audio', 'tts-audio', true);


-- ============================================================
-- 5. Payment + Report columns on patients table
--    Adds columns needed by the Payment & Report Upload flows.
--    Safe to re-run (uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- ============================================================

-- Payment amount (INR)
ALTER TABLE public.patients ADD COLUMN IF NOT EXISTS payment_amount DECIMAL(10,2);

-- Payment method (cash, upi, card, etc.)
ALTER TABLE public.patients ADD COLUMN IF NOT EXISTS payment_method TEXT;

-- Report PDF link (public URL from Supabase Storage)
ALTER TABLE public.patients ADD COLUMN IF NOT EXISTS report_link TEXT;



-- ============================================================
-- 6. Create Supabase Storage bucket for lab reports
--    Run this separately or via Dashboard → Storage → New Bucket
--    Name: lab-reports, Public: true
-- ============================================================
-- insert into storage.buckets (id, name, public) values ('lab-reports', 'lab-reports', true);


-- ============================================================
-- 7. Row-Level Security (RLS) Policies
--    Ensures labs can ONLY access their own data.
-- ============================================================

-- Enable RLS on patients
ALTER TABLE public.patients ENABLE ROW LEVEL SECURITY;

-- Allow labs to select/insert/update/delete their own patients
DROP POLICY IF EXISTS "Labs can access their own patients" ON public.patients;
CREATE POLICY "Labs can access their own patients"
ON public.patients
FOR ALL
USING (lab_id::text = auth.uid()::text);

-- Allow labs to upload reports to their own folder in storage
-- (Note: bucket 'lab-reports' must exist)
-- DROP POLICY IF EXISTS "Labs upload to their own folder" ON storage.objects;
-- CREATE POLICY "Labs upload to their own folder"
-- ON storage.objects
-- FOR ALL
-- USING (bucket_id = 'lab-reports' AND (storage.foldername(name))[1] = auth.uid()::text);


-- ============================================================
-- 8. 30-Day Auto-Cleanup Job (requires pg_cron extension)
--    Deletes old reports and unlinks them from patients.
-- ============================================================

CREATE OR REPLACE FUNCTION cleanup_old_reports()
RETURNS void AS $$
BEGIN
    -- 1. Unlink report_link in patients older than 30 days
    UPDATE public.patients
    SET report_link = NULL
    WHERE report_link IS NOT NULL
      AND updated_at < now() - interval '30 days';

    -- 2. Delete the actual files from storage.objects
    DELETE FROM storage.objects
    WHERE bucket_id = 'lab-reports'
      AND created_at < now() - interval '30 days';
END;
$$ LANGUAGE plpgsql SET search_path = '';

-- Schedule the cleanup to run daily at midnight (if pg_cron is enabled)
-- SELECT cron.schedule('cleanup-old-reports', '0 0 * * *', 'SELECT cleanup_old_reports()');
