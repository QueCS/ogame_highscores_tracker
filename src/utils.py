import glob
import os
import tomllib
import logging
from influxdb_client import InfluxDBClient
from influxdb_client_3 import InfluxDBClient3


def log_cleanup(log_dir):
    for old_log in glob.glob(os.path.join(log_dir, "*.log.old")):
        os.remove(old_log)
    for log in glob.glob(os.path.join(log_dir, "*.log")):
        os.rename(log, f"{log}.old")


def read_config_file():
    os.chdir(f"{os.path.dirname(__file__)}")
    with open("../config.toml", "rb") as config_file:
        config = tomllib.load(config_file)
        return config


def get_logging_config(config):
    log_dir = config.get("SCRIPT", {}).get("log_dir")
    log_lvl_str = config.get("SCRIPT", {}).get("log_lvl")
    module_name, attribute_name = log_lvl_str.rsplit(".", 1)
    log_lvl = getattr(logging, attribute_name)
    return log_dir, log_lvl


def get_influxdb_client(config):
    host = config.get("INFLUXDB", {}).get("host")
    org = config.get("INFLUXDB", {}).get("org")
    database = config.get("INFLUXDB", {}).get("database")
    token = config.get("INFLUXDB", {}).get("token")
    client = InfluxDBClient(token=token, org=org, url=host)
    return database, client


def get_influxdb_client_v3(config):
    host = config.get("INFLUXDB", {}).get("host")
    org = config.get("INFLUXDB", {}).get("org")
    database = config.get("INFLUXDB", {}).get("database")
    token = config.get("INFLUXDB", {}).get("token")
    client = InfluxDBClient3(token=token, org=org, host=host, database=database)
    return client


def get_ogame_config(config):
    servers = config.get("OGAME", {}).get("servers")
    cats = config.get("OGAME", {}).get("categories")
    typs = config.get("OGAME", {}).get("types")
    server_timezone = config.get("OGAME", {}).get("server_timezone")
    local_timezone = config.get("OGAME", {}).get("local_timezone")
    return servers, cats, typs, server_timezone, local_timezone


def typs_to_highscores(typs):
    typs_names = {
        0: "general",
        1: "economy",
        2: "research",
        3: "military",
        4: "mili_lost",
        5: "mili_built",
        6: "mili_destroyed",
        7: "honor",
        8: "lifeforms",
        9: "lf_economy",
        10: "lf_research",
        11: "lf_discovery",
    }
    highscores = [typs_names[t] for t in typs]
    return highscores
