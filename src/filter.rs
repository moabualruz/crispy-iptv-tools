//! Playlist entry filtering.
//!
//! Filter entries by resolution, group, name pattern, and adult content.

use std::sync::LazyLock;

use crispy_iptv_types::{PlaylistEntry, Resolution};
use regex::Regex;

use crate::error::ToolsError;
use crate::resolution::detect_resolution;

/// Adult content group/name patterns (case-insensitive).
/// Uses word boundaries where possible; `18+` uses a lookahead-style
/// anchor since `+` is not a word character.
static ADULT_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(\bxxx\b|\badult\b|\bporn\b|18\+|\berotic\b|\bsex\b)").unwrap()
});

/// Configuration for filtering playlist entries.
#[derive(Debug, Clone, Default)]
pub struct EntryFilter {
    /// Minimum resolution tier (entries below this are excluded).
    pub min_resolution: Option<Resolution>,

    /// Include only entries belonging to these groups.
    pub groups: Option<Vec<String>>,

    /// Exclude entries belonging to these groups.
    pub exclude_groups: Option<Vec<String>>,

    /// How include/exclude group matching should be evaluated.
    pub group_match_mode: GroupMatchMode,

    /// Separator characters used for multi-group tokenization.
    pub group_separators: Vec<char>,

    /// Regex pattern — only entries whose name matches are kept.
    pub name_pattern: Option<String>,

    /// If true, entries with adult-content indicators are excluded.
    pub exclude_adult: bool,
}

/// Group matching behavior.
#[derive(Debug, Clone, Copy, Default)]
pub enum GroupMatchMode {
    #[default]
    Exact,
    Contains,
}

/// Filter entries according to the given filter configuration.
///
/// Returns a new `Vec` containing only entries that pass all filter criteria.
///
/// # Errors
///
/// Returns `ToolsError::InvalidPattern` if `name_pattern` is not a valid regex.
pub fn filter_entries(
    entries: &[PlaylistEntry],
    filter: &EntryFilter,
) -> Result<Vec<PlaylistEntry>, ToolsError> {
    let name_regex = filter
        .name_pattern
        .as_ref()
        .map(|p| Regex::new(p))
        .transpose()?;

    let result = entries
        .iter()
        .filter(|entry| passes_filter(entry, filter, name_regex.as_ref()))
        .cloned()
        .collect();

    Ok(result)
}

/// Check whether a single entry passes all filter criteria.
fn passes_filter(entry: &PlaylistEntry, filter: &EntryFilter, name_regex: Option<&Regex>) -> bool {
    let name = entry.name.as_deref().unwrap_or("");
    let url = entry.primary_url().unwrap_or("");
    let group = entry.group_title.as_deref().unwrap_or("");

    // Resolution filter.
    if let Some(min_res) = filter.min_resolution {
        let detected = detect_resolution(name, url, &entry.extras);
        // Unknown resolution passes (we can't confirm it's below minimum).
        if detected != Resolution::Unknown && detected < min_res {
            return false;
        }
    }

    let group_values = tokenize_groups(group, &filter.group_separators);

    // Include-groups filter (case-insensitive).
    if let Some(include) = &filter.groups {
        if !include
            .iter()
            .any(|expected| group_matches(&group_values, expected, filter.group_match_mode))
        {
            return false;
        }
    }

    // Exclude-groups filter (case-insensitive).
    if let Some(exclude) = &filter.exclude_groups {
        if exclude
            .iter()
            .any(|expected| group_matches(&group_values, expected, filter.group_match_mode))
        {
            return false;
        }
    }

    // Name pattern filter.
    if let Some(re) = name_regex
        && !re.is_match(name)
    {
        return false;
    }

    // Adult content filter.
    if filter.exclude_adult && (ADULT_PATTERN.is_match(name) || ADULT_PATTERN.is_match(group)) {
        return false;
    }

    true
}

fn tokenize_groups(group: &str, separators: &[char]) -> Vec<String> {
    let separators = if separators.is_empty() {
        &[';', '|', ','][..]
    } else {
        separators
    };
    group
        .split(|ch| separators.contains(&ch))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| value.to_lowercase())
        .collect()
}

