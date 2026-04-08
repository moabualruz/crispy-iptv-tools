# crispy-iptv-tools

Reusable IPTV playlist utility crate for transformation, normalization, cleanup, and sorting.

## What This Crate Is

`crispy-iptv-tools` sits on top of `crispy-iptv-types` and provides the reusable data-munging operations that are common in IPTV ingestion pipelines.

## What It Provides

- deduplication
- filtering
- merging
- normalization
- sorting
- resolution detection helpers
- image and stream URL sanitization
- UDPXY helpers
- template application
- title and ID unification helpers
- configurable merge behavior
- normalized URL-aware dedup defaults for merge flows

## Installation

```toml
[dependencies]
crispy-iptv-tools = "0.1.1"
```

MSRV: Rust `1.85`

## Quick Start

```rust
use crispy_iptv_tools::{deduplicate, DeduplicateStrategy};
use crispy_iptv_types::PlaylistEntry;

let items: Vec<PlaylistEntry> = Vec::new();
let _deduped = deduplicate(&items, &DeduplicateStrategy::ByNormalizedUrl);
```

## Typical Uses

- playlist cleanup
- normalization before import
- merging multiple provider feeds
- preparing playlists for export

## Related Crates

- `crispy-iptv-types`
- `crispy-m3u`

## Current Limitations

- utility coverage is intentionally focused on playlist operations; this crate is not a provider client
- caller still owns persistence and orchestration
- group matching is still string-driven rather than full taxonomy-aware category management

## License

See `LICENSE.md` and `NOTICE.md`.
