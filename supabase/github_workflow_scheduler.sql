-- ═══════════════════════════════════════════════════════════════════════════
-- GitHub workflow scheduler (APPLIED to Supabase project wtvgkuuktgrufsozirju)
-- Fires daily_shorts.yml at 18:00 UTC (11:30 PM IST) via workflow_dispatch.
--
-- The GitHub PAT lives in Supabase Vault under the name 'github_pat_shorts'.
-- It is NEVER stored in this file, the repo, or migration history.
-- To (re)set it, run ONCE in the Supabase SQL editor:
--
--   SELECT vault.create_secret('<YOUR_PAT_HERE>', 'github_pat_shorts');
--
-- PAT expiry: fine-grained PATs max out at 1 year. When it expires the log
-- table shows http_status 401 — create a new PAT and run create_secret again
-- (the trigger function always reads the newest secret with that name).
--
-- Verify last 7 nights:
--   SELECT triggered_at, http_status, response_body
--   FROM github_trigger_log ORDER BY id DESC LIMIT 7;
--   -- 204 = success (GitHub returns "204 No Content" for dispatches)
--
-- Fire immediately for testing:
--   SELECT public.trigger_daily_shorts();   -- wait ~20s, then:
--   SELECT public.sync_trigger_log();
--   SELECT * FROM github_trigger_log ORDER BY id DESC LIMIT 1;
-- ═══════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

CREATE TABLE IF NOT EXISTS public.github_trigger_log (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  triggered_at  timestamptz NOT NULL DEFAULT now(),
  request_id    bigint,
  http_status   int,          -- 204 success | 401 PAT expired | 404 bad scope
  response_body text
);
ALTER TABLE public.github_trigger_log ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.trigger_daily_shorts()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
  gh_pat text;
  req_id bigint;
BEGIN
  SELECT decrypted_secret INTO gh_pat
  FROM vault.decrypted_secrets
  WHERE name = 'github_pat_shorts'
  ORDER BY created_at DESC
  LIMIT 1;

  IF gh_pat IS NULL THEN
    INSERT INTO public.github_trigger_log (http_status, response_body)
    VALUES (0, 'ERROR: secret github_pat_shorts not found in Vault');
    RETURN NULL;
  END IF;

  SELECT net.http_post(
    url     := 'https://api.github.com/repos/ranga8885299922/astroverse-auto-shorts/actions/workflows/daily_shorts.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization',        'Bearer ' || gh_pat,
      'Accept',               'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent',           'supabase-cron',
      'Content-Type',         'application/json'
    ),
    body    := '{"ref": "main"}'::jsonb,
    timeout_milliseconds := 15000
  ) INTO req_id;

  INSERT INTO public.github_trigger_log (request_id) VALUES (req_id);
  RETURN req_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION public.sync_trigger_log()
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
  n int;
BEGIN
  UPDATE public.github_trigger_log l
  SET http_status   = r.status_code,
      response_body = left(coalesce(r.content::text, coalesce(r.error_msg, '')), 500)
  FROM net._http_response r
  WHERE l.request_id = r.id
    AND l.http_status IS NULL;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END;
$fn$;

REVOKE EXECUTE ON FUNCTION public.trigger_daily_shorts() FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.sync_trigger_log()    FROM anon, authenticated;

DO $$ BEGIN PERFORM cron.unschedule('github-daily-shorts-trigger'); EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN PERFORM cron.unschedule('github-daily-shorts-logsync'); EXCEPTION WHEN OTHERS THEN NULL; END $$;

SELECT cron.schedule('github-daily-shorts-trigger', '0 18 * * *',
                     $$SELECT public.trigger_daily_shorts();$$);
SELECT cron.schedule('github-daily-shorts-logsync', '5 18 * * *',
                     $$SELECT public.sync_trigger_log();$$);
