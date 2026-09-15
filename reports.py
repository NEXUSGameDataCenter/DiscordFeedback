"""Deterministic counts, evidence ledger, approved facts, labelled AI hypotheses."""
import asyncio
import logging
from ai_analyzer import AIResponseError
from http_client import RemoteError
logger = logging.getLogger(__name__)
import time as clock
from collections import Counter, defaultdict
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from ai_analyzer import TOPICS, PROBLEM_TYPES


def safe(text):
    # User text cannot inject Discord mentions, headings or active Markdown links.
    text=str(text).replace('@','＠').replace('\n',' ').replace('\r',' ')
    for ch in '\\`*_~|<>[]#':
        text=text.replace(ch, '\\'+ch)
    return text

def source_ref(row):
    bits=[str(row.get(k) or '') for k in ('guild_id','channel_id','discord_msg_id')]
    if all(b.isdigit() for b in bits):
        return f'[ข้อความ {row["id"]}](https://discord.com/channels/{"/".join(bits)})'
    return f'หลักฐาน #{row["id"]} ({safe(row.get("source","import"))})'

def summarize(items):
    counts=Counter()
    groups=defaultdict(list)
    for row in items:
        if row['state']!='done' or not row.get('analysis'):
            counts['pending']+=1
            continue
        a=row['analysis']; disposition=a['disposition']
        counts[disposition]+=1
        if disposition!='non_issue':
            groups[a['topic']].append(row)
    return counts, groups

class ReportBuilder:
    def __init__(self, db, ai, tz='Asia/Bangkok', max_batch=20, max_total=1000,
                 time_budget=480, max_rows=10000, prompt_version='tosm-luna-v7'):
        self.db=db; self.ai=ai; self.tz=ZoneInfo(tz)
        self.max_batch=max_batch; self.max_total=max_total
        self.time_budget=time_budget; self.max_rows=max_rows; self.prompt_version=prompt_version
        self._lock=asyncio.Lock()

    async def normalize_pending(self, drain=True):
        async with self._lock:
            end=clock.monotonic()+self.time_budget
            total=0
            while total<self.max_total and clock.monotonic()<end:
                token,items=await self.db.claim(min(self.max_batch,self.max_total-total))
                if not items:
                    break
                from batch_processing import process_batch
                rows,failed,errors,fatal=await process_batch(items,self.ai.normalize_batch,end,'normalization')
                try:
                    if rows:total+=await self.db.complete(token,rows)
                except Exception:
                    await self.db.fail(token)
                    raise
                # complete clears successful row leases; fail touches remaining leases only.
                if failed:await self.db.fail(token)
                if errors:
                    logger.warning('Normalization incomplete: successful=%s failed=%s',len(rows),len(failed))
                    break
                if not drain:
                    break
            return total

    def _today_range_utc(self, ref=None):
        day=(ref or datetime.now(self.tz)).astimezone(self.tz).date()
        return self._range(day,day+timedelta(days=1),f'วันที่ {day:%d/%m/%Y}')

    def _range(self, start, end, label):
        return (datetime.combine(start,time.min,self.tz).astimezone(ZoneInfo('UTC')),
                datetime.combine(end,time.min,self.tz).astimezone(ZoneInfo('UTC')),label)

    def daily_range(self, yesterday=True):
        day=datetime.now(self.tz).date()-timedelta(days=int(yesterday))
        return self._range(day,day+timedelta(days=1),f'วันที่ {day:%d/%m/%Y}')

    def weekly_range(self):
        day=datetime.now(self.tz).date()
        monday=day-timedelta(days=day.weekday())
        start=monday-timedelta(days=7)
        return self._range(start,monday,f'สัปดาห์ {start:%d/%m/%Y}–{monday-timedelta(days=1):%d/%m/%Y}')

    async def build_daily(self,use_yesterday=True):
        return await self.build_report(*self.daily_range(use_yesterday))

    async def build_weekly(self):
        return await self.build_report(*self.weekly_range())

    async def build_report(self,start,end,label):
        from discussion_report import build_discussion_report
        return await build_discussion_report(self,start,end,label)
