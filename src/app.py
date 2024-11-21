import warnings
from influxdb_client.client.warnings import MissingPivotFunction
import pandas as pd
from app_utils import (
    read_config_file,
    get_logging_config,
    get_influxdb_client,
    get_ogame_config,
    typs_to_highscores,
)
from app_table import table_ui, table_server
from app_analysis import analysis_ui, analysis_server
from shiny import App, ui

warnings.simplefilter("ignore", MissingPivotFunction)
pd.options.mode.copy_on_write = True

config = read_config_file()
log_dir, log_lvl = get_logging_config(config)
database, client = get_influxdb_client(config)
servers, typs, server_timezone, local_timezone = get_ogame_config(config)
highscores = typs_to_highscores(typs)
query_api = client.query_api()

app_ui = ui.page_navbar(
    ui.nav_panel(
        "Analysis",
        analysis_ui("analysis", choices_01=servers, choices_02=highscores),
    ),
    ui.nav_panel(
        "Table",
        table_ui("table", choices_01=servers, choices_02=highscores),
    ),
)


def server(input, output, session):
    analysis_server(
        id="analysis",
        bucket=database,
        api=query_api,
        local_tz=local_timezone,
        server_tz=server_timezone,
    )
    table_server(
        id="table",
        bucket=database,
        api=query_api,
        local_tz=local_timezone,
        server_tz=server_timezone,
    )


app = App(app_ui, server)
