import logging
from typing import Dict

import psutil
from flask import Flask, request

from hawkbot import __version__
from hawkbot.core.config.active_config_manager import ActiveConfigManager
from hawkbot.core.data_classes import ExchangeState
from hawkbot.core.mode_processor import ModeProcessor
from hawkbot.core.model import PositionSide, Mode, OrderType, BotStatus
from hawkbot.exchange.exchange import Exchange
from hawkbot.exchange.exchange_factory import create_exchange
from hawkbot.logging.user_log import LogCache
from hawkbot.utils import round_

logger = logging.getLogger(__name__)


class RestFlaskApp(Flask):
    def __init__(self, redis_host: str, redis_port: int, mode_processor: ModeProcessor):
        super().__init__(__name__, static_folder="./web", static_url_path="/")
        self.exchange_state = ExchangeState(redis_host=redis_host, redis_port=redis_port)
        self.bot_config = ActiveConfigManager(redis_host=redis_host, redis_port=redis_port)
        self.exchange: Exchange = create_exchange(config=self.bot_config, exchange_state=self.exchange_state)
        self.mode_processor = mode_processor
        self.user_log_cache: LogCache = LogCache(self.bot_config.user_log_cache_size)
        self.log_cache = LogCache(self.bot_config.memory_log_cache_size)
        self.add_url_rule(rule="/", view_func=self.index, methods=["GET"])
        self.add_url_rule(rule="/operating/overview", view_func=self.index, methods=["GET"])
        self.add_url_rule(rule="/health", view_func=self.health, methods=["GET"])
        self.add_url_rule(rule="/status", view_func=self.status, methods=["GET"])
        self.add_url_rule(rule="/positions", view_func=self.positions, methods=["GET"])
        self.add_url_rule(rule="/openOrders", view_func=self.open_orders, methods=["GET"])
        self.add_url_rule(rule="/latestOrders", view_func=self.latest_orders, methods=["GET"])
        self.add_url_rule(rule="/balance", view_func=self.balance, methods=["GET"])
        self.add_url_rule(rule="/resources", view_func=self.resources, methods=["GET"])
        self.add_url_rule(rule="/apiWeight", view_func=self.api_weight, methods=["GET"])
        self.add_url_rule(rule="/version", view_func=self.version, methods=["GET"])
        self.add_url_rule(rule="/user_logs", view_func=self.user_logs, methods=["GET"])
        self.add_url_rule(rule="/logs", view_func=self.logs, methods=["GET"])
        self.add_url_rule(rule="/all", view_func=self.all, methods=["GET"])
        self.add_url_rule(rule="/setMode", view_func=self.set_mode, methods=["POST"])
        self.add_url_rule(rule="/modes", view_func=self.get_modes, methods=["GET"])
        self.add_url_rule(rule="/cancelOrder", view_func=self.cancel_order, methods=["POST"])
        self.add_url_rule(rule="/closePosition", view_func=self.close_position, methods=["POST"])

    def index(self):
        return self.send_static_file('index.html')

    def health(self):
        return "OK"

    def status(self):
        try:
            return {"status": f"{BotStatus.RUNNING.name}"}
        except:
            logger.exception("Failed to create status information")
            return {"status": "UNKNOWN"}

    def positions(self):
        result = {}
        try:
            for symbol in self.bot_config.symbols:
                result[symbol] = {}
                for position_side in [PositionSide.LONG, PositionSide.SHORT]:
                    if self.bot_config.position_side_enabled(symbol=symbol, position_side=position_side):
                        symbol_information = self.exchange_state.get_symbol_information(symbol)
                        current_price = self.exchange_state.last_tick_price(symbol)
                        position = self.exchange_state.position(symbol=symbol, position_side=position_side)
                        if position.entry_price is None or position.entry_price == 0:
                            entry_price = ''
                            pnl_abs = ''
                            pnl_pct = ''
                            cost = ''
                        else:
                            entry_price = round_(position.entry_price, symbol_information.price_step)
                            leverage = self.bot_config.find_symbol_config(symbol).exchange_leverage
                            if leverage == "MAX":
                                leverage = self.exchange_state.get_symbol_information(symbol).max_leverage
                            pnl_pct = f'({round_(position.calculate_pnl_pct(current_price, leverage), 0.01)}%)'
                            pnl_abs = round_(position.calculate_pnl(current_price), 0.01)
                            cost = round_(position.cost, 0.01)

                        if current_price is None or current_price == 0:
                            current_price_str = ''
                        else:
                            current_price_str = round_(current_price, symbol_information.price_step)

                        data = {}
                        data['cost'] = f'{cost}'
                        data['entry_price'] = f'{entry_price}'
                        data['pnl_abs'] = f'{pnl_abs}'
                        data['pnl_pct'] = f'{pnl_pct}'
                        data['position_size'] = f'{position.position_size or ""}'
                        data['current_price'] = f'{current_price_str}'
                        data['mode'] = self.bot_config.active_mode(symbol=symbol, position_side=position_side).name
                        result[symbol][position_side.name] = data
        except:
            logger.exception("Failed to create positions data")
        return result

    def open_orders(self):
        orders = self.exchange_state.get_all_open_orders_by_symbol()
        result = {}
        try:
            for symbol in self.bot_config.symbols:
                symbol_information = self.exchange_state.get_symbol_information(symbol)
                result.setdefault(symbol, [])
                if symbol in orders:
                    for order in orders[symbol]:
                        order_content = {}
                        order_content['order_type_identifier'] = order.order_type_identifier.name
                        order_content['id'] = order.id
                        order_content['client_id'] = order.client_id
                        order_content['quantity'] = order.quantity
                        order_content['side'] = order.side.name
                        order_content['position_side'] = order.position_side.name
                        order_content['status'] = order.status.name
                        order_content['initial_entry'] = order.initial_entry
                        order_content['type'] = order.type.name
                        order_content['is_on_exchange'] = order.is_on_exchange
                        order_content['event_time'] = order.event_time
                        order_content['cost'] = round_(order.cost, 0.01)
                        order_content['price'] = f'{round_(order.price, symbol_information.price_step)}'

                        result[symbol].append(order_content)
        except:
            logger.exception('Failed to create open orders data')

        return result

    def latest_orders(self):
        filtered_orders = self.exchange_state.get_all_order_history()
        result = []
        try:
            filtered_orders.sort(key=lambda o: o.event_time, reverse=True)
            filtered_orders = filtered_orders[:10]

            for order in filtered_orders:
                symbol_information = self.exchange_state.get_symbol_information(order.symbol)
                order_content = {}
                order_content['order_type_identifier'] = order.order_type_identifier.name
                order_content['id'] = order.id
                order_content['client_id'] = order.client_id
                order_content['quantity'] = order.quantity
                order_content['side'] = order.side.name
                order_content['symbol'] = order.symbol
                order_content['position_side'] = order.position_side.name
                order_content['status'] = order.status.name
                order_content['initial_entry'] = order.initial_entry
                order_content['type'] = order.type.name
                order_content['is_on_exchange'] = order.is_on_exchange
                order_content['event_time'] = order.event_time
                order_content['cost'] = round_(order.cost, 0.01)
                order_content['price'] = f'{round_(order.price, symbol_information.price_step)}'

                result.append(order_content)
        except:
            logger.exception('Failed to create order history data')

        return result

    def balance(self):
        asset_balances = self.exchange_state.get_all_balances()
        result = {}
        try:
            for balance in asset_balances.values():
                result[balance.asset] = f'{balance.balance:f}'
        except:
            logger.exception("Failed to create balance data")

        return result

    def resources(self):
        result = {}

        try:
            result['CPU'] = f'{round(psutil.cpu_percent(), 1):4}%'
            result['Memory'] = f'{round(psutil.virtual_memory().percent, 1):3}%'

            try:
                result['IO/W'] = f'{round(psutil.cpu_times_percent().iowait, 2):4}%'
            except AttributeError:
                result['IO/W'] = '-%'
        except:
            logger.exception("Failed to create resource data")

        return result

    def api_weight(self):
        result = {}
        result['last'] = self.exchange.last_api_weight()
        result['max'] = self.exchange.max_api_weight()
        return result

    def version(self):
        return {"version": __version__}

    def user_logs(self):
        result = {'logs': [{"msg": l.msg, "level": l.level, "timestamp": l.timestamp}
                           for l in self.user_log_cache.log_cache]}
        return result

    def logs(self):
        result = {'logs': [{"msg": l.msg, "level": l.level, "timestamp": l.timestamp}
                           for l in self.log_cache.log_cache]}
        return result

    def all(self):
        result = {}
        logger.debug("Starting /all")
        logger.debug('Fetching status')
        result["status"] = self.status()
        logger.debug('Fetching positions')
        result["positions"] = self.positions()
        logger.debug('Fetching open orders')
        result["open_orders"] = self.open_orders()
        logger.debug('Fetching latest orders')
        result["latest_orders"] = self.latest_orders()
        logger.debug('Fetching balance')
        result["balance"] = self.balance()
        logger.debug('Fetching resources')
        result['resources'] = self.resources()
        logger.debug('Fetching api weight')
        result['api_weight'] = self.api_weight()
        logger.debug('Fetching version')
        result['version'] = self.version()
        logger.debug("Finished /all")
        return result

    def set_mode(self):
        request_body: Dict = request.get_json()
        if 'symbol' not in request_body:
            return "'symbol' is required", 400
        if 'position_side' not in request_body:
            return "'position_side' is required", 400
        if 'mode' not in request_body:
            return "'mode' is required", 400

        allowed_modes = [m.name for m in Mode]
        mode_to_set = request_body['mode']

        if mode_to_set not in allowed_modes:
            return f"Mode '{mode_to_set}' is not supported"

        symbol = request_body['symbol']
        position_side = PositionSide[request_body['position_side']]
        mode = Mode[mode_to_set]

        self.mode_processor.set_mode(symbol=symbol, position_side=position_side, mode=mode)

        return 'OK'

    def get_modes(self):
        result = {}
        for mode_iter in Mode:
            result[mode_iter.name] = mode_iter.value
        return result

    def cancel_order(self):
        request_body: Dict = request.get_json()
        if 'order_id' not in request_body:
            return "'order_id' is required", 400
        if 'symbol' not in request_body:
            return "'symbol' is required", 400

        order_id = request_body['order_id']
        symbol = request_body['symbol']
        self.exchange.cancel_order_by_id(symbol=symbol, order_id=order_id)

        return 'OK'

    def close_position(self):
        request_body: Dict = request.get_json()
        if 'symbol' not in request_body:
            return "'symbol' is required", 400
        if 'position_side' not in request_body:
            return "'position_side' is required", 400
        if 'orderType' not in request_body:
            return "'orderType' is required", 400

        symbol = request_body['symbol']
        position_side = PositionSide[request_body['position_side']]
        order_type = OrderType[request_body['orderType']]

        position = self.exchange_state.get_position(symbol).position(position_side)
        try:
            self.mode_processor.force_sell(symbol=symbol,
                                           position_side=position_side,
                                           position_size=position.position_size,
                                           order_type=order_type,
                                           rethrow_exception=True)
            return 'OK'
        except Exception as e:
            return f"Error: {e}", 400
