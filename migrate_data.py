"""Validate first, then idempotently import SQLite or original 10/11-column Sheets CSV."""
import argparse
import asyncio
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse


def parse_date(value,tz='UTC'):
    value=str(value).strip().replace('Z','+00:00')
    dt=datetime.fromisoformat(value)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc)


def load_feedback(path,kind,dataset='',tz='UTC',guild_id=''):
    if kind=='sqlite':
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as con:
            con.row_factory=sqlite3.Row
            raw=[dict(r) for r in con.execute('SELECT * FROM feedback ORDER BY id')]
    else:
        if not dataset:raise ValueError('--dataset is required for CSV; reuse same name on reruns')
        with open(path,encoding='utf-8-sig',newline='') as f:
            rows=list(csv.reader(f))
        if not rows or len(rows[0]) not in (10,11) or rows[0][0].strip().lower() not in ('id','รหัส','ลำดับ'):
            raise ValueError('CSV must include the original header row starting with ID')
        raw=[]
        for row in rows[1:]:
            if not row or all(not x.strip() for x in row):continue
            if len(row) not in (10,11):raise ValueError('CSV must have original Sheets 10 or 11 columns')
            # Original sheets.py order: id,time,username,content,category,sentiment,severity,summary,tags,normalized_at[,is_issue]
            raw.append(dict(id=row[0],created_at=row[1],username=row[2],content=row[3]))
    result=[];seen={}
    for r in raw:
        if not r.get('content') or not str(r.get('id','')).strip():
            raise ValueError('Missing content or source id')
        msg=str(r.get('discord_msg_id') or '')
        row=dict(discord_msg_id=msg,user_id=str(r.get('user_id') or ''),
            username=str(r.get('username') or ''),channel_id=str(r.get('channel_id') or ''),
            guild_id=str(r.get('guild_id') or guild_id),content=r['content'],
            created_at=parse_date(r['created_at'],tz),
            source='discord' if msg else 'import',
            source_id=msg or f'{dataset or Path(path).name}:{r["id"]}')
        key=(row['source'],row['source_id'])
        if key in seen and seen[key]!=row:raise ValueError('Conflicting duplicate source id in input')
        if key not in seen:result.append(row)
        seen[key]=row
    return result


def load_knowledge(path):
    rows=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    required=('id','topic','title','fact','source_url','source_version','valid_from','verified_by','verified_at')
    if not isinstance(rows,list):raise ValueError('Knowledge must be a JSON array')
    seen=set()
    from ai_analyzer import TOPICS
    for row in rows:
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k].strip() for k in required):
            raise ValueError('Knowledge is missing required provenance fields')
        if row['id'] in seen:raise ValueError('Duplicate knowledge id')
        seen.add(row['id'])
        if row['topic'] not in {*TOPICS,'all'}:raise ValueError('Invalid knowledge topic')
        if row.get('approved') is not True:raise ValueError('Only explicitly approved knowledge can be imported')
        url=urlparse(row['source_url'])
        if url.scheme!='https' or not url.netloc or any(x in row['source_url'] for x in '\n\r<> '):
            raise ValueError('Knowledge source must be an HTTPS URL')
        start=parse_date(row['valid_from']);parse_date(row['verified_at'])
        if row.get('valid_to') and parse_date(row['valid_to'])<=start:raise ValueError('Invalid validity interval')
    return rows

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['sqlite','csv','knowledge'])
    parser.add_argument('path');parser.add_argument('--dataset',default='')
    parser.add_argument('--source-timezone',default='UTC')
    parser.add_argument('--guild-id',default='')
    parser.add_argument('--apply',action='store_true',help='Write after full local validation; default is dry run')
    args=parser.parse_args()
    rows=load_knowledge(args.path) if args.kind=='knowledge' else load_feedback(
        args.path,args.kind,args.dataset,args.source_timezone,args.guild_id)
    print(f'Validated {len(rows)} records. '+('Applying.' if args.apply else 'Dry run: no writes. Add --apply to import.'))
    if not args.apply or not rows:return
    import config
    from database import Database
    config.validate(database_only=True)
    db=Database(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY)
    try:
        await db.init()
        if args.kind=='knowledge':
            for offset in range(0,len(rows),100):await db.import_knowledge(rows[offset:offset+100])
        else:
            for row in rows:
                await db.insert_feedback(**row)
                saved=await db.api.request('GET','/tosm_feedback',params={
                    'source':'eq.'+row['source'],'source_id':'eq.'+row['source_id'],
                    'select':'content,created_at'},retry=True)
                if len(saved)!=1 or saved[0]['content']!=row['content'] or parse_date(saved[0]['created_at'])!=row['created_at']:
                    raise RuntimeError('Existing source id has different data; import stopped, source untouched')
        print(f'Completed {len(rows)} records (existing identical messages are skipped).')
    finally:await db.close()

if __name__=='__main__':asyncio.run(main())
