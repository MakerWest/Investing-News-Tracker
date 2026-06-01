import re
import html
import urllib.parse
from collections import defaultdict

import requests
import feedparser
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Trump Company Mention Tracker", layout="wide")

TRUTH_FEED_URL = "https://trumpstruth.org/feed"

WATCHLIST = {
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

def short_text(text, max_chars=450):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

def anchor_id(company, ticker):
    raw = f"{company}-{ticker}".lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw

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

def detect_mentions(text, exclusions):
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
                if not is_excluded(company, data["ticker"], term, exclusions):
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

def parse_entries(entries, source_name, exclusions):
    posts = []

    for entry in entries:
        title = clean_text(getattr(entry, "title", ""))
        summary = clean_text(getattr(entry, "summary", ""))
        link = getattr(entry, "link", "")
        published = getattr(entry, "published", "")

        full_text = title
        if summary and summary not in title:
            full_text = f"{title} — {summary}"

        mentions = detect_mentions(full_text, exclusions)
        sentiment = simple_sentiment(full_text)

        posts.append({
            "source": source_name,
            "published": published,
            "full_text": full_text,
            "display_text": short_text(full_text),
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
        st.info("No watchlist company mentions found in the items scanned.")
        return

    st.subheader("Grouped summary")

    st.markdown(
        '''
        <style>
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 8px;
            margin-bottom: 20px;
        }
        .summary-card {
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 10px;
            padding: 10px 12px;
            text-decoration: none !important;
            display: block;
            color: inherit !important;
            background: rgba(250, 250, 250, 0.03);
        }
        .summary-card:hover {
            border-color: rgba(255, 75, 75, 0.9);
            background: rgba(255, 75, 75, 0.06);
        }
        .summary-title {
            font-weight: 700;
            margin-bottom: 2px;
        }
        .summary-meta {
            font-size: 0.9rem;
            opacity: 0.75;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    cards = ['<div class="summary-grid">']
    for (company, ticker), items in groups.items():
        aid = anchor_id(company, ticker)
        sources = ", ".join(sorted(set(item["source"] for item in items)))
        cards.append(
            f'''
            <a class="summary-card" href="#{aid}">
                <div class="summary-title">{html.escape(company)} ({html.escape(ticker)})</div>
                <div class="summary-meta">{len(items)} item(s) · {html.escape(sources)}</div>
            </a>
            '''
        )
    cards.append("</div>")
    st.markdown("".join(cards), unsafe_allow_html=True)

    st.subheader("Grouped matching items")

    for (company, ticker), items in groups.items():
        aid = anchor_id(company, ticker)
        st.markdown(f'<div id="{aid}"></div>', unsafe_allow_html=True)

        with st.expander(f"{company} ({ticker}) — {len(items)} item(s)", expanded=True):
            st.markdown(
                '<div style="max-height: 420px; overflow-y: auto; padding-right: 12px;">',
                unsafe_allow_html=True,
            )

            for item in items:
                st.markdown(f"**{item['source']}** · {item['published']} · `{item['sentiment']}`")
                st.caption(f"Matched term: {item['matched_term']}")
                st.write(item["display_text"])

                with st.expander("Show full text"):
                    st.write(item["full_text"])

                if item["link"]:
                    st.link_button("Open source", item["link"])
                st.divider()

            st.markdown("</div>", unsafe_allow_html=True)

def render_all_items(posts):
    st.subheader("All scanned items")
    for post in posts:
        with st.container(border=True):
            st.caption(f'{post["source"]} · {post["published"]}')
            st.write(post["display_text"])
            with st.expander("Show full text"):
                st.write(post["full_text"])
            if post["link"]:
                st.link_button("Open source", post["link"])

st.title("Trump Company & Stock Mention Tracker")
st.caption("Scans archived Trump Truth Social posts plus recent news headlines for company, ticker, product, and CEO mentions.")

with st.sidebar:
    st.header("Settings")
    truth_limit = st.slider("Truth Social posts to scan", min_value=10, max_value=100, value=50, step=10)
    news_limit = st.slider("News headlines to scan", min_value=10, max_value=100, value=50, step=10)

    news_query = st.text_input(
        "News search query",
        value='Trump company OR stock OR shares OR CEO OR Apple OR Nvidia OR Intel OR Dell OR Tesla'
    )

    exclude_raw = st.text_area(
        "Exclude companies / tickers / names",
        value="",
        placeholder="Example: DJT, Trump Media, Tesla, Elon Musk",
        help="Comma-separated. Excludes matching companies, tickers, or matched watchlist terms."
    )

    show_all = st.checkbox("Show all scanned items", value=False)

    st.markdown("---")
    st.caption("Truth source: Trump’s Truth RSS archive. News source: Google News RSS.")

exclusions = normalise_exclusions(exclude_raw)

tab1, tab2, tab3 = st.tabs(["Combined results", "Truth Social", "News"])

truth_posts, news_posts = [], []

try:
    truth_entries = fetch_rss(TRUTH_FEED_URL, limit=truth_limit)
    truth_posts = parse_entries(truth_entries, "Truth Social archive", exclusions)
except Exception as e:
    truth_error = str(e)
else:
    truth_error = None

try:
    news_entries = fetch_rss(google_news_url(news_query), limit=news_limit)
    news_posts = parse_entries(news_entries, "News headline", exclusions)
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