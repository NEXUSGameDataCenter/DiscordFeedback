"""Offline regressions. All feedback is synthetic; no live credentials required."""
import ast,copy,json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from aiohttp import web
from ai_analyzer import AIAnalyzer,validate_classifications,validate_analysis
from database import Database
from http_client import JSONClient,RemoteError
from reports import ReportBuilder,summarize,safe
from migrate_data import load_feedback,load_knowledge
from spool import Outbox
ROOT=Path(__file__).resolve().parents[1]
START=datetime(2026,9,9,tzinfo=timezone.utc);END=START+timedelta(days=1)
def row(i=1,state='done',disposition='issue',topic='gacha',user='u1'):
 return dict(id=i,state=state,content='สุ่ม 850 ครั้งไม่ได้ตัวที่ต้องการ สงสัยว่า UID ถูกลดเรท',user_id=user,
 username='synthetic',guild_id='1',channel_id='2',discord_msg_id=str(i),source='discord',
 analysis=dict(id=i,disposition=disposition,topic=topic,kind='dissatisfaction',
 evidence_quote='สุ่ม 850 ครั้งไม่ได้ตัวที่ต้องการ',retention_signal=False))
def analysis(items):
 return dict(evidence_ids=[r['id'] for r in items],hypothesis='ความไม่พอใจอาจเกี่ยวกับความคาดหวังต่อผลสุ่ม ยังสรุปสาเหตุไม่ได้',
 next_steps=['CS ขอชื่อตู้และประวัติสุ่มเพื่อเทียบกติกาที่ทีมอนุมัติ'],knowledge_ids=[])
