# Flight Price Tracker

GitHub Actions runs at 08:00, 14:00, 20:00 Taiwan time (scheduled runs may be delayed). Each run checks one rotating airline with at most two SerpApi queries, so all three airlines are checked once per day when jobs run on schedule. Monthly nominal use: ~180 API calls per 30 days, not including manual runs. Check your API plan limits.

## Setup
1. Create a **public** GitHub repository (GitHub Free Pages requires public repos).
2. Upload these files, preserving `.github/workflows/update.yml`.
3. Add repository secret `SERPAPI_KEY` under Settings > Secrets and variables > Actions.
4. In Actions, run `Update flight prices` > Run workflow.
5. In Settings > Pages, choose `Deploy from a branch`, branch `main`, folder `/(root)`.
6. Open `https://YOUR-USERNAME.github.io/flight-price-tracker/` after deployment.

**Caveats:** The code stores only the cheapest matching return option for the cheapest token-bearing outbound option; it is not guaranteed to be the globally cheapest available ticket. It strictly checks 2027-01-03 return arrival. Checked luggage and final checkout prices are not verified. GitHub scheduled jobs may be delayed or missed. A public repository exposes flight price history but not the GitHub Actions secret.
