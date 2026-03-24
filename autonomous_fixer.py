import os
from openai import OpenAI
import datetime

# --- KONFIGURÁCIA ---
API_KEY = "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"
BASE_URL = "https://integrate.api.nvidia.com/v1"
PROJECT_ROOT = "/Users/martinholik/Projects/fakturacny_system"
# Cesta k tvojim posledným logom z ls -R výpisu
LOG_FILE = os.path.join(PROJECT_ROOT, "runs/post_phase_exec_20260312T180315Z/runtime_liveprofit_paper/audit.log")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

def get_context():
    """Načíta logy a štruktúru súborov pre kontext."""
    try:
        with open(LOG_FILE, 'r') as f:
            logs = f.readlines()[-100:]  # Posledných 100 riadkov logu
        return "".join(logs)
    except Exception as e:
        return f"Nepodarilo sa načítať logy: {e}"

def ask_ai_for_fix(log_context):
    print("🤖 AI analyzuje logy a navrhuje riešenie pre 30% mesačný zisk...")
    
    prompt = f"""
    ÚLOHA: Si Senior Quant Developer. Môj robot zamrzol (deadlock) na nízkom quote balance a rigidnom profit targete 1.2%.
    CIEĽ: Dosiahnuť 30% mesačný zisk úpravou logiky uvoľňovania kapitálu.
    
    KONTEXT LOGOV:
    {log_context}
    
    POŽIADAVKA:
    1. Identifikuj prekážku v logoch.
    2. Navrhni konkrétny Python kód pre 'Capital Release Mode'.
    3. Navrhni ako zmeniť 'profit_gate.py' na dynamický target.
    
    Odpovedaj v slovenčine, ale kód nechaj v angličtine.
    """

    response = client.chat.completions.create(
        model="meta/llama-3.1-405b-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content

def run():
    logs = get_context()
    suggestion = ask_ai_for_fix(logs)
    
    # Uloženie návrhu do súboru
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"ai_fix_report_{timestamp}.md"
    
    with open(report_name, "w") as f:
        f.write(suggestion)
    
    print(f"\n✅ Analýza dokončená. Návrh bol uložený do: {report_name}")
    print("-" * 50)
    print(suggestion[:500] + "...") # Ukážka začiatku

if __name__ == "__main__":
    run()
