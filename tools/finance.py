import os
import time
import threading
from typing import Callable, Any

import yfinance as yf
from dotenv import load_dotenv
from langchain_core.tools import tool
from twelvedata import TDClient

load_dotenv()

TD_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
_td_client: TDClient | None = None


# ── Twelve Data client (lazy singleton) ───────────────────────────────────────

def get_td_client() -> TDClient:
    global _td_client
    if _td_client is not None:
        return _td_client
    if not TD_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is not set")
    _td_client = TDClient(apikey=TD_API_KEY)
    return _td_client


# ── Timeout wrapper ────────────────────────────────────────────────────────────

def _with_timeout(fn: Callable, timeout: int = 15, *args, **kwargs) -> Any:
    """
    Run fn(*args, **kwargs) in a daemon thread.
    Raises TimeoutError if it doesn't finish within `timeout` seconds.
    This prevents yfinance from hanging the entire process on slow networks
    or Yahoo rate-limits — the single most common cause of crashes.
    """
    result = [None]
    error  = [None]

    def target():
        try:
            result[0] = fn(*args, **kwargs)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError(f"{getattr(fn, '__name__', 'call')} timed out after {timeout}s")
    if error[0] is not None:
        raise error[0]
    return result[0]


# ── Retry wrapper ──────────────────────────────────────────────────────────────

