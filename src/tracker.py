import os
import glob
import tomllib
from influxdb_client_3 import InfluxDBClient3, Point, WritePrecision
import requests
import json
import time
import logging
import itertools

os.chdir(f"{os.path.dirname(__file__)}")

with open("../config.toml", "rb") as config_file:
    config = tomllib.load(config_file)


def main():
    # Parse config file
    log_dir, log_lvl = get_logging_config(config)
    client = get_influxdb_client(config)
    servers, cats, typs = get_ogame_config(config)

    # Remove .log.old logs from log_dir
    log_cleanup(log_dir)

    # Indefinitely iterate over all combinations of server, category and type
    iterations = len(servers) * len(cats) * len(typs)
    while True:
        for server, cat, typ in itertools.product(servers, cats, typs):
            # Logging setup
            logger = logging.getLogger(f"{server}_{cat}_{typ}_logger")
            logger.setLevel(log_lvl)
            log_filename = f"{log_dir}/{server}_{cat}_{typ}_tracker.log"
            if not os.path.exists(os.path.dirname(log_filename)):
                os.makedirs(os.path.dirname(log_filename))
            file_handler = logging.FileHandler(log_filename)
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s - %(funcName)s(): %(message)s"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # Fetch data from API and update database
            data = fetch_api(server, cat, typ, logger)
            if data is None:
                continue
            update_db(data, server, cat, typ, client, logger)

            # Detach logging handler to prevent duplicate logs
            logger.removeHandler(file_handler)

            # Sleep so total loop time is ~15 minutes
            time.sleep(900 / iterations)
            continue


def fetch_api(server: str, cat: str, typ: str, logger: logging.Logger) -> dict | None:
    """
    Fetches and returns OGame "highscores" API data.

    Args:
        server (str): The ID of the OGame server.
        cat (str): The highscore category.
        typ (str): The highscore type.

    Returns:
        data (dict): A dictionnary of the "highscores" API JSON response.
        None if there is an error while making the API request or decoding the JSON-formatted data.

    Raises:
        requests.exceptions.RequestException: If there is an error while making the API request.
        json.JSONDecodeError: If the JSON-formatted data cannot be decoded into a Python object.
    """
    url = f"https://s{server}.ogame.gameforge.com/api/highscore.xml?toJson=1&category={cat}&type={typ}"
    logger.info(f"Fetching {url}")
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed fetching the API: {e}")
        return None
    if response.status_code != 200:
        logger.warning(f"Failed fetching the API: {response.status_code}")
        return None
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed decoding JSON response: {e}")
        return None
    logger.info("Successfully fetched API and parsed data")
    return data


def update_db(
    data: dict,
    server: str,
    cat: str,
    typ: str,
    db_client: InfluxDBClient3,
    logger: logging.Logger,
) -> None:
    logger.info("Parsing data and updating database")
    timestamp = int(data["@attributes"]["timestamp"])
    points = []
    if typ == 0:
        highscore_type = "general"
    elif typ == 1:
        highscore_type = "economy"
    elif typ == 2:
        highscore_type = "research"
    elif typ == 3:
        highscore_type = "military"
    elif typ == 4:
        highscore_type = "mili_lost"
    elif typ == 5:
        highscore_type = "mili_built"
    elif typ == 6:
        highscore_type = "mili_destroyed"
    elif typ == 7:
        highscore_type = "honor"
    elif typ == 8:
        highscore_type = "lifeforms"
    elif typ == 9:
        highscore_type = "lf_economy"
    elif typ == 10:
        highscore_type = "lf_research"
    elif typ == 11:
        highscore_type = "lf_discovery"
    else:
        logger.warning(f"Invalid highscore type: {typ}")
        highscore_type = "unkown"
    if cat == 1:
        highscore_category = "player"
        for player in data["player"]:
            if highscore_type == "military":
                player_id = int(player["@attributes"]["id"])
                rank = int(player["@attributes"]["position"])
                score = int(player["@attributes"]["score"])
                try:
                    ships = int(player["@attributes"]["ships"])
                except KeyError:
                    ships = 0
                point = (
                    Point(player_id)
                    .tag("server", server)
                    .tag("category", highscore_category)
                    .tag("type", highscore_type)
                    .field("rank", rank)
                    .field("score", score)
                    .field("ships", ships)
                    .time(timestamp, write_precision=WritePrecision.S)
                )
                points.append(point)
            else:
                player_id = int(player["@attributes"]["id"])
                rank = int(player["@attributes"]["position"])
                score = int(player["@attributes"]["score"])
                point = (
                    Point(player_id)
                    .tag("server", server)
                    .tag("category", highscore_category)
                    .tag("type", highscore_type)
                    .field("rank", rank)
                    .field("score", score)
                    .time(timestamp, write_precision=WritePrecision.S)
                )
                points.append(point)
    elif cat == 2:
        highscore_category = "alliance"
        for alliance in data["alliance"]:
            alliance_id = int(alliance["@attributes"]["id"])
            rank = int(alliance["@attributes"]["position"])
            score = int(alliance["@attributes"]["score"])
            point = (
                Point(alliance_id)
                .tag("server", server)
                .tag("category", highscore_category)
                .tag("type", highscore_type)
                .field("rank", rank)
                .field("score", score)
                .time(timestamp, write_precision=WritePrecision.S)
            )
            points.append(point)
    else:
        logger.warning(f"Invalid highscore category: {cat}")
        highscore_category = "unknown"
    try:
        db_client.write(points)
    except Exception as e:
        logger.error(f"Failed writing to database: {e}")
        return None
    logger.info("Done")
    return None


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
    client = InfluxDBClient3(token=token, org=org, host=host, database=database)
    return client


def get_ogame_config(config):
    servers = config.get("OGAME", {}).get("servers")
    cats = config.get("OGAME", {}).get("categories")
    typs = config.get("OGAME", {}).get("types")
    return servers, cats, typs


def log_cleanup(log_dir):
    for old_log in glob.glob(os.path.join(log_dir, "*.log.old")):
        os.remove(old_log)
    for log in glob.glob(os.path.join(log_dir, "*.log")):
        os.rename(log, f"{log}.old")


if __name__ == "__main__":
    main()
