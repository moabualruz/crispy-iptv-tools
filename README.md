# crispy-iptv-tools

Reusable IPTV playlist utility crate for transformation, normalization, and cleanup.

## Status

Extracted from CrispyTivi. Intended as a reusable toolbox layered on top of shared IPTV entry types.

## What This Crate Provides

- filtering
- merging
- deduplication
- normalization
- sorting
- resolution labeling
- image and stream URL sanitization
- template application
- UDPXY conversion helpers
- title/id unification helpers

## Installation

```toml
[dependencies]
crispy-iptv-tools = "0.1"
```

## Quick Start

```rust
use crispy_iptv_tools::{deduplicate, DeduplicateStrategy};

# fn demo() {
let items = Vec::new();
let _deduped = deduplicate(&items, DeduplicateStrategy::ByUrlHash);
# }
```

## Relationship To Other Crates

- built on `crispy-iptv-types`
- complements `crispy-m3u`

## Primary Use Cases

- playlist cleanup
- migration pipelines
- dedupe and normalization passes
- provider import tooling

## Caveats

- before public release, scope should stay focused on truly generic utilities and avoid app-specific assumptions
