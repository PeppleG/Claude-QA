"""
Polymarket API client for market data and order execution.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any, Callable, Optional
import logging

import aiohttp
import websocket
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from ..config import APIConfig
from ..models import Market, Order, OrderType, OrderStatus, Side, Position

logger = logging.getLogger(__name__)


class PolymarketClient:
    """
    Client for interacting with Polymarket's CLOB API.

    Supports:
    - REST API for market data and order execution
    - WebSocket for real-time price updates
    """

    BITCOIN_KEYWORDS = [
        "bitcoin", "btc", "crypto", "cryptocurrency",
        "satoshi", "blockchain", "halving"
    ]

    def __init__(self, config: APIConfig):
        self.config = config
        self.base_url = config.polymarket_base_url
        self.ws_url = config.polymarket_ws_url
        self.api_key = config.polymarket_api_key
        self.api_secret = config.polymarket_api_secret
        self.private_key = config.private_key

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[websocket.WebSocket] = None
        self._ws_callbacks: dict[str, list[Callable]] = {}
        self._running = False

        # Initialize Web3 for signing
        if self.private_key:
            self.account = Account.from_key(self.private_key)
            self.address = self.account.address
        else:
            self.account = None
            self.address = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        """Initialize HTTP session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=self._get_headers()
            )
        logger.info("Polymarket client connected")

    async def disconnect(self):
        """Close HTTP session and WebSocket."""
        if self._session:
            await self._session.close()
            self._session = None
        if self._ws:
            self._ws.close()
            self._ws = None
        self._running = False
        logger.info("Polymarket client disconnected")

    def _get_headers(self) -> dict:
        """Get API request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["POLY_API_KEY"] = self.api_key
        return headers

    def _sign_message(self, message: str) -> str:
        """Sign a message with the private key."""
        if not self.account:
            raise ValueError("Private key not configured")
        message_hash = encode_defunct(text=message)
        signed = self.account.sign_message(message_hash)
        return signed.signature.hex()

    def _generate_signature(self, timestamp: int, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for authenticated requests."""
        if not self.api_secret:
            return ""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        authenticated: bool = False
    ) -> dict:
        """Make an API request."""
        if not self._session:
            await self.connect()

        url = f"{self.base_url}{endpoint}"
        headers = {}

        if authenticated:
            timestamp = int(time.time() * 1000)
            body = json.dumps(data) if data else ""
            signature = self._generate_signature(timestamp, method, endpoint, body)
            headers.update({
                "POLY_TIMESTAMP": str(timestamp),
                "POLY_SIGNATURE": signature,
            })

        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=data,
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"API request failed: {e}")
            raise

    # ==================== Market Data ====================

    async def get_markets(
        self,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> list[Market]:
        """
        Fetch available markets.

        Args:
            active_only: Only return active markets
            limit: Maximum number of markets to return
            offset: Pagination offset

        Returns:
            List of Market objects
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        if active_only:
            params["active"] = "true"

        response = await self._request("GET", "/markets", params=params)
        markets = []

        for market_data in response.get("data", []):
            market = self._parse_market(market_data)
            markets.append(market)

        return markets

    async def get_market(self, market_id: str) -> Market:
        """
        Fetch a specific market by ID.

        Args:
            market_id: The market's unique identifier

        Returns:
            Market object
        """
        response = await self._request("GET", f"/markets/{market_id}")
        return self._parse_market(response)

    async def get_market_prices(self, market_id: str) -> dict:
        """
        Get current prices for a market.

        Args:
            market_id: The market's unique identifier

        Returns:
            Dictionary with yes/no prices and spreads
        """
        response = await self._request("GET", f"/prices", params={"market": market_id})

        return {
            "yes_price": float(response.get("yes", 0.5)),
            "no_price": float(response.get("no", 0.5)),
            "yes_bid": float(response.get("yes_bid", 0)),
            "yes_ask": float(response.get("yes_ask", 0)),
            "no_bid": float(response.get("no_bid", 0)),
            "no_ask": float(response.get("no_ask", 0)),
        }

    async def get_orderbook(self, market_id: str, side: Side) -> dict:
        """
        Get orderbook for a market side.

        Args:
            market_id: The market's unique identifier
            side: YES or NO

        Returns:
            Orderbook with bids and asks
        """
        params = {
            "market": market_id,
            "side": side.value.upper(),
        }
        response = await self._request("GET", "/orderbook", params=params)

        return {
            "bids": response.get("bids", []),
            "asks": response.get("asks", []),
            "spread": self._calculate_spread(response),
        }

    async def get_new_bitcoin_markets(self, hours: int = 24) -> list[Market]:
        """
        Find newly launched Bitcoin-related markets.

        Args:
            hours: Look back period in hours

        Returns:
            List of new Bitcoin-related markets
        """
        markets = await self.get_markets(active_only=True, limit=500)
        bitcoin_markets = []

        cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)

        for market in markets:
            if market.created_at.timestamp() >= cutoff_time:
                if self._is_bitcoin_related(market):
                    bitcoin_markets.append(market)

        logger.info(f"Found {len(bitcoin_markets)} new Bitcoin markets")
        return bitcoin_markets

    def _is_bitcoin_related(self, market: Market) -> bool:
        """Check if market is Bitcoin-related."""
        text = f"{market.question} {market.description}".lower()
        return any(keyword in text for keyword in self.BITCOIN_KEYWORDS)

    def _parse_market(self, data: dict) -> Market:
        """Parse market data from API response."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif isinstance(created_at, (int, float)):
            created_at = datetime.fromtimestamp(created_at)
        else:
            created_at = datetime.utcnow()

        market = Market(
            id=data.get("id", data.get("condition_id", "")),
            question=data.get("question", data.get("title", "")),
            description=data.get("description", ""),
            volume=float(data.get("volume", 0)),
            liquidity=float(data.get("liquidity", 0)),
            yes_price=float(data.get("yes_price", data.get("outcomePrices", [0.5, 0.5])[0])),
            no_price=float(data.get("no_price", data.get("outcomePrices", [0.5, 0.5])[1] if len(data.get("outcomePrices", [])) > 1 else 0.5)),
            is_active=data.get("active", True),
            created_at=created_at,
        )
        market.is_bitcoin_related = self._is_bitcoin_related(market)
        return market

    def _calculate_spread(self, orderbook: dict) -> float:
        """Calculate bid-ask spread from orderbook."""
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        if not bids or not asks:
            return 1.0

        best_bid = float(bids[0].get("price", 0))
        best_ask = float(asks[0].get("price", 1))

        return best_ask - best_bid

    # ==================== Order Execution ====================

    async def place_order(
        self,
        market_id: str,
        side: Side,
        quantity: float,
        price: Optional[float] = None,
        order_type: OrderType = OrderType.MARKET
    ) -> Order:
        """
        Place a trading order.

        Args:
            market_id: The market's unique identifier
            side: YES or NO
            quantity: Number of shares to buy/sell
            price: Limit price (optional for market orders)
            order_type: MARKET or LIMIT

        Returns:
            Order object with execution details
        """
        order = Order(
            market_id=market_id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
        )

        order_data = {
            "market": market_id,
            "side": side.value.upper(),
            "size": str(quantity),
            "type": order_type.value.upper(),
        }

        if price is not None and order_type == OrderType.LIMIT:
            order_data["price"] = str(price)

        # Sign the order
        if self.account:
            timestamp = int(time.time() * 1000)
            message = json.dumps(order_data, sort_keys=True)
            signature = self._sign_message(f"{timestamp}{message}")
            order_data["signature"] = signature
            order_data["timestamp"] = timestamp

        try:
            response = await self._request(
                "POST",
                "/order",
                data=order_data,
                authenticated=True
            )

            order.id = response.get("id", order.id)
            order.status = OrderStatus.FILLED if response.get("status") == "filled" else OrderStatus.PENDING
            order.filled_quantity = float(response.get("filled_size", 0))
            order.filled_price = float(response.get("avg_price", price or 0))
            order.updated_at = datetime.utcnow()

            logger.info(f"Order placed: {order.id} - {side.value} {quantity} @ {price or 'market'}")

        except Exception as e:
            order.status = OrderStatus.REJECTED
            logger.error(f"Order failed: {e}")

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: The order's unique identifier

        Returns:
            True if cancellation successful
        """
        try:
            await self._request(
                "DELETE",
                f"/order/{order_id}",
                authenticated=True
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    async def get_positions(self) -> list[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        response = await self._request("GET", "/positions", authenticated=True)
        positions = []

        for pos_data in response.get("data", []):
            position = Position(
                id=pos_data.get("id", ""),
                market_id=pos_data.get("market", ""),
                side=Side.YES if pos_data.get("side", "").lower() == "yes" else Side.NO,
                quantity=float(pos_data.get("size", 0)),
                entry_price=float(pos_data.get("avg_price", 0)),
                current_price=float(pos_data.get("current_price", 0)),
            )
            positions.append(position)

        return positions

    async def close_position(self, position: Position) -> Order:
        """
        Close an open position by placing an opposing order.

        Args:
            position: The position to close

        Returns:
            Order object for the closing trade
        """
        return await self.place_order(
            market_id=position.market_id,
            side=position.side,
            quantity=position.quantity,
            order_type=OrderType.MARKET
        )

    # ==================== WebSocket ====================

    def connect_websocket(self):
        """Connect to WebSocket for real-time updates."""
        self._ws = websocket.WebSocket()
        self._ws.connect(self.ws_url)
        self._running = True
        logger.info("WebSocket connected")

    def subscribe_market(self, market_id: str, callback: Callable[[dict], None]):
        """
        Subscribe to real-time updates for a market.

        Args:
            market_id: The market's unique identifier
            callback: Function to call with price updates
        """
        if market_id not in self._ws_callbacks:
            self._ws_callbacks[market_id] = []
        self._ws_callbacks[market_id].append(callback)

        if self._ws:
            subscribe_msg = {
                "type": "subscribe",
                "channel": "prices",
                "market": market_id,
            }
            self._ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to market: {market_id}")

    def unsubscribe_market(self, market_id: str):
        """Unsubscribe from market updates."""
        if market_id in self._ws_callbacks:
            del self._ws_callbacks[market_id]

        if self._ws:
            unsubscribe_msg = {
                "type": "unsubscribe",
                "channel": "prices",
                "market": market_id,
            }
            self._ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from market: {market_id}")

    async def run_websocket_listener(self):
        """Run WebSocket listener for real-time updates."""
        if not self._ws:
            self.connect_websocket()

        while self._running:
            try:
                message = self._ws.recv()
                if message:
                    data = json.loads(message)
                    market_id = data.get("market")
                    if market_id in self._ws_callbacks:
                        for callback in self._ws_callbacks[market_id]:
                            callback(data)
            except websocket.WebSocketConnectionClosedException:
                logger.warning("WebSocket disconnected, reconnecting...")
                await asyncio.sleep(5)
                self.connect_websocket()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(1)
