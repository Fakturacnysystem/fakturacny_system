import logging
import time

class ProfitGate:
    def __init__(self, min_fixed_threshold=0.012):
        self.min_fixed_threshold = min_fixed_threshold
        self.logger = logging.getLogger("ProfitGate")

    def get_dynamic_threshold(self, age_days, balance):
        # Emergency cash recovery
        if balance < 20.0:
            return 0.002
        
        # Age decay: čím staršia pozícia, tým nižší target
        decay = age_days * 0.0005
        return max(self.min_fixed_threshold - decay, 0.005)

    def should_exit(self, current_pnl, entry_timestamp, current_balance):
        # Výpočet veku v dňoch
        age_days = (time.time() - entry_timestamp) / 86400
        
        threshold = self.get_dynamic_threshold(age_days, float(current_balance))
        can_exit = current_pnl >= threshold
        
        if can_exit:
            self.logger.info(f"✅ EXIT SIGNAL: PnL {current_pnl*100:.2f}% >= Target {threshold*100:.2f}%")
        return can_exit
