#!/usr/bin/env bash
set -euo pipefail
checkpoint=$1
archive_dir=$2
research_sha=$3
archive_label=$4
if [ "${GITHUB_REF:-}" != 'refs/heads/research/daily-walk-forward-20261101' ]; then
  echo 'Research archive publication is restricted to the research branch.' >&2
  exit 1
fi
python scripts/verify_station_manifest.py --input "$checkpoint"
python scripts/summarize_hourly_collection.py --manifest "$checkpoint/stations.csv" --out "$checkpoint/observations" --verify-hashes --report "$checkpoint/collection_progress.json"
python scripts/audit_hourly_coverage.py --manifest "$checkpoint/stations.csv" --observations "$checkpoint/observations" --out "$checkpoint/audit"
cp docs/atmos-hourly-collection.md "$checkpoint/DATA_ATTRIBUTION.md"
python scripts/package_hourly_archive.py --checkpoint "$checkpoint" --out "$archive_dir" --label "$archive_label"
# The tag is explicitly a research-data prerelease targeting this research SHA.
# Never update main, deploy production, or designate it as the latest release.
gh release create "$archive_label" "$archive_dir"/*.zip "$archive_dir"/*-index.json \
  --target "$research_sha" --prerelease --latest=false \
  --title "Atmos hourly research checkpoint $archive_label" \
  --notes-file docs/atmos-hourly-collection.md
# Verify the uploaded asset sizes against the locally hashed archive index.
gh release view "$archive_label" --json url,assets > "$archive_dir/published.json"
python - "$archive_dir" "$archive_label" <<'PY'
import json,pathlib,sys
folder=pathlib.Path(sys.argv[1]);label=sys.argv[2];index=json.loads((folder/(label+'-index.json')).read_text());published=json.loads((folder/'published.json').read_text());assets={a['name']:a for a in published['assets']}
for part in index['parts']:
 assert part['name'] in assets,part['name']
 assert assets[part['name']]['size']==part['bytes'],part['name']
print(json.dumps({'release_url':published['url'],'parts':len(index['parts']),'asset_sizes_verified':True}))
PY
