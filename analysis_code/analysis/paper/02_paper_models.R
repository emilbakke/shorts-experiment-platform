# Paper models: preregistered H1/H2 on time before swipe per served video
# (primary: device/client timestamps), with robustness across timing source
# (server), scale, cap, and measure (actual playback), plus the
# exploratory age x manosphere models accounting for clip heterogeneity.
# Input: analysis/outputs/paper/derived/exposures_time_before_swipe.csv (from 01_build_paper_data.py)

suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
})

paper_dir <- file.path("analysis", "outputs", "paper")
table_dir <- file.path(paper_dir, "tables")
dir.create(table_dir, recursive = TRUE, showWarnings = FALSE)

d0 <- read.csv(file.path(paper_dir, "derived", "exposures_time_before_swipe.csv"))
d0 <- subset(d0, condition_clean == "treatment" & gender_clean %in% c("man", "woman"))
d0$gender_clean <- factor(d0$gender_clean, levels = c("man", "woman"))
d0$age_band <- factor(d0$age_band, levels = c("18-29", "30-34", "35-44", "45-54", "55-64"))
d0$age35 <- as.integer(d0$age_band %in% c("35-44", "45-54", "55-64"))
d0$idx_c <- as.numeric(scale(d0$exposure_index))
ctrl <- lmerControl(optimizer = "bobyqa")

outcome_variants <- list(
  list(label = "Time before swipe (client), log, uncapped", source = "client_dwell_seconds", cap = Inf, log = TRUE),
  list(label = "Time before swipe (client), log, cap 30 s", source = "client_dwell_seconds", cap = 30, log = TRUE),
  list(label = "Time before swipe (client), seconds, uncapped", source = "client_dwell_seconds", cap = Inf, log = FALSE),
  list(label = "Time before swipe (server), log, uncapped", source = "dwell_seconds", cap = Inf, log = TRUE),
  list(label = "Time before swipe (server), log, cap 60 s", source = "dwell_seconds", cap = 60, log = TRUE),
  list(label = "Time before swipe (server), log, cap 30 s", source = "dwell_seconds", cap = 30, log = TRUE),
  list(label = "Time before swipe (server), log, cap 15 s", source = "dwell_seconds", cap = 15, log = TRUE),
  list(label = "Time before swipe (server), seconds, uncapped", source = "dwell_seconds", cap = Inf, log = FALSE),
  list(label = "Time before swipe (server), seconds, cap 30 s", source = "dwell_seconds", cap = 30, log = FALSE),
  list(label = "Actual playback, log, uncapped", source = "actual_playing_seconds", cap = Inf, log = TRUE),
  list(label = "Actual playback, log, cap 30 s", source = "actual_playing_seconds", cap = 30, log = TRUE)
)

make_y <- function(d, v) {
  y <- pmin(d[[v$source]], v$cap)
  if (v$log) log1p(y) else y
}

contrast <- function(model, weights, label, outcome) {
  b <- fixef(model)
  L <- setNames(rep(0, length(b)), names(b))
  L[names(weights)] <- unlist(weights)
  est <- sum(L * b)
  se <- sqrt(drop(t(L) %*% as.matrix(vcov(model)) %*% L))
  data.frame(outcome = outcome, contrast = label, estimate = est, std_error = se,
             statistic = est / se, p_value = 2 * pnorm(-abs(est / se)))
}

# Preregistered H1/H2 contrasts (preregistered fixed/random structure).
h_rows <- list()
for (v in outcome_variants) {
  d <- d0
  d$y <- make_y(d, v)
  d <- d[!is.na(d$y), ]
  m <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id) + (1 | video_id), data = d, control = ctrl)
  h_rows[[v$label]] <- rbind(
    contrast(m, list("gender_cleanwoman" = -1, "manosphere_video:gender_cleanwoman" = -1), "H1: men vs women on manosphere videos", v$label),
    contrast(m, list("manosphere_video" = 1, "manosphere_video:gender_cleanwoman" = 1), "H2: women, manosphere vs non-manosphere", v$label),
    contrast(m, list("manosphere_video" = 1), "Men, manosphere vs non-manosphere", v$label),
    contrast(m, list("manosphere_video:gender_cleanwoman" = 1), "Interaction: manosphere x woman", v$label),
    contrast(m, list("gender_cleanwoman" = 1), "Women vs men, other clips", v$label)
  )
}
write.csv(do.call(rbind, h_rows), file.path(table_dir, "paper_h1_h2_contrasts.csv"), row.names = FALSE)

