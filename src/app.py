import os
import tomllib
from shiny import App, render, ui, reactive
from influxdb_client import InfluxDBClient
import logging

os.chdir(f"{os.path.dirname(__file__)}")

with open("../config.toml", "rb") as config_file:
    config = tomllib.load(config_file)


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


def get_ogame_config(config):
    servers = config.get("OGAME", {}).get("servers")
    typs = config.get("OGAME", {}).get("types")
    return servers, typs


log_dir, log_lvl = get_logging_config(config)
database, client = get_influxdb_client(config)
servers, typs = get_ogame_config(config)

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

query_api = client.query_api()


def run_query(bucket: str, server: str, player_id: str, highscore: str):
    query = f"""
    from(bucket: "{bucket}")
    |> range(start: -90d)
    |> filter(fn: (r) => r["server"] == "{server}")
    |> filter(fn: (r) => r["category"] == "player")
    |> filter(fn: (r) => r["_measurement"] ==  "{player_id}")
    |> filter(fn: (r) => r["type"] == "{highscore}")
    |> filter(fn: (r) => r["_field"] == "score")
    """
    result = query_api.query_data_frame(query=query)
    result = result.drop(columns=["result", "table", "_start", "_stop"])
    result = result.sort_values(by="_time", ascending=True)
    result["diff"] = result["_value"].diff().fillna(0).astype(int)
    result.insert(result.columns.get_loc("_value") + 1, "diff", result.pop("diff"))
    return result


app_ui = ui.page_fluid(
    ui.layout_sidebar(
        ui.sidebar(
            "Query parameters",
            ui.input_select("server", "Server", choices=servers),
            ui.input_select("highscore", "Highscore", choices=highscores),
            ui.input_text("player_id", "Player ID"),
            ui.input_action_button("run_query", "Run query"),
        ),
        ui.card(ui.output_data_frame("show_df")),
        ui.card(
            ui.download_link(id="dl_df", label="Download query as .csv"), max_height=60
        ),
    )
)


def server(input, output, session):
    @render.data_frame
    @reactive.event(input.run_query)
    def show_df():
        df = run_query(
            bucket=database,
            server=input.server._value,
            player_id=input.player_id._value,
            highscore=input.highscore._value,
        )
        return render.DataGrid(df, width=5000, height=1000)

    @render.download(filename="data.csv")
    def dl_df():
        df = run_query(
            bucket=database,
            server=input.server._value,
            player_id=input.player_id._value,
            highscore=input.highscore._value,
        )
        yield df.to_csv(index=False)


app = App(app_ui, server)
