# Preregistered post-survey models (H3, H3a, H3b, H4) on the analysis sample.
# Preregistered specifications: unadjusted OLS primary models, covariate-adjusted
# secondary models, BH-FDR q-values within each contrast type across the items of a family.
# Input: analysis/outputs/paper/derived/participants_paper.csv (from 01_build_paper_data.py)

paper_dir <- file.path("analysis", "outputs", "paper")
table_dir <- file.path(paper_dir, "tables")

p <- read.csv(file.path(paper_dir, "derived", "participants_paper.csv"))
p_all <- subset(p, paper_post_all %in% c(TRUE, "True", "true", 1))  # H4: all post-survey completers (registered model has no gender term)
p <- subset(p, paper_post %in% c(TRUE, "True", "true", 1))          # H3 and gender contrasts: men and women
p$gender_clean <- factor(p$gender_clean, levels = c("man", "woman"))
for (col in c("age_group", "cohabitation_status", "employment_status")) { p[[col]] <- factor(p[[col]]); p_all[[col]] <- factor(p_all[[col]]) }

h3_items <- c("feminist_attitude_rev", "feminism_taken_too_far", "traditional_gender_attitude", "harder_to_be_a_man_today")
h4_items <- c("social_division", "gender_conflict_exaggeration", "online_misinformation")
adjust <- "age_group + cohabitation_status + employment_status + education_scale + political_orientation + video_platform_use_scale"

contrast <- function(model, weights, label, outcome, sd_outcome) {
  b <- coef(model)
  L <- setNames(rep(0, length(b)), names(b))
  L[names(weights)] <- unlist(weights)
  est <- sum(L * b)
  se <- sqrt(drop(t(L) %*% vcov(model) %*% L))
  stat <- est / se
  data.frame(outcome = outcome, contrast = label, estimate = est, std_error = se, statistic = stat,
             p_value = 2 * pt(abs(stat), df = df.residual(model), lower.tail = FALSE),
             d = est / sd_outcome, n = nobs(model))
}

fit_family <- function(items, rhs, contrasts, p = get("p", envir = globalenv())) {
  rows <- list()
  for (y in items) {
    m <- lm(as.formula(paste(y, "~", rhs)), data = p)
    sd_y <- sd(p[[y]], na.rm = TRUE)
    for (k in names(contrasts)) rows[[length(rows) + 1]] <- contrast(m, contrasts[[k]], k, y, sd_y)
  }
  out <- do.call(rbind, rows)
  out$q_value_bh <- ave(out$p_value, out$contrast, FUN = function(x) p.adjust(x, method = "BH"))
  out
}

h3_contrasts <- list(
  "H3: treatment x woman" = list("treatment:gender_cleanwoman" = 1),
  "H3a: treatment among men" = list("treatment" = 1),
  "H3b: treatment among women" = list("treatment" = 1, "treatment:gender_cleanwoman" = 1)
)
h4_contrasts <- list("H4: treatment" = list("treatment" = 1))

out <- rbind(
  cbind(model = "primary", fit_family(h3_items, "treatment * gender_clean", h3_contrasts)),
  cbind(model = "adjusted", fit_family(h3_items, paste("treatment * gender_clean +", adjust), h3_contrasts)),
  cbind(model = "primary", fit_family(h4_items, "treatment", h4_contrasts, p_all)),
  cbind(model = "adjusted", fit_family(h4_items, paste("treatment +", adjust), h4_contrasts, p_all)),
  cbind(model = "binary-gender sample", fit_family(h4_items, "treatment", h4_contrasts)),
  cbind(model = "exploratory", fit_family(h4_items, "treatment * gender_clean", list(
    "Exploratory H4: treatment x woman" = list("treatment:gender_cleanwoman" = 1),
    "Exploratory H4: treatment among men" = list("treatment" = 1),
    "Exploratory H4: treatment among women" = list("treatment" = 1, "treatment:gender_cleanwoman" = 1)))),
  cbind(model = "exploratory", fit_family(h3_items, "treatment", list("Exploratory H3: overall treatment" = list("treatment" = 1))))
)
write.csv(out, file.path(table_dir, "paper_h3_h4_contrasts.csv"), row.names = FALSE)

# Pretreatment balance by condition (analysis sample).
bal_vars <- c("education_scale", "political_orientation", "video_platform_use_scale")
bal <- do.call(rbind, lapply(bal_vars, function(v) {
  tt <- t.test(p[[v]] ~ p$condition_clean)
  data.frame(variable = v, control = tt$estimate[[1]], treatment = tt$estimate[[2]], p_value = tt$p.value)
}))
cat_vars <- c("gender_clean", "age_group", "cohabitation_status", "employment_status")
bal_cat <- do.call(rbind, lapply(cat_vars, function(v) {
  data.frame(variable = v, control = NA, treatment = NA,
             p_value = suppressWarnings(chisq.test(table(p[[v]], p$condition_clean))$p.value))
}))
write.csv(rbind(bal, bal_cat), file.path(table_dir, "paper_balance.csv"), row.names = FALSE)
cat("Survey model tables written to", table_dir, "\n")