fn group_matches(group_values: &[String], expected: &str, mode: GroupMatchMode) -> bool {
    let expected = expected.trim().to_lowercase();
    group_values.iter().any(|actual| match mode {
        GroupMatchMode::Exact => actual == &expected,
        GroupMatchMode::Contains => actual.contains(&expected),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_entry(name: &str, group: &str, url: &str) -> PlaylistEntry {
        let mut entry = PlaylistEntry {
            name: Some(name.to_string()),
            group_title: Some(group.to_string()),
            ..Default::default()
        };
        if !url.is_empty() {
            entry.set_primary_url(url.to_string());
        }
        entry
    }

    #[test]
    fn filter_by_resolution_keeps_hd_and_above() {
        let entries = vec![
            make_entry("BBC SD", "News", "http://a.com/sd"),
            make_entry("CNN HD", "News", "http://a.com/hd"),
            make_entry("Sky FHD", "Sports", "http://a.com/fhd"),
            make_entry("Movie 4K", "Movies", "http://a.com/4k"),
        ];
        let filter = EntryFilter {
            min_resolution: Some(Resolution::HD),
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 3);
        assert!(result.iter().all(|e| {
            let n = e.name.as_deref().unwrap();
            n != "BBC SD"
        }));
    }

    #[test]
    fn filter_by_group_include() {
        let entries = vec![
            make_entry("A", "Sports", "http://a.com/1"),
            make_entry("B", "News", "http://a.com/2"),
            make_entry("C", "Sports", "http://a.com/3"),
        ];
        let filter = EntryFilter {
            groups: Some(vec!["Sports".into()]),
            group_match_mode: GroupMatchMode::Exact,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn filter_by_group_exclude() {
        let entries = vec![
            make_entry("A", "Sports", "http://a.com/1"),
            make_entry("B", "News", "http://a.com/2"),
            make_entry("C", "Movies", "http://a.com/3"),
        ];
        let filter = EntryFilter {
            exclude_groups: Some(vec!["Sports".into()]),
            group_match_mode: GroupMatchMode::Exact,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 2);
        assert!(
            result
                .iter()
                .all(|e| e.group_title.as_deref().unwrap() != "Sports")
        );
    }

    #[test]
    fn filter_by_name_pattern() {
        let entries = vec![
            make_entry("BBC One", "UK", "http://a.com/1"),
            make_entry("CNN International", "US", "http://a.com/2"),
            make_entry("BBC Two", "UK", "http://a.com/3"),
        ];
        let filter = EntryFilter {
            name_pattern: Some("^BBC".into()),
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 2);
        assert!(
            result
                .iter()
                .all(|e| e.name.as_deref().unwrap().starts_with("BBC"))
        );
    }

    #[test]
    fn filter_invalid_regex_returns_error() {
        let filter = EntryFilter {
            name_pattern: Some("[invalid".into()),
            ..Default::default()
        };
        assert!(filter_entries(&[], &filter).is_err());
    }

    #[test]
    fn filter_exclude_adult() {
        let entries = vec![
            make_entry("BBC One", "News", "http://a.com/1"),
            make_entry("XXX Channel", "Adult", "http://a.com/2"),
            make_entry("Movie", "18+", "http://a.com/3"),
            make_entry("Sports", "Sports", "http://a.com/4"),
        ];
        let filter = EntryFilter {
            exclude_adult: true,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn filter_group_case_insensitive() {
        let entries = vec![make_entry("A", "SPORTS", "http://a.com/1")];
        let filter = EntryFilter {
            groups: Some(vec!["sports".into()]),
            group_match_mode: GroupMatchMode::Exact,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn filter_multi_group_exact_match() {
        let entries = vec![make_entry("A", "Sports;News", "http://a.com/1")];
        let filter = EntryFilter {
            groups: Some(vec!["News".into()]),
            group_match_mode: GroupMatchMode::Exact,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn filter_group_contains_match() {
        let entries = vec![make_entry("A", "UK Sports Premium", "http://a.com/1")];
        let filter = EntryFilter {
            groups: Some(vec!["Sports".into()]),
            group_match_mode: GroupMatchMode::Contains,
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn filter_unknown_resolution_passes() {
        // Entry with no resolution hint should pass min_resolution filter.
        let entries = vec![make_entry("Plain Channel", "News", "http://a.com/1")];
        let filter = EntryFilter {
            min_resolution: Some(Resolution::HD),
            ..Default::default()
        };
        let result = filter_entries(&entries, &filter).unwrap();
        assert_eq!(result.len(), 1);
    }
}
