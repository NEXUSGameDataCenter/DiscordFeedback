# TOSM Discord Feedback Bot v7 — Supabase + Sonnet 5

เวอร์ชันนี้แทนชุด discordfinalv6 โดยใช้ Supabase เป็นฐานข้อมูลหลัก และ Claude API model ID `claude-sonnet-5` ทั้งการจัดหมวด วิเคราะห์ และตรวจคุณภาพข้อวิเคราะห์

## สิ่งที่แก้

- เลิกซิงก์ผ่าน Google Sheets / Apps Script บันทึกข้อความและผลวิเคราะห์ลง Supabase โดยตรง
- เก็บข้อความต้นฉบับครบ ไม่ย่อเหลือ 60 ตัวอักษรก่อนวิเคราะห์ และไม่สุ่มเหลือเพียง 8 ตัวอย่างเมื่อมีข้อมูลเกิน 40 ข้อความ
- ตัวเลขคำนวณจากข้อมูลจริง แยกข้อความ ผู้แจ้งที่ทราบ ID หมวดหลัก และข้อความยังไม่ชัดเจน/ยังวิเคราะห์ไม่สำเร็จ
- แต่ละข้อความมีหมวดหลักเดียวเพื่อไม่ให้บวกรวมซ้ำ ไม่ใช้จำนวนหมวดแทนจำนวนปัญหาหรือบั๊กที่ยืนยันแล้ว ข้อความหนึ่งอาจกล่าวถึงหลายประเด็นได้
- นักวิเคราะห์ TOSM แยกคำรายงานผู้เล่น ข้อมูลอ้างอิงที่ทีมอนุมัติ สมมติฐาน และขั้นตอนตรวจสอบ
- โมเดลไม่มีสิทธิอ้างข้อมูลเกมจากความจำ คำว่า UID ลดเรท/สุ่มผิดปกติ/เลิกเล่น/ทีมละเลยไม่ถือเป็นข้อเท็จจริงจากข้อความผู้เล่นเพียงอย่างเดียว
- ตรวจ ID ทุกข้อความ ตรวจข้อความหลักฐานตรงต้นฉบับ ปฏิเสธ JSON ไม่ครบ/ซ้ำ/แหล่งอ้างอิงไม่มีจริง และให้ AI ตรวจข้อวิเคราะห์ซ้ำก่อนแสดง
- คำอ้างอิงที่ตรวจไม่ผ่านแสดงเป็นงานวิเคราะห์ที่ยังไม่สำเร็จ พร้อมแนวทางตรวจเบื้องต้น ไม่รายงานว่าไม่มีปัญหา
- การตีความของโมเดลยังต้องตรวจด้วยข้อมูลจริง การตรวจอัตโนมัติไม่ใช่การรับประกันความจริง
- รายงานเต็ม UTF-8 แนบใน Discord และเก็บพร้อมหลักฐานใน Supabase ไม่มีการตัดให้เหลือ 3500 ตัวอักษร
- คิวพักใน `data/outbox.sqlite3` มีไว้รับมือ Supabase ขัดข้องเท่านั้น ไม่ใช่ฐานรายงานหลัก ส่งสำเร็จแล้วลบจากคิว
- กันบอทหลายตัวหยิบข้อความเดียวกันด้วย transaction/lease และกันงานรายงานอัตโนมัติซ้ำตามช่วงวันที่

## ติดตั้ง

ใช้ Python 3.11 ขึ้นไป (ทดสอบแกนระบบด้วย Python 3.12) เปิด terminal ในโฟลเดอร์นี้

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Linux/macOS:

```bash
source .venv/bin/activate
cp .env.example .env
```

จากนั้น:

```bash
python -m pip install -r requirements.txt
```

1. เลือก Supabase project ที่ต้องการ แล้วรัน `schema.sql` ใน SQL Editor ด้วยเจ้าของฐานข้อมูล สคริปต์ทำงานใน transaction และรันซ้ำได้ ไม่ลบข้อมูลเดิม
2. ตารางทั้งหมดขึ้นต้น `tosm_` เปิด RLS และไม่เปิดให้ `anon`/`authenticated` อ่านหรือเรียก RPC; ให้สิทธิ์เฉพาะ backend `service_role`
3. กรอก `.env`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (secret key ของ backend หรือ legacy service_role), `ANTHROPIC_API_KEY`, `DISCORD_TOKEN`, `GUILD_ID`, `FEEDBACK_CHANNEL_ID`, `REPORT_CHANNEL_ID`
4. เก็บ `.env` บนเครื่องรันบอท ไม่ต้องส่ง key ทางแชท บอทใช้ REST ผ่าน HTTPS ไม่ต้องใช้รหัสผ่าน PostgreSQL
5. ใน Discord Developer Portal เปิด Message Content Intent และให้บอท View Channel, Read Message History, Send Messages, Attach Files ในห้องที่เกี่ยวข้อง พร้อม scope `bot` และ `applications.commands`
6. ผู้เรียกคำสั่งต้องมี Manage Server และอยู่ใน GUILD_ID ที่กำหนด
7. ตรวจการเชื่อมต่อและรัน:

