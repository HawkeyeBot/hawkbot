Hawkbot includes a backtester, that runs backtests based on aggregate trades. This allows it to be more
accurate than if it would only be using candles for backtesting. The downside of this is that it can be quite heavy to process
larger periods.

In order to start a backtest, you can run the following command:

`` python3 backtest.py -b <balance> -d <daterange>``

The daterange is specified as a `FROM-TO`, where `TO` is optional. The format of both of these elements is
`YYYYMMDDhhmm`, where at least the year and month are mandatory.

This will run the backtest, and produce a table-based overview in the console with an overview of the result.
Apart from this overview, a number of files are written in to the backtests folder with relevant information 
(for example the used config file with the used parameters, the overview in both txt & json format, the executed trades etc).

The backtest-command supports the following command-line arguments:

| property                      | type      | default value          | required | description                                              |
|-------------------------------|-----------|------------------------|----------|----------------------------------------------------------|
| `-d` / `--daterange`          | string    |                        | yes      | the startdate of the backtest, format: yyyyMMdd-yyyyMMdd |
| `-b` / `--balance`            | float     |                        | yes      | the balance to run the backtest with                     |
| `-c` / `--config`             | string    | user_data/config.json  | no       | the config file to use                                   |
| `-s` / `--show_chart`         | bool      | true                   | no       | open the generated charts                                |
| `-e` / `--exchange`           | string    | taken from config file | no       | the exchange to get the backtesting data from            |
| `-t` / `--backtest_timeframe` | timeframe | 1s                     | no       | the timeframe to execute the backtest with               |
| `-ct` / `--chart_timeframe`   | string    |                        | no       | the timeframe of the candle chart to show                |
| `--no_chart`                  | bool      |                        | no       | disable the charts                                       |