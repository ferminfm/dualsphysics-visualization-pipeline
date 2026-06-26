# Flythrough Visibility QA

Status: `pass`

The corrected flythrough uses the scientifically safe static source frame `98` at physical time `1.96`. A rendered fluid-object mask was evaluated for every flythrough frame, and sampled camera-to-fluid raycasts were checked for wall/floor-first hits.

Thresholds:
- fluid occupancy must be at least 5% and at most 70% of image pixels;
- fluid bounding box must intersect the central 80% of the image;
- no more than 5 consecutive frames may be below 10% occupancy;
- sampled camera-to-fluid raycasts must not be wall-first;
- camera position must remain outside floor/wall geometry.

Result:
- frames checked: 96
- min occupancy: 0.097066
- max occupancy: 0.182240
- failed frames: 0
- wall/floor-first frames: 0
- max consecutive frames below 10% occupancy: 2

This QA supports internal visual review only. It does not make the benchmark public-ready or fit-ready.
