# Example configs

On this page you'll find a few example configurations, showing commonly used functionality and configurations that have been used in the past
that are usefull as starting point for creating your own configurations

## Support-resistance based grid

The configuration below will make Hawkbot trade on a fixed set of symbols, trading both long & short at the same time. The grid will be based
on 4H support & resistance levels, placing 7 orders in each grid. The total wallet exposure for longs will be 1, while the total wallet
exposure of shorts is 0.8.

This configuration is considered a safe setup, but requires a decently sized wallet ($10K+) due to minimum notional on exchanges. Obviously you
can increase the `wallet_exposure_ratio` to gain more profits, but this will also increase risks. This configuration can be enhanced by adding
the MultiAutoreduceplugin to the configuration so it automatically starts reducing stuck positions.

??? note "config.json"
    ```json
    {
      "hedge_mode": true,
      "persisted_tick_purge_expiry_time": "5m",
      "symbol_configs": [
        {
          "symbol": [
            "CHZUSDT",
            "DOTUSDT",
            "DOGEUSDT",
            "AVAXUSDT",
            "ETCUSDT",
            "LINKUSDT",
            "ADAUSDT",
            "XRPUSDT"
          ],
          "exchange_leverage": 10,
          "long": {
            "enabled": true,
            "strategy": "BigLongStrategy",
            "mode": "NORMAL",
            "wallet_exposure_ratio": 0.125,
            "strategy_config": {
              "entry_order_type": "LIMIT",
              "cancel_orders_on_position_close": true,
              "limit_orders_reissue_threshold": 0.003,
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
                "ratio_power": 0.8
              },
              "tp": {
                "minimum_tp": 0.0028
              }
            }
          },
          "short": {
            "enabled": true,
            "strategy": "BigShortStrategy",
            "mode": "NORMAL",
            "wallet_exposure_ratio": 0.1,
            "strategy_config": {
              "entry_order_type": "LIMIT",
              "cancel_orders_on_position_close": true,
              "limit_orders_reissue_threshold": 0.003,
              "dca": {
                "period": "3M",
                "period_timeframe": "1m",
                "algo": "LIN_PEAKS_TROUGHS_HIGHLOW",
                "nr_clusters": 7,
                "outer_price_level_nr": 2,
                "outer_price_period": "12M",
                "outer_price_timeframe": "4H",
                "outer_price_nr_clusters": 10,
                "outer_price_algo": "PEAKS_TROUGHS_HIGHLOW",
                "minimum_distance_to_outer_price": 0.1,
                "ratio_power": 0.55
              },
              "tp": {
                "minimum_tp": 0.0022
              }
            }
          }
        }
      ]
    }
    ```

## Tight manual grid

The configuration below shows a setup that trades much more aggressively using a fixed-distance grid trading both long & short. The stoploss is disabled
in this configuration, but can simply be enabled by changing the `enabled` field for the stoploss config to `true`.
The configuration trades using a grid of 5 orders, but has an aggressive `ratio_power` value, sticking very close to the price action even in volatile times.
This configuration is a good starting point if you want to run grids specific to the momentum of a coin.

??? note "config.json"
    ```json
    {
      "hedge_mode": true,
      "multicore": false,
      "state_synchronize_interval_s": 5,
      "initial_entry_block_ms": 11000,
      "override_max_exposure_ratio_check": true,
      "persisted_tick_purge_expiry_time": "5m",
      "symbol_configs": [
        {
          "symbol": [
            "ANKRUSDT"
          ],
          "long": {
            "enabled": true,
            "strategy": "BigLongStrategy",
            "tick_execution_interval_ms": 250,
            "wallet_exposure_ratio": 12,
            "strategy_config": {
              "entry_order_type": "LIMIT",
              "limit_orders_reissue_threshold": 0.00001,
              "repost_lower_allowed": false,
              "dca": {
                "period": "3D",
                "period_timeframe": "1m",
                "algo": "LINEAR",
                "nr_clusters": 5,
                "outer_price_distance": 0.042,
                "ratio_power": 1.5,
                "allow_add_new_smaller_dca": false
              },
              "tp": {
                "minimum_tp": 0.0025
              },
              "stoploss": {
                "enabled": false,
                "last_entry_trigger_distance": 0.01,
                "post_stoploss_mode": "MANUAL",
                "order_type": "STOP"
              }
            }
          },
          "short": {
            "enabled": true,
            "strategy": "BigShortStrategy",
            "tick_execution_interval_ms": 250,
            "wallet_exposure_ratio": 12,
            "strategy_config": {
              "entry_order_type": "LIMIT",
              "limit_orders_reissue_threshold": 0.00001,
              "repost_higher_allowed": false,
              "dca": {
                "period": "3D",
                "period_timeframe": "1m",
                "algo": "LINEAR",
                "nr_clusters": 5,
                "outer_price_distance": 0.042,
                "ratio_power": 1.5,
                "allow_add_new_smaller_dca": false
              },
              "tp": {
                "minimum_tp": 0.0025
              },
              "stoploss": {
                "enabled": false,
                "last_entry_trigger_distance": 0.01,
                "post_stoploss_mode": "MANUAL",
                "order_type": "STOP"
              }
            }
          }
        }
      ]
    }
    ```