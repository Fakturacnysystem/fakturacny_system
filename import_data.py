import pandas as pd
import sqlite3

DATABASE = "database.db"
EXCEL_FILE = "data.xlsx"
MAX_COLUMNS = 20

xls = pd.ExcelFile(EXCEL_FILE)

# **Import zákazníkov**
customers_df = xls.parse("databáza KONTAKTY").iloc[:, :MAX_COLUMNS].dropna()
customers_df.columns = [f"column_{i+1}" for i in range(len(customers_df.columns))]

# **Import produktov**
product_sheets = [
    "Cenník Panasonic", "Cenník Beijer Anmima", "Cenník Powering",
    "Cenník VIVAX", "Cenník Sinclair", "cenniktoshiba",
    "Cenník Mitsubishi", "vivax", "Table_2"
]

product_dfs = []
for sheet in product_sheets:
    if sheet in xls.sheet_names:
        try:
            df = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
            df = df.iloc[:, :MAX_COLUMNS]
            df.columns = [f"column_{i+1}" for i in range(len(df.columns))]
            product_dfs.append(df)
        except Exception as e:
            print(f"⚠️ Chyba pri spracovaní {sheet}: {e}")

products_df = pd.concat(product_dfs, ignore_index=True).dropna() if product_dfs else pd.DataFrame()

conn = sqlite3.connect(DATABASE)
customers_df.to_sql("customers", conn, if_exists="replace", index=False)
products_df.to_sql("products", conn, if_exists="replace", index=False)
conn.close()

print("✅ Import údajov dokončený!")
