# Week 3: alerts, the outbox pattern and n8n at the edge

## 1. Concept

### What can go wrong with a sensor

The monitor looks for three kinds of problems:

- **Silence**: a machine sends nothing for more than 60 seconds. The monitor
  remembers the last reading of every machine over the whole history, not only the
  last hour. So a machine that has been dead for two hours still has its silence
  incident open, and the incident closes only when the machine sends data again.
- **Stuck value**: the same value arrives 10 times in a row for torque, rotational
  speed or process temperature. Real measurements wiggle a little, so a flat line
  usually means a frozen sensor. Air temperature is not checked: in the AI4I data
  it has only 93 distinct values and one machine repeats the same value 10 times in
  a row, which would raise a false alarm. This was found by sliding a window over
  the real rows before choosing the sensors.
- **Out of range**: a value outside what is physically sensible, such as 0 Kelvin
  for air temperature.

The replayer can create each of these on purpose with `--fault silence`,
`--fault sensor_stuck` and `--fault out_of_range`.

### Alert fatigue and dedupe

If a machine is silent for an hour and the monitor checks every 5 seconds, a naive
system sends 720 messages. People stop reading alerts. This is **alert fatigue**,
and it makes real problems get ignored.

The fix is **dedupe**: one alert per problem. The key is "machine + type". Here:

- the monitor does not queue a new alert while the same problem is already waiting
  in the outbox or open as an incident
- the database enforces it too: a unique index allows only one **open** incident
  per machine and type
- n8n's first step writes the incident only if this outbox row has none yet, and it
  uses `ON CONFLICT DO NOTHING` on that index. A real duplicate (another outbox row for
  a machine and type that already has an open incident) gets no message
- when the problem disappears, the monitor closes the incident, so a new
  occurrence later creates a fresh alert

### The outbox pattern

Sending an alert means calling another system (n8n), and that system can be down.
If the monitor simply tried once and gave up, the alert would be lost. If it
waited for n8n, it could not do its main job.

The **outbox pattern** solves this in two steps:

1. Write the alert into a table in our own database first (the `outbox`). This is
   fast and almost never fails.
2. A separate step reads the outbox and tries to deliver. If delivery fails, the
   row stays, a counter goes up and the next attempt is scheduled later.

Retries use **exponential backoff**: wait 10 s, then 20 s, 40 s and so on, but
never more than 5 minutes. This avoids hammering a system that is trying to recover.

