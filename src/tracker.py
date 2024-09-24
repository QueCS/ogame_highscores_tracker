import os
import tomllib
from influxdb_client_3 import InfluxDBClient3, Point, WritePrecision
import requests
import json
import time
import random
import logging
import threading

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

logging.basicConfig(
    format="%(asctime)s %(levelname)s - %(funcName)s(): %(message)s",
    level=log_lvl,
    filename=f"{log_dir}",
    filemode="a",
)


def main():
    servers = config.get("OGAME", {}).get("servers")
    cats = config.get("OGAME", {}).get("categories")
    typs = config.get("OGAME", {}).get("types")
    threads = []
    for server in servers:
        for cat in cats:
            for typ in typs:
                thread = threading.Thread(target=process_task, args=(server, cat, typ))
                thread.start()
                threads.append(thread)
    for thread in threads:
        thread.join()


def process_task(server, cat, typ):
    """
    Infinitely loops to check if the API has been updated and updates the database accordingly.
    """
    old_timestamp = 0
    while True:
        time.sleep(random.randrange(30, 60, 1))
        data = fetch_api(server, cat, typ)
        new_timestamp, api_updated = check_if_api_updated(data, old_timestamp)
        if api_updated:
            old_timestamp = new_timestamp
            update_db(data, new_timestamp, server, cat, typ, client)
            sleep_time = new_timestamp + 3600 - time.time()
            if sleep_time < 0:
                continue
            else:
                time.sleep(sleep_time)
                continue
        else:
            continue


def fetch_api(server: str, cat: str, typ: str) -> dict:
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
    while True:
        time.sleep(random.randrange(30, 60, 1))
        logging.info(f"Fetching data from {url}.")
        try:
            response = requests.get(
                url,
            )
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed with status code: {e}. Trying again.")
            continue
        if response.status_code != 200:
            logging.warning(
                f"Failed with status code: {response.status_code}. Trying again."
            )
            continue
        logging.info("Successfully fetched data.")
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to decode JSON response: {e}. Trying again.")
            continue
        logging.info("Successfully parsed data.")
        return data
        break


def check_if_api_updated(data: dict, old_timestamp: int) -> (int, bool):
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
        logging.warning(f"Failed to find timestamp in API response: {e}.")
        return False
    if new_timestamp > old_timestamp:
        logging.info("API updated.")
        return new_timestamp, True
    else:
        logging.info("API not updated yet. Trying again.")
        return old_timestamp, False


def update_db(
    data: dict,
    timestamp: int,
    server: str,
    cat: str,
    typ: str,
    db_client: InfluxDBClient3,
) -> None:
    logging.info("Parsing data and updating database...")
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
        logging.warning(f"Invalid highscore type: {typ}.")
        highscore_type = "unkown"
    if cat == 1:
        highscore_category = "player"
        for player in data["player"]:
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
            client.write(point)
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
            client.write(point)
    else:
        logging.warning(f"Invalid highscore category: {cat}.")
        highscore_category = "unknown"


if __name__ == "__main__":
    main()
