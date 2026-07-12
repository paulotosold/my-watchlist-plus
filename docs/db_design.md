# Database Design Notes

## Overview

This database is designed for a local personal watchlist app. It stores a mix of external media metadata, user-specific watch state, watch history, notes, posters, streaming availability, and raw user input history.

The schema intentionally separates canonical/catalog-like media data from user-specific data.

- `media` stores catalog-like metadata about movies, series, and episodes.

- `media_state` stores an explicit relationship between the user and a media item.
  A catalog item may exist without a `media_state` row. A `NULL` `watch_state`
  means that the item is not individually tracked while preserving other
  personal fields such as `impression` or `is_collection_pick`.

- `watch_history` stores structured watch events.

- `media_notes` stores personal notes.

- `raw_input_history` stores the original text entered by the user.

## `media`

`media` is the central table of the schema. It represents the canonical media item that the rest of the database refers to.

The app uses TMDB as the required external identity source. Every media item stored in the database must have a TMDB ID. Fully manual media entries without a TMDB match are intentionally out of scope for now.

The app intentionally limits media items to three types:

- `movie`
- `series`
- `episode`

There is no first-class `season` media type. Season-level user input is handled as a series-level action. If the user mentions multiple episodes or one or more seasons, the app resolves the input to the parent series. If the user mentions exactly one specific episode, the app may resolve the input to an episode media item.

Saving a series materializes its episodes as catalog items without creating
individual user state for them. An episode only enters the default watchlist
when the user explicitly assigns `to_watch`. Adding an episode watch-history
event promotes the episode to `watched`; removing its final history entry clears
an automatically derived `watched` state. A later explicit override is
preserved until another history event is added. Series state never propagates
to episode state.

`media` should only contain catalog-like metadata, such as title, original title, release date, runtime, TMDB ID, and IMDb ID. User-specific data must live in separate tables, such as `media_state`, `watch_history`, and `media_notes`.
