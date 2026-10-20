-- Clean version of the raw readings: same rows, clear names, one extra helper column.

select
    machine_id,
    event_time,
    received_at,
    udi,
    product_type,
    air_temp_k,
    process_temp_k,
    rotational_speed_rpm,
    torque_nm,
    tool_wear_min,
    machine_failure,
    twf,
    hdf,
    pwf,
    osf,
    rnf,
    (twf + hdf + pwf + osf + rnf) > 0 as has_failure_mode
from {{ source('raw', 'raw_readings') }}
