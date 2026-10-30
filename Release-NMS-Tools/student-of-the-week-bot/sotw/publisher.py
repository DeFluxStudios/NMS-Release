import json
import os
from datetime import datetime, timezone

from aiohttp import web

from .screening import display_text

DEFAULT_PAYLOAD = {
    'active': False,
    'title': '',
    'author': '',
    'url': '',
    'reason': '',
    'week': '',
}


def _atomic_write(path, text):
    tmp = str(path) + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)


class Publisher:
    """Writes the current winner where the client, scripts and the web endpoint read it."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.json_path = cfg.data_dir / 'winner.json'
        self.txt_path = cfg.data_dir / 'winner.txt'
        self.version = 0

    def payload_for(self, winner):
        if not winner:
            return dict(DEFAULT_PAYLOAD)
        return {
            'active': True,
            'title': display_text(winner['title']),
            'author': display_text(winner['author'], 24),
            'url': winner['url'],
            'short_url': self.cfg.public_base_url + '/student',
            'reason': display_text(winner.get('reason') or '', 120),
            'week': winner['week'],
        }

    def write(self, winner):
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.version += 1
        payload = self.payload_for(winner)
        payload['version'] = self.version
        payload['updated'] = datetime.now(timezone.utc).isoformat()
        _atomic_write(self.json_path, json.dumps(payload, indent=2))
        line = '%s by %s' % (payload['title'], payload['author']) if payload['active'] else ''
        _atomic_write(self.txt_path, line + '\n')
        return payload

    def read(self):
        try:
            with open(self.json_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return dict(DEFAULT_PAYLOAD)

    def make_app(self):
        app = web.Application()

        async def winner_json(request):
            return web.json_response(self.read(), headers={'Cache-Control': 'no-cache'})

        async def winner_txt(request):
            try:
                text = self.txt_path.read_text(encoding='utf-8')
            except OSError:
                text = '\n'
            return web.Response(text=text, content_type='text/plain', headers={'Cache-Control': 'no-cache'})

        async def student(request):
            data = self.read()
            if data.get('active') and data.get('url'):
                raise web.HTTPFound(data['url'])
            return web.Response(text='No Student of the Week is featured right now.', content_type='text/plain')

        async def health(request):
            return web.Response(text='ok')

        app.router.add_get('/winner.json', winner_json)
        app.router.add_get('/winner.txt', winner_txt)
        app.router.add_get('/student', student)
        app.router.add_get('/healthz', health)
        return app

    async def start_http(self):
        runner = web.AppRunner(self.make_app())
        await runner.setup()
        site = web.TCPSite(runner, self.cfg.http_host, self.cfg.http_port)
        await site.start()
        return runner
