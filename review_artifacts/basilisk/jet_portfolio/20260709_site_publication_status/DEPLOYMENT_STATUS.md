# Deployment Status

## Site Merge

- PR: <https://github.com/ferminfm/personal-ai-scientific-computing-site/pull/6>
- Result: merged by squash into `main`
- Main SHA after merge: `ef5a4f28c166d176fd07e9e1ad8b065258191e61`
- Branch SHA before merge: `3aa4aa22ba242ad84e61de75d1f66a2bed9be5a1`

## Production Deployment

- Production deployed: yes
- Production deployment URL: <https://personal-ai-scientific-computing-site-qdf4z6qrd.vercel.app>
- Production alias: <https://personal-ai-scientific-computing-si.vercel.app>
- Inspect URL: <https://vercel.com/ferminfm-9008s-projects/personal-ai-scientific-computing-site/EJEfRWeC44CkkxsVGSRA8CPX9zHQ>
- Deployment target: production
- Ready state: `READY`

## Validation Before Deploy

- `npm run lint`: passed
- `npm run build`: passed
- `git diff --check`: passed
- Large asset check: no new large assets were added in the final copy gate.

## Production Access Check

- `/projects`: HTTP 200
- `/projects/basilisk-jet-benchmark`: HTTP 200
- `/projects/visualbasilisk`: HTTP 200
- Vercel SSO/protection wall detected: no

## Notes

The production route is public-site publication of a conservative visualization workflow page. It is not publication of raw solver data, validation results, pressure diagnostics, or fit-ready reduced-model metrics.
