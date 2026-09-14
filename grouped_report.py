"""Five main sections, evidence-based counts and one overall analysis."""
CATEGORIES={
 'technical':'การเข้าเกมและอาการขัดข้อง',
 'language':'การแปลและคำอธิบายในเกม',
 'rewards':'รางวัลกิจกรรมและการชดเชย',
 'economy':'ร้านค้า ผลสุ่ม และความคุ้มค่า',
 'questions':'คำถามและข้อเสนอแนะทั่วไป',
}
DIGEST_PROMPT='''จัดรายงานเป็นหมวดหลักและวิเคราะห์ภาพรวมเพียงครั้งเดียว
ตอบ {"groups":[{"category":"technical|language|rewards|economy|questions",
"candidate_ids":[0,1],"bullets":["สรุปสิ่งที่ผู้เล่นกล่าว ไม่เกิน 280 ตัวอักษรต่อบูลเล็ต"]}],
"unresolved_candidate_ids":[],"overall_analysis":"บทวิเคราะห์ภาพรวมหนึ่งย่อหน้า 3-5 ประโยค ไม่เกิน 900 ตัวอักษร"}
แต่ละหมวดปรากฏได้ครั้งเดียว ไม่เกิน 5 หมวด เฉพาะหมวดที่มีข้อมูล หมวดละ 1-4 บูลเล็ต
ทุก candidate_id ต้องอยู่ในหมวดหนึ่งหรือ unresolved_candidate_ids พอดี ห้ามซ้ำหรือตกหล่น
technical=เข้าเกม/แพตช์/อาการขัดข้อง; language=คำแปล; rewards=รางวัลกิจกรรมและชดเชย;
economy=ร้านค้า/ผลสุ่ม/ความคุ้มค่า; questions=คำถามกลไกและข้อเสนอทั่วไป
เรื่องเดียวกันให้รวมในบูลเล็ตเดียว เช่น การแปลที่กระจายหลายชุด การ์ดอวยพร หรือชดเชยหยดน้ำ
ถ้าต้นทางปนหลายเรื่อง เลือกหมวดหลักเดียว บูลเล็ตยังคงรายละเอียดรองที่จำเป็น ห้ามนับซ้ำ
บูลเล็ตมีแต่สรุปคำกล่าวผู้เล่น ไม่วิเคราะห์ผลกระทบ ไม่ใช้หัวข้อย่อยแบบลำดับเลข
ข้อความที่ไม่รู้ว่ากล่าวถึงอะไร เช่น 3 ขวดไม่พอ โดยไม่มีบริบท ให้ unresolved ไม่ฝืนสร้างปัญหา
คำถามหากล่อง/Family/Convent ไม่ใช่หลักฐานว่าระบบหรือคำอธิบายในเกมมีปัญหา
หัวข้อและบูลเล็ตใช้ ผู้เล่นสงสัย/รายงาน/เสนอ ตามหลักฐาน ไม่เปลี่ยนความสงสัยให้เป็นบั๊กจริง
overall_analysis วิเคราะห์ในมุมเกมออนไลน์จากข้อมูลทั้งหมดที่สรุปได้ครั้งเดียว
แยกคำถามจากอาการขัดข้อง อธิบายผลที่อาจเกิดขึ้นอย่างมีเงื่อนไข ไม่เดาศัพท์ย่อ ความรู้สึก กลไก หรือสาเหตุ
ไม่แยกวิเคราะห์ทีละหัวข้อ ไม่เสนอสิ่งที่ทีมควรทำต่อ ไม่แต่งจำนวนหรือจัดความรุนแรงตามจำนวนข้อความ
ถ้า coverage มีข้อมูลค้างให้ระบุว่าสะท้อนเฉพาะส่วนที่สรุปสำเร็จ ไม่สรุปแทนทั้งสัปดาห์
ถ้าทั้งหมดเป็น unresolved ให้ groups=[] และ overall_analysis=ข้อมูลยังไม่พอวิเคราะห์ภาพรวม'''


