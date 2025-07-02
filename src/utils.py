import os
import tomllib
import logging


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


def get_influxdb_config(config):
    url = config.get("INFLUXDB", {}).get("url")
    org = config.get("INFLUXDB", {}).get("org")
    bucket = config.get("INFLUXDB", {}).get("bucket")
    token = config.get("INFLUXDB", {}).get("token")
    return url, org, bucket, token


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
