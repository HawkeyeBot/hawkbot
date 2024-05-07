While Hawkbot is an incredibly powerful framework to write anything trading-related, it can be challenging to get started with writing a strategy
or a plugin for example.

In order to make use of all the rich features Hawkbot offers out of the box, it is important to understand a few basic components that are available
for you to use in your strategy.

One important thing to know is that your strategy is instantiated by Hawkbot. Along side this creation, there are certain objects that will get 
injected into your strategy if a variable is declared with specific names. The basic strategy class already has some of these fields defined by default,
making it easy for any strategy implementation to reach out to these.

The most important objects that are automatically injected into the strategy are the exchange state, the candlestore, the orderbook and the liquidationstore.

### Exchange state

A central element in Hawkbot is the exchange state object. This object is being maintained by Hawkbot internally to always represent the state on the exchange as
accurately as possible. This includes the orders currently on the exchange, position information, balances etc. Any strategy or plugin can always reach out to this object
at any time and as often as they like to get information on the state on the exchange. As a result of this, a strategy no longer has to actively get information
via REST calls from the exchange, causing unnecessary API weight, which can potentially lead into API bans.

### Candlestore

The candlestore is another crucial element in Hawkbot, which allows any strategy or plugin to retrieve any set of candles (kline) at any point in time. It is the
candlestore's responsibility to ensure that the correct candles are returned for any request. The candlestore will make sure to retrieve information from the exchange
if needed, stores candles into an sqlite database for easier access, processes data from websockets and ensures consistency in the stored data. Apart from that,
the candlestore also offers the option to register a listener, which will then be notified when a new candle is received from the websocket.
In short, the candlestore is your one-stop-shop for getting any candle information, ensuring efficient and swift processing.

### Orderbook

The orderbook is a representation of the orderbook on the exchange, automatically being kept in sync by Hawkbot. It provides an easy exchange-agnostic representation
of the orderbook that is both up-to-date and reachable with out any API penalty. The orderbook is kept in sync via websocket channels, and emits events as orderbook updates
are received. This actually allows a strategy to react to orderbook updates as they come in (every 100ms); one side-note with this is that any heavy processing can have
a detrimental effect on the strategy's performance.

### Liquidationstore

The liquidationstore is similar to the candlestore in a sense that it is a central place to retrieve liquidation data from. Liquidation data is received via websockets,
and the processed into the liquidationstore in an exchange-agnostic way. A strategy can register itself as a listener to liquidation events, making it possible to react to
these liquidation events as soon as they come in. Historic liquidation data can also be retrieved from the liquidationstore.