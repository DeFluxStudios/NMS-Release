import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


def _int(name, default=0):
    raw = os.environ.get(name, '').strip()
    return int(raw) if raw else default


def _float(name, default=0.0):
    raw = os.environ.get(name, '').strip()
    return float(raw) if raw else default


def _list(name, default=''):
    raw = os.environ.get(name, default)
    return [p.strip().lower() for p in raw.split(',') if p.strip()]


@dataclass
class Config:
    token: str = ''
    guild_id: int = 0
    submit_channel_id: int = 0
    staff_channel_id: int = 0
    announce_channel_id: int = 0
    hall_channel_id: int = 0
    ai_url: str = 'https://api.openai.com/v1/chat/completions'
    ai_key: str = ''
    ai_model: str = 'gpt-4o-mini'
    moderation_url: str = ''
    reaction_weight: float = 0.2
    timezone: str = 'America/Los_Angeles'
    cycle_weekday: int = 6
    cycle_hour: int = 20
    veto_hours: float = 12.0
    min_account_age_days: int = 14
    min_member_days: int = 3
    max_entries_per_week: int = 2
    link_hosts: tuple = ('discord.com', 'discordapp.com', 'cdn.discordapp.com', 'youtube.com', 'youtu.be', 'imgur.com')
    blocked_words: tuple = ()
    data_dir: Path = Path('./data')
    http_host: str = '127.0.0.1'
    http_port: int = 8765
    public_base_url: str = 'http://127.0.0.1:8765'

    @property
    def tz(self):
        return ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls):
        return cls(
            token=os.environ.get('DISCORD_TOKEN', '').strip(),
            guild_id=_int('GUILD_ID'),
            submit_channel_id=_int('SUBMIT_CHANNEL_ID'),
            staff_channel_id=_int('STAFF_CHANNEL_ID'),
            announce_channel_id=_int('ANNOUNCE_CHANNEL_ID'),
            hall_channel_id=_int('HALL_CHANNEL_ID'),
            ai_url=os.environ.get('AI_API_URL', cls.ai_url).strip(),
            ai_key=os.environ.get('AI_API_KEY', '').strip(),
            ai_model=os.environ.get('AI_MODEL', cls.ai_model).strip(),
            moderation_url=os.environ.get('MODERATION_URL', '').strip(),
            reaction_weight=_float('REACTION_WEIGHT', cls.reaction_weight),
            timezone=os.environ.get('TIMEZONE', cls.timezone).strip(),
            cycle_weekday=_int('CYCLE_WEEKDAY', cls.cycle_weekday),
            cycle_hour=_int('CYCLE_HOUR', cls.cycle_hour),
            veto_hours=_float('VETO_HOURS', cls.veto_hours),
            min_account_age_days=_int('MIN_ACCOUNT_AGE_DAYS', cls.min_account_age_days),
            min_member_days=_int('MIN_MEMBER_DAYS', cls.min_member_days),
            max_entries_per_week=_int('MAX_ENTRIES_PER_WEEK', cls.max_entries_per_week),
            link_hosts=tuple(_list('LINK_HOSTS', ','.join(cls.link_hosts))),
            blocked_words=tuple(_list('BLOCKED_WORDS')),
            data_dir=Path(os.environ.get('DATA_DIR', './data')),
            http_host=os.environ.get('HTTP_HOST', cls.http_host).strip(),
            http_port=_int('HTTP_PORT', cls.http_port),
            public_base_url=os.environ.get('PUBLIC_BASE_URL', cls.public_base_url).strip().rstrip('/'),
        )
