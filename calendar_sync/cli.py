"""CLI for calendar-sync."""

from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import calendar, claude, db, report, rss
from .models import Action

app = typer.Typer(help="Sync RSS feed events to Google Calendar using Claude")
console = Console()

DEFAULT_FEED = "https://rssglue.subdavis.com/feed/cycling-merge/rss"


@app.command()
def process(
    feed: str = typer.Option(DEFAULT_FEED, "--feed", "-f", help="RSS feed URL"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without making changes"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum posts to process"),
):
    """Process new posts from an RSS feed."""
    db.init_db()

    console.print(f"[bold]Fetching feed:[/bold] {feed}")
    posts = rss.fetch_feed(feed)
    console.print(f"Found {len(posts)} posts in feed")

    # Filter to unprocessed posts, oldest first
    unprocessed = [p for p in posts if not db.is_processed(p.guid)]
    unprocessed.sort(key=lambda p: p.published or datetime.min)
    console.print(f"[green]{len(unprocessed)} unprocessed posts[/green]")

    if limit:
        unprocessed = unprocessed[:limit]

    if not unprocessed:
        console.print("[yellow]Nothing to process[/yellow]")
        return

    total_cost = 0.0

    for i, post in enumerate(unprocessed, 1):
        console.print(f"\n[bold]Processing {i}/{len(unprocessed)}:[/bold] {post.title[:60]}...")

        if post.image_urls:
            console.print(f"  [dim]{len(post.image_urls)} image(s)[/dim]")

        if dry_run:
            console.print("  [yellow](dry run mode)[/yellow]")

        try:
            ctx = claude.analyze_post(post, dry_run=dry_run)
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            continue

        decision = ctx.decision
        if decision is None:
            console.print("  [red]No decision recorded[/red]")
            continue

        # Display results
        style = {
            Action.CREATE: "green",
            Action.UPDATE: "blue",
            Action.CANCEL: "red",
            Action.IGNORE: "dim",
            Action.FLAG: "yellow",
        }.get(decision.action, "")

        console.print(f"  [cyan]Decision:[/cyan] [{style}]{decision.action.value}[/{style}] (confidence: {decision.confidence:.0%})")
        console.print(f"  [dim]{decision.reasoning}[/dim]")

        if decision.is_event and decision.event:
            console.print(f"  [blue]Event:[/blue] {decision.event.title}")
            console.print(f"  [blue]Date:[/blue] {decision.event.date} {decision.event.time or 'all day'}")
            if decision.event.location:
                console.print(f"  [blue]Location:[/blue] {decision.event.location}")

        if ctx.calendar_event_id:
            console.print(f"  [green]Calendar event:[/green] {ctx.calendar_event_id}")

        console.print(f"  [dim]Tokens: {ctx.input_tokens:,} in / {ctx.output_tokens:,} out = ${ctx.cost_usd:.4f}[/dim]")
        console.print(f"  [dim]Log: {ctx.logger.log_path}[/dim]")
        total_cost += ctx.cost_usd

    console.print(f"\n[bold]Total cost:[/bold] ${total_cost:.4f}")
    console.print(f"[bold]Cumulative cost:[/bold] ${db.get_total_cost():.4f}")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of entries to show"),
):
    """Show recent processing history."""
    db.init_db()

    entries = db.get_history(limit)

    if not entries:
        console.print("[yellow]No history yet[/yellow]")
        return

    decision_styles = {
        "create": "green",
        "update": "blue",
        "cancel": "red",
        "ignore": "dim",
        "flag_for_review": "yellow",
    }

    table = Table(title="Processing History")
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("GUID", style="dim", no_wrap=True)
    table.add_column("Title", no_wrap=True, max_width=40)
    table.add_column("Author", style="dim", no_wrap=True)
    table.add_column("Decision", no_wrap=True)
    table.add_column("Event ID", style="dim")
    table.add_column("Cost", justify="right", no_wrap=True)

    for entry in entries:
        style = decision_styles.get(entry["decision"], "")
        table.add_row(
            entry["processed_at"][:19],
            entry["post_guid"],
            entry.get("post_title") or "-",
            entry.get("post_author") or "-",
            f"[{style}]{entry['decision']}[/{style}]",
            entry["calendar_event_id"] or "-",
            f"${entry['cost_usd']:.4f}" if entry["cost_usd"] else "-",
        )

    console.print(table)
    console.print(f"[bold]Total cost:[/bold] ${db.get_total_cost():.4f}")


