"""
    The DCA plugin is a flexible plugin that can be used to calculate the initial & DCA orders forming a complete grid.
    The configuration has a wide number of parameters, providing a flexible way of specifying how a grid of orders should be constructed.

    Typically, a grid is calculated using an outer price marking the boundary of how wide the grid should be, followed by a calculation
    of actual orders that will be placed from the current price all the way to the outer price.

    The outer price can be determined in a number of ways; it can be configured as a specific price, a specific distance from the current price
    in %, or it can be calculated dynamically based on a support/resistance level. Each of these are configurable via the outer_ parameters.

    The prices of the relevant levels where orders can be placed are stored, as well as a list of the quantities to use. The quantities and
    prices are stored separately, to allow a dynamic combination of the two in more complex scenarios like partial take-profits and automatic
    refills during a position's lifecycle.

    The calculation of the prices to use is performed by algos. When using an outer price, the algo calculates one or more prices from which
    the DCA plugin will pick the outer price for the grid. After that, another algo is used to calculate the prices inside the grid where the
    actual orders are placed.

    Example: Explicit outer price and linear grid
        The following snippet shows a DCA plugin configuration where an explicit outer price is used, a linear grid of 4 orders are placed
        to the outer price, and a ratio-power to calculate the quantities of each order::

            "dca": {
                "algo": "LINEAR",
                "ratio_power" 1.4,
                "nr_clusters": 4,
                "outer_price": 69892
            }

    Example: Desired position distance after DCA
        The following snippet shows a DCA plugin configuration where the quantity is governed by the desired position distance after each DCA.
        After a DCA is filled, the position distance will be 1% from where the last DCA was filled::

            "dca": {
                "algo": "LINEAR",
                "desired_position_distance_after_dca": 0.01,
                "nr_clusters": 4,
                "outer_price": 69892
            }

    Example: Outer price distance at 4%
        The following snippet shows a DCA plugin configuration where the outer price is set to a specific distance of 4% from the current price::

            "dca": {
                "algo": "LINEAR",
                "ratio_power" 1.4,
                "nr_clusters": 4,
                "outer_price_distance": 0.04
            }

    Example: Outer price distance up to 4h support maintaining a minimum of 7%
        The following snippet shows a DCA plugin configuration where the outer price is set dynamically to a support on the 4H chart, using the
        last 12 months of data. It will ensure the outer price is at least 7% wide. Within the boundary of the determined outer price, a grid of
        orders will be placed using the LIN_PEAKS_TROUGHS_HIGHLOW algo, which uses a linspace-division, looking for peaks/troughs based on the last
        3 month's 1m data. The quantities are determined by the initial entry size, and a static quantity multiplier::

            "dca": {
                "period": "3M",
                "period_timeframe": "1m",
                "algo": "LIN_PEAKS_TROUGHS_HIGHLOW",
                "nr_clusters": 7,
                "outer_price_level_nr": 1,
                "outer_price_period": "12M",
                "outer_price_timeframe": "4H",
                "outer_price_nr_clusters": 10,
                "outer_price_algo": "PEAKS_TROUGHS_HIGHLOW",
                "minimum_distance_to_outer_price": 0.07,
                "initial_entry_size": 0.01,
                "dca_quantity_multiplier": 1.2
            },

    Attributes:
        enabled (bool): indicates if the plugin is enabled or not. If not specified, the value is true by default if there is a 'dca' block present in the strategy config, otherwise
                 the default is false

        first_level_period (str): specifies the period of candles to use for the first-level grid. For example, `15D` will make it inspect the last 15 days of candles
        first_level_period_timeframe (Timeframe): the timeframe of the candles to use for the first-level grid. For example, `15m` will make it use 15-minute candles for the calculation
        first_level_algo (AlgoType): the type of algo to calculate the prices for the first-level grid
        first_level_nr_clusters (int): the nr of clusters (orders) to use for the first-level grid

        period (str): specifies the period of candles to use for the grid. For example, `15D` will make it inspect the last 15 days of candles
        period_timeframe (Timeframe): the timeframe of the candles to use for the grid. For example, `15m` will make it use 15-minute candles for the calculation
        algo (AlgoType): the type of algo to calculate the prices for the grid
        period_start_date (int): can be used instead of `period`; setting this date instead allows using all the candles from the specified date up to the current date
        nr_clusters (int): the nr of clusters (orders) to use for the grid

        outer_price (float): a specific price to use as the outer price for the grid width
        outer_price_distance (float): a specific distance from the current price for the grid width (for example, setting this at `0.052` will make the grid always 5.2% wide from
                                    the current price)
        outer_price_distance_from_opposite_position (float) a specific distance from the position price of the opposite position side (for example, setting this to '0.05' will use
                                    an outer price 5% above the opposition position price)
        outer_price_period (str): the period of candles to get when calculating a dynamic outer price
        outer_price_timeframe (Timeframe): the timeframe of candles to get when calculating a dynamic outer price
        outer_price_period_start_date (int): a specific starting date to get the candles from for calculating the outer price
        outer_price_algo (AlgoType): the algo to use to calculate the outer price
        minimum_distance_to_outer_price (float): if specified, the price chosen from the calculated outer prices will be at least this far away; if none is found, no grid will be
                                                placed
        maximum_distance_from_outer_price (float): if specified, the price chosen from the calculated outer prices will be at most this far away; if none is found, no grid will be
                                                placed
        outer_price_level_nr (int = 1): specifies which of the calculated prices is used for the outer price
        outer_price_nr_clusters (int): the nr of clusters (prices) to calculate from which the outer price can be selected
        minimum_distance_between_levels (float): TODO

        overlap (float = 0.001): TODO
        quantity_unit_margin (int = 2): TODO
        ratio_power (float): governs the quantity of each subsequent DCA order. Setting this to a higher value will bring the position price closer when a DCA is filled, at the
                            expense of the first orders being smaller
        maximum_position_coin_size (float): TODO
        desired_position_distance_after_dca (float): TODO
        initial_entry_size (float): when using the `dca_quantity_multiplier` parameter, this needs to be set to determine the initial entry size. This is a ratio of the exposed
                                balance, so for example setting this to 0.01 will make the first order 1% of the exposed balance
        previous_quantity_multiplier (float): the multiplier with which each subsequende DCA's order size is multiplied; this multiplier is applied on the quantity of the last
                                        calculated order quantity
        dca_quantity_multiplier (float): the multiplier with which each subsequent DCA order's size is multiplied; this multiplier is applied on the accumulated quantity of all
                                        orders up to that point
        minimum_number_dca_quantities (int = 15): TODO
        override_insufficient_levels_available (bool = False): TODO
        check_dca_against_wallet (bool = true): TODO
        allow_add_new_smaller_dca (bool = true): by default, this value is set to true. As a result, when a (partial) TP occurs freeing up sufficient funds, a new DCA order can
                                            automatically be placed on top
"""