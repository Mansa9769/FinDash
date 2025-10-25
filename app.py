# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
import os
import requests
import yfinance as yf

from add_txns_view_summary import ensure_csv, load_rows, append_row, compute_summary

app = Flask(__name__)

# =========================
# Config (use env vars if possible)
# =========================
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "4b83a7eb707c4349a53ae9406372bc86")
METAL_API_KEY = os.getenv("METAL_API_KEY", "17b8c24671b6199a906d981296df4a29")

# =========================
# Helpers (existing dashboard analytics)
# =========================
def _parse_date_ym(r):
    try:
        d = datetime.strptime((r.get("Date") or "").strip(), "%d-%m-%Y")
        return d.year, d.month
    except Exception:
        return None, None

def _category_expenses(rows):
    totals = defaultdict(float)
    for r in rows:
        if (r.get("Income/Expense") or "").strip().lower() == "expense":
            cat = (r.get("Category") or "Other").strip() or "Other"
            totals[cat] += float(r.get("__amt", 0.0))
    labels = list(totals.keys())
    data = [round(totals[k], 2) for k in labels]
    return {"title": "Category Expenses", "labels": labels, "data": data}

def _mode_expenses(rows):
    totals = defaultdict(float)
    for r in rows:
        if (r.get("Income/Expense") or "").strip().lower() == "expense":
            mode = (r.get("Mode") or "Other").strip() or "Other"
            totals[mode] += float(r.get("__amt", 0.0))
    labels = list(totals.keys())
    data = [round(totals[k], 2) for k in labels]
    return {"title": "Payment Mode Expenses", "labels": labels, "data": data}

def _monthly_net_cashflow(rows):
    totals = defaultdict(float)
    for r in rows:
        y, m = _parse_date_ym(r)
        if not y:
            continue
        key = f"{y}-{m:02d}"
        t = (r.get("Income/Expense") or "").strip().lower()
        amt = float(r.get("__amt", 0.0))
        if t == "income":
            totals[key] += amt
        elif t in ("expense", "transfer-out"):
            totals[key] -= amt
    labels = sorted(totals.keys())
    data = [round(totals[k], 2) for k in labels]
    return {"title": "Monthly Net Cash Flow", "labels": labels, "data": data}

def _cashflow_series(rows, months=6):
    inflow = defaultdict(float)
    outflow = defaultdict(float)
    for r in rows:
        d = r.get("__dt")
        if not d:
            try:
                d = datetime.strptime((r.get("Date") or "").strip(), "%d-%m-%Y")
            except Exception:
                continue
        key = f"{d.year}-{d.month:02d}"
        t = (r.get("Income/Expense") or "").strip().lower()
        amt = float(r.get("__amt", 0.0))
        if t == "income":
            inflow[key] += amt
        elif t in ("expense", "transfer-out"):
            outflow[key] += amt
    keys = sorted(set(inflow.keys()) | set(outflow.keys()))
    if months and len(keys) > months:
        keys = keys[-months:]
    labels = [datetime.strptime(k, "%Y-%m").strftime("%b") for k in keys]
    inflow_data = [round(inflow.get(k, 0.0), 2) for k in keys]
    outflow_data = [round(outflow.get(k, 0.0), 2) for k in keys]
    return {"labels": labels, "inflow": inflow_data, "outflow": outflow_data}

ANALYTICS_MAP = {
    "category": _category_expenses,
    "mode": _mode_expenses,
    "net": _monthly_net_cashflow,
    # if you later add more keys, just extend this map
}

# =========================
# Core Dashboard Routes
# =========================
@app.route("/")
def dashboard():
    ensure_csv()
    rows = load_rows()
    summary = compute_summary(rows)
    latest = sorted(rows, key=lambda r: r["__dt"], reverse=True)[:5]
    return render_template(
        "dashboard.html",
        balance_val=summary["balance"],
        inflow_val=summary["inflow"],
        outflow_val=summary["outflow"],
        netcash_val=summary["net_cashflow"],
        recent_transactions=latest
    )

