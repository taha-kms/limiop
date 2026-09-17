"""What Adzuna is to this service: identity, credentials, ranking, and budget.

Kept apart from the client so the records and normalizer can name the source
without importing transport, and so the entry point can ask for credentials
before any client exists to carry them.
"""

from datetime import timedelta

from job_ingestion.credentials import Credential
from job_ingestion.quota import Quota

SOURCE_KEY = "adzuna"
DISPLAY_NAME = "Adzuna"
DEFAULT_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Adzuna aggregates postings that employers publish elsewhere and serves an
# excerpt of each, so where it disagrees with an employer's own board the
# board is the better account. Ranked with the other aggregators, below every
# board.
PRECEDENCE = 10

# The app id is published alongside the key and identifies the application;
# only the key is confidential. Both are required.
APP_ID = Credential("SKILLSYNC_ADZUNA_APP_ID", secret=False)
APP_KEY = Credential("SKILLSYNC_ADZUNA_APP_KEY")
CREDENTIALS = (APP_ID, APP_KEY)

# The published ceilings (checked 2026-09-15): 250 hits a day, 1,000 a week,
# 2,500 a month. The monthly one binds: 2,500 over a 31-day month is 80 a
# day, against 142 a day from the weekly ceiling and 250 from the daily one.
# The ledger counts days only, so the daily cap is derived from the tightest
# ceiling rather than copied from the daily one: 80 x 31 = 2,480 <= 2,500,
# 80 x 7 = 560 <= 1,000, and 80 <= 250. A schedule that fits under 80 a day
# therefore fits under all three.
PUBLISHED_DAILY_CEILING = 250
WEEKLY_CEILING = 1000
MONTHLY_CEILING = 2500
DAILY_QUOTA = Quota(per_day=MONTHLY_CEILING // 31)

# How much longer than its window a posting may go unseen before it is
# presumed gone. Every request is windowed, so a run sees only what the window
# holds and can never claim the end of the source; the window plus this grace
# is what the run states instead. Five days covers a run of missed schedules:
# a quota spent early, a provider outage, a failed deployment over a weekend.
RETIREMENT_GRACE = timedelta(days=5)

# The markets the project covers, as the ISO codes Adzuna paths are keyed by.
DEFAULT_COUNTRIES = ("gb", "us", "de", "fr", "nl", "at", "ch", "es", "it", "pl", "ca", "au")
