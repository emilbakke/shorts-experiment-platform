# Figures 2-5 for the manuscript (ggplot2). Reads the pipeline outputs
# (bash analysis/run_paper.sh). Run from the repository root:
#   Rscript figures/make_figures.R
suppressPackageStartupMessages({
  library(ggsignif)
  library(ggplot2)
  library(patchwork)
  library(dplyr)
})

out_dir <- "figures"
derived <- file.path("analysis", "outputs", "paper", "derived")
tables <- file.path("analysis", "outputs", "paper", "tables")
group_cols <- c(Women = "#2a78d6", Men = "#eb6834", Overall = "black")  # validated palette + neutral
group_shapes <- c(Women = 15, Men = 16, Overall = 18)
theme_set(theme_bw(base_size = 9) + theme(legend.position = "bottom", legend.title = element_blank(),
                                          panel.grid.minor = element_blank(),
                                          plot.title = element_text(size = 9, face = "bold", colour = "black"),
                                          text = element_text(colour = "black"), axis.text = element_text(colour = "black"),
                                          strip.text = element_text(colour = "black"), legend.text = element_text(colour = "black")))

save_fig <- function(p, name, w, h) {
  ggsave(file.path(out_dir, paste0(name, ".pdf")), p, width = w, height = h, device = cairo_pdf)
  ggsave(file.path(out_dir, paste0(name, ".png")), p, width = w, height = h, dpi = 300)
}

# ---- data: time before swipe per served video (device timestamps), analysis sample
e <- read.csv(file.path(derived, "exposures_time_before_swipe.csv"))
p <- read.csv(file.path(derived, "participants_paper.csv"))
ids <- p$participant_id[p$paper_post %in% c(TRUE, "True", "true")]
e <- subset(e, participant_id %in% ids & !is.na(client_dwell_seconds))
e$gender <- factor(ifelse(e$gender_clean == "woman", "Women", "Men"), levels = c("Women", "Men"))

cluster_boot_median <- function(y, id, reps = 1000) {
  groups <- split(y, id)
  set.seed(20260930)
  meds <- replicate(reps, median(unlist(groups[sample(length(groups), replace = TRUE)], use.names = FALSE)))
  data.frame(median = median(y), lo = quantile(meds, .025), hi = quantile(meds, .975))
}

# ---- Figure 2: served and perceived links
reach <- read.csv(file.path(tables, "paper_slot_reach.csv"))
p2a <- ggplot(reach, aes(insertion, pct_served)) +
  geom_line(linewidth = 0.5) + geom_point(size = 1.6) +
  scale_x_continuous(breaks = c(1, 5, 10, 15, 20)) +
  scale_y_continuous(limits = c(0, 100), expand = expansion(mult = c(0, .03))) +
  labs(x = "Manosphere clip (order in feed)", y = "Served (%)")

dist <- read.csv(file.path(tables, "paper_perceived_distribution.csv"))
answer_labels <- c(nej = "No", ved_ikke_husker_ikke = "Don't know", en_eller_faa = "One or a few", flere = "Several", mange = "Many")
dist$answer <- factor(unname(answer_labels[dist$perceived_content_type]), levels = rev(unname(answer_labels)))
dist$condition <- factor(ifelse(dist$condition_clean == "treatment", "Treatment", "Control"), levels = c("Treatment", "Control"))
answer_cols <- c(No = "#cde2fb", `Don't know` = "grey80", `One or a few` = "#86b6ef", Several = "#3987e5", Many = "#1c5cab")
p2b <- ggplot(dist, aes(share * 100, condition, fill = answer)) +
  geom_col(width = 0.6, colour = "white", linewidth = 0.4) +
  scale_fill_manual(values = answer_cols, breaks = unname(answer_labels)) +
  scale_x_continuous(expand = c(0, 0)) +
  labs(x = "Noticed videos about gender (% of participants)", y = NULL) +
  guides(fill = guide_legend(nrow = 1)) + theme(legend.key.size = unit(0.8, "lines"))