# Exploratory age x manosphere models. Clip (item) heterogeneity is handled by video random
# effects; participant-specific manosphere slopes give the between-person moderator honest SEs.
age_specs <- list(
  "A: participant + clip intercepts" = "(1 | participant_id) + (1 | video_id)",
  "B: + participant manosphere slopes" = "(1 + manosphere_video | participant_id) + (1 | video_id)",
  "C: B + clip-specific age effects" = "(1 + manosphere_video | participant_id) + (1 + age35 | video_id)"
)
covariates <- "gender_clean + education_scale + political_orientation + video_platform_use_scale + cohabitation_status"
age_rows <- list()
for (v in outcome_variants[c(1, 4, 6, 10, 11)]) {
  d <- d0
  d$y <- make_y(d, v)
  d <- d[!is.na(d$y) & !is.na(d$age_band), ]
  dc <- d[complete.cases(d[, c("education_scale", "political_orientation", "video_platform_use_scale", "cohabitation_status")]), ]
  for (spec in names(age_specs)) {
    for (adjusted in c(FALSE, TRUE)) {
      fixed <- if (adjusted) paste0("manosphere_video * (age35 + ", covariates, ")") else "manosphere_video * age35 + gender_clean"
      f <- lmer(as.formula(paste("y ~", fixed, "+ idx_c +", age_specs[[spec]])), data = if (adjusted) dc else d, control = ctrl)
      ct <- coef(summary(f))["manosphere_video:age35", ]
      age_rows[[length(age_rows) + 1]] <- data.frame(outcome = v$label, specification = spec, covariate_adjusted = adjusted,
                                                     estimate = ct[["Estimate"]], std_error = ct[["Std. Error"]],
                                                     df = ct[["df"]], p_value = ct[["Pr(>|t|)"]], singular = isSingular(f))
    }
  }
  # Five-level age band: likelihood-ratio test of manosphere x age band (spec B).
  f1 <- lmer(y ~ manosphere_video * age_band + gender_clean + idx_c + (1 + manosphere_video | participant_id) + (1 | video_id),
             data = d, REML = FALSE, control = ctrl)
  f0 <- update(f1, . ~ . - manosphere_video:age_band)
  lrt <- anova(f0, f1)
  age_rows[[length(age_rows) + 1]] <- data.frame(outcome = v$label, specification = "B: 5-level age band x manosphere, LRT",
                                                 covariate_adjusted = FALSE, estimate = lrt$Chisq[2], std_error = NA,
                                                 df = lrt$Df[2], p_value = lrt$`Pr(>Chisq)`[2], singular = isSingular(f1))
}
write.csv(do.call(rbind, age_rows), file.path(table_dir, "paper_age_manosphere_models.csv"), row.names = FALSE)
cat("Model tables written to", table_dir, "\n")

# Clip heterogeneity net of session position. The feed order was fixed, so clip and position are
# confounded, and later positions are reached only by faster swipers. (1) LRT for clip random
# intercepts controlling for position; (2) each manosphere clip vs the ordinary video it replaced
# at the same position in the control feed (same position, comparable participants).
d <- d0
d$y <- log1p(d$client_dwell_seconds)
d <- d[!is.na(d$y), ]
m1 <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id) + (1 | video_id), data = d, REML = FALSE, control = ctrl)
m0 <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id), data = d, REML = FALSE, control = ctrl)
lrt <- anova(m0, m1)
write.csv(data.frame(test = "clip random intercept (treatment arm, controlling position)", chisq = lrt$Chisq[2], df = lrt$Df[2],
                     p_value = lrt$`Pr(>Chisq)`[2], clip_sd = attr(VarCorr(m1)$video_id, "stddev"), residual_sd = sigma(m1)),
          file.path(table_dir, "paper_clip_heterogeneity.csv"), row.names = FALSE)

all_arms <- read.csv(file.path(paper_dir, "derived", "exposures_time_before_swipe.csv"))
all_arms <- all_arms[!is.na(all_arms$client_dwell_seconds) & all_arms$rank %% 4 == 0 & all_arms$gender_clean %in% c("man", "woman"), ]
pos <- aggregate(client_dwell_seconds ~ condition_clean + rank, data = all_arms, FUN = median)
pos <- reshape(pos, idvar = "rank", timevar = "condition_clean", direction = "wide")
names(pos) <- c("rank", "control_replaced_median", "treatment_manosphere_median")
pos$difference <- pos$treatment_manosphere_median - pos$control_replaced_median
write.csv(pos[order(pos$rank), ], file.path(table_dir, "paper_position_comparison.csv"), row.names = FALSE)

# Exploratory: manosphere-vs-other effect per age band (spec B, device-timed log time before swipe).
d <- d0
d$y <- log1p(d$client_dwell_seconds)
d <- d[!is.na(d$y) & !is.na(d$age_band), ]
mb <- lmer(y ~ manosphere_video * age_band + gender_clean + idx_c + (1 + manosphere_video | participant_id) + (1 | video_id),
           data = d, control = ctrl)
b <- fixef(mb); V <- as.matrix(vcov(mb))
bands <- levels(d$age_band)
age_rows <- do.call(rbind, lapply(bands, function(band) {
  L <- setNames(rep(0, length(b)), names(b)); L["manosphere_video"] <- 1
  term <- paste0("manosphere_video:age_band", band)
  if (term %in% names(L)) L[term] <- 1
  est <- sum(L * b); se <- sqrt(drop(t(L) %*% V %*% L))
  data.frame(age_band = band, estimate = est, std_error = se, n_participants = length(unique(d$participant_id[d$age_band == band])))
}))
write.csv(age_rows, file.path(table_dir, "paper_age_band_effects.csv"), row.names = FALSE)
