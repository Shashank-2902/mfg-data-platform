import argparse
import os
import time

import data_reader
import fault_injector
import message_builder
import mqtt_publisher


def get_arguments():
    parser = argparse.ArgumentParser(description="Replay the AI4I dataset to MQTT.")
    parser.add_argument("--csv", default="/data/ai4i2020.csv")
    parser.add_argument("--rate", type=float, default=10, help="messages per second")
    parser.add_argument("--rows", type=int, default=0, help="stop after this many rows (0 = never stop)")
    parser.add_argument("--fault", choices=fault_injector.FAULTS, default="none")
    parser.add_argument("--fault-start-row", type=int, default=500)
    return parser.parse_args()


def main():
    args = get_arguments()
    rows = data_reader.read_rows(args.csv)
    print(f"Read {len(rows)} rows. Fault: {args.fault}. Timing is synthetic.")

    client = mqtt_publisher.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))

    memory = {}
    last_info = None
    index = 0
    while args.rows == 0 or index < args.rows:
        # When the file ends we start again, but the fake time keeps going.
        row = rows[index % len(rows)]
        message = message_builder.build_message(row, index)

        fault_started = index >= args.fault_start_row
        message = fault_injector.apply_fault(message, args.fault, fault_started, memory)

        if message is not None:
            last_info = mqtt_publisher.publish(client, message)

        index += 1
        if index % 500 == 0:
            print(f"Replayed {index} rows")
        time.sleep(1 / args.rate)

    mqtt_publisher.close(client, last_info)
    print(f"Done. Replayed {index} rows.")


if __name__ == "__main__":
    main()
