"""
Generate a combined market chart image (PNG) for Telegram delivery.
Charts: S&P 500 · IHSG · BTC · Gold — last 30 days.
"""
import io
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from datetime import datetime
import pytz

WIB = pytz.timezone("Asia/Jakarta")

PANELS = [
    ("^GSPC",  "S&P 500",  "#6366f1"),
    ("^JKSE",  "IHSG",     "#22c55e"),
    ("BTC-USD","Bitcoin",   "#f59e0b"),
    ("GC=F",   "Gold",     "#eab308"),
]


def generate_chart() -> bytes:
    """Returns PNG bytes of a 2×2 chart grid."""
    fig = plt.figure(figsize=(12, 7), facecolor="#0f1117")
    gs  = GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.3)

    now_str = datetime.now(WIB).strftime("%A, %d %b %Y  %H:%M WIB")
    fig.suptitle(
        f"📊  Market Overview  —  {now_str}",
        color="white", fontsize=13, fontweight="bold", y=0.98,
    )

    for i, (ticker, label, color) in enumerate(PANELS):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        ax.set_facecolor("#1a1d27")
        for spine in ax.spines.values():
            spine.set_color("#2a2d3e")

        try:
            hist = yf.Ticker(ticker).history(period="30d")
            if hist.empty:
                raise ValueError("No data")

            dates  = hist.index.to_pydatetime()
            prices = hist["Close"].values
            pct    = (prices[-1] - prices[0]) / prices[0] * 100
            arrow  = "▲" if pct >= 0 else "▼"
            clr    = "#22c55e" if pct >= 0 else "#ef4444"

            # Fill under line
            ax.fill_between(dates, prices, prices.min(),
                            alpha=0.15, color=color)
            ax.plot(dates, prices, color=color, linewidth=1.8)

            # Latest price dot
            ax.scatter(dates[-1], prices[-1], color=color, s=40, zorder=5)

            # Labels
            ax.set_title(
                f"{label}   {arrow} {abs(pct):.2f}%  (30d)",
                color=clr, fontsize=10, fontweight="bold", pad=6,
            )
            price_fmt = f"{prices[-1]:,.0f}" if prices[-1] > 100 else f"{prices[-1]:,.2f}"
            ax.text(0.02, 0.92, price_fmt, transform=ax.transAxes,
                    color="white", fontsize=9, fontweight="bold")

        except Exception as e:
            ax.text(0.5, 0.5, f"No data\n{e}", transform=ax.transAxes,
                    color="#64748b", ha="center", va="center", fontsize=9)
            ax.set_title(label, color="#64748b", fontsize=10, pad=6)

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.tick_params(colors="#64748b", labelsize=7)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        ax.grid(axis="y", color="#2a2d3e", linewidth=0.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=130)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
