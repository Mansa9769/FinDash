# add_transaction_cli.py
# CLI to append validated transactions to daily_transactions.csv
# and show recent purchases + summary metrics.
# Inputs removed: Subcategory, Note, old, Currency (auto-empty)

import csv
import os
from datetime import datetime

CSV_PATH = "daily_transactions.csv"

COLUMNS = [
    "Date", "Mode", "Category", "Subcategory", "Note", "old",
    "Amount", "Income/Expense", "Currency"
]

MODE_OPTIONS = [
    "Cash",
    "Credit Card",
    "Debit Card",
    "Equity Mutual Fund A",
    "Equity Mutual Fund B",
    "Equity Mutual Fund C",
    "Equity Mutual Fund D",
    "Fixed Deposit",
    "Recurring Deposit",
    "Saving Bank account 1",
    "Saving Bank account 2",
    "Share Market Trading",
]

CATEGORY_OPTIONS = [
    "Apparel",
    "Beauty",
    "Bonus",
    "Dividend earned on Shares",
    "Education",
    "Family",
    "Festivals",
    "Fixed Deposit",
    "Food",
    "Gift",
    "Grooming",
    "Health",
    "Household",
    "Interest",
    "Investment",
    "Life Insurance",
    "maid",
    "Money transfer",
    "Other",
    "Petty cash",
    "Public Provident Fund",
    "Recurring Deposit",
    "Rent",
    "Salary",
    "Saving Bank account 1",
    "Saving Bank account 2",
    "Share Market",
    "Social Life",
    "subscription",
    "Tourism",
    "Transportation",
]

IE_OPTIONS = ["Income", "Expense", "Transfer-Out"]

# ----------------- utils -----------------

def ensure_csv():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()

def pick_from_list(name, options):
    print(f"\nSelect {name}:")
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    while True:
        raw = input(f"Enter number (1-{len(options)}): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("Invalid choice. Try again.")

def read_date_ddmmyyyy(prompt="Enter Date (DD-MM-YYYY) [blank=today]: "):
    raw = input(prompt).strip()
    if not raw:
        return datetime.today().strftime("%d-%m-%Y")
    try:
        dt = datetime.strptime(raw, "%d-%m-%Y")
        return dt.strftime("%d-%m-%Y")
    except ValueError:
        print("❌ Invalid date. Expected DD-MM-YYYY (e.g., 20-09-2018). Try again.")
        return read_date_ddmmyyyy(prompt)

def parse_date_ddmmyyyy_to_dt(s):
    try:
        return datetime.strptime((s or "").strip(), "%d-%m-%Y")
    except Exception:
        return None

def read_amount():
    while True:
        raw = input("Amount (e.g., 500 or 500.75): ").strip()
        try:
            val = float(raw)
            if val < 0:
                print("Amount must be non-negative.")
                continue
            return val
        except ValueError:
            print("Invalid number. Try again.")

def append_row(row):
    ensure_csv()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

def load_rows():
    """Read CSV into list[dict]; parse dates to datetime for sorting and math."""
    ensure_csv()
    rows = []
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dt = parse_date_ddmmyyyy_to_dt(r.get("Date"))
            if not dt:
                continue
            try:
                amt = float((r.get("Amount") or "0").strip())
            except Exception:
                amt = 0.0
            r["__dt"] = dt
            r["__amt"] = amt
            rows.append(r)
    return rows

# ----------------- summaries -----------------

def compute_summary(rows):
    """Returns dict with inflow, outflow, transfer_out, net_outflow, net_cashflow, balance."""
    inflow = sum(r["__amt"] for r in rows if (r.get("Income/Expense") or "").strip().title() == "Income")
    outflow = sum(r["__amt"] for r in rows if (r.get("Income/Expense") or "").strip().title() == "Expense")
    transfer_out = sum(r["__amt"] for r in rows if (r.get("Income/Expense") or "").strip().title() == "Transfer-Out")
    net_outflow = outflow + transfer_out
    net_cashflow = inflow - net_outflow
    balance = net_cashflow  # no opening balance column; treat cumulative net as balance
    return {
        "inflow": inflow,
        "outflow": outflow,
        "transfer_out": transfer_out,
        "net_outflow": net_outflow,
        "net_cashflow": net_cashflow,
        "balance": balance
    }

def print_summary(rows):
    s = compute_summary(rows)
    print("\n==== Summary ====")
    print(f"Net Inflow        : {s['inflow']:,.2f}")
    print(f"Net Outflow       : {s['net_outflow']:,.2f}  (Expense: {s['outflow']:,.2f} + Transfer-Out: {s['transfer_out']:,.2f})")
    print(f"Net Cashflow      : {s['net_cashflow']:,.2f}  (Inflow - Net Outflow)")
    print(f"Total Balance*    : {s['balance']:,.2f}")
    print("(*Balance = cumulative net cashflow; no opening balance used)")

# ----------------- core actions -----------------

def add_one():
    print("\n=== Add New Transaction ===")
    date = read_date_ddmmyyyy()
    mode = pick_from_list("Mode", MODE_OPTIONS)
    category = pick_from_list("Category", CATEGORY_OPTIONS)
    amount = read_amount()
    ie = pick_from_list("Income/Expense", IE_OPTIONS)

    # Columns we don't take input for are set to empty strings
    row = {
        "Date": date,
        "Mode": mode,
        "Category": category,
        "Subcategory": "",
        "Note": "",
        "old": "",
        "Amount": f"{amount:.2f}",
        "Income/Expense": ie,
        "Currency": "",   # left empty as requested
    }

    print("\nReview entry:")
    for k in COLUMNS:
        print(f"- {k}: {row[k]}")
    confirm = input("Save? (y/n): ").strip().lower()
    if confirm == "y":
        append_row(row)
        print(f"✅ Saved to {CSV_PATH}")
        rows = load_rows()
        print_summary(rows)
    else:
        print("❌ Discarded.")

def show_recent_purchases(top_n=5):
    rows = load_rows()
    expenses = [r for r in rows if (r.get("Income/Expense") or "").strip().title() == "Expense"]
    if not expenses:
        print("\n(no purchases found)")
    else:
        expenses.sort(key=lambda r: r["__dt"], reverse=True)
        print(f"\n🧾 Top {min(top_n, len(expenses))} most recent purchases:\n")
        for i, r in enumerate(expenses[:top_n], start=1):
            dt = r["__dt"].strftime("%d-%m-%Y")
            amt = f"{r['__amt']:.2f}"
            mode = r.get("Mode", "")
            cat = r.get("Category", "")
            line = f"{i}. {dt} | {cat} | {mode} | {amt}"
            print(line)
    print_summary(rows)

# ----------------- menu -----------------

def main_menu():
    ensure_csv()
    while True:
        print("\n==== Personal Finance CLI ====")
        print("1) Add a new transaction")
        print("2) Show 5 most recent purchases (and summary)")
        print("3) Show summary only")
        print("4) Exit")
        choice = input("Choose an option (1-4): ").strip()
        if     choice == "1": add_one()
        elif   choice == "2": show_recent_purchases(top_n=5)
        elif   choice == "3": print_summary(load_rows())
        elif   choice == "4":
            print("bye! 👋")
            break
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main_menu()
