# CFD Evaluation Rubric Bank

| Dimension | What to check | 1 = weak | 3 = acceptable | 5 = strong |
|---|---|---|---|---|
| Physics correctness | Does the response preserve governing equations, conservation, free-surface interpretation, and correct physical regimes? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Boundary and initial conditions | Are inlet/outlet/wall/symmetry/periodic assumptions stated and consistent with the claimed result? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Nondimensional numbers | Are Re, We, Fr, Mach, CFL, or relevant scaling quantities used correctly and not mixed across cases? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Numerical method and stability | Are discretization, timestep, convergence, and solver limitations discussed with appropriate caution? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Mesh/resolution evidence | Does the answer address grid dependence, refinement, station/time alignment, or resolution-sensitive morphology? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Visualization/data support | Do images, fields, and exported variables actually support the claim? Are missing fields such as pressure handled honestly? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Uncertainty and scope | Does the response distinguish exploratory simulation, benchmark visualization, validation, and predictive modeling? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Overclaim detection | Does the response avoid treating connected waviness, one-cell debris, projection artifacts, or imposed inlet shapes as validated breakup/atomisation? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Actionability | Does the feedback give concrete next checks rather than vague criticism? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |
| Ethics/confidentiality | Does the evaluation avoid proprietary prompts, confidential data, or cheating behavior? | Missing or wrong | Partially correct with caveats | Correct, evidence-backed, and scoped |

## Default Verdict Scale

- **Pass:** physically and numerically plausible, scoped, and evidence-backed.
- **Warn:** useful but missing caveats, assumptions, or checks.
- **Fail:** physically wrong, unsupported by data, overclaimed, or unsafe/confidential.
