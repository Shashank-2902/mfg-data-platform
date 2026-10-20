-- Failures and estimated downtime for each machine.
-- Downtime is an estimate: failures times the minutes_per_failure variable.

select
    machine_id,
    count(*) as readings,
    sum(machine_failure) as failures,
    sum(machine_failure) * {{ var('minutes_per_failure') }} as downtime_minutes,
    round(100.0 * sum(machine_failure) / count(*), 2) as failure_percent
from {{ ref('stg_readings') }}
group by machine_id
