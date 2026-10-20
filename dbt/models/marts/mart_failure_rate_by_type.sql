-- How often each failure type happens, per 1000 readings.

with readings as (
    select * from {{ ref('stg_readings') }}
),

total as (
    select count(*) as readings from readings
),

failures as (
    select 'Any failure' as failure_type, sum(machine_failure) as failures from readings
    union all
    select 'TWF tool wear', sum(twf) from readings
    union all
    select 'HDF heat dissipation', sum(hdf) from readings
    union all
    select 'PWF power', sum(pwf) from readings
    union all
    select 'OSF overstrain', sum(osf) from readings
    union all
    select 'RNF random', sum(rnf) from readings
)

select
    failures.failure_type,
    failures.failures,
    total.readings,
    round(1000.0 * failures.failures / total.readings, 2) as failures_per_1000
from failures
cross join total
order by failures.failures desc
