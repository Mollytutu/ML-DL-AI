# Raw Folder Notes

This folder currently contains lightweight crawl-input inventories rather than a full raw snapshot archive.

## Current Files

- `collegedunia_urls_30k.txt`
  Broad URL inventory used as a starting point for filtering and discovery.
- `collegedunia_discovered_urls_selenium_13c.txt`
  Selenium-discovered URL list from a specific discovery run.
- `pipeline_inputs/`
  Current pipeline input tables such as `school_list.csv` and the school/program/subunit seed CSVs.

## Intended Use

- treat these files as crawl inputs and reference inventories
- treat `pipeline_inputs/` as operational pipeline inputs, not final clean outputs
- do not treat this folder as the source of truth for final datasets
- use `data/clean/` for downstream data consumption
