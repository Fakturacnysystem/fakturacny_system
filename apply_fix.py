import os

def apply_dynamic_logic():
    target_file = "src/autonomous_investment_robot/services/execution/profit_gate.py"
    
    if not os.path.exists(target_file):
        print(f"❌ Súbor {target_file} nebol nájdený!")
        return

    # Nový kód pre dynamický profit target, ktorý odstraňuje 1.2% deadlock
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
    
    with open(target_file, "w") as f:
        f.write(dynamic_code.strip())
    print(f"✅ Súbor {target_file} bol úspešne opravený na dynamický režim.")

if __name__ == "__main__":
    apply_dynamic_logic()
