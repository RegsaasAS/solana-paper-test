"""Bounded technical paper test. Public market data only; no order API exists here."""
import argparse
import csv
import datetime as dt
import decimal
import json
import pathlib
import time
import urllib.request

D = decimal.Decimal
API = "https://api.kraken.com/0/public/"


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def public(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "SolanaPaperProbe/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=12) as response:
        value = json.load(response)
    if value.get("error"):
        raise RuntimeError(str(value["error"]))
    return value["result"]


def execute_book(levels, quantity):
    remaining, gross = quantity, D(0)
    for price, available, _ in levels:
        taken = min(remaining, D(available))
        gross += taken * D(price)
        remaining -= taken
        if remaining == 0:
            return gross
    raise RuntimeError("Insufficient visible book depth; no simulated fill recorded")


def run(args):
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    metadata = public("AssetPairs?pair=SOLUSDT")["SOLUSDT"]
    if metadata["status"] != "online":
        raise RuntimeError("Market is not online")
    fee, slip = D(args.fee), D(args.slippage)
    result = {
        "purpose": "technical_roundtrip_test_not_strategy_performance",
        "pair": "SOL/USDT", "started_utc": utc(), "status": "running",
        "virtual_cash_initial_usdt": "100", "virtual_cash_usdt": "100",
        "fee_assumed_per_side": str(fee), "adverse_slippage_assumed_per_side": str(slip),
        "provider_fee_verified": False, "ordermin_sol": metadata["ordermin"],
        "costmin_usdt": metadata["costmin"], "position": None, "trades": [],
        "quote_count": 0, "errors": [], "time_exit_seconds": args.hold,
        "limitations": ["snapshot book simulation; no actual orders", "timed entries and exits test functionality only", "no queue, network execution or failed-order model", "no permanent unattended hosting verified"],
    }
    cash = D("100")
    position = None
    started = time.monotonic()
    hard_stop = started + args.seconds
    cooldown_until = started
    quantum = D(1).scaleb(-int(metadata["lot_decimals"]))
    stop_reason = "time_limit"
    quote_path = out / "quotes.jsonl"
    trade_path = out / "trades.csv"

    def save():
        result["virtual_cash_usdt"] = str(cash)
        result["position"] = position
        result["updated_utc"] = utc()
        tmp = out / "result.json.tmp"
        tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
        tmp.replace(out / "result.json")

    save()
    try:
        with quote_path.open("w", encoding="utf-8") as quotes, trade_path.open("w", newline="", encoding="utf-8") as trades:
            fields = ["utc", "side", "quantity_sol", "book_gross_usdt", "modeled_gross_usdt", "fee_usdt", "cash_change_usdt", "reason"]
            writer = csv.DictWriter(trades, fieldnames=fields)
            writer.writeheader()
            while time.monotonic() < hard_stop or position:
                cycle_at = time.monotonic()
                try:
                    # Server time checks transport freshness; order timestamps alone
                    # do not prove freshness, because resting orders can be old.
                    server = public("Time")
                    if abs(time.time() - int(server["unixtime"])) > 30:
                        raise RuntimeError("Server/local clock mismatch or stale time response")
                    book = public("Depth?pair=SOLUSDT&count=25")["SOLUSDT"]
                    ask, bid = D(book["asks"][0][0]), D(book["bids"][0][0])
                    if ask <= 0 or bid <= 0 or bid > ask:
                        raise RuntimeError("Invalid or crossed order book")
                    quotes.write(json.dumps({"received_utc": utc(), "server_unixtime": server["unixtime"], "book": book}) + "\n")
                    quotes.flush()
                    result["quote_count"] += 1
                    now = time.monotonic()
                    row = None
                    if position and (now >= position["exit_at_monotonic"] or now >= hard_stop):
                        qty = D(position["quantity_sol"])
                        gross = execute_book(book["bids"], qty)
                        modeled = gross * (1 - slip)
                        fees = modeled * fee
                        received = modeled - fees
                        cash += received
                        row = dict(utc=utc(), side="SELL", quantity_sol=str(qty), book_gross_usdt=str(gross), modeled_gross_usdt=str(modeled), fee_usdt=str(fees), cash_change_usdt=str(received), reason="technical_time_exit")
                        position = None
                        cooldown_until = now + args.poll
                    elif position is None and now >= cooldown_until and now + args.hold + 20 < hard_stop:
                        # Fixed entries deliberately isolate data -> buy -> sell -> accounting.
                        qty = (D("10") / (ask * (1 + slip) * (1 + fee))).quantize(quantum, rounding=decimal.ROUND_DOWN)
                        gross = execute_book(book["asks"], qty)
                        modeled = gross * (1 + slip)
                        fees = modeled * fee
                        spent = modeled + fees
                        if qty < D(metadata["ordermin"]) or gross < D(metadata["costmin"]):
                            raise RuntimeError("Virtual trade below exchange minimum")
                        if spent > cash:
                            raise RuntimeError("Insufficient virtual funds")
                        cash -= spent
                        position = {"quantity_sol": str(qty), "entry_utc": utc(), "spent_usdt": str(spent), "exit_at_monotonic": now + args.hold}
                        row = dict(utc=utc(), side="BUY", quantity_sol=str(qty), book_gross_usdt=str(gross), modeled_gross_usdt=str(modeled), fee_usdt=str(fees), cash_change_usdt=str(-spent), reason="technical_fixed_entry")
                    if row:
                        writer.writerow(row)
                        trades.flush()
                        result["trades"].append(row)
                        print(json.dumps(row), flush=True)
                    save()
                except Exception as exc:
                    result["errors"].append({"utc": utc(), "error": str(exc)})
                    print("DATA_ERROR " + str(exc), flush=True)
                    save()
                    # Never synthesize an exit when quotes are unavailable.
                    if len(result["errors"]) >= 3:
                        stop_reason = "data_errors"
                        break
                if time.monotonic() >= hard_stop and position is None:
                    break
                time.sleep(max(0, args.poll - (time.monotonic() - cycle_at)))
    except KeyboardInterrupt:
        stop_reason = "operator_stop"
    result["status"] = "stopped_unresolved_position" if position else "completed"
    result["stop_reason"] = stop_reason
    result["ended_utc"] = utc()
    result["completed_roundtrips"] = sum(t["side"] == "SELL" for t in result["trades"])
    result["realized_net_pnl_usdt"] = str(cash - D("100")) if position is None else None
    save()
    print(json.dumps({k: result[k] for k in ("status", "completed_roundtrips", "quote_count", "realized_net_pnl_usdt", "stop_reason")}), flush=True)
    return 0 if position is None and result["completed_roundtrips"] >= 1 and not result["errors"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--hold", type=int, default=45)
    parser.add_argument("--poll", type=int, default=10)
    parser.add_argument("--fee", default="0.008")
    parser.add_argument("--slippage", default="0.001")
    parser.add_argument("--output", default="paper-result")
    arguments = parser.parse_args()
    if not (90 <= arguments.seconds <= 1800 and 15 <= arguments.hold <= 300 and 5 <= arguments.poll <= 60):
        parser.error("Bounded test only: duration 90-1800s, hold 15-300s, poll 5-60s")
    if not (D(0) <= D(arguments.fee) <= D("0.02") and D(0) <= D(arguments.slippage) <= D("0.02")):
        parser.error("Fee/slippage out of range")
    raise SystemExit(run(arguments))
