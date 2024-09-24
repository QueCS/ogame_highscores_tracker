import os
import tomllib
from influxdb_client_3 import InfluxDBClient3, Point, WritePrecision
import requests
import json
import time
import random
import logging

os.chdir(f"{os.path.dirname(__file__)}")

with open("../config.toml", "rb") as config_file:
    config = tomllib.load(config_file)

log_dir = config.get("SCRIPT", {}).get("log_dir")
log_lvl_str = config.get("SCRIPT", {}).get("log_lvl")
module_name, attribute_name = log_lvl_str.rsplit(".", 1)
log_lvl = getattr(logging, attribute_name)

logging.basicConfig(
    format="%(asctime)s %(levelname)s - %(funcName)s(): %(message)s",
    level=log_lvl,
    filename="../logs/tracker.log",
    filemode="a",
)

host = config.get("INFLUXDB", {}).get("host")
org = config.get("INFLUXDB", {}).get("org")
database = config.get("INFLUXDB", {}).get("database")
token = config.get("INFLUXDB", {}).get("token")
client = InfluxDBClient3(token=token, org=org, host=host, database=database)
