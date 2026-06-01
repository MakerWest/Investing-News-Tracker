import re
import html
import urllib.parse
from collections import defaultdict

import pandas as pd
import requests
import feedparser
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Trump Company Mention Tracker", layout="wide")

TRUTH_FEED_URL = "https://trumpstruth.org/feed"

# Hand-built watchlist remains useful for products, CEOs, and awkward company names.
MANUAL_WATCHLIST = {
    "Apple": {"ticker": "AAPL", "terms": ["apple", "aapl", "$aapl", "iphone", "tim cook"]},
    "Amazon": {"ticker": "AMZN", "terms": ["amazon", "amzn", "$amzn", "andy jassy"]},
    "Nvidia": {"ticker": "NVDA", "terms": ["nvidia", "nvda", "$nvda", "jensen huang"]},
    "Intel": {"ticker": "INTC", "terms": ["intel", "intc", "$intc"]},
    "Dell": {"ticker": "DELL", "terms": ["dell", "dell technologies", "$dell", "michael dell"]},
    "Tesla": {"ticker": "TSLA", "terms": ["tesla", "tsla", "$tsla", "elon musk"]},
    "Microsoft": {"ticker": "MSFT", "terms": ["microsoft", "msft", "$msft", "satya nadella"]},
    "Meta": {"ticker": "META", "terms": ["meta", "facebook", "instagram", "zuckerberg", "$meta", "mark zuckerberg"]},
    "Google / Alphabet": {"ticker": "GOOGL", "terms": ["google", "alphabet", "googl", "goog", "$googl", "$goog", "sundar pichai"]},
    "Walmart": {"ticker": "WMT", "terms": ["walmart", "wmt", "$wmt", "doug mcmillon"]},
    "Ford": {"ticker": "F", "terms": ["ford", "$f", "ford motor"]},
    "General Motors": {"ticker": "GM", "terms": ["general motors", "gm", "$gm"]},
    "Boeing": {"ticker": "BA", "terms": ["boeing", "$ba"]},
    "Lockheed Martin": {"ticker": "LMT", "terms": ["lockheed", "lockheed martin", "$lmt"]},
    "Palantir": {"ticker": "PLTR", "terms": ["palantir", "pltr", "$pltr", "alex karp"]},
    "CoreWeave": {"ticker": "CRWV", "terms": ["coreweave", "crwv", "$crwv"]},
    "Rocket Lab": {"ticker": "RKLB", "terms": ["rocket lab", "rklb", "$rklb"]},
    "Trump Media": {"ticker": "DJT", "terms": ["truth social", "trump media", "djt", "$djt"]},
}

COMMON_FALSE_POSITIVE_TICKERS = {
    # Very short/common words that are also tickers. We only detect these with $ prefix manually.
    "A", "I", "AM", "ON", "OR", "ARE", "CAN", "FOR", "HAS", "NOW", "LOVE", "GOOD",
    "ALL", "USA", "US", "IT", "BE", "BY", "HE", "SO", "GO", "DO", "LIFE", "REAL",
    "TRUE", "BIG", "CEO", "IRS", "AI"
}

COMPANY_SUFFIXES_TO_REMOVE = [
    "inc", "inc.", "corporation", "corp", "corp.", "company", "co", "co.",
    "class a", "class b", "common stock", "ordinary shares", "american depositary shares",
    "adr", "plc", "limited", "ltd", "s.a.", "sa", "n.v.", "nv", "ag", "se"
]

POSITIVE_WORDS = [
    "buy", "great", "strong", "best", "excellent", "beautiful", "winner",
    "support", "like", "love", "praise", "good", "tremendous", "invest",
    "deal", "approved", "backing", "boost", "wins"
]
NEGATIVE_WORDS = [
    "boycott", "bad", "weak", "terrible", "disaster", "avoid", "failed",
    "failure", "crooked", "fake", "overpriced", "tariff", "punish",
    "criticizes", "attacks", "threatens", "ban", "blocked", "slams"
]

def clean_text(raw):
    raw = html.unescape(raw or "")
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)

def fetch_rss(url, limit=50):
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 Trump Company Mention Tracker"},
        timeout=25,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return feed.entries[:limit]

def google_news_url(query):
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

def simplify_company_name(name):
    name = str(name or "")
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\([^)]*\)", "", name).strip()
    lowered = name.lower()

    for suffix in COMPANY_SUFFIXES_TO_REMOVE:
        lowered = re.sub(r"\b" + re.escape(suffix) + r"\b", "", lowered, flags=re.I)

    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.-")
    return lowered.title()

