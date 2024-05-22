"""
    The MultiAutoreducePlugin is a standalone plugin that can automatically reduce positions as they get into trouble using profits gained from any symbol running in the configuration.
    The plugin will periodically inspect all open positions to see if any are eligible for reduction, and if so, it will used gained profits to reduce the position with the biggest negative
    UPNL.

    Attributes:
        enabled (bool = true): indicates if the plugin is enabled or not. If not specified, the value is true by default if the plugin is present in the plugin config, otherwise
                 the default is false
        reduce_interval (str = "1m"): The frequency at which the plugin runs. Be careful if you set this very low, because it might have a severe impact on the rate limit load
        profit_percentage_used_for_reduction (float): Determines how much of the determined profit is used for reducing stuck positions as a ratio (meaning 1 == 100%)
        activate_size_above_exposed_balance_pct (float): Indicates that a position is eligible for reduction if the cost of the position (quantity * price) exceeds this percentage
                                                         of the exposed balance. An example to illustrate: if you're running a wallet balance of $1000, your wallet_exposure_ratio is
                                                         set to 2, and "activate_size_above_exposed_balance_pct" is set to 25, then the position will be eligible for reduction when
                                                         the cost of the position exceeds $500
        activate_above_upnl_pct (float): Indicates that a position is eligible for reduction if the UPNL percentage is bigger than this percentage. Please take note that the UPNL
                                         percentage takes leverage into account
        last_processed_income_file (str = "./data/multi_autoreduce_last_processed_income"): The file where the plugin stores the timestamp of the last time it processed the profits.
                                        Removing this file basically resets the plugin
        max_age_income (str = "3D"): The maximum age of income the plugin will consider. If no reduce is done for more than 3 days for example, it will not take into consideration any
                                     profit made more than 3 days ago


    Example: Minimum example
        The following plugin config will automatically reduce the position with the biggest drawdown for any position that exceeds more than 50% of it's exposed balance. The position
        will be reduced using 50% of the available made profit::

            "plugins": {
                "MultiAutoreducePlugin": {
                    "profit_percentage_used_for_reduction": 0.5,
                    "activate_size_above_exposed_balance_pct": 0.5
                }
            },

    Example: Complex example
        The following plugin config will reduce the position with the biggest drawdown for any position where the leveraged UPNL percentage is more than 200%. The position will be reduced
        using 80% of the gained profits, looking back at most the last 30 minutes. The inspection is ran every 15 seconds::

            "plugins": {
                "MultiAutoreducePlugin": {
                    "reduce_interval": "15s",
                    "profit_percentage_used_for_reduction": 0.8,
                    "activate_above_upnl_pct": 200
                }
            },

    """
