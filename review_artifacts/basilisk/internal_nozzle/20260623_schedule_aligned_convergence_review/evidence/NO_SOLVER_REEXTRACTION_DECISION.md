# No-Solver Re-Extraction Decision

Existing L7 and full L8 raw exports were re-extracted with a shared geometry/threshold configuration and paired through `t=0.18`. No solver was run.

- matched times requested: `[0.03, 0.06, 0.09, 0.12, 0.15, 0.18]`
- valid station/time pairs: `12`
- convergence passed: `False`
- threshold pass fraction: `0.25`
- failure cause classification: `schedule_misalignment_resolved_but_resolution_sensitive`
- existing data sufficient for aligned comparison: `True`

The L7 export still lacks several required L8 stations (`fixed 0.10/0.20/0.30/0.40` and front-relative `0.25/0.75`), but using full existing L8 data through `t=0.18` recovers twelve valid common station/time pairs. The remaining failures therefore cannot be attributed only to too few matched pairs.

The unchanged gates still fail, especially mean exit velocity and active-front agreement. This keeps `fit_ready=false` and `public_ready=false`.
