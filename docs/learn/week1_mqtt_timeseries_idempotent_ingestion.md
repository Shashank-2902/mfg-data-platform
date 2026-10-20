# Week 1: MQTT, time-series data and safe ingestion

## 1. Concept

### Why a message broker?

A factory has many machines and several programs that want their data. If every
machine talked directly to every program, the wiring would turn into a mess, and
one slow program could hold up the machine.

A **broker** sits in the middle. Machines (publishers) send messages to a named
topic. Programs (subscribers) tell the broker which topics they care about. The
broker passes the messages along. Neither side needs to know about the other.

**MQTT** is a small, lightweight protocol made for this. In this project:

- the replayer publishes to the topic `factory/readings`
- the ingest service subscribes to the same topic
- the broker is Mosquitto

MQTT can promise different levels of delivery. We use **QoS 1**, which means "at
least once". The broker confirms every message. If the confirmation is lost, the
message may arrive twice. This matters for the next section.

If the ingest service is stopped for a while, the broker can keep the messages in
a queue and hand them over later. That only works when the subscriber uses a fixed
client id and a persistent session, which ingest does.

### Time-series data versus normal tables

A normal table, like a list of customers, is mostly about the current state of
things. A time-series table is a long list of "what was measured, and when". It
grows all the time, rows are almost never changed, and questions are usually about
time ("what happened between 10:00 and 11:00?").

**TimescaleDB** is Postgres with extra features for this. Its main idea is the
**hypertable**: you use it like a normal table, but behind the scenes it is cut
into chunks by time (here, one chunk per day). Old chunks can be compressed or
dropped, and queries that filter by time only touch the chunks they need.

### Idempotent ingestion

An operation is **idempotent** when doing it twice gives the same result as doing
it once. For ingestion this means: if the same reading arrives two times, the
database still holds it once.

We need this because QoS 1 can deliver a message twice, and because we may replay
a file again by accident. Two things make it work here:

1. The primary key is `(machine_id, event_time)`. One machine cannot have two
   readings at the same moment.
2. The insert uses `ON CONFLICT DO NOTHING`. If the key already exists, the
   database skips the row instead of failing.

The replayer helps by making the fake timestamps the same every time. Row 7 is
always at the same fake time, so replaying it creates the same key.

### A note on honesty: the timestamps are made up

The public AI4I dataset has no time column and no machine column. The replayer
invents both: the rows are shared between five machines, and each row is 10
seconds after the one before. The README says "public data, synthetic timing".

### Rejecting versus judging

Ingest only checks the **shape** of a message: are all fields there, are the types
right, is the date a date. A message with the wrong shape goes into the table
`rejected_readings`, so nothing disappears silently.

Ingest does **not** judge whether a value makes sense. A temperature of 0 Kelvin
has a valid shape, so it is stored. The monitor (week 3) will notice it. This
keeps ingest simple and keeps the evidence of a broken sensor in the database.

## 2. Code walkthrough

**`replayer/`** reads the CSV and sends one message at a time.

- `data_reader.py` reads the file into a list of rows with simple names.
- `message_builder.py` adds `machine_id` and the fake `event_time` to a row.
- `fault_injector.py` can change or drop a message to simulate a broken machine
  (used in week 3).
- `mqtt_publisher.py` connects, publishes with QoS 1 and waits for the last
  confirmation before closing.
- `main.py` reads the options, loops over the rows, and sleeps between messages
  to keep the chosen rate. When the file ends it starts again, but the fake time
  keeps going, so the readings stay unique.

**`ingest/`** listens and stores.

- `validator.py` checks the shape of one message and returns a reason when it is
  wrong. Booleans are not accepted as numbers, because in Python `True` is also
  the number 1.
- `readings_db.py` has the SQL: insert a reading (skipping duplicates) and insert
  a rejected message.
- `handler.py` joins them: parse the JSON, validate, save. It returns "saved",
  "duplicate" or "rejected".
- `main.py` connects to MQTT and calls the handler for each message. If the
  database is down it waits and retries, so the message is not dropped.

**`db/init.sql`** creates the tables. It can be run more than once safely.

**Tests** in `tests/test_replayer.py` and `tests/test_ingest.py` check each piece,
including "the same reading twice is stored once".

## 3. Interview questions

1. **Why use a broker instead of letting machines write to the database directly?**
   The broker separates the machines from the consumers. You can add a second
   consumer, restart the database, or slow down the consumer without touching the
   machines, and the broker queues messages in between.

2. **What does QoS 1 mean, and what is the catch?**
   "At least once". The broker confirms each message, so nothing is lost, but a
   message can arrive twice. The consumer must handle duplicates.

3. **What does idempotent mean? Show an example from this project.**
   Doing it twice equals doing it once. Inserting with `ON CONFLICT DO NOTHING` on
   the key `(machine_id, event_time)` means a repeated reading changes nothing.

4. **Why is `(machine_id, event_time)` a good primary key here?**
   A machine can only produce one reading per moment, so it identifies a reading
   naturally. It also includes the time column, which TimescaleDB needs in a
   unique key on a hypertable.

5. **What is a hypertable?**
   A table that looks normal but is split into time chunks automatically. It keeps
   inserts and time-range queries fast as the data grows.

6. **Why is a time-series table different from a customers table?**
   It is append-only, grows constantly, and is queried by time. A customers table
   holds current state that is updated in place.

7. **What happens to messages if the ingest service is down?**
   With a persistent session and QoS 1, the broker queues them and delivers them
   when ingest reconnects.

8. **Why does ingest accept a reading with 0 Kelvin?**
   Ingest checks shape only. Judging values is the monitor's job. Keeping the bad
   value in the database also leaves evidence for later analysis.

9. **Why not drop invalid messages quietly?**
   You would never know data is missing or why. Storing them in
   `rejected_readings` with a reason makes problems visible.

10. **What are the limits of this setup?**
    One broker and one database, no authentication on the local broker, and
    synthetic timing and machine ids. It is a demo of the pattern, not a
    production plant system.

## 4. Glossary

- **Broker**: the server that receives messages and passes them to subscribers.
- **Publisher / subscriber**: the sender and the receiver of messages on a topic.
- **Topic**: the name messages are sent to, like `factory/readings`.
- **QoS**: quality of service, the delivery promise (0, 1 or 2).
- **Persistent session**: the broker remembers a subscriber and queues its messages while it is away.
- **Time series**: measurements ordered by time.
- **Hypertable**: a TimescaleDB table that is split into time chunks.
- **Chunk**: one time slice of a hypertable.
- **Idempotent**: safe to repeat, the result does not change.
- **Primary key**: the column(s) that identify a row uniquely.
- **Upsert / ON CONFLICT**: insert, but do something else (here: nothing) if the key exists.
- **Synthetic timing**: timestamps that were invented because the data had none.