@app.route("/add", methods=["POST"])
def add_transaction():
    ensure_csv()
    date_ui = request.form.get("date", "")
    try:
        date_csv = datetime.strptime(date_ui, "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        date_csv = datetime.today().strftime("%d-%m-%Y")
    row = {
        "Date": date_csv,
        "Mode": request.form.get("mode", "Cash"),
        "Category": request.form.get("category", "Other"),
        "Subcategory": "",
        "Note": "",
        "old": "",
        "Amount": request.form.get("amount", "0"),
        "Income/Expense": request.form.get("type", "Expense"),
        "Currency": "",
    }
    append_row(row)
    return redirect(url_for("dashboard"))

@app.route("/api/analytics")
def api_analytics():
    by = request.args.get("by", "category").lower()
    fn = ANALYTICS_MAP.get(by, _category_expenses)
    rows = load_rows()
    payload = fn(rows)
    return jsonify(payload)

@app.route("/api/cashflow")
def api_cashflow():
    rows = load_rows()
    return jsonify(_cashflow_series(rows, months=6))

# =========================
# Market Insights Routes (integrated)
# =========================
@app.route("/market")
def market_insights():
    # make sure you have templates/market_insights.html
    return render_template("market.html")

@app.route("/api/currency-rates")
def get_currency_rates():
    try:
        url = "https://api.metalpriceapi.com/v1/latest"
        params = {"api_key": METAL_API_KEY, "base": "INR", "currencies": "USD,EUR"}
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if data.get("success"):
            rates = data.get("rates", {})
            usd = rates.get("USD")
            eur = rates.get("EUR")
            return jsonify({
                "success": True,
                "usd": round(1 / usd, 2) if usd else None,
                "eur": round(1 / eur, 2) if eur else None
            })
        return jsonify({"success": False, "error": "API error"}), 500
    except Exception as e:
        print("Currency API Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/nifty-data")
def get_nifty_data():
    try:
        ticker = yf.Ticker("^NSEI")
        info = getattr(ticker, "info", {}) or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        previous_close = info.get("previousClose")
        change = change_percent = None
        if current_price and previous_close:
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100
        hist = ticker.history(period="5d")
        history = [{"date": idx.strftime("%b %d"), "value": round(row["Close"], 2)}
                   for idx, row in hist.iterrows()]
        return jsonify({
            "success": True,
            "current": round(current_price, 2) if current_price else None,
            "change": round(change, 2) if change is not None else None,
            "changePercent": round(change_percent, 2) if change_percent is not None else None,
            "history": history
        })
    except Exception as e:
        print("NIFTY API Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/news")
def get_news():
    try:
        keywords = ["Personal Finance", "Budgeting Tips"]
        from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        all_articles, seen = [], set()
        for kw in keywords:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": kw, "from": from_date, "sortBy": "publishedAt",
                "language": "en", "apiKey": NEWSAPI_KEY, "pageSize": 10
            }
            r = requests.get(url, params=params, timeout=30)
            data = r.json()
            if data.get("status") == "ok":
                for a in data.get("articles", []):
                    title = a.get("title")
                    if title and title not in seen and title != "[Removed]":
                        seen.add(title)
                        all_articles.append({
                            "title": title,
                            "source": a.get("source", {}).get("name", "Unknown"),
                            "publishedAt": a.get("publishedAt"),
                            "url": a.get("url"),
                            "keyword": kw
                        })
        all_articles.sort(key=lambda x: x["publishedAt"], reverse=True)
        return jsonify({"success": True, "articles": all_articles[:5]})
    except Exception as e:
        print("News API Error:", e)
        return jsonify({"success": False, "error": str(e)}), 500

# =========================
# Run
# =========================
if __name__ == "__main__":
    # one server, both dashboards available:
    #   /           -> finance dashboard
    #   /market     -> market insights page
    app.run(debug=True)
