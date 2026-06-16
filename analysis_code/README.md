# Analysis code

This folder is reserved for the complete reproducible analysis pipeline accompanying the report and paper.

Recommended structure:

- `scripts/`: numbered data-preparation, modeling, table, and figure scripts
- `tests/`: checks for derived variables, exclusions, estimands, and expected outputs
- `README.md`: exact software requirements and commands needed to reproduce the analysis

When analysis code is added, document the analysis sample, exclusion rules, treatment coding, primary estimands, index construction, missing-data handling, statistical models, uncertainty estimates, multiplicity decisions, and commands that regenerate every reported table and figure.

Do **not** commit participant-level data, database exports, restricted media, credentials, or generated confidential outputs. The public pipeline should accept data supplied separately through the study's approved data-access process, or use a synthetic/de-identified example dataset when appropriate.
