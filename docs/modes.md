Hawkbot has a concept of modes to enforce behavior when a specific mode is set. A mode can be set on a specific positionside of a specific symbol,
which means you can set different modes for different positions.

The following modes are currently supported:

## NORMAL

When the mode `NORMAL` is activated, the position is handled completely by the strategy.

## GRACEFUL_STOP

When the mode `GRACEFUL_STOP` is activated, Hawkbot will run the position as governed by the strategy. When the position is
closed however, Hawkbot will no longer call the strategy to open a new position. This mode can be used when you want to allow
a position to be closed gracefully, but have Hawkbot stop trading once it closes the position.

## EXIT_ONLY

When the mode `EXIT_ONLY` is activated, the strategy will only be able to perform actions on TP orders. As a result, the user
can manually set a DCA order, and the bot will not touch this order. It will however automatically adjust the TP order(s) 
when a DCA order is hit for example.

This mode is also very useful when manually entering positions, as the bot will automatically create the desired TP orders instantly.
An ideal aid for scalping manually

## MANUAL

When the mode `MANUAL` is activated, Hawkbot does not perform any interaction with the exchange. This mode can be useful
if you want to perform manual operations on the exchange, or if you want to override the orders placed by Hawkbot and prevent Hawkbot
from updating those orders again.

## PANIC

When the mode `PANIC` is activated, Hawkbot will try to close the position as fast as it can regardless of the cost. This
mode can be used for example when you expect a sudden heavy movement in the market, and just want to close your position
as fast as possible. Once the position is closed, Hawkbot will no longer allow a new position to be opened until the mode
is changed.

When activated via the web UI, the user can choose whether this is to be done using a limit order or by using a market order.

!!! Warning
    
    This mode can cause you to lose money instantly, use it with caution! 

## WIGGLE

When the mode `WIGGLE` is activated, Hawkbot will use the wiggle-plugin to sell & buy portions of the position in order to bring
the position price closer, while maintaining the same size. This can be useful when you know the position is about to retrace,
and you want to bring the position price closer to maximize profit made on the retrace.

!!! Warning
    
    This mode will take a loss in order to bring the position closer. When using futures you need to be extra careful, 
    because you need to make sure the wallet has enough funds to sustain the margin after closing a part of the position 