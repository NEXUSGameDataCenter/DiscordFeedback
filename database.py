"""Supabase is the source of truth. Server-only REST API; transactional RPCs."""
from datetime import datetime, timezone
from uuid import uuid4
from http_client import JSONClient

def iso(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('A timezone-aware datetime is required')
    return value.astimezone(timezone.utc).isoformat()

class Database:
    def __init__(self, url, key):
        headers = {'apikey': key, 'Content-Type': 'application/json'}
        # New sb_secret keys go in apikey; legacy service_role JWT also needs Bearer.
        if key.startswith('eyJ'):
            headers['Authorization'] = 'Bearer ' + key
        self.api = JSONClient(url + '/rest/v1', headers, 'Supabase')

    async def close(self):
        await self.api.close()

    async def rpc(self, name, payload=None, retry=False):
        return await self.api.request('POST', '/rpc/' + name, payload=payload or {}, retry=retry)

    async def init(self):
        value = await self.rpc('tosm_health', retry=True)
        if value != 'tosm-v7':
            raise RuntimeError('Install the supplied schema.sql before starting this bot')

    async def insert_feedback(self, discord_msg_id, user_id, username, channel_id, content, created_at,
                              guild_id='', source='discord', source_id=None):
        row = dict(source=source, source_id=source_id or discord_msg_id,
                   discord_msg_id=discord_msg_id or None, user_id=user_id or '', username=username,
                   channel_id=channel_id or '', guild_id=guild_id or '', content=content,
                   created_at=iso(created_at))
        await self.api.request('POST', '/tosm_feedback', params={'on_conflict': 'source,source_id'},
            payload=row, headers={'Prefer': 'resolution=ignore-duplicates,return=minimal'}, retry=True)

    async def claim(self, limit):
        token = str(uuid4())
        rows = await self.rpc('tosm_claim', {'p_token': token, 'p_limit': limit})
        return token, rows

    async def complete(self, token, rows):
        return await self.rpc('tosm_complete', {'p_token': token, 'p_results': rows})

    async def fail(self, token):
        await self.rpc('tosm_fail', {'p_token': token}, retry=True)

    async def reset_normalized(self, all_rows=False):
        return await self.rpc('tosm_reset', {'p_all': all_rows})

    async def snapshot(self, start, end, max_rows=10000):
        if end <= start:
            raise ValueError('End must be later than start')
        result = await self.rpc('tosm_snapshot', {'p_start': iso(start), 'p_end': iso(end),
                                                 'p_limit': max_rows}, retry=True)
        if result['total'] > len(result['items']):
            raise ValueError('ช่วงนี้มีข้อความเกินเพดานรายงาน โปรดเลือกช่วงวันที่สั้นลง')
        return result

    async def save_report(self, start, end, label, text, ledger, model, prompt_version, incomplete):
        # Same period/model/prompt replaces only the matching report; no duplicate history row on retry.
        row = dict(period_start=iso(start), period_end=iso(end), label=label, report_text=text,
                   evidence=ledger, model=model, prompt_version=prompt_version,
                   incomplete=incomplete, updated_at=datetime.now(timezone.utc).isoformat())
        await self.api.request('POST', '/tosm_reports',
            params={'on_conflict': 'period_start,period_end,model,prompt_version'}, payload=row,
            headers={'Prefer': 'resolution=merge-duplicates,return=minimal'}, retry=True)

    async def import_knowledge(self, rows):
        await self.api.request('POST', '/tosm_knowledge', params={'on_conflict': 'id'}, payload=rows,
            headers={'Prefer': 'resolution=merge-duplicates,return=minimal'}, retry=True)

    async def acquire_job(self, key, owner):
        return await self.rpc('tosm_acquire_job', {'p_key': key, 'p_owner': owner})

    async def finish_job(self, key, owner, success):
        await self.rpc('tosm_finish_job', {'p_key': key, 'p_owner': owner, 'p_success': success})
