# Reimflow

Early testable prototype for a German rap rhyme community.

## Prototype scope

The current MVP focuses on validating the product flow:

* phonetic rhyme search with word type and syllable filters
* rhyme strength and pronunciation hints
* user submissions and points
* tester review queue
* beats and samples discovery
* rapper and producer profile preview
* Free and Premium presentation

Prototype interactions are stored locally in the browser. This first version is intended for UX and concept testing before the shared backend and authentication layer are added.

## Deployment

Pushes to `main` trigger the GitHub Actions deployment workflow. The workflow expects repository secrets named `HOST` and `PASS` and deploys to `reimflow.smarbiz.sbs`.
