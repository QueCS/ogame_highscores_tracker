import os
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

log_dir = config.get("SCRIPT", {}).get("log_dir")
log_lvl_str = config.get("SCRIPT", {}).get("log_lvl")
module_name, attribute_name = log_lvl_str.rsplit(".", 1)
log_lvl = getattr(logging, attribute_name)

host = config.get("INFLUXDB", {}).get("host")
org = config.get("INFLUXDB", {}).get("org")
database = config.get("INFLUXDB", {}).get("database")
token = config.get("INFLUXDB", {}).get("token")
client = InfluxDBClient3(token=token, org=org, host=host, database=database)


def main():
    servers = config.get("OGAME", {}).get("servers")
    cats = config.get("OGAME", {}).get("categories")
    typs = config.get("OGAME", {}).get("types")
    iterations = len(servers) * len(cats) * len(typs)
    for server, cat, typ in itertools.product(servers, cats, typs):
        process_task(server, cat, typ)
        time.sleep(900 / iterations)


def process_task(server, cat, typ):
    """
    Check if the API has been updated and updates the database accordingly.
    """
    logger = logging.getLogger(f"{server}_{cat}_{typ}_tracker")
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
    old_timestamp = 0
    data = fetch_api(server, cat, typ, logger)
    new_timestamp, api_updated = check_if_api_updated(data, old_timestamp, logger)
    if api_updated:
        old_timestamp = new_timestamp
        update_db(data, new_timestamp, server, cat, typ, client, logger)
        return True
    return False


def fetch_api(server: str, cat: str, typ: str, logger: logging.Logger) -> dict:
    """
    Fetches and returns OGame "highscores" API data.

    Args:
        server (str): The ID of the OGame server.
        cat (str): The highscore category.
        typ (str): The highscore type.

    Returns:
        data (dict): A dictionnary of the "highscores" API JSON response.

    Raises:
        requests.exceptions.RequestException: If there is an error while making the API request.
        json.JSONDecodeError: If the JSON-formatted data cannot be decoded into a Python object.
    """
    url = f"https://s{server}.ogame.gameforge.com/api/highscore.xml?toJson=1&category={cat}&type={typ}"
    logger.info(f"Fetching data from {url}.")
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed with status code: {e}.")
        return None
    if response.status_code != 200:
        logger.warning(f"Failed with status code: {response.status_code}.")
        return None
    logger.info("Successfully fetched data.")
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to decode JSON response: {e}.")
        return None
    logger.info("Successfully parsed data.")
    return data


def check_if_api_updated(
    data: dict, old_timestamp: int, logger: logging.Logger
) -> (int, bool):
    """
    Checks if the API data has been updated since the last fetch.

    Args:
        data (dict): A dictionnary of the "highscores" API JSON response.
        old_timestamp (int): The timestamp of the last fetched data.

    Returns:
        bool: True if the API data has been updated, False otherwise or if a KeError is raised.

    Raises:
        KeyError: If the "timestamp" key is not found in the "@attributes" section of the data.
    """
    try:
        new_timestamp = int(data["@attributes"]["timestamp"])
    except KeyError as e:
        logger.warning(f"Failed to find timestamp in API response: {e}.")
        return False
    if new_timestamp > old_timestamp:
        logger.info("API updated.")
        return new_timestamp, True
    else:
        logger.info("API not updated yet.")
        return old_timestamp, False


def update_db(
    data: dict,
    timestamp: int,
    server: str,
    cat: str,
    typ: str,
    db_client: InfluxDBClient3,
    logger: logging.Logger,
) -> None:
    logger.info("Parsing data and updating database...")
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
        logger.warning(f"Invalid highscore type: {typ}.")
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
        logger.warning(f"Invalid highscore category: {cat}.")
        highscore_category = "unknown"
    db_client.write(points)
    logger.info("Done !")


if __name__ == "__main__":
    main()
