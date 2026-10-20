{{ config(severity='warn') }}

-- The public dataset is not perfectly clean: some rows say "machine failure" without any
-- failure mode, and some rows have a failure mode but no "machine failure".
-- This test only warns, so the problem is visible without stopping the build.

select machine_id, event_time, machine_failure, twf, hdf, pwf, osf, rnf
from {{ ref('stg_readings') }}
where (machine_failure = 1 and not has_failure_mode)
   or (machine_failure = 0 and has_failure_mode)
