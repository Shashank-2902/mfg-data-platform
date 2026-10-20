-- Fails if the mart loses or invents rows compared with staging.

select 'row count differs' as problem
from (
    select
        (select count(*) from {{ ref('stg_readings') }}) as staging_rows,
        (select sum(readings) from {{ ref('mart_downtime_per_machine') }}) as mart_rows
) t
where staging_rows <> mart_rows
