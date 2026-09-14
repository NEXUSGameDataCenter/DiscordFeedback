"""
Scheduler module — จัดการ scheduled jobs ทั้งหมด
แยกออกมาเพื่อ debug ง่าย + ทดสอบแยกได้

วิธีทำงาน:
- ใช้ APScheduler CronTrigger
- ทุก job มี ID ชัดเจน
- log ก่อน/หลัง run ทุกครั้ง
- มี status command ให้เช็คได้ใน Discord
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("scheduler")


class BotScheduler:
    def __init__(self, tz_str: str):
        try:
            self.tz = ZoneInfo(tz_str)
            self.tz_str = tz_str
        except Exception:
            # fallback ถ้า tzdata ไม่ได้ลง
            logger.warning(f"ไม่พบ timezone '{tz_str}' — fallback to UTC")
            self.tz = ZoneInfo("UTC")
            self.tz_str = "UTC"

        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._jobs_info: list[dict] = []

    def add_daily(self, coro_func, hour: int, minute: int, label: str = "daily"):
        """เพิ่ม job รายวัน"""
        job_id = f"daily_{label}"
        self.scheduler.add_job(
            coro_func,
            CronTrigger(hour=hour, minute=minute, timezone=self.tz),
            id=job_id,
            replace_existing=True,
            name=label,
        )
        self._jobs_info.append({
            "id": job_id,
            "label": label,
            "schedule": f"ทุกวัน {hour:02d}:{minute:02d} ({self.tz_str})",
            "type": "daily",
        })
        logger.info(f"[scheduler] เพิ่ม daily job '{label}' → {hour:02d}:{minute:02d} {self.tz_str}")

    def add_weekly(self, coro_func, weekday: int, hour: int, minute: int, label: str = "weekly"):
        """เพิ่ม job รายสัปดาห์
        weekday: 0=จันทร์ ... 6=อาทิตย์
        """
        day_names = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
        day_str = day_names[weekday] if 0 <= weekday <= 6 else str(weekday)
        job_id = f"weekly_{label}"
        self.scheduler.add_job(
            coro_func,
            CronTrigger(day_of_week=weekday, hour=hour, minute=minute, timezone=self.tz),
            id=job_id,
            replace_existing=True,
            name=label,
        )
        self._jobs_info.append({
            "id": job_id,
            "label": label,
            "schedule": f"ทุกวัน{day_str} {hour:02d}:{minute:02d} ({self.tz_str})",
            "type": "weekly",
            "weekday": weekday,
        })
        logger.info(f"[scheduler] เพิ่ม weekly job '{label}' → วัน{day_str} {hour:02d}:{minute:02d} {self.tz_str}")

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info(f"[scheduler] เริ่มทำงาน ({len(self._jobs_info)} jobs)")
        else:
            logger.warning("[scheduler] กำลังทำงานอยู่แล้ว")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("[scheduler] หยุดทำงาน")

    def status(self) -> str:
        """คืน string สำหรับ Discord แสดงสถานะ scheduler"""
        now = datetime.now(self.tz)
        lines = [
            f"🕐 **Scheduler Status**",
            f"เวลาปัจจุบัน: `{now.strftime('%d/%m/%Y %H:%M:%S')}` ({self.tz_str})",
            f"สถานะ: {'🟢 Running' if self.scheduler.running else '🔴 Stopped'}",
            "",
            "**Jobs ที่ตั้งไว้:**",
        ]

        for job in self._jobs_info:
            apsjob = self.scheduler.get_job(job["id"])
            if apsjob:
                next_run = apsjob.next_run_time
                if next_run:
                    next_local = next_run.astimezone(self.tz)
                    next_str = next_local.strftime("%d/%m/%Y %H:%M")
                else:
                    next_str = "ไม่ทราบ"
                lines.append(f"• **{job['label']}** — {job['schedule']}")
                lines.append(f"  → ครั้งถัดไป: `{next_str}`")
            else:
                lines.append(f"• **{job['label']}** — ⚠️ ไม่พบ job นี้")

        return "\n".join(lines)
