# Appendix: full coefficient tables for the preregistered models.
# (1) Mixed-effects models for H1/H2 under the three watch-time measures.
# (2) OLS models for H3 (gender-attitude items) and H4 (broader-perception items).
# Inputs: analysis/outputs/paper/derived/exposures_time_before_swipe.csv, participants_paper.csv

suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
})

paper_dir <- file.path("analysis", "outputs", "paper")
table_dir <- file.path(paper_dir, "tables")

d0 <- read.csv(file.path(paper_dir, "derived", "exposures_time_before_swipe.csv"))
d0 <- subset(d0, condition_clean == "treatment" & gender_clean %in% c("man", "woman"))
d0$gender_clean <- factor(d0$gender_clean, levels = c("man", "woman"))
d0$idx_c <- as.numeric(scale(d0$exposure_index))
ctrl <- lmerControl(optimizer = "bobyqa")
measures <- c("Device time (primary)" = "client_dwell_seconds", "Server time" = "dwell_seconds", "Playback time" = "actual_playing_seconds",
              "Device time, raw seconds" = "client_dwell_seconds")

rows <- list()
for (m in names(measures)) {
  d <- d0
  d$y <- if (grepl("raw seconds", m)) d[[measures[[m]]]] else log1p(d[[measures[[m]]]])
  d <- d[!is.na(d$y), ]
  f <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id) + (1 | video_id), data = d, control = ctrl)
  ct <- coef(summary(f))
  vc <- as.data.frame(VarCorr(f))
  # Marginal and conditional R2 (Nakagawa & Schielzeth, 2013): fixed-effect variance and fixed + random variance over total
  v_fixed <- var(as.vector(model.matrix(f) %*% fixef(f)))
  v_random <- sum(vc$vcov[vc$grp != "Residual"])
  v_total <- v_fixed + v_random + sigma(f)^2
  rows[[m]] <- rbind(
    data.frame(measure = m, term = rownames(ct), estimate = ct[, "Estimate"], std_error = ct[, "Std. Error"], p_value = ct[, "Pr(>|t|)"]),
    data.frame(measure = m, term = c("SD participant intercept", "SD video intercept", "SD residual"),
               estimate = c(vc$sdcor[vc$grp == "participant_id"], vc$sdcor[vc$grp == "video_id"], vc$sdcor[vc$grp == "Residual"]), std_error = NA, p_value = NA),
    data.frame(measure = m, term = c("Marginal R2", "Conditional R2"),
               estimate = c(v_fixed / v_total, (v_fixed + v_random) / v_total), std_error = NA, p_value = NA),
    data.frame(measure = m, term = c("N served videos", "N participants", "N videos"),
               estimate = c(nrow(d), length(unique(d$participant_id)), length(unique(d$video_id))), std_error = NA, p_value = NA)
  )
}
write.csv(do.call(rbind, rows), file.path(table_dir, "paper_full_mixed_models.csv"), row.names = FALSE)

p <- read.csv(file.path(paper_dir, "derived", "participants_paper.csv"))
is_true <- function(x) tolower(as.character(x)) %in% c("true", "1")
p_all <- p[is_true(p$paper_post_all), ]
p_bin <- p[is_true(p$paper_post), ]
p_bin$gender_clean <- factor(p_bin$gender_clean, levels = c("man", "woman"))
ols <- function(y, rhs, data, family) {
  f <- lm(as.formula(paste(y, "~", rhs)), data = data)
  ct <- coef(summary(f))
  rbind(data.frame(family = family, outcome = y, term = rownames(ct), estimate = ct[, "Estimate"], std_error = ct[, "Std. Error"], p_value = ct[, "Pr(>|t|)"]),
        data.frame(family = family, outcome = y, term = c("N", "R2"), estimate = c(nobs(f), summary(f)$r.squared), std_error = NA, p_value = NA))
}
h3 <- c("feminist_attitude_rev", "feminism_taken_too_far", "traditional_gender_attitude", "harder_to_be_a_man_today")
h4 <- c("social_division", "gender_conflict_exaggeration", "online_misinformation")
out <- rbind(do.call(rbind, lapply(h3, ols, rhs = "treatment * gender_clean", data = p_bin, family = "H3")),
             do.call(rbind, lapply(h4, ols, rhs = "treatment", data = p_all, family = "H4")))
write.csv(out, file.path(table_dir, "paper_full_ols_models.csv"), row.names = FALSE)
cat("full model tables written to", table_dir, "\n")
