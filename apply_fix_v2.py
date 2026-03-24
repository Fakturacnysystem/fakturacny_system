import os
import subprocess

def find_and_patch():
    # Dynamicky nájdeme cestu k súboru profit_gate.py
    try:
        path = subprocess.check_output(["find", ".", "-name", "profit_gate.py"]).decode().strip().split('\n')[0]
    except Exception:
        print("❌ Súbor profit_gate.py sa nepodarilo nájsť nikde v aktuálnom priečinku!")
        return

    print(f"🎯 Súbor nájdený v: {path}")

    dynamic_code = """
import logging

class ProfitGate:
    def __init__(self, min_fixed_threshold=0.012):
        self.min_fixed_threshold = min_fixed_threshold
        self.logger = logging.getLogger("ProfitGate")

    def get_dynamic_threshold(self, age_days, balance):
        # Ak je balance nízky (< 20 USD), znížime target na uvoľnenie cashu
        if balance < 20.0:
            return 0.002  # 0.2% (pokryje poplatky, uvoľní kapitál)
        
        # Inak target klesá s vekom pozície (čím staršia, tým skôr chceme von)
        decay = age_days * 0.0005
        return max(self.min_fixed_threshold - decay, 0.005)

    def should_exit(self, current_pnl, age_days, current_balance):
        threshold = self.get_dynamic_threshold(age_days, current_balance)
        can_exit = current_pnl >= threshold
        if can_exit:
            self.logger.info(f"DYNAMIC_EXIT: Target {threshold*100:.2f}% dosiahnutý.")
        return can_exit
"""
    
    with open(path, "w") as f:
        f.write(dynamic_code.strip())
    print(f"✅ Súbor bol úspešne prepísaný.")

if __name__ == "__main__":
    find_and_patch()