save_fig(p2a + p2b + plot_layout(widths = c(1, 1.5)) + plot_annotation(tag_levels = "A"), "figure2_served_perceived", 7, 2.8)

# ---- Figure 3: watched link
tr <- subset(e, condition_clean == "treatment")
fa <- tr %>%
  mutate(clip = factor(ifelse(manosphere_video == 1, "Manosphere", "Other"), levels = c("Other", "Manosphere"))) %>%
  group_by(gender, clip) %>%
  group_modify(~ cluster_boot_median(.x$client_dwell_seconds, .x$participant_id)) %>%
  ungroup()
# Brackets: gender differences at each clip type, from the mixed model (device-timed log time before swipe).
hh <- read.csv(file.path(tables, "paper_h1_h2_contrasts.csv"))
hh <- hh[hh$outcome == "Time before swipe (client), log, uncapped", ]
stars_for <- function(p) ifelse(p < .001, "***", ifelse(p < .01, "**", ifelse(p < .05, "*", "")))
brk <- data.frame(clip = c("Other", "Manosphere"),
                  p = c(hh$p_value[hh$contrast == "Women vs men, other clips"],
                        hh$p_value[hh$contrast == "H1: men vs women on manosphere videos"]))
dodge_w <- 0.3                                     # women at x - 0.075, men at x + 0.075
brk$x_women <- c(1, 2) - dodge_w / 4
brk$x_men <- c(1, 2) + dodge_w / 4
brk$y <- sapply(brk$clip, function(cl) max(fa$hi[as.character(fa$clip) == cl])) + 0.25
brk$stars <- stars_for(brk$p)
brk <- brk[brk$stars != "", ]
fa$xpos <- as.numeric(fa$clip)
p3a <- ggplot(fa, aes(xpos, median, colour = gender, shape = gender, group = gender)) +
  geom_signif(data = brk, aes(xmin = x_women, xmax = x_men, annotations = stars, y_position = y),
              manual = TRUE, inherit.aes = FALSE, tip_length = 0.02, textsize = 3.4, vjust = 0.3, colour = "black") +
  geom_line(position = position_dodge(dodge_w), linewidth = 0.6) +
  geom_pointrange(aes(ymin = lo, ymax = hi), position = position_dodge(dodge_w), size = 0.4) +
  scale_colour_manual(values = group_cols) + scale_shape_manual(values = group_shapes) +
  scale_x_continuous(breaks = 1:2, labels = levels(fa$clip), limits = c(0.7, 2.3)) +
  scale_y_continuous(limits = c(0, NA), expand = expansion(mult = c(0, .12))) +
  labs(x = NULL, y = "Median time before swipe (s)")
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
save_fig(p3a + p3b + plot_layout(widths = c(1, 1.9)) + plot_annotation(tag_levels = "A"), "figure3_watched", 7, 3.0)

# ---- Figure 4: attitudes link (overall and by gender)
q <- read.csv(file.path(tables, "paper_h3_h4_contrasts.csv"))
labels <- c(feminist_attitude_rev = "Feminism important (reversed)", feminism_taken_too_far = "Feminism has gone too far",
            traditional_gender_attitude = "Traditional gender roles best", harder_to_be_a_man_today = "Harder to be a man today",
            social_division = "Society increasingly divided", gender_conflict_exaggeration = "Online discussions exaggerate conflicts",
            online_misinformation = "Often encounter misinformation")
pick <- c("Exploratory H3: overall treatment" = "Overall", "H4: treatment" = "Overall",
          "H3a: treatment among men" = "Men", "Exploratory H4: treatment among men" = "Men",
          "H3b: treatment among women" = "Women", "Exploratory H4: treatment among women" = "Women")
