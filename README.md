## Setup

1. Install `uv`
1. `uv sync`
1. `cp .env.example .env` and update.

You will need Google Cloud credentials.

## Running the tool locally

```bash
# Pull the latest DB
mise run pull
# Run
calsync process
# Push the DB
mise run push
```

## Triggering a remote flow

```bash
mise run trigger
gh run list
gh run watch
```

## Development

```bash
mise run validate
```