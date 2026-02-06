## Setup

* Install uv
* uv sync

### GCloud Access Setup

Google cloud's tools are horrible, but we're stuck with GCal API so might as well use google cloud buckets too.

* Ask for a service account and save the creds as `./cal-creds.json`
* `brew install --cask gcloud-cli`
* `gcloud auth activate-service-account --key-file=cal-creds.json`
* `gsutil`

## Running the tooo

```bash
# Pull the latest DB
gsutil cp gs://bikegroups-org/calendar_sync_db/calendar_sync.db ./data/calendar_sync.db 
# Run
uv run calendar-sync --help
# Push the DB
gsutil cp ./data/calendar_sync.db gs://bikegroups-org/calendar_sync_db/calendar_sync.db
```

## Example

```bash
➜  calendar-sync git:(main) ✗ uv run calendar-sync process --limit 2
Fetching feed: https://rssglue.subdavis.com/feed/cycling-merge/rss
Found 30 posts in feed
14 unprocessed posts

Processing 1/2: These are my neighbors 🥲...
  1 image(s)
  Decision: ignore (confidence: 75%)
  This post is primarily a reflection/documentation post about a community gathering that has already occurred, as evidenced by the photo and present/past tense language. While it mentions "Walk these streets with Recovery Bike Shop every Thursday at
5:30," this is presented as general information about an ongoing activity rather than an announcement of a specific upcoming event. The post lacks key event details (specific date, meeting location, etc.) that would be expected in an event announcement.
This appears to be community outreach/awareness content rather than an event announcement.
  Tokens: 17,846 in / 810 out = $0.0657
  Log: /Users/brandondavis/github.com/calendar-sync/logs/20260205-231622-6e41676e.log

Processing 2/2: Come and smell the roses with us!...
  1 image(s)
  Decision: create (confidence: 98%)
  This is clearly an event announcement for a group ride on February 15, 2026. The image contains the date "Feb. 15 2026" and both the post text and image provide detailed event information including meet time (12:00 PM), roll time (12:15 PM), start
location (Behind Bars Bicycle Shop), destination (Como Zoo Conservatory), ending location (The Briar Bar), and distance (15ish miles). The post was published on Feb 2, 2026, which is before the event date. No existing events were found on this date or
matching the Como Conservatory keyword.
  Event: Como Conservatory Group Ride
  Date: 2026-02-15 12:00
  Location: Behind Bars Bicycle Shop
  Calendar event: e4ndi8pb6ugl0u5i5k38tpbm3o
  Tokens: 17,769 in / 1,035 out = $0.0688
  Log: /Users/brandondavis/github.com/calendar-sync/logs/20260205-231647-930da5ee.log

Total cost: $0.1345
Cumulative cost: $0.7296
```