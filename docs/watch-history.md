# Watch history

## Overview

Watch history is the collection of viewing records associated with the media in the user's library. These records are referred to as watch-history entries. A media item may have zero or more entries, allowing multiple viewings of the same media to be preserved as distinct records.

Each persisted watch-history entry represents one viewing of a movie, series, or one or more episodes from the same series. Its media associations are stored as items belonging to that entry. Multiple episode items are displayed as one grouped item. Watch history and current watch state are separately modeled aspects of a media item: watch-history entries describe individual viewings, while watch state describes its current status in the library.

User-supplied viewing dates have day-level precision. The app deliberately does not record the time of day at which a viewing occurred. This is a design decision rather than a storage limitation: time-of-day precision would add complexity without providing meaningful value for the intended use of the history.

Watch-history entries also contain system-managed persistence timestamps. These timestamps are not user-supplied viewing dates. Their precise roles are defined in the temporal model below.

## Storage model

Each viewing is stored as a uniquely identified row in `watch_history_entry`. Its media associations are stored in `watch_history_item`; a media item may participate in multiple distinct viewings.

| Table / column | Storage | Presence | Role |
| --- | --- | --- | --- |
| `watch_history_entry.id` | Integer | Required | Persistent viewing identity |
| `watch_history_entry.date_earliest` | ISO `YYYY-MM-DD` text | Optional | Earliest explicit viewing date |
| `watch_history_entry.date_latest` | ISO `YYYY-MM-DD` text | Optional | Latest explicit viewing date |
| `watch_history_entry.created_at` | Timestamp | Required | Entry creation metadata, shared by all items |
| `watch_history_entry.updated_at` | Timestamp | Optional | Entry update metadata |
| `watch_history_item.id` | Integer | Required | Association identity |
| `watch_history_item.entry_id` | Integer | Required | References `watch_history_entry.id` |
| `watch_history_item.media_id` | Integer | Required | References `media.id` |

An entry contains one movie, one series-level association, or one or more episodes of the same series. The same media cannot appear twice within one entry. Separate viewings retain separate identities even when their members and explicit dates are identical.

Unlike explicit viewing dates, `created_at` and `updated_at` are system-managed persistence metadata. SQLite assigns `created_at` in UTC. New previews and drafts use a provisional UTC timestamp; saving assigns the actual persistence timestamp. Editing preserves the existing creation timestamp.

## Temporal inputs

The temporal model draws on up to four values associated with a watch-history entry:

| Value | Source | Meaning |
| --- | --- | --- |
| `date_earliest` | `watch_history_entry` | The earliest viewing date explicitly supplied by the user. |
| `date_latest` | `watch_history_entry` | The latest viewing date explicitly supplied by the user. |
| `created_at` | `watch_history_entry` | The system-generated timestamp recording when the entry was created. |
| `release_date` | `media` | The release date of the media associated with the entry. |

## Derived temporal representation

The app resolves the available temporal inputs into a plausible viewing interval `[A, B]` using defined boundary-selection rules. Both the selected values and their sources inform the subsequent interpretation. From this interval, the app derives:

1. A viewing-date label representing when the viewing occurred or may have occurred.
2. A timeline anchor `P` used to place the viewing in chronological order.

### Interval resolution

`A` represents the earliest plausible viewing date and `B` represents the latest plausible viewing date. Each boundary retains the temporal input from which it was derived, since its source affects how the interval is subsequently interpreted.

Under normal conditions, the boundaries are resolved as follows:

| Explicit viewing dates | `A` | `B` |
| --- | --- | --- |
| `date_earliest` and `date_latest` | `date_earliest` | `date_latest` |
| `date_earliest` only | `date_earliest` | `created_at` |
| `date_latest` only | `release_date` | `date_latest` |
| Neither | `release_date` | `created_at` |

