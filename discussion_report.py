"""Evidence-covered subtopics across legacy categories, with deterministic counts."""
import asyncio
import logging
import time
from ai_analyzer import PROBLEM_TYPES

ISSUE_PROMPT = '''สรุปบทสนทนาผู้เล่นเป็นประเด็นย่อย ไม่ใช้หมวดเก่าเป็นขอบเขต
ตอบ {"issues":[{"title":"หัวข้อชัดเจนไม่เกิน 90 ตัวอักษร", "evidence_ids":[1],
"problem_type":"technical|economy|reward|balance|content|usability|social|service|expectation|unclear",
"discussion":"ผู้เล่นพูดอะไร 1-2 ประโยค ไม่เกิน 320 ตัวอักษร",
"knowledge_ids":[]}]}
ทุกข้อความต้องอยู่หนึ่งประเด็นหลักพอดี ห้ามตกหล่นหรือซ้ำ เลือกประเด็นหลักเมื่อข้อความมีหลายเรื่อง
แยกการอัปเดต การแปลภาษา การเข้า Total War และฟังก์ชัน launcher เป็นคนละประเด็น
รวมคำรายงานเรื่องรางวัลกิจกรรมเดียวกัน แต่แยกต่างกิจกรรมหรือคนละเงื่อนไขเมื่อจำเป็น
หัวข้อบอกสิ่งที่เกิดขึ้น เช่น รางวัลล่าบอส — สงสัยเงื่อนไขรับรางวัล ห้ามหัวข้อ อื่นๆ หรือ ต้องตรวจรายละเอียด
คำถามบอกได้แค่ว่าผู้เล่นสงสัย ไม่ใช่หลักฐานว่าคำอธิบายในเกมไม่ชัด
ข้อเสนอให้นำกิจกรรมลดต้นทุนกลับมา ไม่เท่ากับผู้เล่นยืนยันว่าต้นทุนสูง
ห้ามเดาคำย่อ/ชื่อไอเทม ถ้าไม่ทราบใช้คำเดิมและบอกสั้นๆ ว่าชื่อจากผู้เล่น ยังระบุไม่ได้
สรุปเฉพาะสิ่งที่ผู้เล่นกล่าว ไม่เขียนข้อวิเคราะห์หรือผลกระทบในแต่ละประเด็น
ผลกระทบที่ผู้เล่นไม่ได้ระบุใช้ อาจ ห้ามยืนยันสาเหตุ กลไก บั๊ก หรือความรู้สึกที่ไม่ได้กล่าว
ไม่เสนอแผนงาน ทีมที่รับผิดชอบ หรือคำแนะนำให้ทีมทำต่อ ไม่ใส่จำนวนหรือระดับความรุนแรงเอง
knowledge_ids ใช้เฉพาะเอกสารอนุมัติที่เกี่ยวกับประเด็นและเวอร์ชันตรงกัน'''
REVIEW_PROMPT = '''ตรวจหลักฐานและข้อสรุป ตอบ {"approved":true|false,"reasons":["unsupported_claim|mixed_topics|repetition|team_actions|unknown_abbreviation"]}
ให้ false หากแต่งข้อเท็จจริง ความรู้สึก จำนวน ผลกระทบ หรือความหมายคำย่อ
ห้ามตีความคำถามว่าเกมอธิบายไม่ชัดโดยไม่มีหลักฐาน หรือข้อเสนอลดต้นทุนว่าผู้เล่นบอกต้นทุนสูง
ห้ามยืนยันบั๊ก/สาเหตุ/กลไกเกมจากคำร้องเรียน ห้ามคำแนะนำหรือสิ่งที่ทีมควรทำต่อ
ตรวจตามรูปแบบที่ร้องขอ: สรุปย่อยมีเฉพาะคำกล่าวผู้เล่น ไม่ต้องมีข้อวิเคราะห์; รายงานรวมมีข้อวิเคราะห์ภาพรวมครั้งเดียว อนุญาตรวมหลายประเด็นเป็นบูลเล็ตในหมวดหลัก แต่ห้ามอ้างว่ามีสาเหตุเดียวกัน'''
MERGE_PROMPT = '''รวมประเด็นซ้ำจากทุกชุดให้เป็นรายงานเดียว ไม่แบ่งตามหมวดเก่าหรือชุดประมวลผล
ตอบ {"issues":[{"candidate_ids":[0,1],"title":"ไม่เกิน 90 ตัวอักษร",
"problem_type":"technical|economy|reward|balance|content|usability|social|service|expectation|unclear",
"discussion":"ไม่เกิน 320 ตัวอักษร","analysis":"ไม่เกิน 350 ตัวอักษร"}]}
ทุก candidate_id ต้องอยู่หนึ่งกลุ่มพอดี ห้ามตกหล่น/ซ้ำ รวมเฉพาะประเด็นเดียวกันจริง
ต่างกิจกรรม ต่างอาการ หรือคนละเงื่อนไขให้แยก แม้อยู่ระบบเดียวกัน
เช่น การแปล กับ ปล่อยแพตช์ช้า กับ เข้าโหมดไม่ได้ ต้องแยก
ใช้หัวข้อเฉพาะเรื่อง ห้าม อื่นๆ หรือ ต้องตรวจรายละเอียด
คงข้อเท็จจริงและความไม่แน่นอนจากต้นทาง ห้ามเดาคำย่อ เพิ่มกลไก จำนวน ความรู้สึก สาเหตุ หรือคำแนะนำ
ข้อวิเคราะห์อธิบายประเด็นเกมออนไลน์และผลที่อาจเกิดขึ้นอย่างกระชับ ไม่ทวนสิ่งที่ผู้เล่นพูด'''


