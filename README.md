# OGame highscores tracker

Python script to fetch player highscores from [OGame public APIs](https://forum.origin.ogame.gameforge.com/forum/thread/44-ogame-api/) and store them inside an [InfluxDB](https://www.influxdata.com/) time series database.\
Data can then be explored using the InfluxDB UI or CLI or using the provided [Shiny](https://shiny.posit.co/py/) web application.

## Getting started

Install and configure [InfluxDB](https://docs.influxdata.com/influxdb/v2/get-started/setup/) as see fit.

Clone the repository at the desired location.
```bash
git clone https://github.com/QueCS/ogame_highscores_tracker.git
```
\
Hop into it.
```bash
cd ogame_highscores_tracker
```
\
Set the appropriate python virtual environment used in further steps.
```bash
python3 -m venv .venv
```
\
Install necessary dependencies in the virtual environment.
```bash
.venv/bin/pip3 install -r requirements.txt
```
\
Modify the configuration file as see fit, keep it saved as `config.toml`:
- The `[INFLUXDB]` section must be adjusted to match your InfluxDB setup.
- The `[SCRIPT]` section configures scripts parmeters, can be left as is or modified.
- The `[OGAME]` section configures which OGame server and highscores to track ([more information on highscores categories and types](https://s1-en.ogame.gameforge.com/api/highscore.xml?toJson=1&category=0&type=0)) as well as what [timezones](https://mljar.com/blog/list-pytz-timezones/) to use when generating tables using the Shiny web application, can be left as is or modified.

##  Running the tracker

Launch `tracker.py` in the virtual environment.
```bash
.venv/bin/python3 src/tracker.py >> logs/tracker.log
```

##  Running the shiny web application

Launch `app.py` in the virtual environment.
```bash
.venv/bin/shiny run src/app.py >> logs/app.log
```
Note that you can adjust the host and port on which you want the webapp to be reachable by using the options `--host` and `--port`.

## Using the shiny web application

Enter necessary query parameters and click on the "Table", the "Analysis" button or both.

The generated analysis consist in a series of bar-charts indicating whether the player gained some points or not whithin the timeframe of your choice for each day of the week, combined. The idea is to easily spot basic player habbits patterns. Two additional parameters are specific to it. "Time interval (min)" allows to adjust the timeframe stringency. "Timezone" allows to run the analysis using either the game server timezone, your local timezone (as set in `config.toml`) or UTC.

The "Download raw table as .csv" link allows to download a raw table (without formating towards better readability) of the query result in order to perform additional manual data analysis if need be.

![Alt text](https://i.ibb.co/3WT50Qr/Capture-d-cran-du-2024-11-17-18-16-00.png)

The generated table is an easy-to-read summary of the query allowing to check point gain and loss of the chosen player.

![Alt text](https://i.ibb.co/1JyG2c3/Capture-d-cran-du-2024-11-17-18-16-42.png)

## One-liner installation

```bash
git clone https://github.com/QueCS/ogame_highscores_tracker.git && cd ogame_highscores_tracker && python3 -m venv .venv && .venv/bin/pip3 install -r requirements.txt
```

## Disclaimer

[OGame](https://gameforge.com/play/ogame) is a registered trademark of [Gameforge Productions GmbH](https://gameforge.com).\
I am not affiliated with, endorsed by, or in any way officially connected to Gameforge Productions GmbH.
