from __future__ import annotations
from argparse import ArgumentParser, ArgumentTypeError


from pathlib import Path
import logging
import paho.mqtt.client as mqtt
from dataclasses import dataclass
import random

import serial
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class ClientConfig:
    client_id: str
    broker: str
    topic: str
    ca_cert_path: Path | str
    cert_dir: Path | str
    port: int = 8883


def create_client(config: ClientConfig) -> mqtt.Client:
    def on_connect(client: mqtt.Client, userdata, flags, rc):
        logging.info(
            f"[{config.client_id}] CONNECTED to {config.broker} with code {rc}"
        )

    def on_publish(client, userdata, mid):
        logging.debug(f"[{config.client_id}] Published message mid: {mid}")

    cert_dir = Path(config.cert_dir)

    certfile = cert_dir / "device.crt"
    keyfile = cert_dir / "device.key"

    client = mqtt.Client()
    client.tls_set(ca_certs=config.ca_cert_path, certfile=certfile, keyfile=keyfile)
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.connect(host=config.broker, port=config.port)

    return client


def mtls_cert_path(str_path: str) -> Path:
    cert_dir = Path(str_path)

    for file in ["device.crt", "device.key", "AmazonRootCA1.pem"]:
        if Path(cert_dir / file).exists():
            logging.info(f"Using {file} from {cert_dir}")
        else:
            raise ArgumentTypeError(f"No {file} found in {cert_dir}")

    return cert_dir


def get_timestamp_ms_bytes(n_bytes: int) -> bytes:
    timestamp_ms = int(time.time() * 1000)
    return timestamp_ms.to_bytes(n_bytes, byteorder="big")


def read_rtcm_packet(serial_port: serial.Serial) -> bytes:
    # First byte is RTCMv3 preamble
    logging.debug("Searching for preamble byte")
    while True:
        preamble = serial_port.read(1)

        if preamble == b"\xd3":
            logging.debug("Found preamble byte")
            break

    # Second two bytes are message length
    # The first six bits of the length are reserved and should be ignored
    reserved_and_length = serial_port.read(2)
    message_length = (
        int.from_bytes(reserved_and_length, byteorder="big") & 0x3FF
    )  # preserve last 10 bits

    # Message is variable length
    message = serial_port.read(message_length)

    # Final 3 bytes are CRC-24Q
    crc = serial_port.read(3)

    return preamble + reserved_and_length + message + crc


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--serial-port",
        help="Serial port to read RTCM packets from",
        default="/dev/ttyACM0",
    )
    parser.add_argument(
        "--baud-rate", help="Baud rate of serial port", default=115200, type=int
    )
    parser.add_argument(
        "--cert-path",
        help="Path to x509 certificates for MQTT mTLS",
        type=mtls_cert_path,
        required=True,
    )
    parser.add_argument("--mqtt-uri", help="URI of MQTT broker", required=True)
    parser.add_argument(
        "--mqtt-port", help="Port for MQTT broker", default=8883, type=int
    )
    parser.add_argument(
        "--mqtt-topic", help="MQTT topic to write RTCM packets", default="ntrip/data"
    )

    args = parser.parse_args()

    logging.info(f"Attaching to {args.serial_port} with baud rate {args.baud_rate}")

    ser = serial.Serial(args.serial_port, args.baud_rate)

    mqtt_config = ClientConfig(
        client_id=f"rtcm_mqtt_streamer{random.randint(10,99):02}",
        broker=args.mqtt_uri,
        ca_cert_path=args.cert_path / "AmazonRootCA1.pem",
        cert_dir=args.cert_path,
        topic=args.mqtt_topic,
    )
    mqtt_client = create_client(config=mqtt_config)

    try:
        ser.flushOutput()
        mqtt_client.loop_start()
        time.sleep(1)

        while True:
            rtcm_packet = read_rtcm_packet(ser)
            payload = get_timestamp_ms_bytes(16) + rtcm_packet

            mqtt_client.publish(topic=mqtt_config.topic, payload=payload, qos=1)
    except Exception as err:
        logging.error(f"Fatal error: {err}")
        logging.error("Shutting down...")
    except KeyboardInterrupt:
        print()
        logging.info("Received KeyboardInterrupt")
        pass
    finally:
        logging.info("Disconnecting from MQTT")
        mqtt_client.disconnect()
        logging.info("Closing serial port")
        ser.close()
