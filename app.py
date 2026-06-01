import re
from datetime import datetime, timezone
from html import unescape

import pandas as pd
import requests
import streamlit as st

TRUTH_ACCOUNT = "realDonaldTrump"

DEFAULT_WATCHLIST = {
    "Apple (AAPL)": ["apple", "aapl", "$aapl", "iphone", "tim cook"],
    "Amazon (AMZN)": ["amazon", "amzn", "$amzn", "jeff bezos", "andy jassy"],
    "Nvidia (NVDA)": ["nvidia", "nvda", "$nvda", "jensen huang"],
    "Intel (INTC)": ["intel", "intc", "$intc"],
    "Tesla (TSLA)": ["tesla", "tsla", "$tsla", "elon musk"],
    "Microsoft (MSFT)": ["microsoft", "msft", "$msft", "satya nadella"],
    "Meta (META)": ["meta", "facebook", "instagram", "zuckerberg", "$meta"],
    "Alphabet / Google (GOOGL)": ["google", "alphabet", "googl", "goog", "$googl", "$goog"],
    "Walmart (WMT)": ["walmart", "wmt", "$wmt"],
    "Trump Media (DJT)": ["truth social", "trump media", "djt", "$djt"],
    "Boeing (BA)": ["boeing", "$ba"],
    "Ford (F)": ["ford", "$f"],
    "General Motors (GM)": ["general motors", "gm", "$gm"],
    "JPMorgan (JPM)": ["jpmorgan", "jp morgan", "jamie dimon", "$jpm"],
    "Goldman Sachs (GS)": ["goldman", "goldman sachs", "$gs"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CompanyMentionTracker/1.0)",
    "Accept": "application/json,text/plain,*/*",
}


def strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(ttl=120)
def lookup_account_id() -> str:
    url = f"https://truthsocial.com/api/v1/accounts/lookup?acct={TRUTH_ACCOUNT}"
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()["id"]


@st.cache_data(ttl=120)
def fetch_posts(limit: int):
    account_id = lookup_account_id()
    url = f"https://truthsocial.com/api/v1/accounts/{account_id}/statuses"
    params = {
        "exclude_replies": "false",
        "only_replies": "false",
        "with_muted": "true",
        "limit": min(limit, 40),
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def build_watchlist(extra_terms: str):
    watchlist = dict(DEFAULT_WATCHLIST)
    for raw in extra_terms.splitlines():
        if not raw.strip():
            continue
        if ":" in raw:
            name, terms = raw.split(":", 1)
            watchlist[name.strip()] = [t.strip() for t in terms.split(",") if t.strip()]
    return watchlist


def term_matches(text: str, term: str) -> bool:
    lower = text.lower()
    term = term.lower().strip()
    if term.startswith("$"):
        return re.search(re.escape(term) + r"\b", lower) is not None
    if len(term) <= 4 and term.isalpha():
        return re.search(r"(?<![$A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", lower) is not None
    return re.search(r"\b" + re.escape(term) + r"\b", lower) is not None


def detect_mentions(text: str, watchlist):
    hits = []
    for company, terms in watchlist.items():
        matched_terms = [term for term in terms if term_matches(text, term)]
        if matched_terms:
            hits.append((company, ", ".join(matched_terms)))
    return hits


def classify_sentiment(text: str) -> str:
    t = text.lower()
    positive = ["great", "excellent", "strong", "record", "winner", "buy", "rise", "rising", "thank", "congratulations", "successful"]
    negative = ["tariff", "bad", "weak", "terrible", "disaster", "boycott", "fake", "illegal", "fine", "punish", "tax", "drop"]
    pos = sum(word in t for word in positive)
    neg = sum(word in t for word in negative)
    if pos > neg:
        return "Positive / supportive"
    if neg > pos:
        return "Negative / risk signal"
    return "Neutral / mention"


st.set_page_config(page_title="Trump Company Mention Tracker", page_icon="📈", layout="wide")

st.title("Trump Truth Social Company Mention Tracker")
st.caption("Scans recent posts from @realDonaldTrump and highlights company, ticker, product, and CEO mentions.")

with st.sidebar:
    st.header("Settings")
    limit = st.slider("Posts to scan", min_value=5, max_value=40, value=25)
    extra_terms = st.text_area(
        "Add custom companies",
        placeholder="Example:\nNetflix (NFLX): netflix, nflx, $nflx, reed hastings",
        height=120,
    )
    st.caption("Format: Company Name: term 1, term 2, $ticker")
    refresh = st.button("Refresh now")

if refresh:
    st.cache_data.clear()

watchlist = build_watchlist(extra_terms)

try:
    posts = fetch_posts(limit)
    rows = []

    for post in posts:
        text = strip_html(post.get("content", ""))
        mentions = detect_mentions(text, watchlist)
        if not mentions:
            continue
        created_at = post.get("created_at")
        rows.append(
            {
                "Created": created_at,
                "Companies": ", ".join(company for company, _ in mentions),
                "Matched terms": ", ".join(terms for _, terms in mentions),
                "Signal": classify_sentiment(text),
                "Post": text,
                "URL": post.get("url", ""),
            }
        )

    left, middle, right = st.columns(3)
    left.metric("Posts scanned", len(posts))
    middle.metric("Matching posts", len(rows))
    right.metric("Watchlist entries", len(watchlist))

    st.divider()

    if not rows:
        st.info("No company or stock mentions found in the posts scanned.")
    else:
        df = pd.DataFrame(rows)
        st.subheader("Latest detected mentions")
        st.dataframe(df[["Created", "Companies", "Matched terms", "Signal"]], use_container_width=True, hide_index=True)

        st.subheader("Post details")
        for row in rows:
            with st.container(border=True):
                st.markdown(f"**{row['Companies']}**")
                st.caption(f"{row['Created']} · {row['Signal']}")
                st.write(row["Post"])
                if row["URL"]:
                    st.link_button("Open Truth Social post", row["URL"])

    st.caption(f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

except Exception as e:
    st.error("The app could not fetch Truth Social posts right now.")
    st.write("This can happen if Truth Social blocks automated requests or changes its public endpoints.")
    st.code(str(e))