class ValidationTests(unittest.TestCase):
 def test_all_python_syntax(self):
  for p in ROOT.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
 def test_valid_classification(self):
  r=row();self.assertEqual(len(validate_classifications({'items':[r['analysis']]},[r])),1)
 def test_unknown_id_rejected(self):
  r=row();a=copy.deepcopy(r['analysis']);a['id']=999
  with self.assertRaises(ValueError):validate_classifications({'items':[a]},[r])
 def test_missing_and_duplicate_rejected(self):
  with self.assertRaises(ValueError):validate_classifications({'items':[]},[row()])
  with self.assertRaises(ValueError):validate_classifications({'items':[row()['analysis']]*2},[row(),row(2)])
 def test_invented_quote_rejected(self):
  r=row();a=copy.deepcopy(r['analysis']);a['evidence_quote']='มีบั๊กแน่นอน'
  with self.assertRaises(ValueError):validate_classifications({'items':[a]},[r])
 def test_short_thai_problem_preserved(self):
  r=row();r['content']='เด้ง';r['analysis']['evidence_quote']='เด้ง'
  self.assertEqual(validate_classifications({'items':[r['analysis']]},[r])[0]['disposition'],'issue')
 def test_unknown_disposition_rejected(self):
  r=row();r['analysis']['disposition']='confirmed_bug'
  with self.assertRaises(ValueError):validate_classifications({'items':[r['analysis']]},[r])
 def test_untrusted_extra_facts_removed(self):
  r=row();r['analysis']['confirmed_fact']='UID secretly manipulated'
  self.assertNotIn('confirmed_fact',validate_classifications({'items':[r['analysis']]},[r])[0])
 def test_analysis_missing_evidence_rejected(self):
  a=analysis([row()]);a['evidence_ids']=[]
  with self.assertRaises(ValueError):validate_analysis(a,[row()],[])
 def test_fabricated_knowledge_rejected(self):
  a=analysis([row()]);a['knowledge_ids']=['made-up']
  with self.assertRaises(ValueError):validate_analysis(a,[row()],[])
 def test_counts_and_pending(self):
  rows=[row(),row(2),row(3,disposition='uncertain'),row(4,state='failed'),row(5,disposition='non_issue')]
  counts,groups=summarize(rows)
  self.assertEqual(sum(counts.values()),5);self.assertEqual(counts['pending'],1);self.assertEqual(len(groups['gacha']),3)
 def test_mentions_escaped(self):
  self.assertNotIn('@everyone',safe('@everyone [link](x)\n# test'));self.assertNotIn('\n',safe('\n# fake fact'))
 def test_csv_utf8_and_dedup(self):
  import csv
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'sheet.csv'
   with p.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['id','time','user','content','cat','sentiment','severity','summary','tags','normalized'])
    for _ in range(2):w.writerow(['1',START.isoformat(),'ผู้เล่น','เด้ง','','','','','',''])
   data=load_feedback(p,'csv','old-sheet')
   self.assertEqual(len(data),1);self.assertEqual(data[0]['content'],'เด้ง');self.assertEqual(data[0]['user_id'],'')
 def test_sqlite_read_only_and_reclassifies(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'old.db'
   with sqlite3.connect(p) as c:
    c.execute('CREATE TABLE feedback(id integer,discord_msg_id text,user_id text,username text,channel_id text,content text,created_at text,summary text)')
    c.execute('INSERT INTO feedback VALUES(1,?,?,?,?,?,?,?)',('123','456','คน','789','เด้ง',START.isoformat(),'สรุปเดิมที่ผิด'))
   data=load_feedback(p,'sqlite',guild_id='111')
   self.assertEqual(data[0]['source_id'],'123');self.assertNotIn('summary',data[0])
 def test_knowledge_requires_provenance(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'kb.json';p.write_text(json.dumps([{'id':'x','fact':'invented'}]))
   with self.assertRaises(ValueError):load_knowledge(p)
class AsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_sonnet_wire_and_thinking_blocks(self):
  ai=AIAnalyzer('fake');ai.api.request=AsyncMock(return_value={'stop_reason':'end_turn','content':[
   {'type':'thinking','thinking':''},{'type':'text','text':'{"ok":true}'}]})
  self.assertEqual(await ai._json('test',{}),{'ok':True})
  request=ai.api.request.call_args.kwargs['payload'];self.assertEqual(request['model'],'claude-sonnet-5')
  for forbidden in ('temperature','top_p','top_k'):self.assertNotIn(forbidden,request)
  self.assertEqual(request['thinking'],{'type':'disabled'})
 async def test_truncated_json_rejected(self):
  ai=AIAnalyzer('fake');ai.api.request=AsyncMock(return_value={'stop_reason':'max_tokens','content':[{'type':'text','text':'{"ok":true}'}]})
  with self.assertRaises(ValueError):await ai._json('test',{})
 async def test_review_rejects(self):
  ai=AIAnalyzer('fake');ai._json=AsyncMock(side_effect=[analysis([row()]),{'approved':False}])
  with self.assertRaises(ValueError):await ai.analyze_topic('gacha',[row()],[])
 async def test_review_accepts(self):
  ai=AIAnalyzer('fake');ai._json=AsyncMock(side_effect=[analysis([row()]),{'approved':True}])
  self.assertEqual((await ai.analyze_topic('gacha',[row()],[]))['evidence_ids'],[1])
 async def test_more_than_40_all_evidence(self):
  rows=[row(i,user=str(i%3)) for i in range(1,56)]
  db=AsyncMock();db.snapshot.return_value={'total':55,'items':rows,'knowledge':[]}
  ai=AsyncMock();ai.model='claude-sonnet-5';ai.analyze_topic.side_effect=lambda topic,items,k:analysis(items)
  text,incomplete=await ReportBuilder(db,ai).build_report(START,END,'synthetic')
  ledger=db.save_report.call_args.args[4];ids=[i for a in ledger['groups']['gacha']['analyses'] for i in a['evidence_ids']]
  self.assertEqual(sorted(ids),list(range(1,56)));self.assertIn('55 ข้อความ / 3 ผู้แจ้ง',text)
  self.assertFalse(incomplete);self.assertIn('สมมติฐาน',text);self.assertIn('ยังไม่มีเอกสาร TOSM',text)
 async def test_failed_not_reported_as_no_issues(self):
  db=AsyncMock();db.snapshot.return_value={'total':1,'items':[row(state='failed')],'knowledge':[]}
  ai=AsyncMock();ai.model='claude-sonnet-5'
  text,incomplete=await ReportBuilder(db,ai).build_report(START,END,'synthetic')
  self.assertTrue(incomplete);self.assertNotIn('ไม่พบปัญหา',text)
 async def test_failure_keeps_counts_and_ledger(self):
  db=AsyncMock();db.snapshot.return_value={'total':1,'items':[row()],'knowledge':[]}
  ai=AsyncMock();ai.model='claude-sonnet-5';ai.analyze_topic.side_effect=ValueError('bad output')
  text,incomplete=await ReportBuilder(db,ai).build_report(START,END,'synthetic')
  self.assertTrue(incomplete);self.assertIn('1 ข้อความ / 1 ผู้แจ้ง',text)
  self.assertEqual(db.save_report.call_args.args[4]['groups']['gacha']['analysis_missing_ids'],[1])
 async def test_failure_releases_claim(self):
  db=AsyncMock();db.claim.return_value=('lease',[row()]);ai=AsyncMock();ai.normalize_batch.side_effect=ValueError('bad')
  self.assertEqual(await ReportBuilder(db,ai).normalize_pending(),0)
  db.fail.assert_awaited_once_with('lease');db.complete.assert_not_awaited()
 async def test_budget_caps_normalization(self):
  db=AsyncMock();db.claim.return_value=('lease',[row()]);db.complete.return_value=1
  ai=AsyncMock();ai.normalize_batch.return_value=[row()['analysis']]
  self.assertEqual(await ReportBuilder(db,ai,max_total=1).normalize_pending(),1);db.claim.assert_awaited_once_with(1)
 async def test_supabase_headers(self):
  db=Database('https://example.invalid','sb_secret_test');self.assertNotIn('Authorization',db.api.headers)
  legacy=Database('https://example.invalid','eyJfake');self.assertEqual(legacy.api.headers['Authorization'],'Bearer eyJfake')
 async def test_snapshot_cap_explicit(self):
  db=Database('https://example.invalid','fake');db.rpc=AsyncMock(return_value={'total':2,'items':[row()]})
  with self.assertRaises(ValueError):await db.snapshot(START,END,1)
 async def test_bangkok_boundary(self):
  b=ReportBuilder(AsyncMock(),AsyncMock());start,end,_=b._today_range_utc(datetime(2026,9,9,1,tzinfo=timezone.utc))
  self.assertEqual(start.isoformat(),'2026-09-08T17:00:00+00:00');self.assertEqual(end-start,timedelta(days=1))
 async def test_outbox_failure_restart(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'outbox.db';o=Outbox(path)
   message=dict(discord_msg_id='123',content='เด้ง',created_at=START)
   await o.put(message);await o.put(message);self.assertEqual(await o.count(),1)
   db=AsyncMock();db.insert_feedback.side_effect=RuntimeError('offline')
   with self.assertRaises(RuntimeError):await o.flush(db)
   self.assertEqual(await Outbox(path).count(),1);db.insert_feedback.side_effect=None
   await Outbox(path).flush(db);self.assertEqual(await o.count(),0)
 async def test_real_http_and_redaction(self):
  seen=[]
  async def handler(request):
   if request.path=='/bad':return web.Response(status=403,text='sensitive credential')
   seen.append(await request.json());return web.json_response({'ok':True})
  app=web.Application();app.router.add_post('/ok',handler);app.router.add_post('/bad',handler)
  runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
  port=site._server.sockets[0].getsockname()[1];client=JSONClient(f'http://127.0.0.1:{port}',{'apikey':'fake'},'test')
  try:
   self.assertEqual(await client.request('POST','/ok',payload={'ภาษา':'ไทย'}),{'ok':True});self.assertEqual(seen,[{'ภาษา':'ไทย'}])
   with self.assertRaises(RemoteError) as error:await client.request('POST','/bad')
   self.assertNotIn('sensitive',str(error.exception))
  finally:await client.close();await runner.cleanup()

class AdditionalRegressionTests(unittest.IsolatedAsyncioTestCase):
 async def test_only_supplied_approved_facts_are_rendered(self):
  fact=dict(id='known',topic='gacha',title='ข้อมูลทดสอบ',fact='เอกสารจำลองสำหรับทดสอบเท่านั้น',
   source_version='test',source_url='https://example.com/test',verified_by='test')
  db=AsyncMock();db.snapshot.return_value={'total':1,'items':[row()],'knowledge':[fact]}
  ai=AsyncMock();ai.model='claude-sonnet-5'
  a=analysis([row()]);a['knowledge_ids']=['known'];ai.analyze_topic.return_value=a
  text,_=await ReportBuilder(db,ai).build_report(START,END,'synthetic')
  self.assertIn(fact['fact'],text);self.assertIn(fact['source_url'],text)
 async def test_unknown_users_are_not_invented(self):
  db=AsyncMock();db.snapshot.return_value={'total':2,'items':[row(user=''),row(2,user='')],'knowledge':[]}
  ai=AsyncMock();ai.model='claude-sonnet-5';ai.analyze_topic.side_effect=lambda t,r,k:analysis(r)
  text,_=await ReportBuilder(db,ai).build_report(START,END,'synthetic')
  self.assertIn('0 ผู้แจ้งที่ระบุ ID ได้',text);self.assertIn('2 ข้อความไม่ทราบ ID',text)
 async def test_headerless_csv_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'file.csv';p.write_text('1,2026-09-09,u,test,,,,,,\n')
   with self.assertRaises(ValueError):load_feedback(p,'csv','dataset')
 async def test_database_save_failure_not_reported_as_success(self):
  db=AsyncMock();db.snapshot.return_value={'total':0,'items':[],'knowledge':[]}
  db.save_report.side_effect=RuntimeError('offline');ai=AsyncMock();ai.model='claude-sonnet-5'
  with self.assertRaises(RuntimeError):await ReportBuilder(db,ai).build_report(START,END,'synthetic')

if __name__=='__main__':unittest.main()
