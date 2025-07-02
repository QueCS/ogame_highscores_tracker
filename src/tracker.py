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
    last_server = None
    # Indefinitely iterate over all combinations of server, category and type
    iterations = len(servers) * len(cats) * len(typs)
    while True:
        for server, cat, typ in itertools.product(servers, cats, typs):
            # Logging setup
            logger = logging.getLogger(f"{server}_logger")
            logger.setLevel(log_lvl)
            log_filename = f"{log_dir}/{server}_tracker.log"
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
            # Fetch highscores_data from Highscores API and update database
            highscores_data = fetch_highscores_api(server, cat, typ, logger)
            if highscores_data is None:
                logger.warning("highscores_data is None")
                # Detach logging handler to prevent duplicate logs and os.error "too many file opened"
                logger.removeHandler(file_handler)
                time.sleep(1)
                continue
            highscores_to_db(
                highscores_data, server, cat, typ, url, org, bucket, token, logger
            )
            time.sleep(1)
            # Check if current iteration is on a new werver or not
            # If it is, update players and alliances attributes
            if server != last_server:
                players_data = fetch_players_api(server, logger)
                if players_data is None:
                    logger.warning("players_data is None")
                    logger.removeHandler(file_handler)
                    time.sleep(1)
                    continue
                players_attributes_to_db(
                    players_data, server, url, org, bucket, token, logger
                )
                time.sleep(1)
                alliances_data = fetch_alliances_api(server, logger)
                if alliances_data is None:
                    logger.warning("alliances_data is None")
                    logger.removeHandler(file_handler)
                    time.sleep(1)
                    continue
                alliances_attributes_to_db(
                    alliances_data, server, url, org, bucket, token, logger
                )
                time.sleep(1)
                last_server = server
            # Detach logging handler to prevent duplicate logs and os.error "too many file opened"
            logger.removeHandler(file_handler)
            # Sleep so total loop time is ~15 minutes
            time.sleep(900 / iterations)
            continue


def fetch_highscores_api(
    server: str, cat: str, typ: str, logger: logging.Logger
) -> dict | None:
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


def highscores_to_db(
    highscores_data: dict,
    server: str,
    cat: str,
    typ: str,
    url: str,
    org: str,
    bucket: str,
    token: str,
    logger: logging.Logger,
) -> None:
    """
    Parses the provided API data and updates the InfluxDB database accordingly.

    Args:
        data (dict): The data fetched from the OGame "highscores" API.
        server (str): The ID of the OGame server.
        cat (str): The highscore category.
        typ (str): The highscore type.
        url (str): The URL of the InfluxDB instance.
        org (str): The organization name in InfluxDB.
        bucket (str): The bucket name in InfluxDB.
        token (str): The authentication token for InfluxDB.
        logger (logging.Logger): The logger instance for logging messages.

    Returns:
        None

    Raises:
        Exception: If there is an error while writing to the database.
    """
    logger.info("Parsing highscores data and updating database")
    timestamp = int(highscores_data["@attributes"]["timestamp"])
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
        for player in highscores_data["player"]:
            player_id = str(player["@attributes"]["id"])
            rank = int(player["@attributes"]["position"])
            score = int(player["@attributes"]["score"])
            if highscore_type == "military":
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
        for alliance in highscores_data["alliance"]:
            alliance_id = str(alliance["@attributes"]["id"])
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


def fetch_players_api(server: str, logger: logging.Logger) -> dict | None:
    url = f"https://s{server}.ogame.gameforge.com/api/players.xml?toJson=1"
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
    return data


def players_attributes_to_db(
    players_data: dict,
    server: str,
    url: str,
    org: str,
    bucket: str,
    token: str,
    logger: logging.Logger,
) -> None:
    logger.info("Parsing players data and updating database")
    points = []
    timestamp = int(players_data["@attributes"]["timestamp"])
    for player in players_data["player"]:
        player_id = player["@attributes"]["id"]
        player_name = player["@attributes"].get("name")
        player_status = str(player["@attributes"].get("status", "A"))
        player_alliance_id = str(player["@attributes"].get("alliance"))
        logger.info(
            f"Successfully fetched players API and extracted player ({player_id}) attributes"
        )
        point = (
            Point(server)
            .tag("player_id", player_id)
            .tag("category", "player_attributes")
            .field("player_name", player_name)
            .field("player_status", player_status)
            .field("player_alliance_id", player_alliance_id)
            .time(timestamp, write_precision=WritePrecision.S)
        )
        points.append(point)
    try:
        influx_client = InfluxDBClient(url, token, org)
        influx_client.write_api(write_options=SYNCHRONOUS).write(bucket, org, points)
        logger.info("Done")
        return None
    except Exception as e:
        logger.error(f"Failed writing to database: {e}")
        return None


def fetch_alliances_api(server: str, logger: logging.Logger) -> dict | None:
    url = f"https://s{server}.ogame.gameforge.com/api/alliances.xml?toJson=1"
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
    return data


def alliances_attributes_to_db(
    alliances_data: dict,
    server: str,
    url: str,
    org: str,
    bucket: str,
    token: str,
    logger: logging.Logger,
) -> None:
    logger.info("Parsing alliances data and updating database")
    points = []
    timestamp = int(alliances_data["@attributes"]["timestamp"])
    for alliance in alliances_data["alliance"]:
        alliance_id = alliance["@attributes"]["id"]
        alliance_name = str(alliance["@attributes"].get("name"))
        alliance_tag = str(alliance["@attributes"].get("tag"))
        logger.info(
            f"Successfully fetched alliance API and extracted alliance ({alliance_id}) attributes"
        )
        point = (
            Point(server)
            .tag("alliance_id", alliance_id)
            .tag("category", "alliance_attributes")
            .field("alliance_name", alliance_name)
            .field("alliance_tag", alliance_tag)
            .time(timestamp, write_precision=WritePrecision.S)
        )
        points.append(point)
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