def _with_retry(fn: Callable, retries: int = 1, delay: float = 1.5) -> Any:
    """
    Retry fn() on transient errors (HTTP 429, connection reset).
    Never retries TimeoutError — it will just hang again.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except TimeoutError:
            raise
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
    raise last_exc


# ── Symbol normalisation ───────────────────────────────────────────────────────

# yfinance uses ^ prefix for indices; Twelve Data uses plain names or
# doesn't support some indices at all. Keep two separate maps.
_YF_ALIASES: dict[str, str] = {
    # Indian indices
    "NIFTY":        "^NSEI",
    "NIFTY50":      "^NSEI",
    "NIFTY 50":     "^NSEI",
    "SENSEX":       "^BSESN",
    "BANKNIFTY":    "^NSEBANK",
    "BANK NIFTY":   "^NSEBANK",
    "FINNIFTY":     "^CNXFIN",
    "MIDCAP":       "^CNXMIDCAP",
    "NIFTYMIDCAP":  "^CNXMIDCAP",
    "SMALLCAP":     "^CNXSMALLCAP",
    "SPX":          "^GSPC",
    "SP500":        "^GSPC",
    "S&P500":       "^GSPC",
    "DOW":          "^DJI",
    "DOWJONES":     "^DJI",
    "NASDAQ":       "^IXIC",
    "VIX":          "^VIX",
    "GOOGLE":       "GOOGL",
    "ALPHABET":     "GOOGL",
    # 
    "BTC":          "BTC-USD",
    "ETH":          "ETH-USD",
    "BITCOIN":      "BTC-USD",
    "ETHEREUM":     "ETH-USD",
}


_TD_ALIASES: dict[str, str | None] = {
    "NIFTY":        None,
    "NIFTY50":      None,
    "NIFTY 50":     None,
    "SENSEX":       None,
    "BANKNIFTY":    None,
    "BANK NIFTY":   None,
    "FINNIFTY":     None,
    "MIDCAP":       None,
    "NIFTYMIDCAP":  None,
    "SMALLCAP":     None,
    "SPX":          "SPX",
    "SP500":        "SPX",
    "S&P500":       "SPX",
    "DOW":          "DJI",
    "DOWJONES":     "DJI",
    "NASDAQ":       "IXIC",
    "VIX":          "VIX",
    "GOOGLE":       "GOOGL",
    "ALPHABET":     "GOOGL",
    # Crypto
    "BTC":          "BTC/USD",
    "ETH":          "ETH/USD",
    "BITCOIN":      "BTC/USD",
    "ETHEREUM":     "ETH/USD",
}


def _resolve_symbol(raw: str) -> str:
    """Resolve to yfinance symbol (used as the canonical symbol throughout)."""
    cleaned = raw.upper().strip()
    return _YF_ALIASES.get(cleaned, cleaned)


def _resolve_td_symbol(yf_symbol: str) -> str | None:
    """
    Convert a yfinance symbol to its Twelve Data equivalent.
    Returns None if Twelve Data doesn't support this symbol (e.g. Indian indices).
    Strips the ^ prefix for symbols not in the alias map as a best-effort fallback.
    """
    upper = yf_symbol.upper()

    # Check reverse map: if the yf symbol is a value in _YF_ALIASES,
    # find the original key and look it up in _TD_ALIASES.
    yf_reverse = {v: k for k, v in _YF_ALIASES.items()}
    original_key = yf_reverse.get(upper)
    if original_key and original_key in _TD_ALIASES:
        return _TD_ALIASES[original_key]  # may be None — caller handles it

    # Plain symbol passthrough (e.g. AAPL, MSFT, RELIANCE.NS)
    return upper


# ── Formatting helpers ─────────────────────────────────────────────────────────

def format_number(value) -> str:
    if value is None:
        return "N/A"
    try:
        value   = float(value)
        sign    = "-" if value < 0 else ""
        abs_val = abs(value)
        if abs_val >= 1_000_000_000:
            return f"{sign}${abs_val / 1_000_000_000:.2f}B"
        if abs_val >= 1_000_000:
            return f"{sign}${abs_val / 1_000_000:.2f}M"
        return f"{sign}${abs_val:,.2f}"
    except Exception:
        return str(value)


def _has_real_data(text: str) -> bool:
    if not text or "No data found" in text or "error" in text.lower():
        return False
    value_lines = [l for l in text.splitlines() if ":" in l]
    if not value_lines:
        return False
    na_count = sum(1 for l in value_lines if l.strip().endswith("N/A"))
    return na_count < len(value_lines)


# ── yfinance helpers ───────────────────────────────────────────────────────────

def _yf_info(symbol: str) -> dict:
    """Fetch ticker.info with a hard 15s timeout."""
    return _with_timeout(lambda: yf.Ticker(symbol).info, 15)


def _yf_quote(symbol: str) -> str:
    info = _yf_info(symbol)
    if not info:
        return f"No data found for {symbol}."
    # Indices use regularMarketPrice, not currentPrice
    price = info.get('currentPrice') or info.get('regularMarketPrice', 'N/A')
    return f"""{info.get('longName', symbol)} ({symbol})
    Price:         ${price}
    Change:        {info.get('regularMarketChange', 'N/A')} ({info.get('regularMarketChangePercent', 'N/A')}%)
    Open/High/Low: ${info.get('open', 'N/A')} / ${info.get('dayHigh', 'N/A')} / ${info.get('dayLow', 'N/A')}
    Volume:        {info.get('volume', 'N/A')}
    Market Cap:    {format_number(info.get('marketCap'))}
    PE Ratio:      {info.get('trailingPE', 'N/A')}  |  EPS: {info.get('trailingEps', 'N/A')}
    52W High/Low:  ${info.get('fiftyTwoWeekHigh', 'N/A')} / ${info.get('fiftyTwoWeekLow', 'N/A')}
    Exchange:      {info.get('exchange', 'N/A')}""".strip()


def _yf_income(symbol: str, period: str, limit: int) -> str:
    ticker = yf.Ticker(symbol)
    df = _with_timeout(
        lambda: ticker.quarterly_financials if period == "quarterly" else ticker.financials,
        15,
    )
    if df is None or df.empty:
        return f"No income statement found for {symbol}."
    result = [f"Income Statement ({'Quarterly' if period == 'quarterly' else 'Annual'}) - {symbol}"]
    for col in list(df.columns)[:limit]:
        result.append(f"""
            Period:        {str(col)[:10]}
            Revenue:       {format_number(df[col].get('Total Revenue'))}
            Gross Profit:  {format_number(df[col].get('Gross Profit'))}
            Operating Inc: {format_number(df[col].get('Operating Income'))}
            Net Income:    {format_number(df[col].get('Net Income'))}
            EBITDA:        {format_number(df[col].get('EBITDA'))}""")
    return "\n---".join(result)


def _yf_balance(symbol: str, period: str, limit: int) -> str:
    ticker = yf.Ticker(symbol)
    df = _with_timeout(
        lambda: ticker.quarterly_balance_sheet if period == "quarterly" else ticker.balance_sheet,
        15,
    )
    if df is None or df.empty:
        return f"No balance sheet found for {symbol}."
    result = [f"Balance Sheet ({'Quarterly' if period == 'quarterly' else 'Annual'}) - {symbol}"]
    for col in list(df.columns)[:limit]:
        result.append(f"""
        Period:             {str(col)[:10]}
        Total Assets:       {format_number(df[col].get('Total Assets'))}
        Total Liabilities:  {format_number(df[col].get('Total Liabilities Net Minority Interest'))}
        Total Equity:       {format_number(df[col].get('Stockholders Equity'))}
        Cash & Equiv:       {format_number(df[col].get('Cash And Cash Equivalents'))}
        Total Debt:         {format_number(df[col].get('Total Debt'))}""")
    return "\n---".join(result)


def _yf_cashflow(symbol: str, period: str, limit: int) -> str:
    ticker = yf.Ticker(symbol)
    df = _with_timeout(
        lambda: ticker.quarterly_cashflow if period == "quarterly" else ticker.cashflow,
        15,
    )
    if df is None or df.empty:
        return f"No cash flow found for {symbol}."
    result = [f"Cash Flow ({'Quarterly' if period == 'quarterly' else 'Annual'}) - {symbol}"]
    for col in list(df.columns)[:limit]:
        result.append(f"""
        Period:         {str(col)[:10]}
        Operating CF:   {format_number(df[col].get('Operating Cash Flow'))}
        Investing CF:   {format_number(df[col].get('Investing Cash Flow'))}
        Financing CF:   {format_number(df[col].get('Financing Cash Flow'))}
        Free CF:        {format_number(df[col].get('Free Cash Flow'))}
        CapEx:          {format_number(df[col].get('Capital Expenditure'))}""")
    return "\n---".join(result)


def _yf_metrics(symbol: str, **_) -> str:
    info = _yf_info(symbol)
    if not info:
        return f"No metrics found for {symbol}."
    return f"""Key Metrics - {symbol}
        PE Ratio:       {info.get('trailingPE', 'N/A')}
        Forward PE:     {info.get('forwardPE', 'N/A')}
        PB Ratio:       {info.get('priceToBook', 'N/A')}
        EV/EBITDA:      {info.get('enterpriseToEbitda', 'N/A')}
        ROE:            {info.get('returnOnEquity', 'N/A')}
        ROA:            {info.get('returnOnAssets', 'N/A')}
        Net Margin:     {info.get('profitMargins', 'N/A')}
        Current Ratio:  {info.get('currentRatio', 'N/A')}
        Debt/Equity:    {info.get('debtToEquity', 'N/A')}
        Dividend Yield: {info.get('dividendYield', 'N/A')}""".strip()


def _yf_ratings(symbol: str, period: str, limit: int) -> str:
    try:
        recs = _with_timeout(lambda: yf.Ticker(symbol).recommendations, 15)
        if recs is None or recs.empty:
            raise ValueError("empty")
        result = [f"Analyst Ratings - {symbol}"]
        for _, row in recs.tail(limit).iterrows():
            result.append(
                f"{str(row.name)[:10]} | {row.get('Firm', 'N/A')} | "
                f"{row.get('To Grade', 'N/A')} (from {row.get('From Grade', 'N/A')})"
            )
        return "\n".join(result)
    except Exception:
        return f"No analyst ratings available for {symbol}."


def _yf_news(symbol: str, period: str, limit: int) -> str:
    news = _with_timeout(lambda: yf.Ticker(symbol).news, 15)
    if not news:
        return f"No news found for {symbol}."
    result = [f"Latest News - {symbol}"]
    for article in news[:limit]:
        content = article.get("content", {})
        title   = content.get("title", "No title")
        url     = content.get("canonicalUrl", {}).get("url", "")
        date    = content.get("pubDate", "")[:10]
        result.append(f"- [{date}] {title}\n  {url}")
    return "\n\n".join(result)


def _yf_profile(symbol: str, **_) -> str:
    info = _yf_info(symbol)
    if not info:
        return f"No profile found for {symbol}."
    summary = info.get("longBusinessSummary", "N/A")
    if len(summary) > 400:
        cutoff  = summary.rfind(".", 0, 400)
        summary = summary[: cutoff + 1] if cutoff != -1 else summary[:400] + "…"
    return f"""{info.get('longName', symbol)} ({symbol})
