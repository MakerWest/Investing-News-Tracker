import re
import html
import urllib.parse
import requests
import feedparser
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Trump Company Mention Tracker", layout="wide")

TRUTH_FEED_URL = "https://trumpstruth.org/feed"

WATCHLIST = {
    "Apple": {"ticker": "AAPL", "terms": ["apple", "aapl", "$aapl", "iphone"]},
    "Amazon": {"ticker": "AMZN", "terms": ["amazon", "amzn", "$amzn"]},
    "Nvidia": {"ticker": "NVDA", "terms": ["nvidia", "nvda", "$nvda"]},
    "Intel": {"ticker": "INTC", "terms": ["intel", "intc", "$intc"]},
    "Dell": {"ticker": "DELL", "terms": ["dell", "dell technologies", "$dell"]},
    "Tesla": {"ticker": "TSLA", "terms": ["tesla", "tsla", "$tsla", "elon musk"]},
    "Microsoft": {"ticker": "MSFT", "terms": ["microsoft", "msft", "$msft"]},
    "Meta": {"ticker": "META", "terms": ["meta", "facebook", "instagram", "zuckerberg", "$meta"]},
    "Google / Alphabet": {"ticker": "GOOGL", "terms": ["google", "alphabet", "googl", "goog", "$googl", "$goog"]},
    "Walmart": {"ticker": "WMT", "terms": ["walmart", "wmt", "$wmt"]},
    "Ford": {"ticker": "F", "terms": ["ford", "$f", "ford motor"]},
    "General Motors": {"ticker": "GM", "terms": ["general motors", "gm", "$gm"]},
    "Boeing": {"ticker": "BA", "terms": ["boeing", "$ba"]},
    "Lockheed Martin": {"ticker": "LMT", "terms": ["lockheed", "lockheed martin", "$lmt"]},
    "Trump Media": {"ticker": "DJT", "terms": ["truth social", "trump media", "djt", "$djt"]},
}

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
        timeout=20,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return feed.entries[:limit]

def google_news_url(query):
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

def detect_mentions(text):
    lower = text.lower()
    hits = []

    for company, data in WATCHLIST.items():
        for term in data["terms"]:
            term_l = term.lower()
            if term_l.startswith("$"):
                pattern = re.escape(term_l) + r"\b"
            else:
                pattern = r"\b" + re.escape(term_l) + r"\b"

            if re.search(pattern, lower):
                hits.append({
                    "company": company,
                    "ticker": data["ticker"],
                    "matched_term": term,
                })
                break

    return hits

def simple_sentiment(text):
    lower = text.lower()
    pos = sum(1 for word in POSITIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower))
    neg = sum(1 for word in NEGATIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower))

    if pos > neg:
        return "Positive / supportive"
    if neg > pos:
        return "Negative / critical"
    return "Neutral / unclear"

def parse_entries(entries, source_name):
    rows = []
    posts = []

    for entry in entries:
        title = clean_text(getattr(entry, "title", ""))
        summary = clean_text(getattr(entry, "summary", ""))
        link = getattr(entry, "link", "")
        published = getattr(entry, "published", "")

        text = title
        if summary and summary not in title:
            text = f"{title} — {summary}"

        mentions = detect_mentions(text)
        sentiment = simple_sentiment(text)

        item = {
            "source": source_name,
            "published": published,
            "text": text,
            "link": link,
            "mentions": mentions,
            "sentiment": sentiment,
        }
        posts.append(item)

        for mention in mentions:
            rows.append({
                "Source": source_name,
                "Published": published,
                "Company": mention["company"],
                "Ticker": mention["ticker"],
                "Matched term": mention["matched_term"],
                "Sentiment": sentiment,
                "Text": text[:320] + ("..." if len(text) > 320 else ""),
                "Link": link,
            })

    return rows, posts

st.title("Trump Company & Stock Mention Tracker")
st.caption("Simple demo: scans archived Trump Truth Social posts plus recent news headlines for company, ticker, product, and CEO mentions.")

with st.sidebar:
    st.header("Settings")
    truth_limit = st.slider("Truth Social posts to scan", min_value=10, max_value=100, value=50, step=10)
    news_limit = st.slider("News headlines to scan", min_value=10, max_value=100, value=50, step=10)
    news_query = st.text_input(
        "News search query",
        value='Trump company OR stock OR shares OR CEO OR Apple OR Nvidia OR Intel OR Dell OR Tesla'
    )
    show_all = st.checkbox("Show items with no company mentions", value=False)
    st.markdown("---")
    st.caption("Truth source: Trump’s Truth RSS archive. News source: Google News RSS.")

tab1, tab2, tab3 = st.tabs(["Combined results", "Truth Social", "News"])

truth_rows, truth_posts, news_rows, news_posts = [], [], [], []

# Truth Social
try:
    truth_entries = fetch_rss(TRUTH_FEED_URL, limit=truth_limit)
    truth_rows, truth_posts = parse_entries(truth_entries, "Truth Social archive")
except Exception as e:
    truth_error = str(e)
else:
    truth_error = None

# News
try:
    news_entries = fetch_rss(google_news_url(news_query), limit=news_limit)
    news_rows, news_posts = parse_entries(news_entries, "News headline")
except Exception as e:
    news_error = str(e)
else:
    news_error = None

all_rows = truth_rows + news_rows
all_posts = truth_posts + news_posts

def render_results(rows, posts, error=None):
    if error:
        st.error("A source could not be fetched right now.")
        st.write(error)

    st.metric("Company mentions found", len(rows))

    if rows:
        st.subheader("Detected company mentions")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("Matching items")
        for post in posts:
            if not post["mentions"]:
                continue

            names = ", ".join([f'{m["company"]} ({m["ticker"]})' for m in post["mentions"]])
            with st.container(border=True):
                st.markdown(f"### {names}")
                st.caption(f'{post["source"]} · {post["published"]} · {post["sentiment"]}')
                st.write(post["text"])
                if post["link"]:
                    st.link_button("Open source", post["link"])
    else:
        st.info("No watchlist company mentions found in the items scanned.")

    if show_all:
        st.subheader("All scanned items")
        for post in posts:
            with st.container(border=True):
                st.caption(f'{post["source"]} · {post["published"]}')
                st.write(post["text"])
                if post["link"]:
                    st.link_button("Open source", post["link"])

with tab1:
    combined_error = None
    if truth_error and news_error:
        combined_error = f"Truth Social error: {truth_error}\n\nNews error: {news_error}"
    elif truth_error:
        st.warning(f"Truth Social source could not be fetched: {truth_error}")
    elif news_error:
        st.warning(f"News source could not be fetched: {news_error}")

    render_results(all_rows, all_posts, combined_error)

with tab2:
    render_results(truth_rows, truth_posts, truth_error)

with tab3:
    render_results(news_rows, news_posts, news_error)