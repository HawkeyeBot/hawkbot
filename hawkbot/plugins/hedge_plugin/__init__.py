"""
    The hedge plugin can be used to use a different grid configuration when a position gets stuck on one side. The idea behind this is that
    this will allow for faster entries to mitigate the stuck position by opening a position on the opposite positionside. Be aware that if
    done incorrectly, you risk getting stuck in reverse.

    The hedge plugin can be nicely combined with the Multisymbol autoreduce plugin, as it will enter faster and then use those profits for
    breaking down the stuck position.

    Note that while this plugin is parsed in the AbstractBaseStrategy, the usage is enforced in the BigLongStrategy and BigShortStrategy, as
    these process the NO_OPEN_POSITION trigger.

    Example: Activate on stuck
        The following plugin config will activate an alternate grid when a positionside exceeds 35% of the exposed balance. When this happens,
        it will place a grid 4% wide with 4 orders::

            "hedge": {
                "activate_hedge_above_wallet_exposure_pct": 35,
                "dca_config": {
                    "algo": "LINEAR",
                    "ratio_power": 1.4,
                    "nr_clusters": 4,
                    "outer_price_distance": 0.04
                }
            }

    Attributes:
        enabled (bool): indicates if the plugin is enabled or not. If not specified, the value is true by default if there is a 'hedge' block present in the strategy config, otherwise
                 the default is false
        first_order_type (str = LIMIT): specifies if the first order should be a limit order or a market order. Be aware that market orders are more expensive, but will guarantee
                                entry whereas limit orders are cheaper but may miss entry during fast moves
        activate_hedge_above_wallet_exposure_pct (float): activate the hedge plugin when the wallet exposure is bigger than this percentage of the
                                                        total exposed balance
        activate_hedge_above_upnl_pct (float): activate the hedge plugin when the UPNL percentage exceeds this amount
        dca_config (DcaConfig): specifies an alternate configuration for the grid to use when the hedge plugin is activated. For more information
                            on the configuration options for this block, please check the DCA plugin documentation

    """