Sector:     {info.get('sector', 'N/A')}  |  Industry: {info.get('industry', 'N/A')}
Exchange:   {info.get('exchange', 'N/A')}  |  Country: {info.get('country', 'N/A')}
Employees:  {info.get('fullTimeEmployees', 'N/A')}
Market Cap: {format_number(info.get('marketCap'))}
Website:    {info.get('website', 'N/A')}

{summary}""".strip()


# ── Twelve Data handlers ───────────────────────────────────────────────────────

_VALID_INTERVALS = {
    "1min", "5min", "15min", "30min",
    "1h", "2h", "4h",
    "1day", "1week", "1month",
}


def _td_price_history(symbol: str, period: str, limit: int) -> str:
    # Resolve to TD-compatible symbol; bail early for unsupported ones (e.g. Indian indices)
    td_symbol = _resolve_td_symbol(symbol)
    if td_symbol is None:
        return (
            f"Price history for {symbol} is not available via Twelve Data. "
            f"Try data_type=\'quote\' which uses yfinance for Indian indices."
        )
    interval = period if period in _VALID_INTERVALS else "1day"
    try:
        ts = _with_timeout(
            lambda: get_td_client().time_series(
                symbol=td_symbol, interval=interval, outputsize=limit,
            ).as_json(),
            20,
        )
        if not ts:
            return f"No price history found for {symbol}."
        result = [f"Price History - {symbol} ({interval})"]
        for bar in ts:
            result.append(
                f"{bar.get('datetime')} | O: {bar.get('open')} "
                f"H: {bar.get('high')} L: {bar.get('low')} "
                f"C: {bar.get('close')} V: {bar.get('volume', 'N/A')}"
            )
        return "\n".join(result)
    except TimeoutError:
        return f"Twelve Data timed out fetching history for {symbol}."
    except Exception as exc:
        return f"Twelve Data error: {exc}"


def _yf_price_history(symbol: str, period: str, limit: int) -> str:
    interval_map = {
        "1min": ("5d", "1m"),
        "5min": ("1mo", "5m"),
        "15min": ("1mo", "15m"),
        "30min": ("1mo", "30m"),
        "1h": ("3mo", "1h"),
        "2h": ("3mo", "2h"),
        "4h": ("6mo", "4h"),
        "1day": ("6mo", "1d"),
        "1week": ("2y", "1wk"),
        "1month": ("5y", "1mo"),
    }
    yf_period, interval = interval_map.get(period, ("6mo", "1d"))
    ticker = yf.Ticker(symbol)
    df = _with_timeout(
        lambda: ticker.history(period=yf_period, interval=interval),
        20,
    )
    if df is None or df.empty:
        return f"No price history found for {symbol}."

    result = [f"Price History - {symbol} ({period if period in _VALID_INTERVALS else '1day'})"]
    for index, row in df.tail(limit).iterrows():
        result.append(
            f"{str(index)[:10]} | O: {row.get('Open')} "
            f"H: {row.get('High')} L: {row.get('Low')} "
            f"C: {row.get('Close')} V: {row.get('Volume', 'N/A')}"
        )
    return "\n".join(result)


def _best_history(symbol: str, period: str, limit: int) -> str:
    td_result = _td_price_history(symbol, period, limit)
    if not any(
        marker in td_result.lower()
        for marker in ("twelve data error", "timed out", "no price history", "not available")
    ):
        return td_result

    try:
        return _yf_price_history(symbol, period, limit)
    except TimeoutError:
        return td_result
    except Exception:
        return td_result


def _td_quote(symbol: str, **_) -> str:
    td_symbol = _resolve_td_symbol(symbol)
    if td_symbol is None:
        return f"Real-time quote for {symbol} is not available via Twelve Data."
    try:
        quote = _with_timeout(
            lambda: get_td_client().quote(symbol=td_symbol).as_json(),
            15,
        )
        if not quote:
            return f"No quote found for {symbol}."
        return f"""{quote.get('name', symbol)} ({symbol}) - Twelve Data
            Price:         ${quote.get('close', 'N/A')}
            Change:        {quote.get('change', 'N/A')} ({quote.get('percent_change', 'N/A')}%)
            Open/High/Low: ${quote.get('open', 'N/A')} / ${quote.get('high', 'N/A')} / ${quote.get('low', 'N/A')}
            Volume:        {quote.get('volume', 'N/A')}
            52W High/Low:  ${quote.get('fifty_two_week', {}).get('high', 'N/A')} / ${quote.get('fifty_two_week', {}).get('low', 'N/A')}
            Market Open:   {quote.get('is_market_open', 'N/A')}""".strip()
    except TimeoutError:
        return f"Twelve Data timed out fetching quote for {symbol}."
    except Exception as exc:
        return f"Twelve Data error: {exc}"


def _best_quote(symbol: str, **_) -> str:
    """
    Try yfinance with a 15s timeout and 1 retry.
    Fall back to Twelve Data if yfinance times out or returns all-N/A data.
    """
    try:
        result = _with_retry(lambda: _yf_quote(symbol), retries=1, delay=1.5)
        if _has_real_data(result):
            return result
    except TimeoutError:
        pass  # yfinance hung — go straight to Twelve Data
    except Exception:
        pass
    return _td_quote(symbol)


# ── Dispatch table ─────────────────────────────────────────────────────────────

HANDLERS = {
    "quote":    _best_quote,
    "income":   _yf_income,
    "balance":  _yf_balance,
    "cashflow": _yf_cashflow,
    "metrics":  _yf_metrics,
    "ratings":  _yf_ratings,
    "news":     _yf_news,
    "profile":  _yf_profile,
    "history":  _best_history,
    "realtime": _td_quote,
}


# ── Tool ───────────────────────────────────────────────────────────────────────

@tool
def get_financial_data(
    symbol: str,
    data_type: str,
    period: str = "annual",
    limit: int = 3,
) -> str:
    """
    Fetch financial data for any publicly traded company or index.

    Args:
        symbol:    Ticker symbol, e.g. "AAPL", "RELIANCE.NS", "NIFTY", "SENSEX".
                   For Indian stocks append .NS (NSE) or .BO (BSE).
                   Common indices like NIFTY, SENSEX, BANKNIFTY, FINNIFTY
                   are resolved automatically.
        data_type: One of: quote, income, balance, cashflow, metrics,
                   ratings, news, profile, history, realtime
        period:    "annual" or "quarterly" for fundamentals.
                   For history, pass a Twelve Data interval:
                   1min, 5min, 15min, 1h, 1day (default), 1week, 1month
        limit:     Number of periods / rows to return (default 3)

    yfinance calls have a 15s timeout with 1 automatic retry.
    Falls back to Twelve Data if yfinance times out or returns empty data.
    """
    symbol    = _resolve_symbol(symbol)
    data_type = data_type.lower().strip()

    if data_type not in HANDLERS:
        return (
            f"Unknown data_type '{data_type}'. "
            f"Valid options: {', '.join(HANDLERS.keys())}"
        )

    try:
        return HANDLERS[data_type](symbol, period=period, limit=limit)
    except TimeoutError:
        return (
            f"Request for {data_type} data on {symbol} timed out on both sources. "
            f"Yahoo Finance may be rate-limiting — please try again in a few seconds."
        )
    except Exception as exc:
        return f"Unable to fetch {data_type} data for {symbol}: {exc}"
