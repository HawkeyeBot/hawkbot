Hawkbot provides an abstraction layer on exchange-implementations, making sure that the rest of the code doesn't need to know exchange-specific details.
This allows for example the core, plugins and strategies to interact with and receive updates from exchange-related information in a more abstract way.

Currently, the following exchanges are implemented:

| Exchange        | configuration key | 
|-----------------|-------------------|
| Binance futures | `binance`         |
| Binance testnet | `binance-testnet` |              
| Binance spot    | `binance-spot`    |
| Bybit           | `bybit`           |                 
| Bybit testnet   | `bybit-testnet`   |

If you have a desire to have a new exchange added you can reach out to discuss. Implementing a new exchange (be it crypto, forex or whatever) requires implementing
the exchange-interface for that specific exchange.

In the past, CCXT has been looked into to provide access to many exchanges with just 1 implementation. After some experiments however, it turned out that
while CCXT provides a nice abstraction layer, there were too many exchange-specific anomalies and lack of certain fundamental exchange-specific aspects.
As a result, the implementations for each exchange are specific, causing a bit more technical work, but allowing far better fine-grained control over the 
actual implementation.