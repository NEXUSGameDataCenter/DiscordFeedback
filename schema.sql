-- Bootstrap for Supabase SQL Editor. Atomic and rerunnable; never drops user data.
-- All objects are namespaced tosm_*. Apply using a database owner.
BEGIN;
CREATE TABLE IF NOT EXISTS public.tosm_feedback (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source text NOT NULL DEFAULT 'discord', source_id text NOT NULL,
 discord_msg_id text, guild_id text NOT NULL DEFAULT '', channel_id text NOT NULL DEFAULT '',
 user_id text NOT NULL DEFAULT '', username text NOT NULL, content text NOT NULL,
 created_at timestamptz NOT NULL, inserted_at timestamptz NOT NULL DEFAULT now(),
 analysis jsonb, normalized_at timestamptz,
 state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','done','failed')),
 lease_token uuid, lease_until timestamptz, attempts integer NOT NULL DEFAULT 0,
 UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS tosm_feedback_period ON public.tosm_feedback(created_at,id);
CREATE INDEX IF NOT EXISTS tosm_feedback_pending ON public.tosm_feedback(created_at,id)
 WHERE state <> 'done';
CREATE TABLE IF NOT EXISTS public.tosm_knowledge (
 id text PRIMARY KEY, topic text NOT NULL, title text NOT NULL, fact text NOT NULL,
 source_url text NOT NULL, source_version text NOT NULL,
 valid_from timestamptz NOT NULL, valid_to timestamptz,
 verified_by text NOT NULL, verified_at timestamptz NOT NULL,
 approved boolean NOT NULL DEFAULT false,
 CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE TABLE IF NOT EXISTS public.tosm_reports (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
 label text NOT NULL, report_text text NOT NULL, evidence jsonb NOT NULL,
 model text NOT NULL, prompt_version text NOT NULL, incomplete boolean NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (period_end > period_start),
 UNIQUE(period_start,period_end,model,prompt_version)
);
CREATE TABLE IF NOT EXISTS public.tosm_jobs (
 key text PRIMARY KEY, owner uuid NOT NULL, lease_until timestamptz NOT NULL,
 completed boolean NOT NULL DEFAULT false
);
ALTER TABLE public.tosm_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tosm_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tosm_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tosm_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.tosm_feedback,public.tosm_knowledge,public.tosm_reports,public.tosm_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.tosm_feedback,public.tosm_knowledge,public.tosm_reports,public.tosm_jobs TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.tosm_feedback_id_seq,public.tosm_reports_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.tosm_health() RETURNS text
 LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT 'tosm-v7'::text $$;

CREATE OR REPLACE FUNCTION public.tosm_claim(p_token uuid,p_limit integer)
 RETURNS SETOF public.tosm_feedback LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 WITH selected AS (
  SELECT id FROM public.tosm_feedback
  WHERE (state='pending' OR (state='processing' AND lease_until < now())) AND attempts < 5
  ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT greatest(1,least(p_limit,50))
 )
 UPDATE public.tosm_feedback f SET state='processing',lease_token=p_token,
   lease_until=now()+interval '25 minutes',attempts=attempts+1
 FROM selected s WHERE f.id=s.id RETURNING f.*
$$;

CREATE OR REPLACE FUNCTION public.tosm_complete(p_token uuid,p_results jsonb)
 RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
 DECLARE n integer;
 BEGIN
  IF jsonb_typeof(p_results)<>'array' THEN RAISE EXCEPTION 'Expected array'; END IF;
  WITH result AS (SELECT value AS v FROM jsonb_array_elements(p_results)), updated AS (
   UPDATE public.tosm_feedback f SET analysis=r.v,state='done',normalized_at=now(),
    lease_token=NULL,lease_until=NULL
   FROM result r WHERE f.id=(r.v->>'id')::bigint AND f.lease_token=p_token
    AND f.state='processing' AND f.lease_until>now()
   RETURNING f.id
  ) SELECT count(*) INTO n FROM updated;
  RETURN n;
 END $$;

CREATE OR REPLACE FUNCTION public.tosm_fail(p_token uuid) RETURNS void
 LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 UPDATE public.tosm_feedback SET state='failed',lease_token=NULL,lease_until=NULL
 WHERE lease_token=p_token AND state='processing'
$$;
CREATE OR REPLACE FUNCTION public.tosm_reset(p_all boolean DEFAULT false) RETURNS integer
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
 DECLARE n integer;
 BEGIN
  UPDATE public.tosm_feedback SET state='pending',analysis=NULL,normalized_at=NULL,
   lease_token=NULL,lease_until=NULL,attempts=0
  WHERE (p_all OR state='failed' OR (state<>'done' AND attempts>=5))
   AND (state<>'processing' OR lease_until<now());
  GET DIAGNOSTICS n=ROW_COUNT; RETURN n;
 END $$;

CREATE OR REPLACE FUNCTION public.tosm_snapshot(p_start timestamptz,p_end timestamptz,p_limit integer DEFAULT 10000)
 RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object(
  'total',(SELECT count(*) FROM public.tosm_feedback WHERE created_at>=p_start AND created_at<p_end),
  'items',coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY t.created_at,t.id) FROM (
    SELECT * FROM public.tosm_feedback WHERE created_at>=p_start AND created_at<p_end
    ORDER BY created_at,id LIMIT greatest(1,least(p_limit,10000))
  ) t),'[]'::jsonb),
  'knowledge',coalesce((SELECT jsonb_agg(to_jsonb(k) ORDER BY k.id) FROM public.tosm_knowledge k
   WHERE approved AND valid_from<=p_start AND (valid_to IS NULL OR valid_to>=p_end)), '[]'::jsonb)
 ) $$;

CREATE OR REPLACE FUNCTION public.tosm_acquire_job(p_key text,p_owner uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
 DECLARE n integer;
 BEGIN
  INSERT INTO public.tosm_jobs(key,owner,lease_until) VALUES(p_key,p_owner,now()+interval '60 minutes')
  ON CONFLICT(key) DO UPDATE SET owner=excluded.owner,lease_until=excluded.lease_until
  WHERE NOT public.tosm_jobs.completed AND public.tosm_jobs.lease_until<now();
  GET DIAGNOSTICS n=ROW_COUNT; RETURN n=1;
 END $$;
CREATE OR REPLACE FUNCTION public.tosm_finish_job(p_key text,p_owner uuid,p_success boolean) RETURNS void
 LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 UPDATE public.tosm_jobs SET completed=p_success,lease_until=now()
 WHERE key=p_key AND owner=p_owner
$$;
REVOKE ALL ON FUNCTION public.tosm_health(),public.tosm_claim(uuid,integer),public.tosm_complete(uuid,jsonb),
 public.tosm_fail(uuid),public.tosm_reset(boolean),public.tosm_snapshot(timestamptz,timestamptz,integer),
 public.tosm_acquire_job(text,uuid),public.tosm_finish_job(text,uuid,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.tosm_health(),public.tosm_claim(uuid,integer),public.tosm_complete(uuid,jsonb),
 public.tosm_fail(uuid),public.tosm_reset(boolean),public.tosm_snapshot(timestamptz,timestamptz,integer),
 public.tosm_acquire_job(text,uuid),public.tosm_finish_job(text,uuid,boolean) TO service_role;
NOTIFY pgrst, 'reload schema';
COMMIT;
