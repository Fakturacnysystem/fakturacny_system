import json
import asyncio
import threading
import logging
import collections
import websockets

logger = logging.getLogger("HFT-WS-Native")

class MarketMicrostructureHFT:
    def __init__(self, pairs=None):
        self.pairs = pairs or []
        self.trade_history = {pair: collections.deque(maxlen=200) for pair in self.pairs}
        self.whale_signals = {pair: False for pair in self.pairs}
        self.lock = threading.Lock()
        self.loop = None

    def start_streaming(self, pairs):
        self.pairs = pairs
        # Spustíme asynchrónny loop v samostatnom vlákne
        thread = threading.Thread(target=self._run_async_loop, daemon=True)
        thread.start()
        logger.info(f"⚡ HFT Native WebSocket spustený pre: {pairs}")

    def _run_async_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._listen())

    async def _listen(self):
        url = "wss://ws.kraken.com"
        ws_pairs = [p.replace("BTC", "XBT") for p in self.pairs]
        
        async with websockets.connect(url) as ws:
            # Prihlásenie na odber tradeov
            subscribe_msg = {
                "event": "subscribe",
                "pair": ws_pairs,
                "subscription": {"name": "trade"}
            }
            await ws.send(json.dumps(subscribe_msg))

            while True:
                try:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    # Kraken trade správa je list: [channelID, [[price, volume, time, side, type, misc]], "trade", pair]
                    if isinstance(data, list) and data[-2] == "trade":
                        pair = data[-1].replace("XBT", "BTC")
                        trades = data[1]
                        
                        with self.lock:
                            for t in trades:
                                self.trade_history[pair].append({
                                    'v': float(t[1]),
                                    's': 'buy' if t[3] == 'b' else 'sell'
                                })
                            self._detect_whales(pair)
                except Exception as e:
                    logger.error(f"WS Recv Error: {e}")
                    await asyncio.sleep(1)

    def _detect_whales(self, pair):
        trades = list(self.trade_history[pair])
        if len(trades) < 15: return

        recent = trades[-1]
        # Inštitucionálny filter: Nákup, ktorý je 12x väčší ako priemer posledných 15 obchodov
        avg_vol = sum(t['v'] for t in trades[:-1]) / len(trades[:-1])
        
        if recent['s'] == 'buy' and recent['v'] > (avg_vol * 12):
            self.whale_signals[pair] = True
        else:
            self.whale_signals[pair] = False

    def get_signal(self, pair):
        with self.lock:
            signal = self.whale_signals.get(pair, False)
            if signal:
                self.whale_signals[pair] = False # Reset po prečítaní (one-shot trigger)
            return signal
