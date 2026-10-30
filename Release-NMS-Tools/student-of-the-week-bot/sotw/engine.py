import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger('sotw.engine')


def week_key(moment, tz):
    year, week, _ = moment.astimezone(tz).isocalendar()
    return '%d-W%02d' % (year, week)


async def _no_reactions(entry):
    return 0


class Engine:
    """Weekly cycle: score, pick, veto window, publish. No Discord dependency."""

    def __init__(self, cfg, db, scorer, publisher, notify, reaction_counter=None):
        self.cfg = cfg
        self.db = db
        self.scorer = scorer
        self.publisher = publisher
        self.notify = notify
        self.reaction_counter = reaction_counter or _no_reactions

    def current_week(self, now=None):
        return week_key(now or datetime.now(timezone.utc), self.cfg.tz)

    def cycle_due(self, now=None):
        now = now or datetime.now(timezone.utc)
        local = now.astimezone(self.cfg.tz)
        week = week_key(now, self.cfg.tz)
        if self.db.is_paused() or self.db.week_has_winner(week):
            return False
        if self.db.get_setting('last_cycle_week') == week:
            return False
        return (local.weekday(), local.hour) >= (self.cfg.cycle_weekday, self.cfg.cycle_hour)

    async def _rank(self, week):
        entries = [e for e in self.db.valid_entries(week) if not self.db.is_optout(e['user_id'])]
        if not entries:
            return []
        reactions = {e['id']: await self.reaction_counter(e) for e in entries}
        ai = await self.scorer.score(entries)
        ranked = []
        for e in entries:
            ai_score, reason = ai.get(e['id'], (0.0, ''))
            final = ai_score + self.cfg.reaction_weight * min(reactions[e['id']], 25)
            self.db.set_entry_score(e['id'], ai_score, final, reason)
            ranked.append((final, e['id'], e, reason))
        ranked.sort(key=lambda r: (-r[0], r[1]))
        return ranked

    async def run_cycle(self, now=None):
        """Pick this week's winner and start the veto window. Returns a status string."""
        now = now or datetime.now(timezone.utc)
        week = self.current_week(now)
        self.db.set_setting('last_cycle_week', week)
        try:
            ranked = await self._rank(week)
        except Exception as exc:
            log.exception('Scoring failed')
            await self.notify('staff', 'Student of the Week: scoring failed (%s). Keeping the current banner.' % exc)
            return 'scoring failed; kept current banner'
        if not ranked:
            await self.notify('staff', 'Student of the Week: no valid entries for %s. Keeping the current banner.' % week)
            return 'no entries; kept current banner'
        return await self._propose(week, ranked[0][2], ranked[0][3], now)

    async def _propose(self, week, entry, reason, now):
        publish_at = now + timedelta(hours=self.cfg.veto_hours)
        winner_id = self.db.add_winner(week, entry, reason, publish_at.isoformat())
        await self.notify(
            'staff',
            'Student of the Week pick for %s: "%s" by %s (entry #%d).\n%s\nReason: %s\n'
            'Goes live %s UTC. Use /sotw_veto to stop it; the runner-up is then picked.'
            % (week, entry['title'], entry['author'], entry['id'], entry['url'], reason or 'n/a',
               publish_at.strftime('%Y-%m-%d %H:%M')))
        if self.cfg.veto_hours <= 0:
            await self.publish_due(now)
        return 'picked entry %d (winner %d)' % (entry['id'], winner_id)

    async def publish_due(self, now=None):
        now = now or datetime.now(timezone.utc)
        pending = self.db.pending_winner()
        if not pending or self.db.is_paused():
            return False
        if datetime.fromisoformat(pending['publish_at']) > now:
            return False
        self.db.retire_live()
        self.db.set_winner_state(pending['id'], 'live')
        self.publisher.write(pending)
        self.db.set_entry_status(pending['entry_id'], 'won')
        await self.notify('announce', 'This week\'s Student of the Week: "%s" by %s\n%s\n%s'
                          % (pending['title'], pending['author'], pending['url'], pending['reason'] or ''))
        await self.notify('hall', 'Student of the Week %s: "%s" by %s - %s'
                          % (pending['week'], pending['title'], pending['author'], pending['url']))
        return True

    async def veto(self, now=None):
        """Cancel the pending pick and promote the runner-up. Returns a status string."""
        now = now or datetime.now(timezone.utc)
        pending = self.db.pending_winner()
        if not pending:
            return 'There is no pending pick to veto.'
        self.db.set_winner_state(pending['id'], 'vetoed')
        self.db.set_entry_status(pending['entry_id'], 'vetoed')
        runners = sorted(
            (e for e in self.db.valid_entries(pending['week']) if not self.db.is_optout(e['user_id'])),
            key=lambda e: (-(e['final_score'] or 0), e['id']))
        if not runners:
            await self.notify('staff', 'Vetoed. No runner-up, so the current banner stays.')
            return 'vetoed; no runner-up, current banner kept'
        return await self._propose(pending['week'], runners[0], runners[0]['reason'], now)

    def revert(self):
        """Kill switch: show the default banner and pause the cycle."""
        self.db.set_setting('paused', '1')
        pending = self.db.pending_winner()
        if pending:
            self.db.set_winner_state(pending['id'], 'cancelled')
        self.db.retire_live()
        self.publisher.write(None)

    def resume(self):
        self.db.set_setting('paused', '0')

    def restore_published(self):
        """Rewrite the output files from the database on startup."""
        self.publisher.write(self.db.live_winner())
