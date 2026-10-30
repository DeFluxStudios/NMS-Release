import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sotw.ai import parse_scores
from sotw.config import Config
from sotw.db import Database
from sotw.engine import Engine
from sotw.publisher import Publisher

# Sunday 2026-11-01 21:00 Pacific (cycle time); ISO week 2026-W44
SUNDAY = datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)


class FakeScorer:
    def __init__(self, scores=None, fail=False):
        self.scores, self.fail = scores or {}, fail

    async def score(self, entries):
        if self.fail:
            raise RuntimeError('boom')
        return {e['id']: self.scores.get(e['id'], (1.0, 'ok')) for e in entries}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(data_dir=Path(self.tmp.name), veto_hours=12)
        self.db = Database(Path(self.tmp.name) / 't.sqlite')
        self.pub = Publisher(self.cfg)
        self.sent = []

        async def notify(kind, text):
            self.sent.append((kind, text))
        self.notify = notify
        self.week = '2026-W44'

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def engine(self, scorer=None, reactions=None):
        return Engine(self.cfg, self.db, scorer or FakeScorer(), self.pub, self.notify, reactions)

    def add(self, user, title, url='https://youtube.com/x'):
        return self.db.add_entry(self.week, user, 'User%d' % user, title, url + str(user), 'a description')

    def test_cycle_due_schedule(self):
        e = self.engine()
        self.assertFalse(e.cycle_due(datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)))
        self.assertTrue(e.cycle_due(SUNDAY))
        self.db.set_setting('paused', '1')
        self.assertFalse(e.cycle_due(SUNDAY))

    def test_pick_veto_window_then_publish(self):
        a, b = self.add(1, 'First'), self.add(2, 'Second')
        e = self.engine(FakeScorer({a: (5, 'meh'), b: (9, 'great')}))
        asyncio.run(e.run_cycle(SUNDAY))
        self.assertEqual(self.db.pending_winner()['title'], 'Second')
        self.assertFalse(asyncio.run(e.publish_due(SUNDAY + timedelta(hours=1))))
        self.assertFalse(self.pub.read()['active'])
        self.assertTrue(asyncio.run(e.publish_due(SUNDAY + timedelta(hours=13))))
        data = self.pub.read()
        self.assertTrue(data['active'])
        self.assertEqual(data['title'], 'Second')
        self.assertIn('/student', data['short_url'])
        self.assertEqual((Path(self.tmp.name) / 'winner.txt').read_text().strip(), 'Second by User2')
        self.assertTrue(any(k == 'announce' for k, _ in self.sent))
        self.assertFalse(e.cycle_due(SUNDAY + timedelta(hours=14)))

    def test_veto_promotes_runner_up(self):
        a, b = self.add(1, 'First'), self.add(2, 'Second')
        e = self.engine(FakeScorer({a: (5, 'meh'), b: (9, 'great')}))
        asyncio.run(e.run_cycle(SUNDAY))
        asyncio.run(e.veto(SUNDAY + timedelta(hours=1)))
        self.assertEqual(self.db.pending_winner()['title'], 'First')

    def test_veto_without_runner_up_keeps_banner(self):
        self.add(1, 'Only')
        e = self.engine()
        asyncio.run(e.run_cycle(SUNDAY))
        asyncio.run(e.veto(SUNDAY))
        self.assertIsNone(self.db.pending_winner())

    def test_scoring_failure_keeps_current_banner(self):
        self.add(1, 'Only')
        e = self.engine(FakeScorer(fail=True))
        asyncio.run(e.run_cycle(SUNDAY))
        self.assertIsNone(self.db.pending_winner())
        self.assertTrue(any('failed' in t for _, t in self.sent))

    def test_no_entries_keeps_banner(self):
        asyncio.run(self.engine().run_cycle(SUNDAY))
        self.assertIsNone(self.db.pending_winner())

    def test_reactions_break_ties(self):
        a, b = self.add(1, 'First'), self.add(2, 'Second')

        async def reactions(entry):
            return 10 if entry['id'] == a else 0
        e = self.engine(FakeScorer({a: (5, ''), b: (5, '')}), reactions)
        asyncio.run(e.run_cycle(SUNDAY))
        self.assertEqual(self.db.pending_winner()['title'], 'First')

    def test_optout_excluded(self):
        a, b = self.add(1, 'First'), self.add(2, 'Second')
        self.db.add_optout(1)
        e = self.engine(FakeScorer({a: (9, ''), b: (1, '')}))
        asyncio.run(e.run_cycle(SUNDAY))
        self.assertEqual(self.db.pending_winner()['title'], 'Second')

    def test_revert_pauses_and_clears(self):
        self.add(1, 'Only')
        e = self.engine()
        asyncio.run(e.run_cycle(SUNDAY))
        asyncio.run(e.publish_due(SUNDAY + timedelta(hours=13)))
        e.revert()
        self.assertFalse(self.pub.read()['active'])
        self.assertTrue(self.db.is_paused())

    def test_published_title_is_sanitised(self):
        self.db.add_entry(self.week, 9, 'U', '[Bad] <b>title</b>', 'https://youtube.com/z', 'a description')
        e = self.engine()
        asyncio.run(e.run_cycle(SUNDAY))
        asyncio.run(e.publish_due(SUNDAY + timedelta(hours=13)))
        self.assertNotRegex(self.pub.read()['title'], r'[\[\]<>]')


class ParseScoreTests(unittest.TestCase):
    def test_parse_with_noise_and_clamp(self):
        text = 'Sure!\n' + json.dumps({'scores': [{'id': 1, 'score': 15, 'reason': 'x'},
                                                    {'id': 99, 'score': 3}, {'id': 'bad'}]})
        out = parse_scores(text, {1, 2})
        self.assertEqual(out, {1: (10.0, 'x')})

    def test_parse_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_scores('no json here', {1})


if __name__ == '__main__':
    unittest.main()
