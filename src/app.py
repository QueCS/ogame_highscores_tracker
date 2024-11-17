import os
import tomllib
from shiny import App, render, ui, reactive
from influxdb_client import InfluxDBClient
import logging
import warnings
from influxdb_client.client.warnings import MissingPivotFunction
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

warnings.simplefilter("ignore", MissingPivotFunction)
pd.options.mode.copy_on_write = True

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
    server_timezone = config.get("OGAME", {}).get("server_timezone")
    local_timezone = config.get("OGAME", {}).get("local_timezone")
    return servers, typs, server_timezone, local_timezone


log_dir, log_lvl = get_logging_config(config)
database, client = get_influxdb_client(config)
servers, typs, server_timezone, local_timezone = get_ogame_config(config)

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


def run_query(
    bucket: str,
    server: str,
    player_id: str,
    highscore: str,
    server_tz: str,
    local_tz: str,
    days: str,
    format: bool,
):
    query = f"""
    from(bucket: "{bucket}")
    |> range(start: -{days}d)
    |> filter(fn: (r) => r["server"] == "{server}")
    |> filter(fn: (r) => r["category"] == "player")
    |> filter(fn: (r) => r["_measurement"] ==  "{player_id}")
    |> filter(fn: (r) => r["type"] == "{highscore}")
    |> filter(fn: (r) => r["_field"] == "score")
    """
    result = query_api.query_data_frame(query=query)
    result = result.drop(
        columns=["result", "table", "_start", "_stop", "_field", "category"]
    )
    result = result.rename(
        columns={
            "_time": "UTC Datetime",
            "_value": "Points",
            "_measurement": "ID",
            "server": "Server",
            "type": "Highscore",
        }
    )
    result = result.sort_values(by="UTC Datetime", ascending=True)
    result.insert(1, "Local Datetime", result["UTC Datetime"].copy())
    result.insert(2, "Server Datetime", result["UTC Datetime"].copy())
    result["Local Datetime"] = result["Local Datetime"].dt.tz_convert(f"{local_tz}")
    result["Server Datetime"] = result["Server Datetime"].dt.tz_convert(f"{server_tz}")
    result["Delta"] = result["Points"].diff().fillna(0).astype(int)
    result.insert(result.columns.get_loc("Points") + 1, "Delta", result.pop("Delta"))
    result["Total Delta"] = result["Delta"].cumsum()
    result.insert(
        result.columns.get_loc("Delta") + 1, "Total Delta", result.pop("Total Delta")
    )
    result["Gained Points"] = np.where(result["Delta"] > 0, 1, 0)
    result.insert(
        result.columns.get_loc("Total Delta") + 1,
        "Gained Points",
        result.pop("Gained Points"),
    )
    result["Day"] = result["Server Datetime"].dt.day_name()
    result.insert(
        result.columns.get_loc("Server Datetime") + 1,
        "Day",
        result.pop("Day"),
    )
    if format is True:
        for col in ["Points", "Delta", "Total Delta"]:
            if col in result.columns:
                if col == "Points":
                    result[col] = result[col].apply(
                        lambda x: f"{int(x):,}".replace(",", " ")
                    )
                else:
                    result[col] = result[col].apply(
                        lambda x: f"+ {int(x):,}".replace(",", " ")
                        if x >= 0
                        else f"- {-int(x):,}".replace(",", " ")
                    )
    return result


app_ui = ui.page_fluid(
    ui.layout_sidebar(
        ui.sidebar(
            "Query Parameters",
            ui.input_select("server", "Server", choices=servers),
            ui.input_select("highscore", "Highscore", choices=highscores),
            ui.input_text("player_id", "Player ID"),
            ui.input_text("days", "Last n days", "90"),
            ui.input_action_button("run_query", "Table"),
            "Analysis parameters",
            ui.input_text("time_interval", "Time Interval (min)", "15"),
            ui.input_select("timezone", "Timezone", choices=["Server", "Local", "UTC"]),
            ui.input_action_button("run_analysis", "Analysis"),
        ),
        ui.card(
            ui.download_link(id="dl_df", label="Download raw table as .csv"),
            max_height=60,
        ),
        ui.card(ui.output_plot("show_analysis"), width=5000, height=1100),
        ui.card(ui.output_data_frame("show_df"), width=5000, height=1200),
    )
)


def server(input, output, session):
    @render.download(filename="data.csv")
    def dl_df():
        df = run_query(
            bucket=database,
            server=input.server._value,
            player_id=input.player_id._value,
            highscore=input.highscore._value,
            server_tz=server_timezone,
            local_tz=local_timezone,
            days=input.days._value,
            format=False,
        )
        yield df.to_csv(index=False)

    @render.data_frame
    @reactive.event(input.run_query)
    def show_df():
        df = run_query(
            bucket=database,
            server=input.server._value,
            player_id=input.player_id._value,
            highscore=input.highscore._value,
            server_tz=server_timezone,
            local_tz=local_timezone,
            days=input.days._value,
            format=True,
        )
        return render.DataGrid(df, width=5000)

    @render.plot
    @reactive.event(input.run_analysis)
    def show_analysis():
        interval = int(input.time_interval._value)
        tz = str(input.timezone._value)
        df = run_query(
            bucket=database,
            server=input.server._value,
            player_id=input.player_id._value,
            highscore=input.highscore._value,
            server_tz=server_timezone,
            local_tz=local_timezone,
            days=input.days._value,
            format=False,
        )
        df = df[[f"{tz} Datetime", "Day", "Gained Points"]].copy()
        days = [
            day
            for day in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            if day in pd.unique(df["Day"])
        ]
        fig, axes = plt.subplots(nrows=len(days), ncols=1)

        for i, day in enumerate(days):
            subset_df = df[df["Day"].isin([day])]
            subset_df[f"Rounded {tz} Datetime"] = subset_df[f"{tz} Datetime"].dt.floor(
                f"{interval}min", ambiguous=True
            )
            subset_df["Time Interval"] = subset_df[
                f"Rounded {tz} Datetime"
            ].dt.strftime("%H:%M")
            counts = (
                subset_df.groupby("Time Interval")["Gained Points"]
                .value_counts()
                .unstack()
            )
            ax = counts.plot(kind="bar", stacked=True, ax=axes[i])
            if i != 0:
                ax.get_legend().remove()
            else:
                handles, labels = ax.get_legend_handles_labels()
                ax.get_legend().remove()
            ax.set_xlabel("")
            ax.set_ylabel("Count")
            ax.set_title(f"{day}s")
            time_labels = np.unique(subset_df["Time Interval"])
            ax.set_xticklabels(time_labels)
        fig.legend(handles, labels, loc="upper right", title="Gained Points")
        return fig


app = App(app_ui, server)
