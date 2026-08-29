-- Create a table to persist WhatsApp agent memory across server restarts
CREATE TABLE IF NOT EXISTS public.whatsapp_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_key TEXT NOT NULL UNIQUE,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- RLS policies
ALTER TABLE public.whatsapp_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable read/write for authenticated users" 
ON public.whatsapp_sessions 
FOR ALL 
TO authenticated 
USING (true) 
WITH CHECK (true);

CREATE POLICY "Enable read/write for service role" 
ON public.whatsapp_sessions 
FOR ALL 
TO service_role 
USING (true) 
WITH CHECK (true);
