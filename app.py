import re
import html
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

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

POSITIVE_WORDS = ["buy", "great", "strong", "best", "excellent", "beautiful", "winner", "support", "like", "love", "praise", "good", "tremendous", "invest", "deal", "approved", "backing", "boost", "wins"]
NEGATIVE_WORDS = ["boycott", "bad", "weak", "terrible", "disaster", "avoid", "failed", "failure", "crooked", "fake", "overpriced", "tariff", "punish", "criticizes", "attacks", "threatens", "ban", "blocked", "slams"]

def clean_text(raw):
    raw = html.unescape(raw or "")
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)

def short_text(text, max_chars=450):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

def parse_datetime_safe(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def human_age(dt):
    if not dt:
        return "Unknown"
    delta = datetime.now(timezone.utc) - dt
    seconds = max(0, int(delta.total_seconds()))
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days:
        return f"{days} day(s), {hours % 24} hour(s) old"
    if hours:
        return f"{hours} hour(s), {minutes % 60} minute(s) old"
    if minutes:
        return f"{minutes} minute(s) old"
    return f"{seconds} second(s) old"

def fetch_rss(url, limit=50, bust_cache=False):
    params = {}
    if bust_cache:
        params["_"] = str(int(datetime.now(timezone.utc).timestamp()))
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0 Trump Company Mention Tracker", "Cache-Control": "no-cache", "Pragma": "no-cache"},
        timeout=20,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return feed.entries[:limit], response

def google_news_url(query):
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

def normalise_exclusions(raw):
    return {x.strip().lower().replace("$", "") for x in raw.split(",") if x.strip()}

def is_excluded(company, ticker, matched_term, exclusions):
    if not exclusions:
        return False
    checks = {company.lower(), ticker.lower(), ticker.lower().replace("$", ""), matched_term.lower().replace("$", "")}
    return any(exclusion in checks for exclusion in exclusions)

def detect_mentions(text, exclusions):
    lower = text.lower()
    hits = []
    for company, data in WATCHLIST.items():
        for term in data["terms"]:
            term_l = term.lower()
            pattern = re.escape(term_l) + r"\b" if term_l.startswith("$") else r"\b" + re.escape(term_l) + r"\b"
            if re.search(pattern, lower):
                if not is_excluded(company, data["ticker"], term, exclusions):
                    hits.append({"company": company, "ticker": data["ticker"], "matched_term": term})
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
        published_dt = parse_datetime_safe(published)
        full_text = title
        if summary and summary not in title:
            full_text = f"{title} — {summary}"
        mentions = detect_mentions(full_text, exclusions)
        posts.append({
            "source": source_name,
            "published": published,
            "published_dt": published_dt,
            "age": human_age(published_dt),
            "full_text": full_text,
            "display_text": short_text(full_text),
            "link": link,
            "mentions": mentions,
            "sentiment": simple_sentiment(full_text),
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
            groups[key].append({**post, "matched_term": mention["matched_term"]})
    return dict(sorted(groups.items(), key=lambda item: item[0][0]))

def render_grouped_results(posts, error=None, key_prefix=""):
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
    summary_rows, company_options, key_lookup = [], ["Show all"], {}
    for (company, ticker), items in groups.items():
        sources = sorted(set(item["source"] for item in items))
        latest = items[0]["published"] if items else ""
        label = f"{company} ({ticker})"
        company_options.append(label)
        key_lookup[label] = (company, ticker)
        summary_rows.append({"Company": company, "Ticker": ticker, "Items": len(items), "Sources": ", ".join(sources), "Latest / first shown": latest})
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)
    selected_company = st.radio("Show matching items for", company_options, horizontal=True, key=f"{key_prefix}_company_filter")
    groups_to_render = groups if selected_company == "Show all" else {key_lookup[selected_company]: groups[key_lookup[selected_company]]}
    st.subheader("Grouped matching items")
    for (company, ticker), items in groups_to_render.items():
        with st.expander(f"{company} ({ticker}) — {len(items)} item(s)", expanded=False):
            for item in items:
                st.markdown(f"**{item['source']}** · {item['published']} · `{item['sentiment']}`")
                st.caption(f"Matched term: {item['matched_term']} · Feed age: {item.get('age', 'Unknown')}")
                st.write(item["display_text"])
                with st.expander("Show full text"):
                    st.write(item["full_text"])
                if item["link"]:
                    st.link_button("Open source", item["link"])
                st.divider()

def render_all_items(posts):
    st.subheader("All scanned items")
    for post in posts:
        with st.container(border=True):
            st.caption(f'{post["source"]} · {post["published"]} · {post.get("age", "Unknown")}')
            st.write(post["display_text"])
            with st.expander("Show full text"):
                st.write(post["full_text"])
            if post["link"]:
                st.link_button("Open source", post["link"])

def render_truth_diagnostics(truth_posts, response=None, error=None):
    st.header("Truth Social archive freshness check")
    st.write("This tab shows the latest raw archive items, whether or not they mention any company.")
    if error:
        st.error("Could not fetch the Truth Social archive feed.")
        st.write(error)
        return
    if not truth_posts:
        st.warning("The feed returned no posts.")
        return
    newest = truth_posts[0]
    newest_dt = newest.get("published_dt")
    col1, col2, col3 = st.columns(3)
    col1.metric("Raw archive posts fetched", len(truth_posts))
    col2.metric("Newest archive post age", human_age(newest_dt))
    col3.metric("Newest post has company mention?", "Yes" if newest["mentions"] else "No")
    if response is not None:
        st.caption(f"Feed URL: {TRUTH_FEED_URL} · HTTP status: {response.status_code} · Fetched at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    st.info("If the newest archive post is older than the newest post visible on Truth Social, the archive/feed is stale or incomplete. If it is recent but missing from the main results, it probably has no tracked company mention.")
    st.subheader("Latest raw archive posts")
    rows = []
    for i, post in enumerate(truth_posts[:30], start=1):
        mentions = ", ".join([f'{m["company"]} ({m["ticker"]})' for m in post["mentions"]]) or "None"
        rows.append({"#": i, "Published": post["published"], "Age": post.get("age", "Unknown"), "Detected companies": mentions, "Preview": post["display_text"], "Link": post["link"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("Raw post details")
    for i, post in enumerate(truth_posts[:10], start=1):
        with st.expander(f'{i}. {post["published"]} · {post.get("age", "Unknown")} · Mentions: {", ".join([m["company"] for m in post["mentions"]]) or "None"}'):
            st.write(post["display_text"])
            with st.expander("Show full text"):
                st.write(post["full_text"])
            if post["link"]:
                st.link_button("Open archive item", post["link"])

st.title("Trump Company & Stock Mention Tracker")
st.caption("Scans archived Trump Truth Social posts plus recent news headlines for company, ticker, product, and CEO mentions.")

with st.sidebar:
    st.header("Settings")
    truth_limit = st.slider("Truth Social posts to scan", min_value=10, max_value=100, value=50, step=10)
    news_limit = st.slider("News headlines to scan", min_value=10, max_value=100, value=50, step=10)
    news_query = st.text_input("News search query", value='Trump company OR stock OR shares OR CEO OR Apple OR Nvidia OR Intel OR Dell OR Tesla')
    exclude_raw = st.text_area("Exclude companies / tickers / names", value="", placeholder="Example: DJT, Trump Media, Tesla, Elon Musk", help="Comma-separated. Excludes matching companies, tickers, or matched watchlist terms.")
    show_all = st.checkbox("Show all scanned items", value=False)
    bust_cache = st.checkbox("Try to bypass RSS cache", value=True, help="Adds a timestamp query parameter and no-cache headers when fetching the Truth archive feed.")
    st.markdown("---")
    st.caption("Truth source: Trump’s Truth RSS archive. News source: Google News RSS.")

exclusions = normalise_exclusions(exclude_raw)

tab1, tab2, tab3, tab4 = st.tabs(["Combined results", "Truth Social", "News", "Truth freshness check"])

truth_posts, news_posts = [], []
truth_response = None

try:
    truth_entries, truth_response = fetch_rss(TRUTH_FEED_URL, limit=truth_limit, bust_cache=bust_cache)
    truth_posts = parse_entries(truth_entries, "Truth Social archive", exclusions)
except Exception as e:
    truth_error = str(e)
else:
    truth_error = None

try:
    news_entries, _ = fetch_rss(google_news_url(news_query), limit=news_limit, bust_cache=False)
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
    combined_error = f"Truth Social error: {truth_error}\\n\\nNews error: {news_error}" if truth_error and news_error else None
    render_grouped_results(all_posts, combined_error, key_prefix="combined")
    if show_all:
        render_all_items(all_posts)

with tab2:
    render_grouped_results(truth_posts, truth_error, key_prefix="truth")
    if show_all:
        render_all_items(truth_posts)

with tab3:
    render_grouped_results(news_posts, news_error, key_prefix="news")
    if show_all:
        render_all_items(news_posts)

with tab4:
    render_truth_diagnostics(truth_posts, response=truth_response, error=truth_error)