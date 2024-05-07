The bot provides a core framework that supports all the flexibility a strategy could need to achieve it's goal.  
The strategy itself is called based on triggers as they occur, and the strategy can act on it as needed.

This opens up a lot of possibilities to write all sorts of different strategies (scalping, TA-based entry, DCA etc).  
The only limitation really is your own imagination!

To get an idea of the possibilities, there are a few example strategies included in the repository.

## Configuration

The framework works out of the box with a lot of default configuration, but these can all be overridden if needed.  
The sections [Command line arguments](#Command line arguments) and [Configuration file](#Configuration file)
describe the various available parameters

## Command line arguments

The parameters in the table below can be provided when starting the bot. An example of how to use these to override the
configuration file used by the bot:

    python3 trade.py -a -c my_custom_config_file.json

| property                  | type   | default value            | description                                   |
|---------------------------|--------|--------------------------|-----------------------------------------------|
| `-c` / `--config-file`    | string | `user_data/config.json`  | the config file to use                        |
| `-a` / `--account`        | string | none                     | the account alias to use                      |
| `-ac` / `--accountconfig` | string | `user_data/account.json` | the file to load the account information from | 
| `-l` / `--logfile`        | string | `logs/hawkbot.log`       | Specify the location of the logfile           |
| `--logging`               | string | `logging.yaml`           | Path to default logging configuration file    |                 
| `-W` / `--web`            | bool   | `false`                  | Enable the web UI                             |

## Configuration file

Apart from the parameters that can be passed to the command-line, the configuration json file allows further
configuration. The available configuration options
can be defined in 2 sections basically: the configuration of items in the core, and configuration items in the strategy.

## Logging

By default, the bot will output the logs in the logs in a rotating file logs/hawkbot.log.  
This file location can be overridden (see [Command line arguments](#Command line arguments)).  
The entire logging configuration is specified in the `logging.yaml` file found in the root of the project if you need
more modifications.
