import re
from urllib.parse import urlparse

CONTROL_RE = re.compile(r'[\x00-\x1f\x7f]')
MENTION_RE = re.compile(r'@(everyone|here)|<[@#&!]?\d+>', re.I)
CLIENT_UNSAFE_RE = re.compile(r'[<>\[\]{}|\\^~`]')

MAX_TITLE = 60
MAX_DESC = 400
MAX_DISPLAY = 40

LEET = str.maketrans('01345@$', 'oieasas')


def clean_text(text, limit):
    text = CONTROL_RE.sub(' ', text or '')
    text = MENTION_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def display_text(text, limit=MAX_DISPLAY):
    """Plain text safe for the game client: no markup, links or special characters."""
    text = clean_text(text, 200)
    text = re.sub(r'https?://\S+', '', text)
    text = CLIENT_UNSAFE_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + '...'
    return text


def validate_url(url, allowed_hosts):
    url = (url or '').strip()
    if len(url) > 300 or any(c.isspace() for c in url):
        return None, 'The link is invalid or too long.'
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return None, 'The link must start with http:// or https://.'
    if parsed.username or parsed.password:
        return None, 'Links with embedded credentials are not allowed.'
    host = parsed.hostname.lower()
    if not any(host == h or host.endswith('.' + h) for h in allowed_hosts):
        return None, 'That site is not on the allowed list: ' + ', '.join(sorted(allowed_hosts))
    return parsed.geturl(), None


def _normalise(text):
    return re.sub(r'[^a-z ]', '', text.lower().translate(LEET))


def has_blocked_word(text, blocked_words):
    norm = ' ' + _normalise(text) + ' '
    squashed = norm.replace(' ', '')
    for word in blocked_words:
        w = _normalise(word).strip()
        if not w:
            continue
        if ' ' + w + ' ' in norm or (len(w) >= 5 and w in squashed):
            return True
    return False


def screen_entry(title, url, description, cfg):
    """Return (clean_entry_dict, None) or (None, reason)."""
    title = clean_text(title, MAX_TITLE)
    description = clean_text(description, MAX_DESC)
    if len(title) < 3:
        return None, 'The title is too short.'
    if len(description) < 10:
        return None, 'Please add a short description (at least 10 characters).'
    clean_url, err = validate_url(url, cfg.link_hosts)
    if err:
        return None, err
    if has_blocked_word(title + ' ' + description, cfg.blocked_words):
        return None, 'Your entry contains words that are not allowed.'
    if not display_text(title):
        return None, 'The title has no usable characters.'
    return {'title': title, 'url': clean_url, 'description': description}, None
