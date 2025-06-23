import os
from utils import (
    read_config_file,
    get_logging_config,
    get_influxdb_config,
    get_ogame_config,
)
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
import json
import time
import logging
import logging.handlers
import itertools

os.chdir(f"{os.path.dirname(__file__)}")


def main():
    # Parse config file
    config = read_config_file()
    log_dir, log_lvl = get_logging_config(config)
    servers, cats, typs, server_timezone, local_timezone = get_ogame_config(config)
    url, org, bucket, token = get_influxdb_config(config)

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
            file_handler = logging.handlers.RotatingFileHandler(
                log_filename, maxBytes=1024 * 1024, backupCount=1
            )
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s - %(funcName)s(): %(message)s"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # Fetch data from API and update database
            data = fetch_api(server, cat, typ, logger)
            if data is None:
                # Detach logging handler to prevent duplicate logs and os.error "too many file opened"
                logger.removeHandler(file_handler)
                continue
            update_db(data, server, cat, typ, url, org, bucket, token, logger)

            # Detach logging handler to prevent duplicate logs and os.error "too many file opened"
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
    url: str,
    org: str,
    bucket: str,
    token: str,
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
                    Point(server)
                    .tag("player_id", player_id)
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
                    Point(server)
                    .tag("player_id", player_id)
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
                Point(server)
                .tag("alliance_id", alliance_id)
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
        influx_client = InfluxDBClient(url, token, org)
        influx_client.write_api(write_options=SYNCHRONOUS).write(bucket, org, points)
        logger.info("Done")
        return None
    except Exception as e:
        logger.error(f"Failed writing to database: {e}")
        return None


if __name__ == "__main__":
    main()
