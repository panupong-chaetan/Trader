"""
Futures CLI — เทรดจาก terminal ด้วยพอร์ตเดียวกับ dashboard
==========================================================
ใช้ futures_state.json ไฟล์เดียวกัน เปิดไม้ใน terminal แล้วเห็นบนเว็บทันที (และกลับกัน)

    python futures_cli.py watch                      # จอเฝ้าราคา + ไม้ที่ถือ (refresh 5 วิ)
    python futures_cli.py long BTC/USDT 200 10       # long, margin 200 USDT, 10x
    python futures_cli.py short ETH/USDT 100 5 --sl 3500 --tp 3100
    python futures_cli.py close BTC/USDT             # ปิดทั้งไม้
    python futures_cli.py close BTC/USDT 0.5         # ปิดครึ่ง
    python futures_cli.py stats
    python futures_cli.py reset 10000
"""

import argparse
import os
import sys
import time

import futures as fx

G, R, D, B, X = "\033[32m", "\033[31m", "\033[90m", "\033[1m", "\033[0m"


def col(v):
    return G if v > 0 else R if v < 0 else D


def show_account():
    a = fx.account()
    print(f"{B}พอร์ต{X}  equity {a['equity']:,.2f} USDT  "
          f"({col(a['total_pnl'])}{a['total_pnl']:+,.2f} / {a['total_pnl_pct']:+.2f}%{X})  "
          f"{D}ว่าง {a['available_margin']:,.2f} · ล้างพอร์ต {a['liquidations']} ครั้ง{X}")
    if not a["positions"]:
        print(f"{D}  ไม่มีไม้ที่เปิดอยู่{X}")
    for p in a["positions"]:
        c = col(p["unrealized_pnl"])
        warn = f" {R}⚠ ใกล้ liq{X}" if p["liq_distance_pct"] < 5 else ""
        print(f"  {p['side'].upper():<5} {p['symbol']:<10} {p['leverage']:>3}x "
              f"qty {p['qty']:.6f} @ {p['entry_price']:,.2f} → {p['mark_price']:,.2f}  "
              f"{c}{p['unrealized_pnl']:+,.2f} ({p['roe_pct']:+.1f}% ROE){X}  "
              f"{D}liq {p['liq_price']:,.2f} ({p['liq_distance_pct']:.1f}%){X}{warn}")
    for e in a["events"][:3]:
        print(f"{D}  · {e['message']}{X}")


def cmd_watch(_):
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{B}FUTURES — เงินปลอม ราคาจริง{X}  {D}Ctrl+C เพื่อออก{X}\n")
            for s in fx.SYMBOLS:
                try:
                    print(f"  {s['label']:<10} {fx.mark_price(s['symbol']):>12,.2f}  "
                          f"{D}funding {fx.funding_rate(s['symbol']) * 100:+.4f}%{X}")
                except Exception as e:
                    print(f"  {s['label']:<10} {R}ดึงราคาไม่ได้{X} {D}{e}{X}")
            print()
            fx.tick()
            show_account()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nออกแล้ว — พอร์ตถูกเซฟไว้")


def cmd_open(args):
    side = args.cmd
    pv = fx.preview(args.symbol, side, args.margin, args.leverage, args.tp, args.sl)
    print(f"{B}ก่อนยิง:{X} {side.upper()} {args.symbol} {args.leverage}x "
          f"margin {args.margin:,.2f} → ขนาดไม้ {pv['notional']:,.2f} USDT "
          f"(qty {pv['qty']:.6f})")
    print(f"  ราคาตลาด {pv['mark_price']:,.2f} · {R}liq {pv['liq_price']:,.2f} "
          f"(วิ่งผิดทาง {pv['liq_move_pct']:.2f}% = หมดไม้){X}")
    print(f"  {D}ค่าธรรมเนียมไปกลับ {pv['fee_round_trip']:.2f} · "
          f"funding/รอบ {pv['funding_per_cycle']:+.4f}{X}")
    if "risk_usdt" in pv:
        print(f"  เสี่ยงถ้าโดน SL {R}{pv['risk_usdt']:,.2f}{X} "
              f"({pv['risk_pct_of_margin']:.0f}% ของ margin)"
              + (f" · R:R 1:{pv['rr_ratio']:.2f}" if pv.get("rr_ratio") else ""))
    else:
        print(f"  {R}ไม่ได้ตั้ง SL — liquidation จะเป็น stop loss ของคุณ{X}")

    if input("ยืนยัน? (y/N) ").strip().lower() != "y":
        print("ยกเลิก")
        return
    pos = fx.open_position(args.symbol, side, margin=args.margin, leverage=args.leverage,
                           tp=args.tp, sl=args.sl, reason=args.reason or "")
    print(f"{G}เปิดไม้แล้ว{X} @ {pos['entry_price']:,.2f} liq {pos['liq_price']:,.2f}")


