import unittest

from sotw.config import Config
from sotw.screening import display_text, screen_entry, validate_url

CFG = Config(link_hosts=('youtube.com', 'discord.com'), blocked_words=('badword',))


class ScreeningTests(unittest.TestCase):
    def test_accepts_good_entry(self):
        entry, err = screen_entry('Guk guide', 'https://www.youtube.com/watch?v=abc', 'A walkthrough of Guk.', CFG)
        self.assertIsNone(err)
        self.assertEqual(entry['title'], 'Guk guide')

    def test_rejects_unlisted_host(self):
        _, err = screen_entry('Guk guide', 'https://evil.example/x', 'A walkthrough of Guk.', CFG)
        self.assertIn('allowed list', err)

    def test_rejects_lookalike_host(self):
        _, err = validate_url('https://notyoutube.com/x', CFG.link_hosts)
        self.assertIsNotNone(err)

    def test_rejects_credentials_and_scheme(self):
        self.assertIsNotNone(validate_url('https://user:pw@youtube.com/x', CFG.link_hosts)[1])
        self.assertIsNotNone(validate_url('javascript:alert(1)', CFG.link_hosts)[1])

    def test_blocked_word_with_leetspeak(self):
        _, err = screen_entry('B4dw0rd here', 'https://youtube.com/x', 'A walkthrough of Guk.', CFG)
        self.assertIn('not allowed', err)

    def test_short_description(self):
        _, err = screen_entry('Guk guide', 'https://youtube.com/x', 'short', CFG)
        self.assertIn('description', err)

    def test_mentions_removed(self):
        entry, _ = screen_entry('Hi @everyone guide', 'https://youtube.com/x', 'A walkthrough of Guk.', CFG)
        self.assertNotIn('@everyone', entry['title'])

    def test_display_text_is_client_safe(self):
        out = display_text('[Best] <guide> {x} http://a.b/c|d ' + 'y' * 100)
        self.assertNotRegex(out, r'[\[\]<>{}|]')
        self.assertLessEqual(len(out), 40)
        self.assertNotIn('http', out)


if __name__ == '__main__':
    unittest.main()