@st.cache_data(ttl=24 * 60 * 60)
def load_public_company_watchlist():
    """
    Loads Nasdaq-listed and other-listed public-company symbols.
    If Nasdaq blocks or changes the files, the app still works with the manual watchlist.
    """
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]

    auto = {}

    for url in urls:
        try:
            df = pd.read_csv(url, sep="|")
        except Exception:
            continue

        if "Symbol" in df.columns and "Security Name" in df.columns:
            symbol_col = "Symbol"
            name_col = "Security Name"
        elif "ACT Symbol" in df.columns and "Security Name" in df.columns:
            symbol_col = "ACT Symbol"
            name_col = "Security Name"
        else:
            continue

        for _, row in df.iterrows():
            ticker = str(row.get(symbol_col, "")).strip()
            raw_name = str(row.get(name_col, "")).strip()

            if not ticker or ticker == "nan" or not raw_name or raw_name == "nan":
                continue

            if ticker.upper() in {"File Creation Time"}:
                continue

            ticker = ticker.replace(".", "-").upper()
            if ticker in COMMON_FALSE_POSITIVE_TICKERS:
                continue

            clean_name = simplify_company_name(raw_name)
            if len(clean_name) < 4:
                continue

            # Avoid ETFs/funds/noisy securities where possible.
            lower_raw = raw_name.lower()
            if any(x in lower_raw for x in [" etf", " fund", " notes due", "warrant", "unit", "rights", "preferred"]):
                continue

            terms = [clean_name, ticker, f"${ticker}"]

            # Also add first part before comma/hyphen if useful.
            first_part = re.split(r"[-,]", clean_name)[0].strip()
            if len(first_part) >= 5 and first_part.lower() != clean_name.lower():
                terms.append(first_part)

            auto[clean_name] = {"ticker": ticker, "terms": sorted(set(terms), key=len, reverse=True)}

    return auto

def build_watchlist(use_auto_tickers=True):
    watchlist = dict(MANUAL_WATCHLIST)

    if use_auto_tickers:
        auto = load_public_company_watchlist()
        # Manual list wins where there is overlap.
        for company, data in auto.items():
            if company not in watchlist:
                watchlist[company] = data

    return watchlist

def normalise_exclusions(raw):
    return {x.strip().lower().replace("$", "") for x in raw.split(",") if x.strip()}

def is_excluded(company, ticker, matched_term, exclusions):
    if not exclusions:
        return False

    checks = {
        company.lower(),
        ticker.lower(),
        ticker.lower().replace("$", ""),
        matched_term.lower().replace("$", ""),
    }

    return any(exclusion in checks for exclusion in exclusions)

def is_probably_valid_auto_match(term, ticker, text):
    """
    Reduces false positives for automatic ticker/name matching.
    - $TICKER is always strong.
    - Company names must be at least 5 chars and not just a very common word.
    - Bare ticker matching requires uppercase ticker-like appearance in the original text.
    """
    term_plain = term.replace("$", "")
    if term.startswith("$"):
        return True

    if term_plain.upper() == ticker:
        return re.search(r"\b" + re.escape(ticker) + r"\b", text) is not None

    return len(term_plain) >= 5

def detect_mentions(text, exclusions, watchlist):
    lower = text.lower()
    hits = []

    for company, data in watchlist.items():
        ticker = data["ticker"]

        for term in data["terms"]:
            term_l = term.lower()
            if term_l.startswith("$"):
                pattern = re.escape(term_l) + r"\b"
            else:
                pattern = r"\b" + re.escape(term_l) + r"\b"

            if re.search(pattern, lower):
                if not is_probably_valid_auto_match(term, ticker, text):
                    continue
                if not is_excluded(company, ticker, term, exclusions):
                    hits.append({
                        "company": company,
                        "ticker": ticker,
                        "matched_term": term,
                    })
                break

    # Dedupe by ticker, preferring the shortest company name shown if duplicates occur.
    by_ticker = {}
    for hit in hits:
        ticker = hit["ticker"]
        if ticker not in by_ticker or len(hit["company"]) < len(by_ticker[ticker]["company"]):
            by_ticker[ticker] = hit

    return list(by_ticker.values())

def simple_sentiment(text):
    lower = text.lower()
    pos = sum(1 for word in POSITIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower))
    neg = sum(1 for word in NEGATIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower))

    if pos > neg:
        return "Positive / supportive"
    if neg > pos:
        return "Negative / critical"
    return "Neutral / unclear"

def parse_entries(entries, source_name, exclusions, watchlist):
    posts = []

    for entry in entries:
        title = clean_text(getattr(entry, "title", ""))
        summary = clean_text(getattr(entry, "summary", ""))
        link = getattr(entry, "link", "")
        published = getattr(entry, "published", "")

        text = title
        if summary and summary not in title:
            text = f"{title} — {summary}"

        mentions = detect_mentions(text, exclusions, watchlist)
        sentiment = simple_sentiment(text)

        posts.append({
            "source": source_name,
            "published": published,
            "text": text,
            "link": link,
            "mentions": mentions,
            "sentiment": sentiment,
        })

    return posts

