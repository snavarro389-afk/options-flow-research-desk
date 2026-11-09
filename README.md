# Options Flow Research Desk

A Barchart-first options activity research and paper-tracking dashboard. This project is deliberately designed for delayed/manual data: it does not scrape Barchart, claim real-time flow, or place trades.

## Version 0.1
- Import Barchart Unusual Options Activity CSV exports.
- Add individual contracts manually.
- Normalize common CSV column names.
- Score observations separately for intraday and swing research.
- Filter broad-market activity or the starter watchlist.
- Save paper-tracked ideas and outcomes in a local SQLite database.
- Clearly label source and observation time.

## Data limitations
Barchart's Unusual Options Activity page reports options data delayed approximately 25–30 minutes and refreshes around every five minutes during the session. Free site members can download the displayed table as CSV, subject to a one-download-per-day limit. Historical report access and additional filtering may require Premier. See:
- https://www.barchart.com/options/unusual-activity
- https://help.barchart.com/support/solutions/articles/242687-what-time-does-the-unusual-options-activity-page-start-updating-

A high volume/open-interest ratio is a screening clue, not proof of opening trades, institutional intent, or bullish/bearish conviction. Barchart's sentiment flag is based on the last trade relative to bid/ask and should not be treated as a complete trade tape.

## Run locally
Python 3.10+ recommended.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy without maintaining a computer
1. Push this repository to GitHub.
2. Open https://share.streamlit.io/ and sign in with GitHub.
3. Choose this repository, branch `main`, and main file `app.py`.
4. Deploy.

The SQLite database is suitable for an initial single-user prototype, but hosted app filesystems may reset or be ephemeral. Export paper-tracking records regularly. For durable cloud persistence, a managed database will be a later phase.

## Barchart workflow
1. Open https://www.barchart.com/options/unusual-activity
2. Sign in to your Barchart site-member account.
3. Download the currently displayed table as CSV.
4. Upload the CSV in the dashboard's **Import Barchart CSV** section.
5. Check the import preview and source timestamp before relying on the scores.

## Starter watchlist
SPY, QQQ, IWM, NVDA, TSLA, META, AAPL, AMD, AMZN, MSFT, GOOGL, NFLX.

## Scoring status
All scoring weights are experimental placeholders for paper research, not validated predictive models or financial advice. The app stores the raw imported fields and does not infer whether a trade opened or closed a position.
