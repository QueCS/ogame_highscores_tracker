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
        logging.info("Successfully pased data.")
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