eff <- q %>%
  filter(model %in% c("primary", "exploratory"), contrast %in% names(pick)) %>%
  mutate(group = factor(pick[contrast], levels = c("Overall", "Women", "Men")),
         item = factor(unname(labels[outcome]), levels = rev(unname(labels))))
forest <- function(items, title) {
  ggplot(filter(eff, outcome %in% items), aes(estimate, item, colour = group, shape = group)) +
    geom_vline(xintercept = 0, colour = "grey40") +
    geom_pointrange(aes(xmin = estimate - 1.96 * std_error, xmax = estimate + 1.96 * std_error),
                    position = position_dodge(width = 0.6), size = 0.35) +
    scale_colour_manual(values = group_cols, breaks = c("Overall", "Women", "Men")) +
    scale_shape_manual(values = group_shapes, breaks = c("Overall", "Women", "Men")) +
    scale_y_discrete(limits = rev(unname(labels[items]))) +
    coord_cartesian(xlim = c(-0.62, 0.62)) +
    labs(title = title, x = "Treatment effect (scale points, 95% CI)", y = NULL)
}
p4a <- forest(names(labels)[1:4], "Gender attitudes") + theme(axis.title.x = element_blank())
p4b <- forest(names(labels)[5:7], "Broader perceptions")
save_fig(p4a / p4b + plot_layout(heights = c(4, 3), guides = "collect") & theme(legend.position = "bottom"),
         "figure4_attitudes", 5.2, 5.3)

# ---- Figure 5: exploratory profile of relative attention (raw participant-level averages)
prof <- read.csv(file.path(tables, "paper_profile_gaps.csv"))
var_labels <- c(age_band = "A  Age group", time_of_day = "B  Time of day", living = "C  Living situation", political = "D  Political orientation")
group_labels <- c("Daytime (06-17)" = "Day", "Evening/night (18-05)" = "Evening/\nnight", "Living alone" = "Alone",
                  "Cohabiting" = "Cohabiting", "Living with parents" = "With\nparents", "Left (0-4)" = "Left", "Centre (5-6)" = "Centre",
                  "Right (7-10)" = "Right")
prof$label <- ifelse(prof$group %in% names(group_labels), group_labels[prof$group], sub("-", "–", prof$group))
prof$label <- factor(prof$label, levels = unique(prof$label))
prof$variable <- factor(var_labels[prof$variable], levels = var_labels)
prof$measure <- factor(prof$measure, levels = c("Time before swipe", "Playback time"))
prof$stars <- ifelse(prof$p_vs_zero < .001, "***", ifelse(prof$p_vs_zero < .01, "**", ifelse(prof$p_vs_zero < .05, "*", "")))
dodge <- position_dodge(width = 0.55)
p5 <- ggplot(prof, aes(label, mean_gap, colour = measure, shape = measure)) +
  geom_hline(yintercept = 0, colour = "grey40") +
  geom_pointrange(aes(ymin = ci_low, ymax = ci_high), position = dodge, size = 0.45) +
  geom_text(aes(y = ci_high, label = stars), position = dodge, vjust = -0.3, size = 3.8, colour = "black", show.legend = FALSE) +
  facet_wrap(~ variable, ncol = 2, scales = "free_x") +
  scale_colour_manual(values = c("Time before swipe" = "#2a78d6", "Playback time" = "#eb6834")) +
  scale_shape_manual(values = c("Time before swipe" = 16, "Playback time" = 17)) +
  scale_y_continuous(expand = expansion(mult = c(0.05, 0.17))) +
  labs(x = NULL, y = "Manosphere minus other clips (s, 95% CI)") +
  theme(strip.background = element_blank(), strip.text = element_text(face = "bold", hjust = 0, size = 11, colour = "black"),
        axis.text = element_text(size = 10, colour = "black"), axis.title = element_text(size = 11),
        legend.text = element_text(size = 10.5), panel.spacing = unit(0.9, "lines"))
save_fig(p5, "figure5_profiles", 6.5, 5.4)
cat("figures written to", out_dir, "\n")
