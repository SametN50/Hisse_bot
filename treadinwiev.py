from tradingview_ta import TA_Handler, Interval
from telegram.ext import ApplicationBuilder, CommandHandler
from telegram.constants import ParseMode
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import logging, io
import os

# === AYARLAR ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_SYMBOL = "ASELS"
DEFAULT_INTERVAL = "1D"
DEFAULT_EXCHANGE = "BIST"
DEFAULT_SCREENER = "turkey"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tv_graph_bot")

INTERVALS = {
    "1": Interval.INTERVAL_1_MINUTE,
    "5": Interval.INTERVAL_5_MINUTES,
    "15": Interval.INTERVAL_15_MINUTES,
    "1H": Interval.INTERVAL_1_HOUR,
    "4H": Interval.INTERVAL_4_HOURS,
    "1D": Interval.INTERVAL_1_DAY,
    "1W": Interval.INTERVAL_1_WEEK,
    "1M": Interval.INTERVAL_1_MONTH,
}


def create_chart(symbol, close, ema50, ema200, rsi, macd, macd_signal):
    fig, axes = plt.subplots(3, 1, figsize=(6, 7), sharex=True)
    fig.suptitle(f"{symbol} Teknik Görünüm", fontsize=12)
    axes[0].plot(close, label="Fiyat", linewidth=1.5)
    axes[0].plot(ema50, label="EMA50", linestyle="--")
    axes[0].plot(ema200, label="EMA200", linestyle=":")
    axes[0].legend()
    axes[0].set_ylabel("Fiyat")
    axes[1].plot(rsi, color="purple", label="RSI")
    axes[1].axhline(70, color="red", linestyle="--", linewidth=0.8)
    axes[1].axhline(30, color="green", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("RSI")
    axes[1].legend()
    axes[2].plot(macd, label="MACD", color="blue")
    axes[2].plot(macd_signal, label="Sinyal", color="orange")
    axes[2].axhline(0, color="gray", linewidth=0.8)
    axes[2].legend()
    axes[2].set_ylabel("MACD")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def analyze(symbol, screener, exchange, interval_key):
    handler = TA_Handler(
        symbol=symbol.upper(),
        screener=screener,
        exchange=exchange,
        interval=INTERVALS.get(interval_key, Interval.INTERVAL_1_DAY),
    )
    a = handler.get_analysis()
    ind = a.indicators

    rsi = ind.get("RSI", 0)
    macd = ind.get("MACD.macd", 0)
    macd_signal = ind.get("MACD.signal", 0)
    ema50 = ind.get("EMA50", 0)
    ema200 = ind.get("EMA200", 0)
    close = ind.get("close", 0)

    score, reasons = 0, []

    if rsi < 30:
        score += 2
        reasons.append("RSI <30 (aşırı satım)")
    elif 30 <= rsi < 45:
        score += 1
        reasons.append("RSI toparlanıyor")
    elif rsi > 70:
        score -= 2
        reasons.append("RSI >70 (aşırı alım)")

    if macd > macd_signal:
        score += 2
        reasons.append("MACD > Sinyal (pozitif kesişim)")
    else:
        score -= 1
        reasons.append("MACD < Sinyal")

    if close > ema50:
        score += 1
        reasons.append("Fiyat > EMA50")
    else:
        score -= 1
        reasons.append("Fiyat < EMA50")

    if ema50 > ema200:
        score += 1
        reasons.append("EMA50 > EMA200 (trend yukarı)")
    else:
        score -= 1
        reasons.append("EMA50 < EMA200 (trend aşağı)")

    if score >= 4:
        verdict = "🟢 **GÜÇLÜ AL**"
    elif score >= 2:
        verdict = "🟢 **AL**"
    elif score <= -4:
        verdict = "🔴 **GÜÇLÜ SAT**"
    elif score <= -2:
        verdict = "🔴 **SAT**"
    else:
        verdict = "⚪ **NÖTR**"

    summary = a.summary
    msg = f"""📊 *{symbol.upper()}* `{interval_key}` _{exchange}/{screener}_
Fiyat: `{close:.2f}`
RSI: `{rsi:.2f}` | MACD: `{macd:.2f}` | Sinyal: `{macd_signal:.2f}`
EMA50: `{ema50:.2f}` | EMA200: `{ema200:.2f}`

🧮 Puan: `{score}` → {verdict}
📌 TradingView Özeti: *{summary.get('RECOMMENDATION','N/A')}* ({summary.get('BUY',0)}B / {summary.get('SELL',0)}S / {summary.get('NEUTRAL',0)}N)

ℹ️ Yorumlar:
• """ + "\n• ".join(reasons) + "\n\n_Uyarı: Bu içerik yatırım tavsiyesi değildir._"

    arr = np.linspace(0, 1, 50)
    data = pd.Series(np.linspace(close * 0.98, close * 1.02, 50))
    buf = create_chart(
        symbol,
        data,
        data * 0.99,
        data * 1.01,
        np.linspace(rsi - 10, rsi, 50),
        np.linspace(macd - 0.1, macd, 50),
        np.linspace(macd_signal - 0.1, macd_signal, 50),
    )
    return msg, buf


# === Komutlar ===
async def ta_cmd(update, context):
    try:
        args = context.args
        symbol = args[0] if len(args) >= 1 else DEFAULT_SYMBOL
        interval_key = args[1] if len(args) >= 2 else DEFAULT_INTERVAL
        exchange = args[2] if len(args) >= 3 else DEFAULT_EXCHANGE
        screener = args[3] if len(args) >= 4 else DEFAULT_SCREENER

        msg, chart = analyze(symbol, screener, exchange, interval_key)
        await update.message.reply_photo(photo=chart, caption=msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.exception("Analiz hatası")
        await update.message.reply_text(f"❌ Hata: {e}")


async def start(update, context):
    await update.message.reply_text(
        "TradingView grafik destekli analiz botuna hoş geldin! 🧭\n"
        "Kullanım: /ta ASELS 1D BIST veya /ta BTCUSDT 1H BINANCE"
    )


from telegram.ext import ApplicationBuilder, CommandHandler

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ta", ta_cmd))
    application.run_polling()

if __name__ == "__main__":
    main()
