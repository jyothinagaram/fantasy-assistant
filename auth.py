"""
The password on the front door, for when this runs anywhere but your Mac.

On your own machine there is nothing to protect: the page is on your Wi-Fi
and your ESPN login never leaves the computer. On a public host that stops
being true. The app reads YOUR ESPN account, so anyone who guesses the
address would see your rosters, your waiver plans and every trade you are
thinking about. This puts one password in front of all of it.

It is deliberately the smallest thing that works, because a login is the
one part of this project where being clever is a liability:

  * ONE shared password, from the APP_PASSWORD environment variable. There
    are no accounts, because there is one user. If APP_PASSWORD is not set
    the door is simply open, which is what you want on your own machine and
    is why nothing changes when you run it at home.
  * The password is never stored, logged, or written to the cookie. What
    goes in the cookie is an expiry date and a signature over it, so a
    stolen cookie is useless once it expires and cannot be edited to last
    longer -- changing the date breaks the signature.
  * Comparisons use hmac.compare_digest, which takes the same time whether
    the first character is wrong or the last. A plain `==` leaks how much
    of a guess was right, one character at a time.
  * Wrong guesses are slowed down. Without that, a password is only as
    good as how fast someone can try the whole dictionary, and a small
    server will happily answer thousands of times a minute.

WHAT THIS IS NOT. It is not multi-user, it is not a login for your friends,
and it does not protect you if you pick "password". Use something long.
The transport security comes from the host: Render, Fly and Oracle all
terminate HTTPS for you, and the cookie is marked Secure whenever the
request arrived over HTTPS, so it is never sent back in the clear.
"""

import base64
import hashlib
import hmac
import os
import time


COOKIE_NAME = "fa_session"

# How long a phone stays logged in. Long on purpose: this guards a fantasy
# football board, and a login prompt at 12:55 on a Sunday is how people end
# up turning the password off altogether.
SESSION_DAYS = 30

# After this many wrong guesses from one address, start refusing for a
# while. Slow enough to make guessing hopeless, forgiving enough that
# fat-fingering your own password three times is not a lockout for the day.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


def password():
    """The configured password, or None when the door is meant to be open."""
    return os.getenv("APP_PASSWORD") or None


def secret():
    """
    The key the cookie is signed with.

    Derived from the password unless APP_SECRET is set, so there is only one
    thing to configure. Changing the password therefore signs everyone out,
    which is the behaviour you want from changing a password.
    """
    explicit = os.getenv("APP_SECRET")
    if explicit:
        return explicit.encode()
    return hashlib.sha256(("fa-session:" + (password() or "")).encode()).digest()


def sign(expires_at):
    payload = str(int(expires_at)).encode()
    signature = hmac.new(secret(), payload, hashlib.sha256).digest()
    return (base64.urlsafe_b64encode(payload).decode().rstrip("=") + "."
            + base64.urlsafe_b64encode(signature).decode().rstrip("="))


def unpad(value):
    return value + "=" * (-len(value) % 4)


def valid(token, now=None):
    """Is this cookie one we issued, and has it not expired?"""
    if not token or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(unpad(encoded))
        given = base64.urlsafe_b64decode(unpad(signature))
    except Exception:
        return False
    expected = hmac.new(secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(given, expected):
        return False
    try:
        expires_at = int(payload)
    except ValueError:
        return False
    return (now if now is not None else time.time()) < expires_at


def new_cookie(now=None, https=True):
    """A fresh session cookie, ready for a Set-Cookie header."""
    now = time.time() if now is None else now
    token = sign(now + SESSION_DAYS * 24 * 3600)
    parts = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        "HttpOnly",                      # JavaScript can never read it
        "SameSite=Lax",                  # not sent from other people's sites
        f"Max-Age={SESSION_DAYS * 24 * 3600}",
    ]
    if https:
        parts.append("Secure")           # never sent over plain HTTP
    return "; ".join(parts)


def cleared_cookie():
    return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def read_cookie(header):
    """Pulls our cookie out of a raw Cookie: header."""
    for piece in (header or "").split(";"):
        name, _, value = piece.strip().partition("=")
        if name == COOKIE_NAME:
            return value
    return None


def correct(attempt):
    """Constant-time check of a submitted password."""
    wanted = password()
    if not wanted:
        return True
    return hmac.compare_digest((attempt or "").encode(), wanted.encode())


class Attempts:
    """Remembers wrong guesses per address, so guessing cannot be brute-forced."""

    def __init__(self, max_attempts=MAX_ATTEMPTS, lockout=LOCKOUT_SECONDS):
        self.max_attempts = max_attempts
        self.lockout = lockout
        self.failures = {}          # address -> [count, when it unlocks]

    def locked(self, address, now=None):
        now = time.time() if now is None else now
        count, until = self.failures.get(address, (0, 0))
        if count >= self.max_attempts and now < until:
            return int(until - now)
        return 0

    def failed(self, address, now=None):
        now = time.time() if now is None else now
        count, until = self.failures.get(address, (0, 0))
        if now >= until and count >= self.max_attempts:
            count = 0               # the lockout expired; start again
        count += 1
        self.failures[address] = (count, now + self.lockout)

    def passed(self, address):
        self.failures.pop(address, None)