```bash
python check_connection.py
python check_connection.py --ai
python bot.py
```

`--ai` เรียก Sonnet จริงหนึ่งครั้งและมีค่า API ตามการใช้งาน หากได้ HTTP 404/403 ให้ตรวจสิทธิ์โมเดลและ key; ระบบจะไม่สลับไป Haiku โดยเงียบ ๆ

Sonnet 5 ไม่รับ sampling parameters แบบเดิม โค้ดจึงไม่ส่ง temperature/top_p/top_k และเลือกอ่านเฉพาะ text blocks ตั้ง thinking disabled ไว้ชัดเจนสำหรับงาน JSON เพื่อคุมเวลาและไม่ให้ thinking ใช้โควตาผลลัพธ์ โมเดลยังคงเป็น Sonnet 5

## ย้ายข้อมูลเดิม

เลือก **SQLite เดิมเป็นแหล่งหลักถ้ามี** เพราะมี Discord message/user IDs ครบกว่า Sheets หยุดบอทเดิมก่อนตัดระบบไปใช้เวอร์ชันใหม่ และเก็บสำเนาไฟล์ต้นทางไว้

```bash
python migrate_data.py sqlite /path/to/feedback.db --guild-id YOUR_GUILD_ID
python migrate_data.py sqlite /path/to/feedback.db --guild-id YOUR_GUILD_ID --apply
```

คำสั่งแรกตรวจไฟล์อย่างเดียว คำสั่งที่สองนำเข้าจริง ไม่แก้ไฟล์ SQLite ต้นทาง ข้อมูล AI เดิมจะไม่ถูกนำมาใช้เป็นข้อเท็จจริง ทุกข้อความเริ่มคิววิเคราะห์ใหม่

ถ้ามีเฉพาะ Google Sheets: export เป็น CSV UTF-8 โดยคง 10 หรือ 11 คอลัมน์ตามโค้ดเดิมและมีแถวหัวตาราง:

`id, created_at, username, content, category, sentiment, severity, summary, tags, normalized_at[, issue_flag]`

```bash
python migrate_data.py csv /path/to/feedback.csv --dataset old-tosm-sheet
python migrate_data.py csv /path/to/feedback.csv --dataset old-tosm-sheet --apply
```

ใช้ชื่อ `--dataset` เดิมทุกครั้งที่นำเข้าชีตเดิม การนำเข้าซ้ำ source ID เดิมไม่เพิ่มข้อความซ้ำ และตรวจ content/เวลาเทียบหลังบันทึก CSV เดิมไม่มี user ID จึงนับผู้แจ้งเฉพาะที่ยืนยัน ID ได้ ไม่เดาจากชื่อ

อย่านำเข้าทั้ง SQLite และ Sheets ชุดเดียวกันโดยไม่มีการจับคู่ ID เพราะ CSV เดิมไม่มี Discord message ID ที่ใช้เทียบข้ามแหล่งได้ หาก CSV ไม่มีแถวหัวตารางหรือสลับคอลัมน์ ต้องจัดกลับก่อนนำเข้า

เวลาแบบไม่มี timezone ถือเป็น UTC ตามค่าเดิมของบอท หาก CSV เป็นเวลาท้องถิ่นจริง ให้เพิ่ม `--source-timezone Asia/Bangkok` ต้องตรวจวัน/เดือนและ encoding ต้นทาง ถ้าไฟล์เดิมเป็น `???` ไปแล้ว โปรแกรมไม่สามารถกู้ข้อความจริงจากเครื่องหมายคำถามได้

## ฐานความรู้ TOSM

เริ่มต้น `knowledge.example.json` เป็น `[]` โดยตั้งใจ เนื่องจากยังไม่ได้รับเอกสารยืนยันระบบเกม และไม่มีการแต่งกติกาเกมเติมเอง

แต่ละรายการต้องมี:

| ฟิลด์ | ความหมาย |
|---|---|
| id | รหัสเอกสาร/ข้อเท็จจริงที่ไม่ซ้ำ |
| topic | gacha, farming, patch, support, shop, access, payment, performance, balance, other หรือ all |
| title / fact | หัวข้อและข้อเท็จจริงที่ตรวจแล้ว ระบุชื่อตู้/เซิร์ฟเวอร์/เงื่อนไขให้ครบ |
| source_url | HTTPS URL ของประกาศหรือเอกสารภายในที่ทีมตรวจได้ |
| source_version | แพตช์/รุ่น/ชื่อตู้หรือรุ่นเอกสาร |
| valid_from / valid_to | เวลาเริ่มและสิ้นสุดที่ข้อมูลใช้ได้; valid_to เป็น null ได้ |
| verified_by / verified_at | ผู้ตรวจและเวลาตรวจ ISO 8601 |
| approved | ต้องเป็น true เพื่อใช้ประกอบรายงาน |

