# Putting this on your phone

Goal: open the app from anywhere, for free, without your Mac being awake
and without a terminal.

This takes about fifteen minutes. You need two free accounts (Render and
UptimeRobot). Nothing here costs money, and nothing asks for a card.

---

## What you are setting up

Render runs the app on a small server of its own and gives you a web
address. A password sits in front of it, because the app reads **your**
ESPN account — without one, anyone who found the address would see your
rosters, your waiver plans and your trade ideas.

Render's free plan puts a service to sleep after 15 minutes of quiet, and
wiping its disk when it wakes is what would make the app rebuild all three
leagues from scratch — about three minutes of staring at a loading screen.
UptimeRobot fixes that by visiting the page every few minutes so it never
falls asleep. That is the only reason it is here.

---

## Step 1 — get your ESPN cookies

You already have these in the `.env` file on your Mac. Open it and copy the
two long values:

```
ESPN_S2=...
ESPN_SWID=...
```

Keep them somewhere for a minute. **Do not paste them into a chat, an
issue, or this repository** — they are the keys to your ESPN account.

## Step 2 — deploy to Render

1. Go to <https://render.com> and sign up (the free plan, GitHub login is
   easiest).
2. **New → Web Service**, then connect this repository
   (`fantasy-assistant`).
3. Render reads `render.yaml` and fills in the build and start commands
   itself. You should not need to type either.
4. It will ask you for four values. Fill them in:

   | Name | What to put |
   |---|---|
   | `APP_PASSWORD` | A password you invent, for the page. Make it long. |
   | `ESPN_S2` | From your `.env` |
   | `ESPN_SWID` | From your `.env` |
   | `ESPN_SEASON` | `2026` |

5. Choose the **Free** instance type and create the service.

First build takes a few minutes. When it finishes you get an address like
`https://fantasy-assistant.onrender.com`.

## Step 3 — check it

Open that address on your phone. You should see a password box, then your
teams. The first load after deploying will take a couple of minutes while
it reads all three leagues — that happens once, not every time.

Add it to your home screen: **Share → Add to Home Screen**. It then opens
like an app, and the password is remembered for 30 days.

## Step 4 — stop it falling asleep

1. Sign up at <https://uptimerobot.com> (free).
2. **Add New Monitor** → type **HTTP(s)**.
3. URL: your Render address **with `/healthz` on the end** —
   `https://your-app.onrender.com/healthz`. Interval: **5 minutes**.
4. Save.

Point it at `/healthz`, not at the front page. `/healthz` answers
instantly and needs no password, so a monitor can check it without
logging in. The front page has to render, and while the app is working
out a league on a free instance's tenth of a CPU that can be slow enough
for a monitor to call it down when it is perfectly fine.

That is it. The service now stays awake, so opening it on your phone is
instant instead of a three-minute rebuild.

> `/healthz` replies `{"ok": true}` and nothing else — no league names, no
> teams, nothing worth protecting. The monitor never logs in and never sees
> your data.

**If you get "down" alerts anyway**, check the Render logs at that
timestamp. Two different things look identical from outside:
>
> * **Slow, not dead.** A league refresh on a free instance can saturate
>   the CPU for minutes. Raise the monitor's timeout to 30 seconds.
> * **Actually restarting.** Render restarts free services, and a restart
>   drops requests for a few seconds. Occasional alerts are normal; a
>   constant stream is not.

---

## Things that will happen eventually

**Your ESPN cookies expire.** Every few months the app will stop being able
to read your leagues. Fix: get the new `ESPN_S2` and `ESPN_SWID` from your
browser, then in Render go to **Environment**, update the two values, and
the service restarts itself. Nothing else changes.

**Render restarts the service occasionally** (they do this to free
services). When that happens the cache is wiped and the next open rebuilds
the leagues — one slow load, then back to normal.

**The free plan allows 750 hours a month.** Running all month uses about
730, so one service fits. A second free service on the same account would
not.

---

## Running it at home, unchanged

None of this affects your Mac. With no `APP_PASSWORD` set, there is no
login and everything behaves exactly as it did:

```
.venv/bin/python app.py
```

The password only appears when `APP_PASSWORD` exists, which is why the
deployed copy has one and your laptop does not.
