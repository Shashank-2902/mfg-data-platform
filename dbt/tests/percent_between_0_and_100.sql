-- Fails if any percentage in the marts is outside 0 to 100.

select machine_id, 'downtime failure_percent' as column_name
from {{ ref('mart_downtime_per_machine') }}
where failure_percent < 0 or failure_percent > 100

union all

select machine_id, 'availability_percent'
from {{ ref('mart_oee_style_kpi') }}
where availability_percent < 0 or availability_percent > 100

union all

select machine_id, 'performance_percent'
from {{ ref('mart_oee_style_kpi') }}
where performance_percent < 0 or performance_percent > 100
