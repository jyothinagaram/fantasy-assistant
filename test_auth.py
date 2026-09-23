"""
Checks the front-door password.

Run with:  .venv/bin/python test_auth.py
"""

import os
import time

import auth


def with_password(value):
    if value is None:
        os.environ.pop("APP_PASSWORD", None)
    else:
        os.environ["APP_PASSWORD"] = value
    os.environ.pop("APP_SECRET", None)


def test_no_password_means_an_open_door():
    """Running at home must work exactly as it always did."""
    with_password(None)
    assert auth.password() is None
    assert auth.correct("") is True
    assert auth.correct("anything") is True


def test_the_right_password_is_accepted_and_a_wrong_one_is_not():
    with_password("a-long-and-boring-passphrase")
    assert auth.correct("a-long-and-boring-passphrase")
    assert not auth.correct("a-long-and-boring-passphras")
    assert not auth.correct("")
    assert not auth.correct(None)


def test_a_cookie_we_issued_is_accepted():
    with_password("secret-one")
    token = auth.sign(time.time() + 60)
    assert auth.valid(token)


def test_an_expired_cookie_is_refused():
    with_password("secret-one")
    token = auth.sign(time.time() - 1)
    assert not auth.valid(token)


def test_a_cookie_cannot_be_edited_to_last_longer():
    """The whole point of signing it."""
    with_password("secret-one")
    token = auth.sign(time.time() - 1)
    forged = auth.sign(time.time() + 99999).split(".")[0] + "." + token.split(".")[1]
    assert not auth.valid(forged)


def test_rubbish_is_refused_rather_than_crashing():
    with_password("secret-one")
    for junk in (None, "", "....", "abc", "a.b", "!!!.???", "x" * 500):
        assert not auth.valid(junk), junk


def test_changing_the_password_signs_everyone_out():
    with_password("first-password")
    token = auth.sign(time.time() + 3600)
    assert auth.valid(token)
    with_password("second-password")
    assert not auth.valid(token)


def test_the_cookie_is_locked_down():
    with_password("secret-one")
    cookie = auth.new_cookie(https=True)
    assert "HttpOnly" in cookie          # JavaScript cannot read it
    assert "SameSite=Lax" in cookie      # other sites cannot make you send it
    assert "Secure" in cookie            # never sent in the clear
    assert auth.password() not in cookie # the password itself is never in it
    # Over plain HTTP (a local run) Secure would stop it working at all.
    assert "Secure" not in auth.new_cookie(https=False)


def test_the_cookie_is_found_in_a_real_header():
    with_password("secret-one")
    token = auth.sign(time.time() + 60)
    header = f"other=1; {auth.COOKIE_NAME}={token}; another=2"
    assert auth.read_cookie(header) == token
    assert auth.read_cookie("nothing=here") is None
    assert auth.read_cookie(None) is None


def test_guessing_gets_locked_out():
    attempts = auth.Attempts(max_attempts=3, lockout=60)
    now = 1000.0
    assert attempts.locked("1.2.3.4", now) == 0
    for _ in range(3):
        attempts.failed("1.2.3.4", now)
    assert attempts.locked("1.2.3.4", now) > 0
    # Somebody else is unaffected.
    assert attempts.locked("5.6.7.8", now) == 0
    # It lets go once the lockout passes.
    assert attempts.locked("1.2.3.4", now + 61) == 0


def test_getting_it_right_clears_the_count():
    attempts = auth.Attempts(max_attempts=3, lockout=60)
    attempts.failed("1.2.3.4", 1000.0)
    attempts.failed("1.2.3.4", 1000.0)
    attempts.passed("1.2.3.4")
    assert attempts.locked("1.2.3.4", 1000.0) == 0


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    with_password(None)
    print(f"\nAll {len(tests)} auth tests passed.")
