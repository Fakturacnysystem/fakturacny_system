import os
import time
import json
import logging
from openai import OpenAI

# Nastavenie logovania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ComputeWorker")

class ComputeWorker:
    def __init__(self):
        self.api_key = "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"
        self.client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=self.api_key)
        logger.info("🤖 Compute Worker inicializovaný s NVIDIA NIM.")

    def get_market_prediction(self, market_data):
        """Odosiela dáta na AI analýzu pre predikciu smeru trhu."""
        try:
            prompt = f"Analyzuj tieto dáta z Krakenu a urči smer (BUY/SELL/HOLD) pre 30% mesačný zisk: {market_data}"
            response = self.client.chat.completions.create(
                model="meta/llama-3.1-405b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Chyba pri AI predikcii: {e}")
            return "HOLD"

    def run(self):
        logger.info("🚀 Worker začína počúvať úlohy...")
        # Tu by v produkcii bol Redis stream.read()
        # Pre demo simulujeme nekonečnú slučku spracovania
        while True:
            # Simulácia prijatia dát z trhu
            sample_data = {"symbol": "BTC/EUR", "price": 65000, "volatility": "high"}
            prediction = self.get_market_prediction(sample_data)
            logger.info(f"✅ Predikcia spracovaná: {prediction[:50]}...")
            time.sleep(10) # Počkáme 10 sekúnd na ďalšiu analýzu

if __name__ == "__main__":
    worker = ComputeWorker()
    worker.run()
