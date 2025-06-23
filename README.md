# OGame highscores tracker
Python script to fetch player highscores from [OGame public APIs](https://forum.origin.ogame.gameforge.com/forum/thread/44-ogame-api/) and store them inside an [InfluxDB v2](https://www.influxdata.com) time series database.

## Requirements
- [Python 3.11.2](https://www.python.org/downloads/release/python-3112/)
- [InfluxDB v2](https://docs.influxdata.com/influxdb/v2/)

## Getting started
Install and configure InfluxDB as see fit.\
Clone the repository in the current directory, cd into it and create the `logs` directory.
```bash
git clone https://github.com/QueCS/ogame_highscores_tracker.git
cd ogame_highscores_tracker
mkdir logs
```
Set up a python virtual environment and install necessary dependencies.
```bash
python3 -m venv .venv
.venv/bin/pip3 install -r requirements.txt
```
Modify `config_example.toml` and save it as `config.toml`:
- `[INFLUXDB]`: Adjust to match your InfluxDB setup.
- `[SCRIPT]`: Adjust script parameters, can be left as is or modified.
- `[OGAME]`: Adjust which servers and highscores to track ([more information on highscores categories and types](https://s1-en.ogame.gameforge.com/api/highscore.xml?toJson=1&category=0&type=0)).

##  Running the script
Run the script manually or set up a [systemd](https://systemd.io/) service.

## One-liner installation (no systemd service)
```bash
cd $HOME
git clone https://github.com/QueCS/ogame_highscores_tracker.git
cd ogame_highscores_tracker
mkdir logs
python3 -m venv .venv
.venv/bin/pip3 install -r requirements.txt
```
Do not forget to modify `config_example.toml` and save it as `config.toml` before continuing.
```bash
nohup .venv/bin/python3 src/tracker.py 1> /dev/null 2> logs/tracker.log &
```

## One-liner installation (with systemd service)
```bash
git clone https://github.com/QueCS/ogame_highscores_tracker.git
cd ogame_highscores_tracker
mkdir logs
python3 -m venv .venv
.venv/bin/pip3 install -r requirements.txt
cat <<EOL | sudo tee /etc/systemd/system/ogame_highscores_tracker.service > /dev/null
[Unit]
Description=OGame Highscores Tracker
After=influxdb.service
Requires=influxdb.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
ExecStartPre=/bin/sh -c "until ping -c1 gameforge.com; do sleep 1; done;"
ExecStart=$PWD/.venv/bin/python3 $PWD/src/tracker.py
Restart=on-failure
StandardError=append:$PWD/logs/service.log

[Install]
WantedBy=multi-user.target
EOL
```
Do not forget to modify `config_example.toml` and save it as `config.toml` before continuing.
```bash
sudo systemctl daemon-reload
sudo systemctl enable ogame_highscores_tracker.service
sudo systemctl start ogame_highscores_tracker.service
```

## Disclaimer
[OGame](https://gameforge.com/play/ogame) is a registered trademark of [Gameforge Productions GmbH](https://gameforge.com).\
I am not affiliated with, endorsed by, or in any way connected to Gameforge Productions GmbH.
