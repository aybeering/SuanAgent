# Visual marks tools

Run from the workspace root. Do not edit `input/`, `tools/`, or `agent/`.

## Accept HTML

HTML pages are packed under `input/pages/` and listed in `input/run_request.json`.

## Collect points then mark

1. Write `output/collected_points.json` (`collected_points_v1`, `points` may be `[]`).
2. Call the built-in marking script:

```bash
python tools/write_mark_points.py \
  --run-request input/run_request.json \
  --points output/collected_points.json \
  --output-dir output
```

This writes `output/mark_points.json` and `output/mark_points.csv`.
Empty points are valid and yield `mark_count=0`.

## Stub agent

```bash
python agent/stub_visual_agent.py
```
