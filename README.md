# Trump Company & Stock Mention Tracker

This version includes "Level 2.5" automatic company/ticker detection.

Features:

- Truth Social archive scanning
- Google News RSS headline scanning
- Automatic public-company/ticker detection using Nasdaq symbol directories
- Manual watchlist for CEOs/products/brand references
- Exclusions
- Grouped results by company/ticker
- Scrollable grouped sections

## Deploy

Replace your existing GitHub files with:

- app.py
- requirements.txt
- README.md

Then redeploy or refresh your Streamlit app.

## Notes

This does not require an AI API key or paid data provider.

It will catch far more companies than the fixed watchlist, but it can still miss private companies, very new listings, unusual references, or company names not included in the public ticker directories.