**At least once delivery.** The monitor cannot know whether n8n did its work when an
answer is lost, so it tries again. That means a message can arrive twice, but it
cannot be lost. In this project the row counts as delivered only after Telegram
answered with success. If Telegram accepts the message and the next step ("Mark outbox
delivered") fails, the retry sends the same message a second time. The receiver must
therefore be safe to call twice: the incident is written once, the message can repeat.

**Failure rule of this project:** if n8n is down, ingestion carries on and alerts
wait in the outbox. There is a test for exactly this
(`test_ingestion_keeps_working_while_n8n_is_down`).

**Second failure rule:** if the Telegram call fails inside n8n, n8n answers the monitor
with an error (HTTP 500), the row stays undelivered and the monitor retries. The retry
sends the message again and does not create a second incident. This was checked against
the fake Telegram server with `FAKE_TELEGRAM_FAIL_FIRST=1`: request 1 got HTTP 500, the
retry sent the text once with HTTP 200 and `delivered_at` was set only after that.

### Why n8n only sits at the edge

n8n is a visual tool for connecting services. It is great for "when X happens,
send a message and write a row". It is a poor place for important logic, because
visual flows are harder to test, review and version than code.

So the rule is:

- **All decisions are in tested Python (monitor) or dbt.** What counts as a
  problem, how to dedupe, how to retry.
- **n8n only does delivery.** Receive the alert, log the incident, send the
  Telegram message, mark the outbox row as delivered. One small rule lives in the
  workflow: whether to send (new incident or retry) or skip (real duplicate). It is a
  single SQL query, and `tests/test_n8n_workflow.py` runs that query on a test database.

If n8n were replaced tomorrow by an email script, the monitor would not change.

## 2. Code walkthrough

**`monitor/`**

- `rules.py`: the limits (60 s silence, 10 stuck readings, the list of sensors the
  stuck check uses, allowed ranges). The numbers can be changed with environment variables.
- `checks.py`: three small functions that take plain data and return a list of
  alerts. They do not touch the database or the clock, so they are easy to test.
- `monitor_db.py`: reads the last reading time of every machine (whole history)
  and the latest rows of the last hour from Postgres, and closes incidents that
  have cleared. The hour only limits the stuck and range checks, not silence.
- `outbox.py`: `add_if_new` queues an alert unless it is a duplicate;
  `deliver_pending` tries every due alert; `backoff_seconds` calculates the wait.
- `n8n_client.py`: one function that posts to the webhook and raises an error on
  failure.
- `runner.py`: `run_once` ties it together: read, check, queue, close, deliver.
- `main.py`: calls `run_once` every 5 seconds and reconnects if the database
  connection drops.

**`n8n/workflows/alert_flow.json`** (exported, no secrets)

1. Webhook receives the alert.
2. "Open incident" runs one Postgres query. It inserts the incident, unless this outbox
   row already has one, and returns a `send` flag. `send` is true when the incident was
   just created, or when this row already has an incident but is still undelivered
   (a retry after a failed Telegram call). It is false for a real duplicate or for a row
   that is already delivered.
3. An IF node ("Send the message?") checks the `send` flag.
4. If true, a Switch node picks the message by severity and Telegram sends it. The text is
   one expression and goes out with `parse_mode` HTML, so sensor names like `air_temp_k`
   keep their underscores. The characters `&`, `<` and `>` are escaped.
5. Only after Telegram succeeded, Postgres marks the outbox row as delivered. For a real
   duplicate (the false branch) the row is marked delivered without a message.
6. The flow answers the monitor with 200.

If any step fails, for example the Telegram call, the run stops before step 6. In this
response mode n8n answers the webhook with HTTP 500 (read from the n8n 1.70.3 source), the
monitor sees the error and retries with backoff. The Telegram nodes have no error handling
on purpose: a failure must stop the flow.

**Credentials** are not in the JSON. `scripts/make_n8n_credentials.py` builds them
from your `.env` file, and n8n imports them at startup.

**`scripts/fake_telegram.py`** lets you try the whole flow without a Telegram bot. It prints
one line per request. With `FAKE_TELEGRAM_FAIL_FIRST=N` the first N requests answer HTTP
500, so you can test the failure case.

**`benchmark/`** measures the result: detection delay per fault, false alarms and
lost rows, compared with a baseline that only checks for silence. The live test runs
every fault and the clean run 5 times and saves each finished run, so it can be
stopped and continued. A run that took far longer than the replay (for example the
laptop slept) is thrown away and repeated.

## 3. Interview questions

1. **What is alert fatigue and how do you reduce it?**
   Too many repeated or useless alerts make people ignore all of them. Reduce it
   with dedupe, sensible thresholds and one alert per problem.

2. **What is your dedupe key?**
   Machine plus incident type, enforced with a unique index on open incidents.

3. **Explain the outbox pattern.**
   Write the message to your own database first, then deliver it in a separate
   step that retries on failure. The write is fast and local, so you do not lose
   the message when the target is down.

4. **What happens if n8n is down, or if Telegram fails inside n8n?**
   Ingestion is not affected. The monitor writes alerts to the outbox, delivery
   fails, the attempt counter goes up and the retry is scheduled with backoff.
   When n8n returns, the waiting alerts are delivered. If only the Telegram call fails,
   n8n answers with HTTP 500, the row stays undelivered and the retry sends the message
   again without a second incident.

5. **Why exponential backoff?**
   It gives a struggling system time to recover and avoids a flood of retries.

6. **What delivery guarantee do you give, and what does "delivered" mean?**
   At least once. A row is delivered only after Telegram answered with success and the
   outbox row was marked. If Telegram accepts the message and the marking step fails, the
   retry sends it twice. The incident is still written once, because the first query
   writes an incident only if this outbox row has none.

7. **Why keep the logic out of n8n?**
   Code can be unit tested, reviewed and versioned. Visual flows are hard to test.
   n8n stays a thin delivery layer that is easy to replace. The one rule that does live in the
   workflow (send or skip) is a single SQL query that I test on a database, and the
   workflow file itself is checked by tests that read the JSON.

8. **How do you detect a stuck sensor?**
   The same value many times in a row. Real signals vary slightly, so ten
   identical readings point to a frozen sensor. I check torque, rotational speed and
   process temperature. I left out air temperature after sliding a window over the
   real data: it has few distinct values and one machine repeats one value 10 times,
   which would be a false alarm. The alert message names the sensor.

9. **Why does the monitor read the database and not listen to MQTT?**
   The database is the single source of truth, and checks like "no data for 60
   seconds" are easy to answer with a query. It also keeps the monitor separate
   from ingestion, so one cannot break the other.

10. **How did you show the monitor is better than a simple check?**
    I compared it with a baseline that only alerts on silence. The baseline
    misses stuck and out-of-range sensors completely. The monitor finds them
    within one check interval. Both had zero false alarms on a clean run.

11. **How did you measure the detection delay on the real stack, and why repeat it?**
    Each fault and the clean run were replayed 5 times through the real containers,
    measuring from the row where the fault starts to the incident written by n8n.
    One run can be lucky, because the monitor checks every 5 seconds at a random
    moment. Five runs give a mean and a minimum and maximum. They are still my own
    simulated faults found by my own monitor, so they test the pipeline, not real plant data.

12. **What happens to a silence incident when a machine is dead for hours?**
    It stays open. The monitor keeps the last reading time of every machine over all
    history, so the machine does not fall out of the check. It closes when new data arrives.

## 4. Glossary

- **Alert fatigue**: people stop reacting because there are too many alerts.
- **Dedupe**: sending only one alert for the same problem.
- **Incident**: a recorded problem with an open and a resolved state.
- **Outbox pattern**: save the message in your own database first, deliver it afterwards.
- **Retry**: trying again after a failure.
- **Exponential backoff**: waiting longer after each failed attempt.
- **Webhook**: a URL that another system calls to trigger something.
- **Idempotent receiver**: a receiver that can safely get the same message twice.
- **Severity**: how serious an alert is (here: high or medium).
- **Threshold**: the limit that turns a measurement into an alert.
- **Baseline**: a simple method you compare your solution against.
- **False alarm**: an alert for something that is not a problem.
- **Detection delay**: time between the problem starting and the alert.