def cmd_close(args):
    rec = fx.close_position(args.symbol, args.portion, args.note or "")
    print(f"ปิดแล้ว @ {rec['exit_price']:,.2f} — "
          f"{col(rec['net_pnl'])}PnL {rec['net_pnl']:+,.2f} USDT "
          f"({rec['roe_pct']:+.1f}% ROE){X}")


def cmd_stats(_):
    s = fx.stats()
    if not s.get("trades"):
        print(s.get("message", "ยังไม่มีข้อมูล"))
        return
    pf = s["profit_factor"]
    print(f"{B}สถิติ {s['trades']} ไม้{X}")
    print(f"  ชนะ {s['wins']} / แพ้ {s['losses']} = {s['win_rate_pct']:.1f}%")
    print(f"  เฉลี่ยชนะ {G}{s['avg_win']:+,.2f}{X} · เฉลี่ยแพ้ {R}{s['avg_loss']:+,.2f}{X}")
    print(f"  profit factor {pf if pf == float('inf') else f'{pf:.2f}'} · "
          f"คาดหวังต่อไม้ {col(s['expectancy'])}{s['expectancy']:+,.2f}{X}")
    print(f"  leverage เฉลี่ย {s['avg_leverage']:.1f}x · ถือเฉลี่ย {s['avg_hold_hours']:.1f} ชม.")
    print(f"  จบด้วย: เป้า {s['by_trigger']['tp']} · SL {s['by_trigger']['sl']} · "
          f"มือ {s['by_trigger']['manual']} · {R}ล้างพอร์ต {s['by_trigger']['liquidation']}{X}")
    print(f"  {D}ค่าธรรมเนียมรวม {s['total_fees']:,.2f} · funding {s['total_funding']:+,.2f} · "
          f"DD สูงสุด {s['max_drawdown_pct']:.2f}%{X}")


def cmd_reset(args):
    if input(f"ล้างพอร์ตเริ่มใหม่ด้วย {args.balance:,.0f} USDT? (y/N) ").strip().lower() != "y":
        return
    st = fx.reset(args.balance)
    print(f"เริ่มใหม่ด้วย {st['wallet_balance']:,.2f} USDT")


def main():
    p = argparse.ArgumentParser(description="Futures paper trading CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("watch").set_defaults(fn=cmd_watch)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    for side in ("long", "short"):
        sp = sub.add_parser(side, help=f"เปิดไม้ {side}")
        sp.add_argument("symbol")
        sp.add_argument("margin", type=float, help="USDT ที่วางเป็นหลักประกัน")
        sp.add_argument("leverage", type=int, nargs="?", default=10)
        sp.add_argument("--tp", type=float)
        sp.add_argument("--sl", type=float)
        sp.add_argument("--reason")
        sp.set_defaults(fn=cmd_open)

    sc = sub.add_parser("close")
    sc.add_argument("symbol")
    sc.add_argument("portion", type=float, nargs="?", default=1.0, help="0.5 = ปิดครึ่ง")
    sc.add_argument("--note")
    sc.set_defaults(fn=cmd_close)

    sr = sub.add_parser("reset")
    sr.add_argument("balance", type=float, nargs="?", default=10_000.0)
    sr.set_defaults(fn=cmd_reset)

    args = p.parse_args()
    try:
        args.fn(args)
    except ValueError as e:
        print(f"{R}ไม่ได้: {e}{X}")
        sys.exit(1)


if __name__ == "__main__":
    main()