class DiscussionError(ValueError):
    def __init__(self,code,detail=""):
        self.code=code
        self.detail=detail
        super().__init__('Discussion analysis: '+code+(' ('+detail+')' if detail else ''))


def failure_code(exc):
    from ai_analyzer import AIResponseError
    from http_client import RemoteError
    if isinstance(exc,DiscussionError):return exc.code
    if isinstance(exc,RemoteError):return 'http_'+str(exc.status)
    if isinstance(exc,AIResponseError):return 'ai_response_invalid'
    if isinstance(exc,TimeoutError):return 'timeout'
    if isinstance(exc,(AttributeError,ImportError)):return 'version_mismatch'
    if isinstance(exc,ValueError):return 'schema_invalid'
    return 'connection_or_internal_error'

ERROR_LABELS={
 'schema_invalid':'รูปแบบคำตอบหรือรายการหลักฐานไม่ผ่านเงื่อนไข',
 'review_rejected':'ข้อวิเคราะห์ไม่ผ่านการตรวจเทียบหลักฐานหลังลองแก้แล้ว',
 'ai_response_invalid':'AI ส่งคำตอบว่าง ไม่ครบ หรือ JSON ใช้งานไม่ได้',
 'timeout':'หมดเวลารอคำตอบหรือเกินเวลาสร้างรายงาน',
 'version_mismatch':'ไฟล์โปรแกรมอาจเป็นคนละรุ่นหรือขาดไฟล์',
 'connection_or_internal_error':'การเชื่อมต่อหรือโปรแกรมผิดพลาด ต้องตรวจ log',
 'http_400':'API ไม่รับรูปแบบคำขอหรือการตั้งค่า',
 'http_401':'API key ไม่ผ่านการยืนยัน',
 'http_403':'ไม่มีสิทธิ์เรียก API หรือโมเดลนี้',
 'http_404':'API ไม่พบปลายทางหรือโมเดลที่ตั้งไว้',
 'http_429':'API จำกัดการใช้งาน',
}


def _text_fields(issue):
    if not isinstance(issue,dict): raise ValueError('Invalid issue')
    clean={}
    for key,limit in [('title',90),('discussion',320)]:
        value=issue.get(key)
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise ValueError('Invalid issue '+key)
        clean[key]=value.strip()
    kind=issue.get('problem_type')
    if not isinstance(kind,str) or kind not in PROBLEM_TYPES: raise ValueError('Invalid issue type')
    clean['problem_type']=kind
    return clean


def _partition(values,expected):
    if any(type(i) is not int for i in values) or len(values)!=len(set(values)) or set(values)!=expected:
        raise ValueError('Missing, duplicate or unknown evidence')


