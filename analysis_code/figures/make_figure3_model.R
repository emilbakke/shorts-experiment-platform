# Alternative Figure 3 (watched link): panel A shows model-estimated time before swipe
# from the preregistered H1/H2 mixed model (device time, log1p, uncapped; same
# specification as analysis/paper/02_paper_models.R), so points, intervals and brackets
# all come from one model. Panel B is unchanged from make_figures.R.
# Run from the repository root:
#   Rscript figures/make_figure3_model.R
suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
  library(ggsignif)
  library(ggplot2)
  library(patchwork)
  library(dplyr)
})

out_dir <- "figures"
derived <- file.path("analysis", "outputs", "paper", "derived")
group_cols <- c(Women = "#2a78d6", Men = "#eb6834")
group_shapes <- c(Women = 15, Men = 16)
theme_set(theme_bw(base_size = 9) + theme(legend.position = "bottom", legend.title = element_blank(),
                                          panel.grid.minor = element_blank(),
                                          text = element_text(colour = "black"), axis.text = element_text(colour = "black"),
                                          legend.text = element_text(colour = "black")))

# ---- model: identical to the primary H1/H2 model in analysis/paper/02_paper_models.R
d <- read.csv(file.path(derived, "exposures_time_before_swipe.csv"))
d <- subset(d, condition_clean == "treatment" & gender_clean %in% c("man", "woman"))
d$gender_clean <- factor(d$gender_clean, levels = c("man", "woman"))
d$idx_c <- as.numeric(scale(d$exposure_index))
d$y <- log1p(d$client_dwell_seconds)
d <- d[!is.na(d$y), ]
m <- lmer(y ~ manosphere_video * gender_clean + idx_c + (1 | participant_id) + (1 | video_id),
          data = d, control = lmerControl(optimizer = "bobyqa"))
b <- fixef(m)
V <- as.matrix(vcov(m))
lin <- function(w) {
  L <- setNames(rep(0, length(b)), names(b))
  L[names(w)] <- unlist(w)
  c(est = sum(L * b), se = sqrt(drop(t(L) %*% V %*% L)))
}

# Cell estimates at the average feed position (idx_c = 0), back-transformed to seconds.
cells <- list(
  list(gender = "Men", clip = "Other", w = list("(Intercept)" = 1)),
  list(gender = "Women", clip = "Other", w = list("(Intercept)" = 1, "gender_cleanwoman" = 1)),
  list(gender = "Men", clip = "Manosphere", w = list("(Intercept)" = 1, "manosphere_video" = 1)),
  list(gender = "Women", clip = "Manosphere", w = list("(Intercept)" = 1, "manosphere_video" = 1, "gender_cleanwoman" = 1,
                                                     "manosphere_video:gender_cleanwoman" = 1))
)
fa <- do.call(rbind, lapply(cells, function(cl) {
  s <- lin(cl$w)
  data.frame(gender = cl$gender, clip = cl$clip,
             est = expm1(s[["est"]]), lo = expm1(s[["est"]] - 1.96 * s[["se"]]), hi = expm1(s[["est"]] + 1.96 * s[["se"]]))
}))
fa$gender <- factor(fa$gender, levels = c("Women", "Men"))
fa$clip <- factor(fa$clip, levels = c("Other", "Manosphere"))
fa$xpos <- as.numeric(fa$clip)

# Brackets: women vs men at each clip type, same contrasts as paper_h1_h2_contrasts.csv.
pz <- function(w) { s <- lin(w); 2 * pnorm(-abs(s[["est"]] / s[["se"]])) }
stars_for <- function(p) ifelse(p < .001, "***", ifelse(p < .01, "**", ifelse(p < .05, "*", "")))
brk <- data.frame(clip = c("Other", "Manosphere"),
                  p = c(pz(list("gender_cleanwoman" = 1)),
                        pz(list("gender_cleanwoman" = 1, "manosphere_video:gender_cleanwoman" = 1))))
dodge_w <- 0.3
brk$x_women <- c(1, 2) - dodge_w / 4
brk$x_men <- c(1, 2) + dodge_w / 4
brk$y <- sapply(brk$clip, function(cl) max(fa$hi[as.character(fa$clip) == cl])) + 0.25
brk$stars <- stars_for(brk$p)
print(fa, digits = 3)
print(brk[, c("clip", "p", "stars")], digits = 3)
brk <- brk[brk$stars != "", ]

p3a <- ggplot(fa, aes(xpos, est, colour = gender, shape = gender, group = gender)) +
  geom_signif(data = brk, aes(xmin = x_women, xmax = x_men, annotations = stars, y_position = y),
              manual = TRUE, inherit.aes = FALSE, tip_length = 0.02, textsize = 3.4, vjust = 0.3, colour = "black") +
  geom_line(position = position_dodge(dodge_w), linewidth = 0.6) +
  geom_pointrange(aes(ymin = lo, ymax = hi), position = position_dodge(dodge_w), size = 0.4) +
  scale_colour_manual(values = group_cols) + scale_shape_manual(values = group_shapes) +
  scale_x_continuous(breaks = 1:2, labels = levels(fa$clip), limits = c(0.7, 2.3)) +
  scale_y_continuous(limits = c(0, NA), expand = expansion(mult = c(0, .12))) +
  labs(x = NULL, y = "Estimated time before swipe (s)")

# ---- panel B: as in make_figures.R
p <- read.csv(file.path(derived, "participants_paper.csv"))
ids <- p$participant_id[p$paper_post %in% c(TRUE, "True", "true")]
e <- read.csv(file.path(derived, "exposures_time_before_swipe.csv"))
e <- subset(e, participant_id %in% ids & !is.na(client_dwell_seconds))
pos <- e %>%
  filter(rank %% 4 == 0) %>%
  mutate(feed = factor(ifelse(condition_clean == "treatment", "Manosphere clip (treatment feed)",
                              "Replaced ordinary video (control feed)"),
                       levels = c("Manosphere clip (treatment feed)", "Replaced ordinary video (control feed)"))) %>%
  group_by(feed, rank) %>%
  summarise(median = median(client_dwell_seconds), .groups = "drop")
p3b <- ggplot(pos, aes(rank, median, colour = feed, shape = feed)) +
  geom_line(linewidth = 0.5) + geom_point(size = 1.6) +
  scale_colour_manual(values = c("black", "grey60")) + scale_shape_manual(values = c(16, 1)) +
  scale_x_continuous(breaks = seq(4, 80, 8)) +
  scale_y_log10(breaks = c(0.5, 1, 2, 5, 10)) +
  labs(x = "Position in feed", y = "Median time before swipe (s)") +
  theme(legend.position = "bottom")

fig <- p3a + p3b + plot_layout(widths = c(1, 1.9)) + plot_annotation(tag_levels = "A")
ggsave(file.path(out_dir, "figure3_watched_model.pdf"), fig, width = 7, height = 3.0, device = cairo_pdf)
ggsave(file.path(out_dir, "figure3_watched_model.png"), fig, width = 7, height = 3.0, dpi = 300)
