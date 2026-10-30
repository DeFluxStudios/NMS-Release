import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from sotw.config import Config
from sotw.publisher import Publisher


class HttpTests(unittest.TestCase):
    def test_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(data_dir=Path(tmp), public_base_url='http://x')
            pub = Publisher(cfg)

            async def go():
                async with TestClient(TestServer(pub.make_app())) as client:
                    r = await client.get('/winner.json')
                    self.assertFalse((await r.json())['active'])
                    r = await client.get('/student')
                    self.assertEqual(r.status, 200)
                    pub.write({'title': 'T', 'author': 'A', 'url': 'https://youtube.com/x',
                               'reason': '', 'week': 'W'})
                    r = await client.get('/winner.json')
                    data = await r.json()
                    self.assertEqual(data['title'], 'T')
                    r = await client.get('/student', allow_redirects=False)
                    self.assertEqual(r.status, 302)
                    self.assertEqual(r.headers['Location'], 'https://youtube.com/x')
                    r = await client.get('/winner.txt')
                    self.assertEqual((await r.text()).strip(), 'T by A')
            asyncio.run(go())


if __name__ == '__main__':
    unittest.main()