def group_posts_by_company(posts):
    groups = defaultdict(list)

    for post in posts:
        seen_keys_for_post = set()
        for mention in post["mentions"]:
            key = (mention["company"], mention["ticker"])
            if key in seen_keys_for_post:
                continue
            seen_keys_for_post.add(key)

            groups[key].append({
                **post,
                "matched_term": mention["matched_term"],
            })

    return dict(sorted(groups.items(), key=lambda item: item[0][0]))

def render_grouped_results(posts, error=None):
    if error:
        st.error("A source could not be fetched right now.")
        st.write(error)

    groups = group_posts_by_company(posts)
    total_mentions = sum(len(items) for items in groups.values())

    col1, col2 = st.columns(2)
    col1.metric("Companies / tickers found", len(groups))
    col2.metric("Matching items found", total_mentions)

    if not groups:
        st.info("No company mentions found in the items scanned.")
        return

    summary_rows = []
    for (company, ticker), items in groups.items():
        sources = sorted(set(item["source"] for item in items))
        latest = items[0]["published"] if items else ""
        summary_rows.append({
            "Company": company,
            "Ticker": ticker,
            "Items": len(items),
            "Sources": ", ".join(sources),
            "Latest / first shown": latest,
        })

    st.subheader("Grouped summary")
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    st.subheader("Grouped matching items")

    for (company, ticker), items in groups.items():
        with st.expander(f"{company} ({ticker}) — {len(items)} item(s)", expanded=True):
            st.markdown(
                """
                <div style="max-height: 420px; overflow-y: auto; padding-right: 12px;">
                """,
                unsafe_allow_html=True,
            )

            for item in items:
                st.markdown(f"**{item['source']}** · {item['published']} · `{item['sentiment']}`")
                st.caption(f"Matched term: {item['matched_term']}")
                st.write(item["text"])
                if item["link"]:
                    st.link_button("Open source", item["link"])
                st.divider()

            st.markdown("</div>", unsafe_allow_html=True)

def render_all_items(posts):
    st.subheader("All scanned items")
    for post in posts:
        with st.container(border=True):
            st.caption(f'{post["source"]} · {post["published"]}')
            st.write(post["text"])
            if post["link"]:
                st.link_button("Open source", post["link"])

st.title("Trump Company & Stock Mention Tracker")
st.caption("Scans archived Trump Truth Social posts plus recent news headlines. Now includes automatic public-company/ticker detection.")

with st.sidebar:
    st.header("Settings")
    truth_limit = st.slider("Truth Social posts to scan", min_value=10, max_value=100, value=50, step=10)
    news_limit = st.slider("News headlines to scan", min_value=10, max_value=100, value=50, step=10)

    news_query = st.text_input(
        "News search query",
        value='Trump company OR stock OR shares OR CEO OR Apple OR Nvidia OR Intel OR Dell OR Tesla'
    )

    use_auto_tickers = st.checkbox(
        "Auto-detect public companies/tickers",
        value=True,
        help="Loads a large US-listed company/ticker directory, so the app can catch companies outside the manual watchlist."
    )

    exclude_raw = st.text_area(
        "Exclude companies / tickers / names",
        value="",
        placeholder="Example: DJT, Trump Media, Tesla, Elon Musk",
        help="Comma-separated. Excludes matching companies, tickers, or matched terms."
    )

    show_all = st.checkbox("Show all scanned items", value=False)

    st.markdown("---")
    st.caption("Truth source: Trump’s Truth RSS archive. News source: Google News RSS. Ticker source: Nasdaq symbol directories.")

exclusions = normalise_exclusions(exclude_raw)
watchlist = build_watchlist(use_auto_tickers=use_auto_tickers)

with st.sidebar:
    st.metric("Companies/tickers being scanned", len(watchlist))

tab1, tab2, tab3 = st.tabs(["Combined results", "Truth Social", "News"])

truth_posts, news_posts = [], []

try:
    truth_entries = fetch_rss(TRUTH_FEED_URL, limit=truth_limit)
    truth_posts = parse_entries(truth_entries, "Truth Social archive", exclusions, watchlist)
except Exception as e:
    truth_error = str(e)
else:
    truth_error = None

try:
    news_entries = fetch_rss(google_news_url(news_query), limit=news_limit)
    news_posts = parse_entries(news_entries, "News headline", exclusions, watchlist)
except Exception as e:
    news_error = str(e)
else:
    news_error = None

all_posts = truth_posts + news_posts

with tab1:
    if truth_error:
        st.warning(f"Truth Social source could not be fetched: {truth_error}")
    if news_error:
        st.warning(f"News source could not be fetched: {news_error}")

    combined_error = None
    if truth_error and news_error:
        combined_error = f"Truth Social error: {truth_error}\n\nNews error: {news_error}"

    render_grouped_results(all_posts, combined_error)
    if show_all:
        render_all_items(all_posts)

with tab2:
    render_grouped_results(truth_posts, truth_error)
    if show_all:
        render_all_items(truth_posts)

with tab3:
    render_grouped_results(news_posts, news_error)
    if show_all:
        render_all_items(news_posts)