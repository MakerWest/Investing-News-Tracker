# Trump Company & Stock Mention Tracker

This version adds a Truth Social archive freshness experiment.

New diagnostic tab:

- Shows latest raw archive posts, even if they do not match any company/ticker
- Shows newest archive post age
- Shows whether the newest post has a company mention
- Shows archive feed fetch time and HTTP status
- Adds an optional cache-bypass toggle

This lets you tell whether:
1. The archive feed is stale/incomplete, or
2. The post exists in the archive but simply does not mention a tracked company.

## Deploy

Replace your existing GitHub files with:

- app.py
- requirements.txt
- README.md

Then redeploy or refresh your Streamlit app.