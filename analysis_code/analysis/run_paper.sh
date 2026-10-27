#!/usr/bin/env bash
set -euo pipefail

# Paper analyses (time before swipe per served video). Requires the
# derived datasets from analysis/01_build_analysis_data.py. The R scripts need lme4 and lmerTest;
# if they are not in the default library, set R_LIBS (e.g. a project-local library).
python3 analysis/paper/01_build_paper_data.py
Rscript analysis/paper/02_paper_models.R
Rscript analysis/paper/03_paper_survey_models.R
python3 analysis/paper/04_paper_profile_gaps.py
python3 analysis/paper/05_paper_robustness_data.py
Rscript analysis/paper/06_paper_robustness_models.R
python3 analysis/paper/07_paper_backgrounding.py
Rscript analysis/paper/08_paper_full_model_tables.R

echo "Outputs written under analysis/outputs/paper/"