def validate_digest(result,candidates):
    from discussion_report import _partition
    if not isinstance(result,dict):raise ValueError('Invalid overall object')
    groups=result.get('groups');unresolved=result.get('unresolved_candidate_ids');overall=result.get('overall_analysis')
    if not isinstance(groups,list) or len(groups)>5:raise ValueError('Invalid groups')
    if not isinstance(unresolved,list):raise ValueError('Invalid unresolved ids')
    if not isinstance(overall,str) or not overall.strip() or len(overall)>900:raise ValueError('Invalid overall analysis')
    ids=list(unresolved);seen=set();clean=[]
    for group in groups:
        if not isinstance(group,dict):raise ValueError('Invalid group')
        category=group.get('category');members=group.get('candidate_ids');bullets=group.get('bullets')
        if not isinstance(category,str) or category not in CATEGORIES or category in seen:raise ValueError('Invalid category')
        seen.add(category)
        if not isinstance(members,list) or not members:raise ValueError('Missing group ids')
        if not isinstance(bullets,list) or not 1<=len(bullets)<=4 or any(not isinstance(b,str) or not b.strip() or len(b)>280 for b in bullets):raise ValueError('Invalid bullets')
        ids.extend(members);clean.append({'category':category,'candidate_ids':members,'bullets':bullets})
    _partition(ids,set(range(len(candidates))))
    for group in clean:
        group['evidence_ids']=sorted({e for i in group['candidate_ids'] for e in candidates[i]['evidence_ids']})
    return {'groups':clean,'unresolved_ids':sorted({e for i in unresolved for e in candidates[i]['evidence_ids']}),
            'overall_analysis':overall.strip()}


def render_grouped(label,items,counts,ledger):
    from reports import safe
    from discussion_report import ERROR_LABELS
    relevant=counts['issue']+counts['uncertain'];missing=len(ledger['analysis_missing_ids'])
    lines=[f'**สรุป Feedback TOSM — {safe(label)}**',
        f'ข้อความทั้งหมด {len(items)} | คัดแยกแล้ว {len(items)-counts["pending"]} | รอคัดแยก {counts["pending"]}',
        f'มีประเด็น {counts["issue"]} | ยังไม่ชัดเจน {counts["uncertain"]} | คุยทั่วไป/ไม่มีประเด็น {counts["non_issue"]}',
        f'สรุปข้อความผ่านการตรวจหลักฐาน {relevant-missing} จาก {relevant} ข้อความ']
    if counts['pending'] or missing:
        lines.append(f'⚠️ ข้อมูลยังไม่ครบ: รอคัดแยก {counts["pending"]} ข้อความ และรอสรุปอีก {missing} ข้อความ (คนละชุดกัน)')
    digest=ledger.get('digest')
    if digest:
        by_id={r['id']:r for r in items}
        for category,title in CATEGORIES.items():
            group=next((g for g in digest['groups'] if g['category']==category),None)
            if not group:continue
            rows=[by_id[i] for i in group['evidence_ids']];users={r['user_id'] for r in rows if r.get('user_id')}
            lines+=['',f'**{title}**',f'{len(rows)} ข้อความ / {len(users)} ผู้แจ้งที่ระบุ ID ได้']
            unknown=sum(not r.get('user_id') for r in rows)
            if unknown:lines.append(f'{unknown} ข้อความไม่ทราบ ID ผู้แจ้ง')
            lines+=['- '+safe(b) for b in group['bullets']]
        if digest['unresolved_ids']:
            lines+=['',f'อีก {len(digest["unresolved_ids"])} ข้อความยังระบุบริบทไม่ได้ จึงไม่นำมาสรุปเป็นปัญหาเกม']
        lines+=['','**วิเคราะห์ภาพรวม**',safe(digest['overall_analysis'])]
    elif not relevant and not counts['pending']:
        lines+=['','ในข้อความที่คัดแยกแล้ว ยังไม่พบประเด็นจากผู้เล่น']
    else:
        lines+=['','ยังสรุปประเด็นไม่ได้: การจัดหมวดหลักหรือบทวิเคราะห์ภาพรวมยังไม่สำเร็จ ข้อความต้นฉบับยังอยู่ครบ']
    if ledger.get('errors'):
        lines+=['','**สถานะการประมวลผล**']
        for code in sorted({e['code'] for e in ledger['errors']}):
            lines.append('- '+ERROR_LABELS.get(code,'API หรือบริการขัดข้อง')+' ('+code+')')
    facts={k for issue in ledger['issues'] for k in issue['knowledge_ids']}
    if digest and facts:
        lines+=['','**ข้อมูลเกมที่ใช้ตรวจเทียบ**']
        for k in ledger['knowledge_snapshot']:
            if k['id'] in facts:lines.append(f'- {safe(k["fact"])} ({safe(k["source_version"])}) {k["source_url"]}')
    lines+=['','หมายเหตุ: แต่ละข้อความนับในหมวดหลักเดียว จำนวนข้อความไม่ใช่จำนวนบั๊ก ข้อวิเคราะห์เป็นสมมติฐานจากเสียงผู้เล่น ไม่ใช่การยืนยันสาเหตุหรือบั๊ก']
    if not ledger['knowledge_snapshot']:lines.append('ยังไม่มีเอกสาร TOSM ที่อนุมัติให้ใช้ตรวจเทียบ')
    return '\n'.join(lines)
