"""
    The TP plugin can be used to calculate take-profit orders. There are various configuration options to determine where the take-profit orders are to be placed.

    Example: Minimum example
        The following plugin config will place 1 take-profit order and place it at 0.28% distance from the position price::

            "tp": {
                "minimum_tp": 0.0028
            }

    Example: Grid of take-profit orders
        The following plugin config will place 3 take-profit orders, the first take-profit order placed at 0.28% distance from the position price,
        and the next 2 orders each placed 0.1% further away. This will lead to the orders being 0.28%, 0.38% and 0.48% from the position price::

            "tp": {
                "minimum_tp": 0.0028,
                "maximum_tp_orders": 3,
                "tp_interval": 0.001
            }

    Example: Trailing take-profit
        The following plugin config will place 1 take-profit order at 0.5% distance from the position price. Once the price goes beyond 0.19% in profit, it will place a stop-limit
        order at 0.14% behind the activation price (meaning at 0.05% from the position price). After this, it will move the stop-limit order at 0.2% from the current price. The
        close price is 3 times the price step behind the stop-limit price::

            "tp": {
                "minimum_tp": 0.005,
                "trailing_enabled": true,
                "trailing_activation_distance_from_position_price": 0.0019,
                "trailing_trigger_distance_from_current_price": 0.0014,
                "trailing_execution_distance_price_steps": 3,
                "trailing_shift_threshold": 0.002
            },

    Attributes:
        enabled (bool): indicates if the plugin is enabled or not. If not specified, the value is true by default if there is a 'tp' block present in the strategy config, otherwise
                 the default is false
        minimum_tp (float): specifies the distance from the position price at which the first take-profit order should be placed
        maximum_tp_orders (int = 1): the number of take-profit orders that should be placed. The number of orders will adhere to the minimum quantity and minimum notional,
                                 which could result in less orders than specified in this parameter.
        tp_interval (float): the distance to be maintained between the take-profit orders. This only applies when ```maximum_tp_orders``` is set to more than 1
        tp_when_wallet_exposure_at_pct (Dict[float, StaticTpConfig]): allows specifying a different TP distance based on the wallet exposure
        tp_at_upnl_pct (float): TODO
        trailing_enabled (bool = false): specifies if trailing is enabled or not
        trailing_activation_upnl_pct (float): dictates at which upnl percentage the trailing TP is activaed
        trailing_trigger_distance_upnl_pct (float): TODO
        trailing_shift_threshold_upnl_pct (float): TODO
        trailing_activation_distance_from_position_price (float): determines at which distance from the position price the trailing TP is activated
        trailing_trigger_distance_from_current_price (float): the distance that the trailing TP initially has from the current price when activated
        trailing_execution_distance_price_steps (int): determines how many quantity steps from the trigger price the sell (long) / buy (short) price is
        trailing_shift_threshold (float): the distance that the trailing TP maintains from the current price after activation
        allow_move_away (bool = false): a safety check to ensure a trailing TP order only moves in a more profitable direction; generally you won't need to set this unless you know
                                    what you're doing

    """