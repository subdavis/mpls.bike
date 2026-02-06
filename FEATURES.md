I want to build an automation that reads posts from an RSS feed, determines if they are posts about an event that someone might attend, and puts them into a google calendar.

It's likely that the same event may appear in the feed multiple times.  The RSS posts are largely going to be derived from instagram posts using a merge feed from RSS glue (this app) but I want to keep this automation completely separate from RSS Glue.

My idea is to build this using Claude Code because I suspect it's going to involve intelligent manipulation of the calendar (For example, an event may be announced, announced again, postponed, and then canceled).

I want to be able to run a command that processes new posts from the feed one at a time and only processes them once.

Event information may be embedded in the image only (it could be a poster) so I want to feed the images in as well.

## Command line tool that invokes Claude Code SDK

Have a deterministic program pull the latests posts and invoke claude code sdk once per post.

Give claude a number of tools for accessing a calendar and submitting its decision.

Use the google calendar api directly.

## Data Source

https://rssglue.subdavis.com/feed/cycling-merge/rss

## SQLite

Use sqlite db in `./data`

## Github Action

I want this to run scheduled nightly.  Also make it possible to run from the github actions UI.

you can use gsutil for this.

1. Download the db from `gs://bikegroups-org/calendar_sync_db/calendar_sync.db`
1. Run Sync (requires ANTHROPIC_API_KEY and ./cal-creds.json)
1. cat every log in the logs directory
1. Re-upload the DB

```
jobs:
  job_id:
    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
    - id: 'checkout'
      uses: 'actions/checkout@v4'

    - name: Create Google Calendar credentials file
      run: echo '${{ secrets.GOOGLE_CALENDAR_CREDENTIALS }}' > cal-creds.json

    - id: 'auth'
      uses: 'google-github-actions/auth@v3'
      with:
       credentials_json: // From a secret

    - name: 'Set up Cloud SDK'
      uses: 'google-github-actions/setup-gcloud@v3'
      with:
        version: '>= 363.0.0'
``` 

## Updates

1. Update the script to get the credentials path from an environment variable (but still default to local directory)
1. I want `calendar-sync reset <guid>` so that I can re-process items in the next run
1. I want to track attributes from the RSS feed in the DB.

* post title
* author
* post time

