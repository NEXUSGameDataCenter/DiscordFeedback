"""Environment settings; no credentials are committed."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))

def integer(name, default, minimum=1, maximum=100000):
    value = int(os.getenv(name, '').strip() or str(default))
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')
GUILD_ID = integer('GUILD_ID', 0, 0, 2**64)
FEEDBACK_CHANNEL_ID = integer('FEEDBACK_CHANNEL_ID', 0, 0, 2**64)
REPORT_CHANNEL_ID = integer('REPORT_CHANNEL_ID', 0, 0, 2**64)
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.6-luna')
TIMEZONE = os.getenv('TIMEZONE', 'Asia/Bangkok')
DAILY_REPORT_TIME = os.getenv('DAILY_REPORT_TIME', '09:00')
WEEKLY_REPORT_TIME = os.getenv('WEEKLY_REPORT_TIME', '09:00')
WEEKLY_REPORT_DAY = integer('WEEKLY_REPORT_DAY', 0, 0, 6)
MAX_FEEDBACK_PER_BATCH = integer('MAX_FEEDBACK_PER_BATCH', 20, 1, 50)
NORMALIZE_MAX_TOTAL = integer('NORMALIZE_MAX_TOTAL', 1000, 1, 10000)
NORMALIZE_TIME_BUDGET = integer('NORMALIZE_TIME_BUDGET', 480, 30, 1200)
REPORT_MAX_ROWS = integer('REPORT_MAX_ROWS', 10000, 1, 10000)
PROMPT_VERSION = 'tosm-luna-v7'

def validate(database_only=False):
    names = ['SUPABASE_URL', 'SUPABASE_SECRET_KEY']
    if not database_only:
        names += ['DISCORD_TOKEN', 'GUILD_ID', 'FEEDBACK_CHANNEL_ID', 'REPORT_CHANNEL_ID', 'OPENAI_API_KEY']
    missing = [name for name in names if not globals()[name]]
    if missing:
        raise RuntimeError('Missing settings: ' + ', '.join(missing))
    if not SUPABASE_URL.startswith('https://'):
        raise ValueError('SUPABASE_URL must use HTTPS')
    if not SUPABASE_SECRET_KEY.startswith(('sb_secret_', 'eyJ')):
        raise ValueError('Use a backend Supabase secret key or legacy service_role JWT')
    if not database_only:
        for setting in [DAILY_REPORT_TIME, WEEKLY_REPORT_TIME]:
            h, m = map(int, setting.split(':'))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError('Report time must be HH:MM')
