## Requirements

The bot requires Python 3.8 or later.

`requirements.txt` contains the dependencies.


## Quick startup procedure

* (If desired, create and activate a virtual environment)
* Install the requirements: `pip install -r requirements.txt`
* Copy the example account from `user_data/account.example.json` into `user_data/account.json` and modify it by entering API key and secret
* Copy the `pyarmor*.rkey` to the root folder of Hawkbot and rename it to `pyarmor.rkey`
* Launch the bot with `python3 trade.py -a <account alias>`

The account alias is can be found in the `user_data/account.json`. In the following example, the account alias is `binance_01`::
    
    "binance_01": {
        "exchange": "binance",
        "key": "",
        "secret": ""
    },

## The account file

The account file specifies the api key and secret per exchange.  
It can contain multiple exchange configurations, and the exchange specified in the config file 
defines which account information is actually used.

### Bybit unified account

If you're using a Unified Trading Account on bybit, make sure to set the unified flag to true in the `account.json` file::

    "bybit_01": {
        "exchange": "bybit",
        "key": "<your key>",
        "secret": "<your secret>",
        "unified": true
    },

## The config file

When starting the bot, it will load a configuration file containing the settings to run with. If not specified, Hawkbot will
try to load a file located at `user_data/config.json`. This location can be overriden by passing the `-c` when starting Hawkbot::

    python3 trade.py -a <account_alias> -c user_data/my_custom_config.json

## License file

When starting the bot, you will need to have a license file. You can get one by joining the [Discord - Hawkbot](https://discord.gg/45aRPz3QmQ) server.