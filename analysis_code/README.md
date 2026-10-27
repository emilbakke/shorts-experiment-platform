# Analysis code

Scripts that reproduce every table, model, and figure reported in the paper from the study's
raw platform data. The data are not included: participant-level data cannot be shared publicly
under the terms of participants' consent. The scripts therefore do not run without the original
data, but they are provided so that the data preparation, exclusions, models, and corrections can
be inspected. Running the pipeline requires data supplied through the study's data-access process.

## Inputs

- `analysis/outputs/raw/*.csv`: platform tables (users, sessions, impressions, events), produced by
  `analysis/00_extract_postgres.py` from the platform databases.

Included: `study_media/sequence_manifest.csv`, the two feed sequences reduced to feed, position,
manosphere flag, and duration (no titles, creators, or video identifiers). Script 05 uses it for
the stimulus-duration comparison and skips that comparison if the file is missing.

## Run (from this folder)

```bash
python3 analysis/00_extract_postgres.py      # needs VIEWTUBE_BEHAVIOR_DATABASE_URL
python3 analysis/01_build_analysis_data.py   # participant- and exposure-level data
bash analysis/run_paper.sh                   # all models and tables (analysis/outputs/paper/tables)
Rscript figures/make_figures.R               # Figures 2-6 (as numbered in the paper)
Rscript figures/make_figure3_model.R         # model-based variant of the watched-link figure
python3 figures/make_chain_figure.py         # Figure 1 (exposure chain)
```

`analysis/paper/` in order: 01 builds time before swipe per served video and the analysis samples,
02 fits the preregistered H1/H2 mixed models and the exploratory age models, 03 fits the
preregistered H3/H4 OLS models with Benjamini-Hochberg correction, 04 computes the exploratory
participant-level watch-time gaps, 05-06 run the robustness checks (navigation mode, repeat views,
first 12 positions), 07 compares leaving the feed between conditions, and 08 writes the full
coefficient tables in the appendix.

## Software

Python 3.13 (pandas 2.3, numpy 2.4, scipy 1.16, statsmodels 0.14, matplotlib 3.10, sqlalchemy for
extraction) and R 4.5 (lme4 2.0.6, lmerTest 3.2.1, ggplot2 4.0.3, patchwork 1.3.2, dplyr 1.2.1,
ggsignif 0.6.4).

Never commit participant-level data, database exports, or study media to this folder.
