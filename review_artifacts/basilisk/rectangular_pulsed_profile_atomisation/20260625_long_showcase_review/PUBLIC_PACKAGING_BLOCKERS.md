# Public Packaging Blockers

Status: `public_packaging_blocked`

The current packet is for internal Layer-1 review only. It is not a public-ready showcase package.

Before any public packaging task, the following blockers must be resolved:

- Human visual review of the v2 videos:
  - `videos_proxy/long_primary_route_blender_sequence_v2.mp4`
  - `videos_proxy/round_vs_rectangular_split_screen_v2.mp4`
  - `videos_proxy/final_complex_geometry_flythrough_v2.mp4`
- Public wording review, including the mandatory caveats:
  - the selected rectangular case is `C1_rect_area_top_hat`;
  - the selected rectangular profile is `rect_area_top_hat`;
  - the selected rectangular route is a `2:1 rectangular top-hat imposed-inlet comparison`;
  - the rectangular case does not resolve internal nozzle flow;
  - Poiseuille-series profiles were implemented/tested but were not selected.
- Final site asset selection, including which stills, contact sheets, or videos should be excluded from public use.
- An explicit separate public packaging task approved after human review.

Until these blockers are closed:

- `fit_ready=false`;
- `public_ready=false`;
- do not deploy;
- do not publish;
- do not move assets to the public site repository.
