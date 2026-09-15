"""Discord entrypoint. All commands restricted to Manage Server in configured guild."""
import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import discord
from discord import app_commands
from discord.ext import commands, tasks
import config
from database import Database
from ai_analyzer import AIAnalyzer
from reports import ReportBuilder
from scheduler import BotScheduler
from spool import Outbox

from log_setup import configure_logging
configure_logging()
log=logging.getLogger('tosm')

class TOSMBot(commands.Bot):
    def __init__(self):
        intents=discord.Intents.default();intents.message_content=True
        super().__init__(command_prefix='!',intents=intents,allowed_mentions=discord.AllowedMentions.none())
        self.db=Database(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY)
        self.ai=AIAnalyzer(config.OPENAI_API_KEY,config.OPENAI_MODEL)
        self.reports=ReportBuilder(self.db,self.ai,config.TIMEZONE,config.MAX_FEEDBACK_PER_BATCH,
            config.NORMALIZE_MAX_TOTAL,config.NORMALIZE_TIME_BUDGET,config.REPORT_MAX_ROWS,config.PROMPT_VERSION)
        self.outbox=Outbox()
        self.scheduler=BotScheduler(config.TIMEZONE)
        self.work_lock=asyncio.Lock()

    async def setup_hook(self):
        # Fail startup if schema/credentials are invalid; do not start a broken scheduler.
        await self.db.init()
        guild=discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        dh,dm=map(int,config.DAILY_REPORT_TIME.split(':'))
        wh,wm=map(int,config.WEEKLY_REPORT_TIME.split(':'))
        self.scheduler.add_daily(self.daily_job,dh,dm,label='รายงานรายวัน')
        self.scheduler.add_weekly(self.weekly_job,config.WEEKLY_REPORT_DAY,wh,wm,label='รายงานรายสัปดาห์')
        self.scheduler.start()
        self.flush_outbox.start()

    async def close(self):
        self.flush_outbox.cancel()
        self.scheduler.stop()
        await self.ai.close();await self.db.close()
        await super().close()

    @tasks.loop(seconds=30)
    async def flush_outbox(self):
        try:
            await self.outbox.flush(self.db)
        except Exception:
            log.error('Supabase upload pending; durable outbox will retry')

    @flush_outbox.before_loop
    async def before_flush(self):
        await self.wait_until_ready()

    async def on_ready(self):
        log.info('Connected as %s; model=%s',self.user,config.OPENAI_MODEL)

    async def capture(self,message):
        if message.author.bot or not message.guild or message.guild.id!=config.GUILD_ID:
            return
        if message.channel.id!=config.FEEDBACK_CHANNEL_ID or not message.content.strip():
            return
        await self.outbox.put(dict(discord_msg_id=str(message.id),user_id=str(message.author.id),
            username=str(message.author),guild_id=str(message.guild.id),channel_id=str(message.channel.id),
            content=message.content,created_at=message.created_at.astimezone(timezone.utc)))

    async def on_message(self,message):
        try:
            await self.capture(message)
        except Exception:
            log.critical('Capture failed for message id=%s; check disk and use /backfill',message.id)
        await self.process_commands(message)

    async def prepare_report(self,start,end,label):
        # A report cannot silently exclude locally queued messages.
        while await self.outbox.count():
            await self.outbox.flush(self.db)
        await self.reports.normalize_pending()
        return await self.reports.build_report(start,end,label)

    async def send_report(self,send,text,incomplete):
        prefix='⚠️ รายงานยังวิเคราะห์ไม่ครบ\n' if incomplete else ''
        # Always attach the full UTF-8 report; avoid truncation and long embed spam.
        preview=text if len(text)<=1700 else text[:1500].rsplit('\n',1)[0]+'\n\nอ่านรายละเอียดต่อในไฟล์แนบ'
        await send(prefix+preview,file=discord.File(io.BytesIO(text.encode('utf-8-sig')),
                                                  filename='TOSM-report.txt'),
                   allowed_mentions=discord.AllowedMentions.none())

    async def scheduled_report(self,kind):
        await self.wait_until_ready()
        async with self.work_lock:
            start,end,label=(self.reports.daily_range() if kind=='daily' else self.reports.weekly_range())
            key=f'{kind}:{start.isoformat()}:{end.isoformat()}'
            owner=str(uuid4())
            if not await self.db.acquire_job(key,owner):
                return
            success=False
            try:
                async with asyncio.timeout(1800):
                    text,incomplete=await self.prepare_report(start,end,label)
                    channel=self.get_channel(config.REPORT_CHANNEL_ID) or await self.fetch_channel(config.REPORT_CHANNEL_ID)
                    await self.send_report(channel.send,text,incomplete)
                    success=True
                    if incomplete:log.warning("Report delivered with incomplete analysis: %s",kind)
                    else:log.info("Report delivered with complete analysis: %s",kind)
            except Exception:
                log.exception('Scheduled report failed: %s',kind)
            finally:
                await self.db.finish_job(key,owner,success)

    async def daily_job(self):
        await self.scheduled_report('daily')

    async def weekly_job(self):
        await self.scheduled_report('weekly')

