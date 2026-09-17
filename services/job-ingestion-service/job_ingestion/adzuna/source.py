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

# How long an Adzuna posting is kept after a run last saw it. Every request is
# windowed to postings created in the last `max_days_old` days, so a posting is
# seen during its first days and never again, live or not, and the API has no
# closing signal. The window decides what is seen; this lifetime decides how
# long it is kept, so the two are independent: a posting is shown for thirty
# days after it was last seen, roughly thirty to thirty-two days after it was
# created, whether or not Adzuna still lists it. The terms permit holding the
# data while the licence stands, and a posting older than this is more often
# filled than open.
PRESUMED_LIFETIME = timedelta(days=30)

# The markets the project covers, as the ISO codes Adzuna paths are keyed by.
DEFAULT_COUNTRIES = ("gb", "us", "de", "fr", "nl", "at", "ch", "es", "it", "pl", "ca", "au")