สร้างไฟล์ JSON จากข้อมูลจริง แล้วใช้:

```bash
python migrate_data.py knowledge /path/to/tosm-knowledge.json
python migrate_data.py knowledge /path/to/tosm-knowledge.json --apply
```

โปรแกรมใช้เฉพาะเอกสารอนุมัติที่มีช่วงใช้ได้ครอบคลุมช่วงรายงานทั้งหมด เพื่อไม่เผลออ้างกติกาคนละแพตช์ หากมีเปลี่ยนแพตช์กลางสัปดาห์ ให้แยกรายงานก่อน/หลังวันเปลี่ยน หรือเพิ่มเอกสารอ้างอิงที่ครอบคลุมช่วงนั้น ไม่มีเอกสารไม่ทำให้บอทหยุด แต่รายงานจะระบุว่ายังไม่มีข้อมูลยืนยัน

`source_url` เป็น provenance ที่ทีมให้ บอทไม่ได้เปิดเว็บไปตรวจความจริงหรืออัปเดตแพตช์เอง ใช้ข้อมูลที่ผ่านการอนุมัติเท่านั้น

## คำสั่ง Discord

| คำสั่ง | ผล |
|---|---|
| /report_now | วิเคราะห์คิวและรายงานวันนี้ |
| /report_daily | รายงานเมื่อวาน |
| /report_weekly | รายงานจันทร์–อาทิตย์สัปดาห์ก่อน |
| /report_range | ช่วงวันเริ่มถึงวันสิ้นสุด รวมวันสิ้นสุด ตามเวลาไทย |
| /feedback_stats | ตัวเลขวันนี้และจำนวนคิวพัก โดยไม่เรียก AI |
| /renormalize | เข้าคิวใหม่เฉพาะรายการล้มเหลว; all_rows=true จัดใหม่ทั้งหมดที่ไม่มีงานถือครองอยู่ |
| /database_status | ตรวจ Supabase/โมเดลที่ตั้ง/คิวพัก |
| /scheduler_status | เวลารายงานครั้งถัดไป |
| /backfill days:1 | อ่านย้อนหลังเมื่อบอทหยุดทำงาน สูงสุด 2000 ข้อความต่อครั้ง |

รายงานอัตโนมัติรายวันเวลา 09:00 ของเมื่อวาน รายสัปดาห์วันจันทร์ 09:00 ตาม Asia/Bangkok เปลี่ยนได้ใน .env
คำสั่ง Google Sheets ถูกนำออกพร้อมส่วนซิงก์ รายงานแบบสั่งเองส่งเข้า REPORT_CHANNEL_ID เพื่อไม่ติดอายุ interaction token ระหว่างงานยาว

ข้อความรูปภาพ/ไฟล์แนบยังไม่ถูกอ่านอัตโนมัติ คิวพักช่วยเฉพาะข้อความที่บอทรับได้แล้ว ถ้าบอทหยุดหรือหลุดจนพลาดข้อความ ให้ /backfill และตรวจคำเตือนเพดาน ควรเก็บโฟลเดอร์ data บนดิสก์ที่ไม่ถูกล้างเมื่อ restart

## การทดสอบและข้อจำกัด

```bash
python -m unittest discover -s tests -v
```

ดู `TEST_RESULTS.md` สำหรับผลที่รันแล้วและสิ่งที่ยังไม่ได้ตรวจจริง `tests/verify_database.sql` ใช้ทดสอบ SQL ใน schema แยกและ ROLLBACK ทั้งหมด รันด้วยเจ้าของฐาน Supabase ไม่ใช้กับ schema งานจริง

รายงานที่มีข้อมูลมากอาจใช้หลาย API calls เพราะส่งข้อความครบ แบ่งกลุ่มละ 20 และตรวจข้อวิเคราะห์อีกครั้ง มีเพดานเวลาและจำนวนคิว ไม่ได้อ้างว่ารายงานครบหากชนเพดาน ใช้ช่วงสั้นลงหรือรันรายงานใหม่หลัง /renormalize เมื่อแก้การเชื่อมต่อแล้ว

การส่ง Discord กับการบันทึกฐานข้อมูลไม่ใช่ transaction เดียวกัน หาก Discord รับรายงานแล้วบอทล้มก่อนบันทึกสถานะงานสำเร็จ อาจส่งซ้ำหลัง lease หมดได้ การกันซ้ำลดกรณีปกติแต่ไม่รับประกัน exactly-once

## เอกสาร API ที่ตรวจประกอบ

- https://platform.claude.com/docs/en/models/sonnet-5/migration-guide
- https://supabase.com/docs/guides/database/overview
- https://supabase.com/docs/guides/api/securing-your-api
- https://supabase.com/docs/reference/python/upsert