bot=TOSMBot()

def staff():
    async def check(interaction):
        return (interaction.guild_id==config.GUILD_ID and
                interaction.permissions.manage_guild)
    return app_commands.check(check)

async def run_report(interaction,period):
    await interaction.response.defer(thinking=True,ephemeral=True)
    if bot.work_lock.locked():
        await interaction.followup.send('มีรายงานกำลังประมวลผล โปรดลองใหม่ภายหลัง',ephemeral=True)
        return
    async with bot.work_lock:
        try:
            # Deliver completion to a channel: interaction tokens expire on long workloads.
            await interaction.followup.send('กำลังประมวลผล ผลรายงานจะส่งในห้องรายงานที่กำหนด',ephemeral=True)
            async with asyncio.timeout(1800):
                text,incomplete=await bot.prepare_report(*period)
                channel=bot.get_channel(config.REPORT_CHANNEL_ID) or await bot.fetch_channel(config.REPORT_CHANNEL_ID)
                await bot.send_report(channel.send,text,incomplete)
        except Exception:
            log.exception('Manual report failed')
            await interaction.channel.send('❌ สร้างรายงานไม่สำเร็จ ตรวจการเชื่อมต่อและ log ของบอท ข้อมูลที่ค้างยังเก็บไว้',
                                           allowed_mentions=discord.AllowedMentions.none())

@bot.tree.command(name='report_now',description='รายงาน Feedback วันนี้')
@staff()
async def report_now(interaction:discord.Interaction):
    await run_report(interaction,bot.reports.daily_range(False))

@bot.tree.command(name='report_daily',description='รายงาน Feedback เมื่อวาน')
@staff()
async def report_daily(interaction:discord.Interaction):
    await run_report(interaction,bot.reports.daily_range())

@bot.tree.command(name='report_weekly',description='รายงาน Feedback สัปดาห์ที่แล้ว')
@staff()
async def report_weekly(interaction:discord.Interaction):
    await run_report(interaction,bot.reports.weekly_range())

@bot.tree.command(name='report_range',description='รายงานช่วงวันที่ YYYY-MM-DD')
@staff()
async def report_range(interaction:discord.Interaction,start:str,end:str):
    try:
        a=datetime.strptime(start,'%Y-%m-%d').date();b=datetime.strptime(end,'%Y-%m-%d').date()
        if b<a:raise ValueError()
    except ValueError:
        await interaction.response.send_message('วันที่ต้องเป็น YYYY-MM-DD และวันสิ้นสุดต้องไม่ก่อนวันเริ่ม',ephemeral=True)
        return
    await run_report(interaction,bot.reports._range(a,b+timedelta(days=1),f'{start} ถึง {end}'))

