-- An OEE-style KPI for each machine.
--
-- OEE is availability x performance x quality. This dataset can only support two of them:
--   availability = share of readings without a failure
--   performance  = average speed compared with a normal top speed (95th percentile)
-- There is no scrap or good-part data, so quality is left out. Read the result as
-- "OEE without quality", not as a real plant OEE.

with per_machine as (
    select
        machine_id,
        count(*) as readings,
        sum(machine_failure) as failures,
        avg(rotational_speed_rpm) as average_rpm
    from {{ ref('stg_readings') }}
    group by machine_id
),

top_speed as (
    select percentile_cont(0.95) within group (order by rotational_speed_rpm) as top_rpm
    from {{ ref('stg_readings') }}
)

select
    per_machine.machine_id,
    round(100.0 * (per_machine.readings - per_machine.failures) / per_machine.readings, 2) as availability_percent,
    round(100.0 * least(per_machine.average_rpm / top_speed.top_rpm, 1)::numeric, 2) as performance_percent,
    round(
        ((per_machine.readings - per_machine.failures)::numeric / per_machine.readings)
        * least(per_machine.average_rpm / top_speed.top_rpm, 1)::numeric * 100,
        2
    ) as oee_style_percent
from per_machine
cross join top_speed
