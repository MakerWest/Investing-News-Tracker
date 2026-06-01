import re
import html
from datetime import datetime
import requests
import feedparser
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Trump Company Mention Tracker", layout="wide")

FEED_URL = "https://trumpstruth.org/feed"

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
    "support", "like", "love", "praise", "good", "tremendous"
]
NEGATIVE_WORDS = [
    "boycott", "bad", "weak", "terrible", "disaster", "avoid", "failed",
    "failure", "crooked", "fake", "overpriced", "tariff", "punish"
]

def clean_text(raw):
    raw = html.unescape(raw or "")
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)

def fetch_posts(limit=50):
    response = requests.get(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 Trump Company Mention Tracker"},
        timeout=20,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return feed.entries[:limit]

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

st.title("Trump Company Mention Tracker")
st.caption("Simple demo: scans recent archived Truth Social posts and highlights company, ticker, product, and CEO mentions.")

with st.sidebar:
    st.header("Settings")
    limit = st.slider("Posts to scan", min_value=10, max_value=100, value=50, step=10)
    show_all_posts = st.checkbox("Show posts with no company mentions", value=False)
    st.markdown("---")
    st.caption("Source: Trump’s Truth RSS archive, not the direct Truth Social API.")

try:
    entries = fetch_posts(limit=limit)

    rows = []
    all_posts = []

    for entry in entries:
        text = clean_text(getattr(entry, "summary", "") or getattr(entry, "title", ""))
        title = clean_text(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        published = getattr(entry, "published", "")

        if title and title not in text:
            combined_text = f"{title} — {text}"
        else:
            combined_text = text

        mentions = detect_mentions(combined_text)
        sentiment = simple_sentiment(combined_text)

        all_posts.append({
            "published": published,
            "text": combined_text,
            "link": link,
            "mentions": mentions,
            "sentiment": sentiment,
        })

        for mention in mentions:
            rows.append({
                "Published": published,
                "Company": mention["company"],
                "Ticker": mention["ticker"],
                "Matched term": mention["matched_term"],
                "Sentiment": sentiment,
                "Post": combined_text[:300] + ("..." if len(combined_text) > 300 else ""),
                "Link": link,
            })

    st.metric("Company mentions found", len(rows))

    if rows:
        st.subheader("Detected company mentions")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("Matching posts")
        for post in all_posts:
            if not post["mentions"]:
                continue

            names = ", ".join([f'{m["company"]} ({m["ticker"]})' for m in post["mentions"]])
            with st.container(border=True):
                st.markdown(f"### {names}")
                st.caption(f'{post["published"]} · {post["sentiment"]}')
                st.write(post["text"])
                if post["link"]:
                    st.link_button("Open source", post["link"])

    else:
        st.info("No watchlist company mentions found in the recent posts scanned.")

    if show_all_posts:
        st.subheader("All scanned posts")
        for post in all_posts:
            with st.container(border=True):
                st.caption(post["published"])
                st.write(post["text"])
                if post["link"]:
                    st.link_button("Open source", post["link"])

except Exception as e:
    st.error("The app could not fetch the RSS feed right now.")
    st.write(str(e))
    st.info("Try refreshing the app. If this keeps happening, the archive feed may be temporarily unavailable.")