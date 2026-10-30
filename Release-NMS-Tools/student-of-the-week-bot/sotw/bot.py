import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import tasks

from .ai import AIScorer, ReactionScorer, flagged_by_moderation
from .config import Config
from .db import Database
from .engine import Engine
from .publisher import Publisher
from .screening import screen_entry

log = logging.getLogger('sotw.bot')
THUMB = '\N{THUMBS UP SIGN}'


class SotwBot(discord.Client):
    def __init__(self, cfg: Config):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.cfg = cfg
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(cfg.data_dir / 'sotw.sqlite')
        self.publisher = Publisher(cfg)
        scorer = AIScorer(cfg) if cfg.ai_key else ReactionScorer()
        self.engine = Engine(cfg, self.db, scorer, self.publisher, self.notify, self.count_reactions)
        self.tree = app_commands.CommandTree(self)
        self.http_runner = None
        self._register_commands()

    async def setup_hook(self):
        self.engine.restore_published()
        self.http_runner = await self.publisher.start_http()
        guild = discord.Object(id=self.cfg.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.scheduler.start()

    async def close(self):
        self.scheduler.cancel()
        if self.http_runner:
            await self.http_runner.cleanup()
        self.db.close()
        await super().close()

    async def notify(self, kind, text):
        channel_id = {
            'staff': self.cfg.staff_channel_id,
            'announce': self.cfg.announce_channel_id,
            'hall': self.cfg.hall_channel_id,
        }.get(kind)
        if not channel_id:
            return
        channel = self.get_channel(channel_id)
        if channel is None:
            log.warning('Channel %s for %s not found', channel_id, kind)
            return
        try:
            await channel.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.exception('Could not post to %s', kind)

    async def count_reactions(self, entry):
        if not entry.get('message_id') or not entry.get('channel_id'):
            return 0
        try:
            channel = self.get_channel(entry['channel_id']) or await self.fetch_channel(entry['channel_id'])
            message = await channel.fetch_message(entry['message_id'])
        except discord.HTTPException:
            return 0
        for reaction in message.reactions:
            if str(reaction.emoji) == THUMB:
                return max(0, reaction.count - (1 if reaction.me else 0))
        return 0

    @tasks.loop(minutes=1)
    async def scheduler(self):
        try:
            if self.engine.cycle_due():
                result = await self.engine.run_cycle()
                log.info('Weekly cycle: %s', result)
            await self.engine.publish_due()
        except Exception:
            log.exception('Scheduler tick failed')

    @scheduler.before_loop
    async def _wait_ready(self):
        await self.wait_until_ready()

    def _is_staff(self, interaction):
        return interaction.user.guild_permissions.manage_guild

    def _register_commands(self):
        tree, cfg, db, engine = self.tree, self.cfg, self.db, self.engine

        @tree.command(name='submit', description='Submit your work for Student of the Week')
        @app_commands.describe(title='Short title', link='Link to your work (allowed sites only)',
                               description='What it is and why it helps players')
        async def submit(interaction: discord.Interaction, title: str, link: str, description: str):
            await interaction.response.defer(ephemeral=True)
            user = interaction.user
            now = datetime.now(timezone.utc)
            if db.is_paused():
                return await interaction.followup.send('Submissions are paused right now.')
            if db.is_optout(user.id):
                return await interaction.followup.send('You opted out. Use /sotw_optin to submit again.')
            if (now - user.created_at).days < cfg.min_account_age_days:
                return await interaction.followup.send('Your Discord account is too new to submit.')
            joined = getattr(user, 'joined_at', None)
            if joined and (now - joined).days < cfg.min_member_days:
                return await interaction.followup.send('Please wait a few days after joining to submit.')
            week = engine.current_week(now)
            if db.count_user_week(user.id, week) >= cfg.max_entries_per_week:
                return await interaction.followup.send(
                    'You have reached the limit of %d entries this week.' % cfg.max_entries_per_week)
            entry, err = screen_entry(title, link, description, cfg)
            if err:
                return await interaction.followup.send(err)
            if db.url_used(entry['url']):
                return await interaction.followup.send('That link has already been submitted.')
            if await flagged_by_moderation(cfg, entry['title'] + '\n' + entry['description']):
                return await interaction.followup.send('Your entry was not accepted by the content filter.')
            entry_id = db.add_entry(week, user.id, user.display_name, entry['title'], entry['url'],
                                    entry['description'])
            channel = self.get_channel(cfg.submit_channel_id) if cfg.submit_channel_id else None
            if channel:
                embed = discord.Embed(title=entry['title'], url=entry['url'], description=entry['description'])
                embed.set_footer(text='Entry #%d by %s - react %s to support it' % (entry_id, user.display_name, THUMB))
                message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                await message.add_reaction(THUMB)
                db.set_entry_message(entry_id, channel.id, message.id)
            await interaction.followup.send('Entry #%d received. Good luck!' % entry_id)

        @tree.command(name='mysubmissions', description='Show your entries for this week')
        async def mysubmissions(interaction: discord.Interaction):
            rows = db.user_entries(interaction.user.id, engine.current_week())
            text = '\n'.join('#%d %s [%s]' % (r['id'], r['title'], r['status']) for r in rows) or 'No entries this week.'
            await interaction.response.send_message(text, ephemeral=True)

        @tree.command(name='withdraw', description='Withdraw one of your entries')
        async def withdraw(interaction: discord.Interaction, entry_id: int):
            ok = db.withdraw_entry(entry_id, interaction.user.id)
            await interaction.response.send_message('Withdrawn.' if ok else 'Could not withdraw that entry.',
                                                    ephemeral=True)

        @tree.command(name='sotw_optout', description='Never feature me, and remove my current entries')
        async def optout(interaction: discord.Interaction):
            db.add_optout(interaction.user.id)
            db.remove_user_entries(interaction.user.id)
            await interaction.response.send_message('You will not be featured.', ephemeral=True)

        @tree.command(name='sotw_optin', description='Allow me to be featured again')
        async def optin(interaction: discord.Interaction):
            db.remove_optout(interaction.user.id)
            await interaction.response.send_message('You can submit again.', ephemeral=True)

        @tree.command(name='student', description='Show the current Student of the Week')
        async def student(interaction: discord.Interaction):
            data = self.publisher.read()
            if data.get('active'):
                text = '%s by %s\n%s' % (data['title'], data['author'], data['url'])
            else:
                text = 'No Student of the Week is featured right now.'
            await interaction.response.send_message(text)

        staff = app_commands.default_permissions(manage_guild=True)

        @tree.command(name='sotw_status', description='Staff: show state')
        @staff
        async def status(interaction: discord.Interaction):
            pending, live = db.pending_winner(), db.live_winner()
            text = 'Paused: %s\nLive: %s\nPending: %s' % (
                db.is_paused(), live['title'] if live else 'none',
                '%s (live at %s UTC)' % (pending['title'], pending['publish_at'][:16]) if pending else 'none')
            await interaction.response.send_message(text, ephemeral=True)

        @tree.command(name='sotw_run', description='Staff: run the weekly cycle now')
        @staff
        async def run_now(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(await engine.run_cycle())

        @tree.command(name='sotw_veto', description='Staff: cancel the pending pick and promote the runner-up')
        @staff
        async def veto(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(await engine.veto())

        @tree.command(name='sotw_revert', description='Staff: kill switch, default banner and pause')
        @staff
        async def revert(interaction: discord.Interaction):
            engine.revert()
            await interaction.response.send_message('Reverted to the default banner. The bot is paused.',
                                                    ephemeral=True)

        @tree.command(name='sotw_resume', description='Staff: resume after a pause')
        @staff
        async def resume(interaction: discord.Interaction):
            engine.resume()
            await interaction.response.send_message('Resumed.', ephemeral=True)


def run():
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    cfg = Config.from_env()
    if not cfg.token or not cfg.guild_id:
        raise SystemExit('Set DISCORD_TOKEN and GUILD_ID in .env (see .env.example).')
    SotwBot(cfg).run(cfg.token, log_handler=None)
