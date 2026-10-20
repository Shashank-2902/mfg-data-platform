import csv


def read_rows(path):
    """Read the AI4I csv file and return a list of rows with simple names."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in csv.DictReader(f):
            rows.append({
                "udi": int(line["UDI"]),
                "product_type": line["Type"],
                "air_temp_k": float(line["Air temperature [K]"]),
                "process_temp_k": float(line["Process temperature [K]"]),
                "rotational_speed_rpm": int(line["Rotational speed [rpm]"]),
                "torque_nm": float(line["Torque [Nm]"]),
                "tool_wear_min": int(line["Tool wear [min]"]),
                "machine_failure": int(line["Machine failure"]),
                "twf": int(line["TWF"]),
                "hdf": int(line["HDF"]),
                "pwf": int(line["PWF"]),
                "osf": int(line["OSF"]),
                "rnf": int(line["RNF"]),
            })
    return rows
