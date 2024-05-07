# Plugins

Hawkbot provides the ability to dynamically load different plugins as desired by a strategy or standalone.
A plugin has full access to any data & functionality provided by the core. Any relevant desired objects (like orderbook, exchange etc)
will be automatically injected by the framework if defined as a variable.

There are several plugins provided by default in Hawkbot, but custom plugins can be added by providing the desired 
plugin in the `user_data/plugins` folder. The following plugins (and likely others in the future) are provided by Hawkbot by default:

* Clustering support/resistance
* DCA
* Gridstorage
* GTFO
* Orderbook TP
* Profit transfer
* Rest server
* Score storage
* Stoploss
* Timeframe support/resistance
* TP
* TP refill
* Wiggle

For a description of each of the plugins you can check the Plugins section of the documentation