@bot.tree.command(name='feedback_stats',description='นับข้อความวันนี้โดยไม่เรียก AI')
@staff()
async def feedback_stats(interaction:discord.Interaction):
    from reports import summarize
    await interaction.response.defer(ephemeral=True)
    start,end,_=bot.reports.daily_range(False)
    snap=await bot.db.snapshot(start,end,config.REPORT_MAX_ROWS)
    counts,_=summarize(snap['items'])
    await interaction.followup.send(f'ทั้งหมด {snap["total"]} ข้อความ | มีประเด็น {counts["issue"]} | '
        f'ไม่ชัดเจน {counts["uncertain"]} | ไม่ใช่ประเด็น {counts["non_issue"]} | '
        f'ยังไม่สำเร็จ {counts["pending"]} | รอส่งจากเครื่อง {await bot.outbox.count()}',ephemeral=True)

@bot.tree.command(name='renormalize',description='เข้าคิววิเคราะห์ใหม่: ค่าเริ่มต้นเฉพาะรายการล้มเหลว')
@staff()
async def renormalize(interaction:discord.Interaction,all_rows:bool=False):
    await interaction.response.defer(ephemeral=True)
    if bot.work_lock.locked():
        await interaction.followup.send('มีงานกำลังทำงาน โปรดลองหลังงานเสร็จ',ephemeral=True);return
    async with bot.work_lock:
        n=await bot.db.reset_normalized(all_rows)
    await interaction.followup.send(f'เข้าคิว {n} ข้อความแล้ว ใช้ /report_now เพื่อวิเคราะห์และสร้างรายงาน',ephemeral=True)

@bot.tree.command(name='database_status',description='ตรวจ Supabase และคิวข้อมูล')
@staff()
async def database_status(interaction:discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await bot.db.init()
    await interaction.followup.send(f'Supabase พร้อม | โมเดล {config.OPENAI_MODEL} | '
                                   f'คิวรอส่ง {await bot.outbox.count()}',ephemeral=True)

@bot.tree.command(name='scheduler_status',description='ตรวจเวลารายงานครั้งถัดไป')
@staff()
async def scheduler_status(interaction:discord.Interaction):
    await interaction.response.send_message(bot.scheduler.status(),ephemeral=True)

@bot.tree.command(name='backfill',description='เก็บข้อความย้อนหลังในห้อง Feedback สูงสุด 2000 ข้อความ')
@staff()
async def backfill(interaction:discord.Interaction,days:app_commands.Range[int,1,30]=1):
    await interaction.response.defer(ephemeral=True)
    channel=bot.get_channel(config.FEEDBACK_CHANNEL_ID) or await bot.fetch_channel(config.FEEDBACK_CHANNEL_ID)
    n=0
    async for message in channel.history(limit=2000,after=datetime.now(timezone.utc)-timedelta(days=days),oldest_first=True):
        await bot.capture(message);n+=1
    await interaction.followup.send(f'ตรวจ {n} ข้อความและเข้าคิวแล้ว ข้อความซ้ำจะไม่ถูกเพิ่มซ้ำ'
        +(' — ถึงเพดาน 2000 ข้อความ ช่วงนี้อาจยังเก็บไม่ครบ' if n==2000 else ''),ephemeral=True)

@bot.tree.error
async def command_error(interaction,error):
    message=('คำสั่งนี้ใช้ได้เฉพาะผู้มีสิทธิ์ Manage Server ในเซิร์ฟเวอร์ที่กำหนด'
             if isinstance(error,app_commands.CheckFailure) else 'คำสั่งไม่สำเร็จ โปรดตรวจ log และการเชื่อมต่อ')
    if not isinstance(error,app_commands.CheckFailure):log.error('Command failed: %s',type(error).__name__)
    if interaction.response.is_done():await interaction.followup.send(message,ephemeral=True)
    else:await interaction.response.send_message(message,ephemeral=True)

if __name__=='__main__':
    config.validate()
    bot.run(config.DISCORD_TOKEN,log_handler=None)
