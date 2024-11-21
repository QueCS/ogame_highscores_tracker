from shiny import module, ui, render, reactive
import pandas as pd
import numpy as np


@module.ui
def table_ui(choices_01: list, choices_02: list):
    return ui.page_fluid(
        ui.layout_sidebar(
            ui.sidebar(
                "Query Parameters",
                ui.input_select("table_server", "Server", choices=choices_01),
                ui.input_select("table_highscore", "Highscore", choices=choices_02),
                ui.input_text("table_player_id", "Player ID"),
                ui.input_text("table_days", "Last n days", "90"),
                ui.input_action_button("table_run_query", "Run Query"),
                width=220,
            ),
            ui.output_data_frame("show_table"),
            height=1000,
        )
    )


def run_query_for_table(
    bucket: str, days: str, server: str, player_id: str, highscore: str, api
):
    query = f"""
    from(bucket: "{bucket}")
    |> range(start: -{days}d)
    |> filter(fn: (r) => r["server"] == "{server}")
    |> filter(fn: (r) => r["category"] == "player")
    |> filter(fn: (r) => r["_measurement"] ==  "{player_id}")
    |> filter(fn: (r) => r["type"] == "{highscore}")
    |> filter(fn: (r) => r["_field"] == "score" or r["_field"] == "rank")
    """
    query_df = api.query_data_frame(query=query)
    return query_df


def format_query_for_table(df: pd.DataFrame, local_tz: str, server_tz: str):
    points = df[df["_field"] == "score"].copy()
    ranks = df[df["_field"] == "rank"].copy()
    for df in [points, ranks]:
        df.rename(
            columns={
                "_time": "UTC Datetime",
                "_value": df["_field"].iloc[0].capitalize(),
            },
            inplace=True,
        )
        df.drop(
            columns=[
                "result",
                "table",
                "_start",
                "_stop",
                "_field",
                "category",
                "_measurement",
                "server",
                "type",
            ],
            inplace=True,
        )
    result = pd.merge(points, ranks, on=["UTC Datetime"])
    result = result.sort_values(by="UTC Datetime", ascending=True)
    result.insert(1, "Local Datetime", result["UTC Datetime"].copy())
    result.insert(2, "Server Datetime", result["UTC Datetime"].copy())
    result["Local Datetime"] = result["Local Datetime"].dt.tz_convert(f"{local_tz}")
    result["Server Datetime"] = result["Server Datetime"].dt.tz_convert(f"{server_tz}")
    result["Delta"] = result["Score"].diff().fillna(0).astype(int)
    result.insert(result.columns.get_loc("Score") + 1, "Delta", result.pop("Delta"))
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
    result.insert(result.columns.get_loc("Score"), "Rank", result.pop("Rank"))
    for col in ["Rank", "Score"]:
        if col in result.columns:
            result[col] = result[col].apply(lambda x: f"{int(x):,}".replace(",", " "))
    for col in ["Delta", "Total Delta"]:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"+ {int(x):,}".replace(",", " ")
                if x >= 0
                else f"- {-int(x):,}".replace(",", " ")
            )
    return result


@module.server
def table_server(input, output, session, bucket, api, local_tz, server_tz):
    @render.data_frame
    @reactive.event(input.table_run_query)
    def show_table():
        query_df = run_query_for_table(
            bucket=bucket,
            days=input.table_days._value,
            server=input.table_server._value,
            player_id=input.table_player_id._value,
            highscore=input.table_highscore._value,
            api=api,
        )
        df = format_query_for_table(query_df, local_tz=local_tz, server_tz=server_tz)
        return render.DataGrid(df, width="100%")