When used as a boundary, `created_at` is reduced to day-level precision. Missing or inconsistent boundaries are handled separately under [Edge cases](#edge-cases).

### Viewing-date label

The viewing-date label is derived from the resolved interval and its boundary sources, independently of the timeline anchor. When `A` and `B` are equal, the label represents a single date. When they differ, the label represents a date range.

Single dates and ranges are formatted according to the resolved temporal span:

| Resolved interval | Label format | Example |
| --- | --- | --- |
| A single day | `D Mon YYYY, Ddd` | `12 Aug 2026, Wed` |
| Different days within the same month | `Mon YYYY` | `Aug 2026` |
| Different months within the same year | `Mon-Mon YYYY` | `Jan-Mar 2026` |
| One complete calendar year | `YYYY` | `2026` |
| Dates in different years | `YYYY-YYYY` | `2001-2026` |

The following examples show how boundary values and their sources affect the resulting label:

| `A` (source → resolved date) | `B` (source → resolved date) | Label |
| --- | --- | --- |
| `date_earliest` → `2026-08-12` | `date_latest` → `2026-08-12` | `12 Aug 2026, Wed` |
| `date_earliest` → `2026-08-03` | `date_latest` → `2026-08-20` | `Aug 2026` |
| `date_earliest` → `2026-01-10` | `date_latest` → `2026-03-02` | `Jan-Mar 2026` |
| `date_earliest` → `2026-01-01` | `date_latest` → `2026-12-31` | `2026` |
| `date_earliest` → `2024-11-10` | `date_latest` → `2026-02-03` | `2024-2026` |
| `date_earliest` → `2026-08-03` | `created_at` → `2026-08-20` | `~Aug 2026` |
| `release_date` → `2026-01-10` | `date_latest` → `2026-03-02` | `~Jan-Mar 2026` |
| `release_date` → `2001-10-11` | `created_at` → `2026-08-16` | `~2001-2026` |

When at least one boundary is derived from latent temporal context rather than explicitly supplied as a viewing date, the label is prefixed with `~` to indicate approximation.

The timeline anchor does not affect the label. The same entry may therefore be displayed as `~2001-2026` while being positioned at `2001-10-11` in the timeline.

Grouped episode entries use the same viewing-date formatting rules once their interval has been resolved. The rules for forming a group and selecting its temporal boundaries are defined under [Grouped episode entries](#grouped-episode-entries).

### Timeline anchor

The timeline anchor `P` is an internal positioning value derived from the resolved interval. It is used exclusively for chronological ordering and does not replace the viewing-date label or represent a claim about the most probable viewing date.

When `A` and `B` are equal, `P` is equal to their shared date. When they differ, the calculation of `P` depends on the combination of temporal inputs that supplied the two boundaries:

| Source of `A` | Source of `B` | Timeline anchor `P` |
| --- | --- | --- |
| `date_earliest` | `date_latest` | Midpoint of `[A, B]` |
| `date_earliest` | `created_at` | `A` |
| `release_date` | `date_latest` | Midpoint of `[A, B]` |
| `release_date` | `created_at` | `A` |

For midpoint anchors, `A` and `B` are converted to ordinal day values and their arithmetic mean becomes `P`. Because the anchor is an internal sorting value, a midpoint may fall between two calendar days; it is retained as a numeric position and is neither rounded nor displayed as a viewing date.

#### Rationale

The anchor rules prioritize an intuitive chronological experience over mathematical symmetry, recognizing that explicit viewing dates and latent temporal bounds do not carry the same meaning. An exact date gives the viewing an explicit chronological position, while an explicitly supplied range is represented by its midpoint.

The subtler cases arise when one or both explicit boundaries are missing. Each case is considered separately because every combination of explicit and latent boundaries represents a different kind of temporal knowledge.

- **Only `date_latest` is supplied.** `release_date` provides `A`, the earliest plausible boundary. Although `A` is latent, `B` remains an explicit viewing date supplied by the user. The app uses the midpoint as a balanced position, allowing the user's explicit upper boundary to influence placement without collapsing the viewing onto the media's release date.

- **Only `date_earliest` is supplied.** `created_at` provides `B`, the latest plausible boundary. This produces a plausible interval, but `created_at` only records when the entry was created and provides no indication of how close the viewing was to that date. Using the midpoint would give this persistence timestamp undue influence and impose an artificial center on the interval. The anchor therefore remains at `A`, the boundary explicitly supplied by the user.

- **Neither `date_earliest` nor `date_latest` is supplied.** `release_date` and `created_at` still establish a plausible interval, but neither boundary contains user-supplied information about where the viewing falls within it. A midpoint would introduce an unsupported assumption of centrality. The anchor is therefore set to `A`, the release date, providing a deliberately early placement for an undated entry while the viewing-date label continues to communicate the full plausible interval.

In the latter two cases, the deliberate bias toward `A` prevents the latent `created_at` boundary from pulling uncertain entries into newer, more precisely dated portions of the timeline. This preserves the clarity of the more precise chronology while still allowing users to record viewings they remember without knowing exactly when they occurred.

## Grouped episode entries

An episode group is the set of episode items belonging to one persisted `watch_history_entry`. The display layer does not merge distinct entries by date pair, series, or membership. Editing or deleting a group operates on that entry and its associations.

Episodes within an entry are ordered first by season number and then by episode number. Episode-range formatting compresses those ordered members for display without changing membership or persistent identity.

### Group interval resolution

The same temporal model used for an individual entry applies to a grouped item. The entry supplies the shared explicit dates and `created_at`. When `date_earliest` is absent, the first episode in season/episode order supplies `release_date` for `A`; this is not necessarily the earliest release date among the members. When `date_latest` is absent, the entry's shared `created_at` supplies `B`.

These rules also apply to an entry containing just one episode. Missing release information on the first episode uses the normal missing-boundary fallback, never another episode's or the series' release date. Opening a group from a member episode's Media Details still resolves the complete entry.

For a series-level entry with no episode items, `first_air_date` from the series summary takes precedence over the series metadata's `release_date`, preserving the existing series-level convention.

### Episode-range representation

Episode identifiers are grouped by season, sorted numerically, and compressed when consecutive. Non-consecutive ranges and different seasons remain separate parts of the representation.

| Episodes | Episode-range label |
| --- | --- |
| Season 1, episode 4 | `S1:E4` |
| Season 1, episodes 4, 5, and 6 | `S1:E4-6` |
| Season 1, episodes 1, 2, and 4 | `S1:E1-2, S1:E4` |
| Season 1, episodes 1 and 2; season 2, episode 1 | `S1:E1-2, S2:E1` |

## Display-entry composition

The viewing-date label is the temporal component of a displayed watch-history item. Media titles, episode identifiers, and episode titles provide additional context but do not participate in interval resolution or chronological ordering.

| Display item | Representation |
| --- | --- |
| Movie or standalone episode in Media Details | `{viewing-date label}` |
| Series-level entry without episode information in Media Details | `{viewing-date label} · no episode info` |
| Episode group in Media Details | `{viewing-date label} · {episode-range label}` |
| Movie or series card in History | The media title, with the viewing-date label displayed separately |
| Single-episode card in History | `{series title} ({episode-range label}) – {episode title}`, with the viewing-date label displayed separately |
| Multi-episode group in History | `{series title} ({episode-range label})`, with the viewing-date label displayed separately |

The surrounding representation may vary by surface, but the temporal label itself must remain unchanged for the same resolved interval and boundary sources.

## Chronological ordering

Watch-history display items are ordered from newest to oldest using a descending composite sort key. The timeline anchor `P` is the primary ordering value. Additional values are used only to make the order deterministic when two items share the same anchor.

| Priority | Sort component | Descending behavior |
| --- | --- | --- |
| 1 | Timeline anchor `P` | Later anchors appear first |
| 2 | Temporal specificity | Exact dates precede explicit ranges, which precede entries with one explicit boundary, which precede fully undated entries |
| 3 | `created_at` | More recently created entries appear first |
| 4 | Persistent identity | Greater watch-history identifiers appear first as the final deterministic tie-breaker |

Temporal specificity is determined by the original explicit dates: exact date (3), explicit range (2), one explicit boundary (1), or neither (0). A collapsed inferred interval does not become more specific. The timestamp tie-breaker uses full precision, normalizing offsets to UTC; timestamps without an offset are compared as stored. Persisted entry IDs, not association IDs, provide the final tie-breaker. Unsaved entries use their stable `draft_id`, with persisted identities preceding draft identities when all prior components tie.

Tie-breakers do not alter `P`, the resolved interval, or the viewing-date label. Persistent identity has no temporal meaning and is used only to guarantee a stable order.

### Consistency across application surfaces

The temporal model is shared by every presentation of watch history. A surface may add contextual text, but it must preserve entry membership and must not reinterpret the raw date fields independently.

| Surface | Viewing-date label | Chronological ordering | Episode grouping |
| --- | --- | --- | --- |
| History grid | Uses the shared label | Uses the shared sort key | Projects each entry’s episode items before sorting |
| Media Details watch-history list | Uses the shared label | Uses the shared sort key | Projects each entry’s episode items before sorting |
| Watch-entry preview | Uses the shared label for the prospective entry | Not applicable | Shows the prospective episode-range representation when episodes are selected |

Each card in History represents one display item and occupies the position determined by that item's sort key. The rows in Media Details use the same ordering rules. A preview does not participate in ordering, but its date label must match the label that the saved entry will receive.

## Relationship with current watch state

Watch history and current watch state remain separate in the persistence model. Both are associated with media, but no watch-history entry or item directly references a watch-state row, and the presence of history does not permanently determine the media item's current state.

Application workflows may connect the two concepts. A user-initiated transition to `watched` may require or create at least one watch-history entry; when the viewing date is unknown, an entry with neither explicit boundary is valid and avoids inventing a date. This is an application-level consistency rule rather than a database relationship.

Because watch state describes the present and watch history preserves past viewing events, an existing history entry may coexist with another current state or with no current state. Changing the current state does not by itself erase history, and editing an existing history entry does not by itself redefine the current state.

## Edge cases

The following rules complete normal interval resolution. A missing or unparseable latent value is treated as unavailable. Invalid explicit input is rejected rather than silently reinterpreted.

| Situation | Treatment |
| --- | --- |
| An explicit date is not a real ISO `YYYY-MM-DD` value | Reject the input |
| Both explicit dates are present and `date_latest < date_earliest` | Reject the interval |
| Both explicit dates contain the same value | Resolve a single-day interval with `A = B` |
| An explicit viewing date is in the future | Accept it; explicit information takes precedence over inconsistent latent bounds |
| A required latent boundary is unavailable, with one explicit date present | Collapse both boundaries onto the explicit date |
| A latent boundary would contradict the one explicit date (`A > B`) | Collapse both boundaries onto the explicit date |
| Neither explicit date is present and only one latent value is usable | Collapse onto that latent value |
| Neither explicit date is present and release is later than creation | Collapse onto the release date |
| No valid temporal value can be resolved | Label `~unknown date`; use `P = 0` and the normal deterministic tie-breakers, after all dated entries |
| `created_at` contains a time or offset | Use its stored calendar day as the boundary, without timezone conversion |
| `updated_at` is present | Exclude it from interval resolution, labels, anchors, and ordering |
| A midpoint falls between two calendar days | Preserve the fractional ordinal internally; do not round or display it |
| `release_date` changes after an entry was created | Recompute derived values on the next load/refresh; do not persist them |
| Separate viewings have identical series, members, and explicit dates | Keep separate entries, ordered using their own persistent identity |

When a boundary is replaced during collapse, its source becomes the input whose date was retained. Approximation and specificity still reflect the original explicit inputs: any entry missing at least one explicit date keeps the `~` prefix, including collapsed single-day intervals.

Preview labels use the same rules and provisional UTC creation time as drafts. Persistence supplies the actual creation time, so saving on a different UTC day may legitimately change the upper latent boundary and label.
