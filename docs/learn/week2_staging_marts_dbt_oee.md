# Week 2: staging, marts, dbt tests and OEE

## 1. Concept

### Raw, staging and marts

Data usually goes through layers, each with one job:

- **Raw**: exactly what arrived. We never edit it. Here that is `raw_readings`.
- **Staging**: a cleaned copy, one-to-one with the raw table. Clear names, simple
  fixes, no business logic. Here that is the view `stg_readings`.
- **Marts**: tables built for a question someone asks. They aggregate and
  calculate. Here we have three:
  - `mart_downtime_per_machine`
  - `mart_failure_rate_by_type`
  - `mart_oee_style_kpi`

Why layers? If a number looks wrong you can walk back: mart, staging, raw. If the
raw format changes, you fix staging once and all marts keep working.

### What dbt does

**dbt** turns SQL `select` statements into tables and views, in the right order.
You write a model as a `select`. When one model uses another with `ref()`, dbt
learns the order and builds them one after the other. You never write
`CREATE TABLE` yourself.

### What dbt tests catch

A dbt test is a query that should return **zero rows**. If it returns rows, the
test fails and those rows are the problems. Types of tests used here:

- `not_null`: a column has no empty values.
- `unique`: a column has no repeats (for example one row per machine in a mart).
- `accepted_values`: a column only contains allowed values (for example
  `product_type` is L, M or H).
- **Singular tests**: your own SQL file in `dbt/tests/`.
  - percentages stay between 0 and 100
  - the marts have the same number of readings as staging (nothing lost)
  - the failure flag matches the failure modes (this one only **warns**)

The last one is a real finding. The public dataset has 27 rows that disagree with
themselves: 9 rows say "machine failure" but list no failure mode, and 18 rows
list a failure mode but are not marked as a failure. We keep the data as it is and
let the test warn. A warning keeps the problem visible without stopping the build.

### How OEE is calculated, and what this dataset can support

**OEE** (Overall Equipment Effectiveness) is the standard number for how well a
machine is used:

> OEE = availability x performance x quality

- **Availability**: how much of the planned time the machine actually ran.
- **Performance**: how fast it ran compared with its ideal speed.
- **Quality**: how many of the parts were good.

This dataset has failure flags and rotational speed. It has **no** scrap or
good-part counts, **no** planned production time and **no** ideal speed. So we can
only build an OEE-style number:

- availability = share of readings without a failure
- performance = average speed divided by a normal top speed (the 95th percentile)
- quality = not available, left out

The result is called `oee_style_percent` and the README says so. It is useful for
comparing machines inside this dataset. It is not a real plant OEE and should not
be presented as one.

Downtime is also an estimate. We assume one failure stops a machine for 30
minutes (the dbt variable `minutes_per_failure`). That number is ours, not the
data's.

## 2. Code walkthrough

**`dbt/dbt_project.yml`** sets the project name, the variable `minutes_per_failure`
and that staging models are views and marts are tables.

**`dbt/profiles.yml`** tells dbt how to connect. Host, user and password come from
environment variables, so no secret is stored in the file.

**`models/staging/`**

- `sources.yml` declares `raw_readings` as the source.
- `stg_readings.sql` selects the columns and adds `has_failure_mode`, which is
  true if any of the five failure-mode flags is set.
- `schema.yml` holds the tests for staging.

**`models/marts/`**

- `mart_downtime_per_machine.sql` groups by machine: readings, failures, estimated
  downtime minutes and failure percent.
- `mart_failure_rate_by_type.sql` counts each failure type with `union all` and
  divides by the number of readings to get failures per 1000.
- `mart_oee_style_kpi.sql` calculates availability, performance and the product.
- `schema.yml` holds the tests for the marts.

**`dbt/tests/`** has the three singular tests described above.

**`grafana/`** has the provisioned data source and the dashboard JSON. Grafana
reads the mart tables with plain SQL. Nothing needs to be clicked together by
hand, so anyone who runs `docker compose up` gets the same dashboard.

**Run it:** `docker compose run --rm dbt build` builds the models and runs the
tests in order.

## 3. Interview questions

1. **What is the difference between staging and marts?**
   Staging is a cleaned copy of one raw table with no business logic. Marts
   combine and aggregate data to answer a specific question.

2. **Why never edit the raw table?**
   It is the record of what really arrived. If you change it you cannot trace a
   wrong number back, and you cannot rebuild the layers from scratch.

3. **What does `ref()` do in dbt?**
   It points to another model and tells dbt that this model depends on it, so dbt
   builds them in the right order.

4. **How does a dbt test work?**
   It is a query that returns the bad rows. Zero rows means the test passes.

5. **Give an example of a data problem your tests found.**
   27 rows in the public dataset where the failure flag and the failure modes
   disagree. The test warns so the problem is visible.

6. **Why is that test a warning and not an error?**
   The data comes from outside and we do not own it. Stopping the whole build for
   a known issue in public data would make the pipeline useless, but hiding it
   would be wrong too.

7. **How is OEE calculated?**
   Availability times performance times quality.

8. **Why do you call your KPI "OEE-style"?**
   The dataset has no scrap data, no planned time and no ideal speed. Quality is
   missing and the other two parts are proxies, so it is not a true OEE.

9. **Why is downtime an estimate?**
   The data has no real stop times. We multiply the failure count by an assumed 30
   minutes, and that assumption is a setting you can change.

10. **How do you know the marts did not lose rows?**
    A singular test compares the sum of readings in the mart with the row count of
    staging. I also compared the mart numbers with a plain pandas count of the CSV.

## 4. Glossary

- **Raw layer**: data exactly as it arrived.
- **Staging**: a light cleanup of a raw table.
- **Mart**: a table prepared to answer one business question.
- **Model (dbt)**: a `select` statement that dbt turns into a table or view.
- **Source (dbt)**: a table dbt reads but does not build.
- **Materialization**: whether a model becomes a view or a table.
- **Singular test**: a custom SQL test file that returns bad rows.
- **Generic test**: a ready-made test such as `not_null` or `unique`.
- **OEE**: Overall Equipment Effectiveness, availability x performance x quality.
- **Availability / performance / quality**: the three parts of OEE.
- **Percentile**: the value below which a given share of the data falls (95th percentile: 95 percent are below).
- **Proxy**: a stand-in number used when the real one is not available.