@app.command()
def details(
    guid: str = typer.Argument(help="Post GUID to look up"),
):
    """Show full details for a processed post."""
    db.init_db()

    record = db.get_processed(guid)
    if not record:
        console.print(f"[yellow]No record found for:[/yellow] {guid}")
        raise typer.Exit(1)

    console.print(f"[bold]GUID:[/bold]       {record['post_guid']}")
    console.print(f"[bold]Title:[/bold]      {record.get('post_title') or '-'}")
    console.print(f"[bold]Author:[/bold]     {record.get('post_author') or '-'}")
    console.print(f"[bold]Post Time:[/bold]  {record.get('post_time') or '-'}")
    console.print(f"[bold]Processed:[/bold]  {record['processed_at']}")
    console.print(f"[bold]Decision:[/bold]   {record['decision']}")
    console.print(f"[bold]Event ID:[/bold]   {record['calendar_event_id'] or '-'}")
    console.print(f"[bold]Tokens:[/bold]     {record.get('input_tokens', 0) or 0:,} in / {record.get('output_tokens', 0) or 0:,} out")
    console.print(f"[bold]Cost:[/bold]       ${record.get('cost_usd', 0) or 0:.4f}")
    console.print()
    console.print("[bold]Reasoning:[/bold]")
    console.print(record.get("reasoning") or "-")


@app.command()
def reset(
    guid: Optional[str] = typer.Argument(None, help="Post GUID to reset (omit to clear all history)"),
):
    """Reset processing history. Pass a GUID to re-process a single item, or omit to clear all."""
    db.init_db()

    if guid:
        if db.delete_processed(guid):
            console.print(f"[green]Reset post:[/green] {guid}")
        else:
            console.print(f"[yellow]No record found for:[/yellow] {guid}")
    else:
        if not typer.confirm("This will clear all processing history. Continue?"):
            return

        import sqlite3
        conn = sqlite3.connect(db.get_db_path())
        conn.execute("DELETE FROM processed_posts")
        conn.commit()
        conn.close()

        console.print("[green]All history cleared[/green]")


@app.command("report")
def report_cmd(
    output: str = typer.Option("report.html", "--output", "-o", help="Output HTML file path"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of entries to include"),
):
    """Generate a static HTML report of processing history."""
    db.init_db()
    entries = db.get_history(limit)

    if not entries:
        console.print("[yellow]No history to report[/yellow]")
        return

    report_html = report.generate_report(entries, db.get_total_cost())

    with open(output, "w") as f:
        f.write(report_html)

    console.print(f"[green]Report written to:[/green] {output} ({len(entries)} entries)")


@app.command()
def validate():
    """Validate Google Calendar API access."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    console.print("[bold]Validating calendar access...[/bold]\n")

    # Check credentials file
    creds_path = calendar.get_credentials_path()
    if not creds_path.exists():
        console.print(f"[red]Credentials file not found:[/red] {creds_path}")
        raise typer.Exit(1)
    console.print(f"[green]Credentials file:[/green] {creds_path}")

    # Try to authenticate
    try:
        service = calendar.get_calendar_service()
        console.print("[green]Authentication:[/green] OK")
    except Exception as e:
        console.print(f"[red]Authentication failed:[/red] {e}")
        raise typer.Exit(1)

    # Try to access the calendar
    calendar_id = calendar.DEFAULT_CALENDAR_ID
    console.print(f"[dim]Calendar ID:[/dim] {calendar_id[:40]}...")

    try:
        cal = service.calendars().get(calendarId=calendar_id).execute()
        console.print(f"[green]Calendar name:[/green] {cal.get('summary', 'Unnamed')}")
        console.print(f"[green]Timezone:[/green] {cal.get('timeZone', 'Unknown')}")
    except Exception as e:
        console.print(f"[red]Failed to access calendar:[/red] {e}")
        raise typer.Exit(1)

    # Test write permissions by creating and deleting a test event
    from .models import EventDetails

    console.print("\n[bold]Testing write permissions...[/bold]")
    test_event = EventDetails(
        title="[TEST] Calendar Sync Validation",
        date="2020-01-01",
        time="12:00",
        timezone="America/Chicago",
        description="This event was created to test write permissions and should be deleted immediately.",
    )

    try:
        event_id = calendar.create_event(test_event)
        console.print(f"[green]Write test:[/green] Created test event {event_id[:20]}...")

        # Delete it immediately
        calendar.delete_event(event_id)
        console.print("[green]Write test:[/green] Deleted test event")
    except Exception as e:
        console.print(f"[red]Write test failed:[/red] {e}")
        raise typer.Exit(1)

    # List upcoming events
    try:
        now = datetime.now(ZoneInfo("UTC"))
        events = calendar.search_events_by_date(
            start_date=now.strftime("%Y-%m-%d"),
            end_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"),
        )
        console.print(f"\n[bold]Upcoming events (next 30 days):[/bold] {len(events)}")
        for event in events[:5]:
            console.print(f"  - {event.start.strftime('%Y-%m-%d')} {event.title}")
        if len(events) > 5:
            console.print(f"  [dim]...and {len(events) - 5} more[/dim]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not list events:[/yellow] {e}")

    console.print("\n[green]Calendar access validated successfully![/green]")


if __name__ == "__main__":
    app()