def validate_issues(result,items,knowledge):
    issues=result.get('issues') if isinstance(result,dict) else None
    if not isinstance(issues,list) or not issues: raise ValueError('Missing issues')
    output=[];all_ids=[];known={k['id'] for k in knowledge}
    for issue in issues:
        clean=_text_fields(issue);ids=issue.get('evidence_ids');refs=issue.get('knowledge_ids')
        if not isinstance(ids,list) or not ids: raise ValueError('Missing evidence')
        if not isinstance(refs,list) or any(not isinstance(k,str) or k not in known for k in refs):
            raise ValueError('Unknown knowledge')
        all_ids.extend(ids);clean.update(evidence_ids=ids,knowledge_ids=refs);output.append(clean)
    _partition(all_ids,{r['id'] for r in items})
    return output


def validate_merge(result,candidates):
    issues=result.get('issues') if isinstance(result,dict) else None
    if not isinstance(issues,list) or not issues: raise ValueError('Missing merged issues')
    all_ids=[];output=[]
    for issue in issues:
        clean=_text_fields(issue);ids=issue.get('candidate_ids')
        if not isinstance(ids,list) or not ids or any(type(i) is not int or not 0<=i<len(candidates) for i in ids):
            raise ValueError('Invalid candidate ids')
        all_ids.extend(ids)
        clean['evidence_ids']=sorted({e for i in ids for e in candidates[i]['evidence_ids']})
        clean['knowledge_ids']=sorted({k for i in ids for k in candidates[i]['knowledge_ids']})
        output.append(clean)
    _partition(all_ids,set(range(len(candidates))))
    return output


def render_discussions(label,items,counts,ledger):
    from grouped_report import render_grouped
    return render_grouped(label,items,counts,ledger)


async def build_discussion_report(builder,start,end,label):
    from reports import summarize,source_ref
    snapshot=await builder.db.snapshot(start,end,builder.max_rows)
    items=snapshot['items'];knowledge=snapshot['knowledge'];counts,_=summarize(items)
    relevant=[r for r in items if r['state']=='done' and r.get('analysis') and r['analysis']['disposition']!='non_issue']
    ledger={'counts':dict(counts),'total_messages':len(items),'source_ids':[r['id'] for r in items],
            'knowledge_snapshot':knowledge,'sources':[dict(id=r['id'],content=r['content'],reference=source_ref(r)) for r in relevant],
            'issues':[],'analysis_missing_ids':[],'merge_incomplete':False,'errors':[]}
    deadline=time.monotonic()+builder.time_budget;candidates=[]
    for offset in range(0,len(relevant),20):
        batch=relevant[offset:offset+20]
        if time.monotonic()>=deadline:
            ledger['analysis_missing_ids'].extend(r['id'] for r in relevant[offset:])
            ledger['errors'].append({'stage':'analysis','code':'timeout'});break
        from batch_processing import process_batch
        values,failed,errors,fatal=await process_batch(batch,
            lambda rows:builder.ai.analyze_discussions(rows,knowledge),deadline,'discussion')
        candidates.extend(values)
        ledger['analysis_missing_ids'].extend(failed)
        ledger['errors'].extend(errors)
        if fatal:
            ledger['analysis_missing_ids'].extend(r['id'] for r in relevant[offset+20:])
            break
    ledger['batch_issues']=candidates
    ledger['issues']=candidates
    if candidates:
        try:
            if time.monotonic()>=deadline:raise TimeoutError()
            if len(candidates)>500:raise ValueError('Summary budget exceeded')
            async with asyncio.timeout(max(0.01,deadline-time.monotonic())):
                ledger['digest']=await builder.ai.summarize_overall(candidates,
                    {'total':len(items),'pending_classification':counts['pending'],
                     'pending_extraction':len(ledger['analysis_missing_ids'])})
        except Exception as exc:
            code=failure_code(exc)
            logging.getLogger(__name__).warning('Overall summary failed: code=%s',code)
            ledger['errors'].append({'stage':'overall','code':code})
            ledger['merge_incomplete']=True
    incomplete=bool(counts['pending'] or ledger['analysis_missing_ids'] or ledger['merge_incomplete'])
    text=render_discussions(label,items,counts,ledger)
    await builder.db.save_report(start,end,label,text,ledger,builder.ai.model,builder.prompt_version,incomplete)
    return text,incomplete
