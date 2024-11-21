from shiny import module, ui, render, reactive
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


@module.ui
def analysis_ui(choices_01, choices_02):
    return ui.page_fluid(
        ui.layout_sidebar(
            ui.sidebar(
                "Query Parameters",
                ui.input_select("analysis_server", "Server", choices=choices_01),
                ui.input_select("analysis_highscore", "Highscore", choices=choices_02),
                ui.input_text("analysis_player_id", "Player ID"),
                ui.input_text("analysis_days", "Last n days", "90"),
                "Analysis parameters",
                ui.input_text("analysis_time_interval", "Time Interval (min)", "30"),
                ui.input_select(
                    "analysis_timezone",
                    "Timezone",
                    choices=["Server", "Local", "UTC"],
                ),
                ui.input_action_button("run_analysis", "Run Analysis"),
                width=220,
            ),
            ui.output_plot("show_analysis"),
            height=1000,
        )
    )


def run_query_for_analysis(
    bucket: str, days: str, server: str, player_id: str, highscore: str, api
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
    query_df = api.query_data_frame(query=query)
    return query_df


def format_query_for_analysis(df: pd.DataFrame, local_tz: str, server_tz: str):
    df.rename(
        columns={
            "_time": "UTC Datetime",
            "_value": "Score",
            "_measurement": "ID",
            "server": "Server",
            "type": "Highscore",
        },
        inplace=True,
    )
    df.drop(
        columns=["result", "table", "_start", "_stop", "_field", "category"],
        inplace=True,
    )
    result = df.sort_values(by="UTC Datetime", ascending=True)
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
    for col in ["Delta", "Total Delta"]:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"+ {int(x):,}".replace(",", " ")
                if x >= 0
                else f"- {-int(x):,}".replace(",", " ")
            )
    return result


def compute_analysis(tz: str, interval: int, df: pd.DataFrame):
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
        subset_df["Time Interval"] = subset_df[f"Rounded {tz} Datetime"].dt.strftime(
            "%H:%M"
        )
        counts = (
            subset_df.groupby("Time Interval")["Gained Points"].value_counts().unstack()
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


@module.server
def analysis_server(input, output, session, bucket, api, local_tz, server_tz):
    @render.plot
    @reactive.event(input.run_analysis)
    def show_analysis():
        query_df = run_query_for_analysis(
            bucket=bucket,
            days=input.analysis_days._value,
            server=input.analysis_server._value,
            player_id=input.analysis_player_id._value,
            highscore=input.analysis_highscore._value,
            api=api,
        )
        df = format_query_for_analysis(query_df, local_tz=local_tz, server_tz=server_tz)
        tz = input.analysis_timezone._value
        interval = int(input.analysis_time_interval._value)
        return compute_analysis(tz=tz, interval=interval, df=df)
