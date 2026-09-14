"""Local durable outbound queue ONLY. Supabase remains the reporting database."""
import asyncio
import json
import sqlite3
from pathlib import Path
from datetime import datetime

class Outbox:
    def __init__(self,path='data/outbox.sqlite3'):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=asyncio.Lock()
        with sqlite3.connect(self.path) as con:
            con.execute('CREATE TABLE IF NOT EXISTS outbox (key TEXT PRIMARY KEY,payload TEXT NOT NULL)')

    async def put(self,row):
        copy=dict(row);copy['created_at']=row['created_at'].isoformat()
        def write():
            with sqlite3.connect(self.path) as con:
                con.execute('INSERT OR IGNORE INTO outbox VALUES (?,?)',
                            (row['discord_msg_id'],json.dumps(copy,ensure_ascii=False)))
        await asyncio.to_thread(write)

    async def flush(self,db,limit=500):
        async with self.lock:
            def read():
                with sqlite3.connect(self.path) as con:
                    return con.execute('SELECT key,payload FROM outbox ORDER BY rowid LIMIT ?', (limit,)).fetchall()
            rows=await asyncio.to_thread(read)
            for key,raw in rows:
                row=json.loads(raw);row['created_at']=datetime.fromisoformat(row['created_at'])
                await db.insert_feedback(**row)
                def delete():
                    with sqlite3.connect(self.path) as con:
                        con.execute('DELETE FROM outbox WHERE key=?',(key,))
                await asyncio.to_thread(delete)
            return len(rows)

    async def count(self):
        def read():
            with sqlite3.connect(self.path) as con:
                return con.execute('SELECT count(*) FROM outbox').fetchone()[0]
        return await asyncio.to_thread(read)
