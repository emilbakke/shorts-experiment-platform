# Robustness models for the watched link (H1/H2).
# (1) Common-exposure set: only the first 12 feed positions (the first three manosphere slots,
#     reached by more than 92% of treated participants), first views only.
# (2) Participants who navigated by touch swipes only. (3) Excluding repeat views (backward
#     swipes and the feed looping after 80 videos).
# Input: analysis/outputs/paper/derived/exposures_robustness.csv (from 05_paper_robustness_data.py)

suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
})

paper_dir <- file.path("analysis", "outputs", "paper")
table_dir <- file.path(paper_dir, "tables")

d0 <- read.csv(file.path(paper_dir, "derived", "exposures_robustness.csv"))
d0 <- subset(d0, condition_clean == "treatment" & gender_clean %in% c("man", "woman") & !is.na(client_dwell_seconds))
d0$gender_clean <- factor(d0$gender_clean, levels = c("man", "woman"))
d0$y <- log1p(d0$client_dwell_seconds)
is_true <- function(x) tolower(as.character(x)) %in% c("true", "1")
d0$repeat_view <- is_true(d0$repeat_view)
d0$touch_only <- is_true(d0$touch_only)
ctrl <- lmerControl(optimizer = "bobyqa")

contrast <- function(model, weights, label, sample, d) {
  b <- fixef(model)
  L <- setNames(rep(0, length(b)), names(b))
  L[names(weights)] <- unlist(weights)
  est <- sum(L * b)
  se <- sqrt(drop(t(L) %*% as.matrix(vcov(model)) %*% L))
  data.frame(sample = sample, contrast = label, estimate = est, std_error = se, p_value = 2 * pnorm(-abs(est / se)),
             n_participants = length(unique(d$participant_id)), n_exposures = nrow(d), n_clips = length(unique(d$video_id)))
}

samples <- list(
  "All served videos (primary)" = d0,
  "First 12 feed positions, first views" = subset(d0, rank <= 12 & !repeat_view),
  "Touch-swipe-only participants" = subset(d0, touch_only),
  "Excluding repeat views" = subset(d0, !repeat_view)
)
rows <- list()
for (s in names(samples)) {
  d <- samples[[s]]
  d$idx_c <- as.numeric(scale(d$exposure_index))
  m <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id) + (1 | video_id), data = d, control = ctrl)
  rows[[s]] <- rbind(
    contrast(m, list("gender_cleanwoman" = -1, "manosphere_video:gender_cleanwoman" = -1), "H1: men vs women on manosphere videos", s, d),
    contrast(m, list("manosphere_video" = 1, "manosphere_video:gender_cleanwoman" = 1), "H2: women, manosphere vs non-manosphere", s, d),
    contrast(m, list("manosphere_video" = 1), "Men, manosphere vs non-manosphere", s, d),
    contrast(m, list("manosphere_video:gender_cleanwoman" = 1), "Interaction: manosphere x woman", s, d)
  )
}
write.csv(do.call(rbind, rows), file.path(table_dir, "paper_h1_h2_robustness.csv"), row.names = FALSE)

cat("Robustness tables written to", table_dir, "\n")
