This is a website for the minneapolis cycling community.

* I would like to keep the stylesheet separate from the code for easy contribution by others
* Semantic HTML and proper accessibility are critical.  Aria tags, semantic elements, etc should be used.

Parameterize design tokens in CSS variables so that I can change colors and stuff.  Use regular CSS semantics.

## General vibes

This is a mobile-optimized site.  I want it to have a basic, 90-early-2000s design (kinda blocky, amateurish, almost neocities style but not too outlandish)

## Pages

The homepage should be a Linktree-style list of links:

* To the event list page at `/events`
* To the google calendar directly at https://calendar.google.com/calendar/u/0/embed?src=6a256e25e316cc67771b99bd499dfa57d2780d51f6eb5f9df1a9d84299a1b3c2@group.calendar.google.com&ctz=America/Chicago
* To "Local Clubs and Teams" at `https://bikegroups.org`
* To a "submit your event" for at https://docs.google.com/forms/d/e/1FAIpQLScO18rkN9ajjnckLpzGYd1Jb1fAYb2PnLDFmSlO-OXyY-mKNA/viewform


The events page should be generated based on the data document in `data/events.json`

Events should be a sort of 2-column table with a thumbnail image on the left and the event description and details on the right.  The event title should be in a header row colspan 2.  (Don't actually use a table for this, use modern CSS, I'm just telling you how it should look.)

in the future most events should have `extra_metadata` which is where you'll get the images from.  If it's missing, just show an empty cell of the same fixed width for good vertical alignment.