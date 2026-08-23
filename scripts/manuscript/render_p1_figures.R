# =============================================================================
#  P1 Data Descriptor — figures, rendered in R
#
#  Reads the tidy CSVs written by scripts/manuscript/export_figure_data.py and
#  draws Figures 1–4 with one shared visual system. The science stays in Python:
#  Figure 4 needs Resnik best-match-average similarity scored against the pinned
#  HPO release, which 18b_build_hard_candidates.py already does and which the
#  Figshare deposit archives. This file only draws.
#
#  ---- the design system ------------------------------------------------------
#
#  Type      Source Sans 3 (SIL OFL). A humanist sans drawn for interfaces and
#            data, so it holds up at 8-9 pt where Helvetica-alikes get muddy.
#            Two weights carry the hierarchy: bold for panel titles and figures
#            that matter, regular for everything else.
#
#  Headers   Each panel opens with a coloured letter, the title in bold, and a
#            muted one-line takeaway. The takeaway is the point: a reader should
#            be able to skip the caption and still know what the panel shows.
#
#  Colour    Taken from the original Figure 4, and it carries meaning everywhere:
#              grey    baseline or reference series   (random distractors, overlap-present)
#              orange  the highlighted subset         (hard distractors, overlap-absent)
#              red     a threshold or reference value (dashed, never a fill)
#            Fills are tinted rather than saturated so bars read as areas, not as
#            blocks of ink, and the text on them stays legible.
#
#  Labels    Direct labels wherever a legend can be avoided - on the bars, on the
#            distributions, on the point clouds. A legend makes the eye travel;
#            a label in place does not.
#
#  Furniture Dotted hairline grid on the value axis only, a thin baseline rule
#            instead of a heavy axis, and no ticks where the grid already says
#            where the values are.
#
#  Requires: ggplot2, patchwork, jsonlite, scales, showtext, sysfonts, ragg
#      install.packages(c("ggplot2","patchwork","jsonlite","scales",
#                         "showtext","sysfonts","ragg"))
#
#  Run from the project root:
#      Rscript scripts/manuscript/render_p1_figures.R [--out DIR] [--data DIR]
# =============================================================================

suppressPackageStartupMessages({
  library(ggplot2); library(patchwork); library(jsonlite); library(scales)
  library(grid); library(sysfonts); library(showtext); library(ragg)
})

args   <- commandArgs(trailingOnly = TRUE)
arg_of <- function(flag, default) {
  i <- match(flag, args); if (is.na(i) || i == length(args)) default else args[i + 1]
}
DATA_DIR <- arg_of("--data", "reports/figures/P1_figures/data")
OUT_DIR  <- arg_of("--out",  "reports/figures/P1_figures")
dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)

need <- function(f) {
  p <- file.path(DATA_DIR, f)
  if (!file.exists(p)) stop("missing ", p, " - run scripts/manuscript/export_figure_data.py first")
  p
}

# ---- type -------------------------------------------------------------------
FONT <- "sans"
if (isTRUE(tryCatch({ font_add_google("Source Sans 3", "p1"); TRUE }, error = function(e) FALSE))) {
  FONT <- "p1"
} else {
  message("note: Source Sans 3 unavailable; falling back to the default sans")
}
showtext_auto(); showtext_opts(dpi = 300)

# ---- palette ----------------------------------------------------------------
P <- list(
  grey   = "#8F8F8F", greyF   = "#C3C6C7",   # reference series: mark / fill tint
  orange = "#D9773F", orangeF = "#EBAE84",   # highlighted subset
  greyT  = "#555D60", orangeT = "#8A4A22",   # text on those tints
  red    = "#B33F44",                        # thresholds, dashed only
  ink    = "#1F2426", ink2    = "#41494C",
  muted  = "#7A8285",
  rule   = "#E4E7E8", hair    = "#CDD2D3",
  panelF = "#F1F3F4",
  bg     = "#FFFFFF"
)
BASE <- 9

# ---- theme ------------------------------------------------------------------
theme_p1 <- function(base_size = BASE, grid_x = FALSE) {
  th <- theme_minimal(base_size = base_size, base_family = FONT) +
    theme(
      text               = element_text(colour = P$ink2, family = FONT),
      plot.title         = element_blank(),   # headers are drawn by hdr()
      plot.subtitle      = element_blank(),
      axis.title         = element_text(size = base_size * 0.96, colour = P$muted),
      axis.title.x       = element_text(margin = margin(t = 7)),
      axis.title.y       = element_text(margin = margin(r = 7)),
      axis.text          = element_text(size = base_size * 0.92, colour = P$muted),
      axis.ticks         = element_blank(),
      axis.line.x        = element_line(colour = P$hair, linewidth = 0.35),
      panel.grid.major.y = element_line(colour = P$rule, linewidth = 0.35, linetype = "12"),
      panel.grid.major.x = element_blank(),
      panel.grid.minor   = element_blank(),
      panel.background   = element_rect(fill = P$bg, colour = NA),
      plot.background    = element_rect(fill = P$bg, colour = NA),
      legend.position    = "none",
      plot.margin        = margin(4, 10, 6, 4)
    )
  if (grid_x) th <- th + theme(panel.grid.major.x =
                                 element_line(colour = P$rule, linewidth = 0.35, linetype = "12"))
  th
}
theme_diagram <- function() {
  theme_void(base_size = BASE, base_family = FONT) +
    theme(plot.background = element_rect(fill = P$bg, colour = NA),
          plot.margin = margin(4, 8, 4, 4))
}

# A panel header: coloured letter, bold title, muted one-line takeaway.
hdr <- function(letter, title, note = NULL) {
  gp_l <- grid::gpar(col = P$orange, fontfamily = FONT, fontface = "bold", fontsize = 10.5)
  gp_t <- grid::gpar(col = P$ink,    fontfamily = FONT, fontface = "bold", fontsize = 10.5)
  x0   <- grid::unit(0.004, "npc")
  # Panel letters are for multi-panel figures. Figures 1 and 2 are single panels
  # numbered by the LaTeX caption, so they pass letter = "" and the title starts
  # at the margin; anything else is offset by the measured width of the letter,
  # since drawing both at x0 is what made "a" and "Disease-category" collide.
  has_letter <- !is.null(letter) && nzchar(letter)
  xt <- if (has_letter) x0 + grid::grobWidth(grid::textGrob(letter, gp = gp_l)) +
                             grid::unit(3.2, "pt") else x0
  wrap_elements(full = grid::gTree(children = grid::gList(
    if (has_letter) grid::textGrob(letter, x = x0, y = 0.80, hjust = 0, vjust = 1, gp = gp_l)
    else grid::nullGrob(),
    grid::textGrob(title, x = xt, y = 0.80, hjust = 0, vjust = 1, gp = gp_t),
    if (!is.null(note))
      grid::textGrob(note, x = x0, y = 0.30, hjust = 0, vjust = 1,
                     gp = grid::gpar(col = P$muted, fontfamily = FONT, fontsize = 8.4))
    else grid::nullGrob()
  )))
}
stack_hdr <- function(letter, title, note, plot, h = c(1, 9))
  (hdr(letter, title, note) / plot) + plot_layout(heights = h)

lab_n <- function(x) format(x, big.mark = ",", trim = TRUE)
save_fig <- function(name, plot, w, h)
  ggsave(file.path(OUT_DIR, name), plot, width = w, height = h,
         dpi = 300, bg = "white", device = ragg::agg_png)

# =============================================================================
#  Figure 1 - cohort selection
# =============================================================================
f1 <- read.csv(need("fig1_funnel.csv"), stringsAsFactors = FALSE)
n  <- nrow(f1)
f1$y      <- seq(n, 1)
f1$is_end <- seq_len(n) == n
f1$fill   <- ifelse(f1$is_end, P$orangeF, P$panelF)
f1$accent <- ifelse(f1$is_end, P$orange,  P$hair)
f1$numcol <- ifelse(f1$is_end, P$orangeT, P$ink)

wrap_reason <- function(r) paste(strsplit(r, "; ", fixed = TRUE)[[1]], collapse = "\n")
dr <- f1[f1$dropped > 0, ]
dr$yb <- dr$y + 0.5
dr$hd <- sprintf("−%s excluded", lab_n(dr$dropped))
dr$bd <- vapply(dr$reason, wrap_reason, character(1))

BW <- 1.16; BH <- 0.58
fig1 <- ggplot() +
  geom_tile(data = f1, aes(x = 0, y = y, fill = I(fill)), width = BW, height = BH, colour = NA) +
  geom_segment(data = f1, aes(x = -BW/2, xend = -BW/2, y = y - BH/2, yend = y + BH/2,
                              colour = I(accent)), linewidth = 1.6, lineend = "butt") +
  geom_text(data = f1, aes(x = -BW/2 + 0.10, y = y + 0.125, label = stage),
            hjust = 0, size = 2.7, colour = P$muted, family = FONT) +
  geom_text(data = f1, aes(x = -BW/2 + 0.10, y = y - 0.115, label = lab_n(n), colour = I(numcol)),
            hjust = 0, size = 4.4, family = FONT, fontface = "bold") +
  geom_segment(data = f1[-n, ], aes(x = 0, xend = 0, y = y - BH/2 - 0.03, yend = y - 0.62),
               colour = P$hair, linewidth = 0.45,
               arrow = arrow(length = unit(4, "pt"), type = "closed")) +
  geom_segment(data = dr, aes(x = 0.03, xend = 0.74, y = yb, yend = yb),
               colour = P$rule, linewidth = 0.4) +
  geom_text(data = dr, aes(x = 0.80, y = yb + 0.09, label = hd),
            hjust = 0, size = 2.6, colour = P$red, family = FONT, fontface = "bold") +
  geom_text(data = dr, aes(x = 0.80, y = yb - 0.07, label = bd),
            hjust = 0, vjust = 1, size = 2.4, colour = P$muted, family = FONT, lineheight = 1.3) +
  scale_x_continuous(limits = c(-0.66, 2.16)) +
  scale_y_continuous(limits = c(0.56, n + 0.44)) +
  theme_diagram()

save_fig("fig1_consort_flow.png",
         stack_hdr("", "Cohort selection",
                   sprintf("From %s phenopackets to the %s-case analytic cohort; exclusions itemised on the right.",
                           lab_n(f1$n[1]), lab_n(f1$n[n])),
                   fig1, h = c(1, 11)),
         w = 7.6, h = 4.7)

# =============================================================================
#  Figure 2 - index-build pipeline
# =============================================================================
top <- data.frame(
  x = 1:4, y = 2,
  lab = c("PMC OA full text", "Section-aware chunking", "Dense + sparse encoding", "Qdrant index"),
  sub = c("genetics-relevance filter\n~2.25M articles",
          "512 tokens, 50 overlap\nPubMedBERT tokeniser",
          "PubMedBERT 768-d\nBM25 sparse",
          "52,777,395 chunks\nHNSW · cosine"),
  end = c(FALSE, FALSE, FALSE, TRUE), stringsAsFactors = FALSE)
bot <- data.frame(
  x = c(3, 4), y = 1,
  lab = c("UUID5 content identifiers", "Hybrid retrieval"),
  sub = c("derived from the chunk text", "RRF, Qdrant default k = 2"),
  end = c(FALSE, TRUE), stringsAsFactors = FALSE)
bx <- rbind(top, bot)
bx$fill   <- ifelse(bx$end, P$orangeF, P$panelF)
bx$accent <- ifelse(bx$end, P$orange,  P$hair)
bx$labcol <- ifelse(bx$end, P$orangeT, P$ink)

BW2 <- 0.86; BH2 <- 0.50
fig2 <- ggplot() +
  geom_tile(data = bx, aes(x = x, y = y, fill = I(fill)), width = BW2, height = BH2, colour = NA) +
  geom_segment(data = bx, aes(x = x - BW2/2, xend = x - BW2/2,
                              y = y - BH2/2, yend = y + BH2/2, colour = I(accent)),
               linewidth = 1.5, lineend = "butt") +
  geom_text(data = bx, aes(x = x - BW2/2 + 0.055, y = y + 0.14, label = lab, colour = I(labcol)),
            hjust = 0, size = 2.7, family = FONT, fontface = "bold") +
  geom_text(data = bx, aes(x = x - BW2/2 + 0.055, y = y - 0.005, label = sub),
            hjust = 0, vjust = 1, size = 2.4, colour = P$muted, family = FONT, lineheight = 1.3) +
  geom_segment(data = top[-4, ], aes(x = x + BW2/2 + 0.02, xend = x + 1 - BW2/2 - 0.05,
                                     y = y, yend = y),
               colour = P$hair, linewidth = 0.45,
               arrow = arrow(length = unit(4, "pt"), type = "closed")) +
  geom_segment(aes(x = 3, xend = 3.70, y = 1 + BH2/2 + 0.02, yend = 2 - BH2/2 - 0.05),
               colour = P$hair, linewidth = 0.45,
               arrow = arrow(length = unit(4, "pt"), type = "closed")) +
  geom_segment(aes(x = 4, xend = 4, y = 2 - BH2/2 - 0.02, yend = 1 + BH2/2 + 0.05),
               colour = P$hair, linewidth = 0.45,
               arrow = arrow(length = unit(4, "pt"), type = "closed")) +
  scale_x_continuous(limits = c(0.50, 4.50)) +
  scale_y_continuous(limits = c(0.68, 2.34)) +
  theme_diagram()

save_fig("fig2_index_pipeline.png",
         stack_hdr("", "Index-build pipeline",
                   "Every stage is version-pinned, so the chunk set and its content-addressed identifiers regenerate from public inputs.",
                   fig2, h = c(1, 7)),
         w = 9.2, h = 3.3)

# =============================================================================
#  Figure 3 - cohort characterisation
# =============================================================================
a <- read.csv(need("fig3a_categories.csv"), stringsAsFactors = FALSE)
a$fill <- ifelse(a$oversampled == 1, P$orangeF, P$greyF)
a$txt  <- ifelse(a$oversampled == 1, P$orangeT, P$greyT)

p3a <- ggplot(a, aes(x = category, y = n)) +
  geom_col(aes(fill = I(fill)), width = 0.56) +
  geom_text(aes(label = n, colour = I(txt)), vjust = -0.65, size = 3.0,
            family = FONT, fontface = "bold") +
  annotate("curve", x = 1.60, xend = 1.86, y = 340, yend = 313, curvature = 0.28,
           colour = P$orange, linewidth = 0.32,
           arrow = arrow(length = unit(3, "pt"), type = "closed")) +
  annotate("text", x = 1.56, y = 344, hjust = 1, vjust = 1,
           label = "oversampled for\nsubgroup precision",
           size = 2.4, colour = P$orange, family = FONT, lineheight = 1.2) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.19))) +
  labs(x = NULL, y = "Cases") + theme_p1()

b <- read.csv(need("fig3b_overlap.csv"), stringsAsFactors = FALSE)
b$stratum <- factor(b$stratum, levels = c("Overlap-present", "Overlap-absent"))
tot <- tapply(b$n, b$stratum, sum)
b1   <- b[b$category == "Developmental", ]
n_pr <- b1$n[b1$stratum == "Overlap-present"]
n_ab <- b1$n[b1$stratum == "Overlap-absent"]

p3b <- ggplot(b, aes(x = category, y = n, fill = stratum)) +
  geom_col(width = 0.56, position = position_stack(reverse = TRUE)) +
  scale_fill_manual(values = c("Overlap-present" = P$greyF, "Overlap-absent" = P$orangeF)) +
  annotate("text", x = 1, y = n_pr / 2,
           label = sprintf("Overlap-present\n%s  (%.1f%%)", lab_n(tot[[1]]), 100 * tot[[1]] / sum(tot)),
           size = 2.5, colour = P$greyT, family = FONT, lineheight = 1.25, fontface = "bold") +
  annotate("text", x = 1, y = n_pr + n_ab / 2,
           label = sprintf("Overlap-absent\n%s  (%.1f%%)", lab_n(tot[[2]]), 100 * tot[[2]] / sum(tot)),
           size = 2.5, colour = P$orangeT, family = FONT, lineheight = 1.25, fontface = "bold") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.06))) +
  labs(x = NULL, y = "Cases") + theme_p1()

cc  <- read.csv(need("fig3c_years.csv"), stringsAsFactors = FALSE)
pre <- sum(cc$n[cc$year < 2020]); post <- sum(cc$n[cc$year >= 2020])
cc$fill <- ifelse(cc$year >= 2020, P$orangeF, P$greyF)

p3c <- ggplot(cc, aes(x = year, y = n)) +
  geom_col(aes(fill = I(fill)), width = 0.76) +
  geom_vline(xintercept = 2019.5, colour = P$red, linetype = "22", linewidth = 0.45) +
  annotate("text", x = 2018.6, y = max(cc$n) * 1.10, hjust = 1, vjust = 1,
           label = sprintf("pre-2020\n%s cases", lab_n(pre)),
           size = 2.45, colour = P$greyT, family = FONT, lineheight = 1.25, fontface = "bold") +
  annotate("text", x = 2020.4, y = max(cc$n) * 1.10, hjust = 0, vjust = 1,
           label = sprintf("post-2020\n%s cases", lab_n(post)),
           size = 2.45, colour = P$orangeT, family = FONT, lineheight = 1.25, fontface = "bold") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.16))) +
  labs(x = NULL, y = "Cases") + theme_p1()

d   <- read.csv(need("fig3d_hpo.csv"), stringsAsFactors = FALSE)
med <- median(rep(d$n_terms, d$n_cases))

p3d <- ggplot(d, aes(x = n_terms, y = n_cases)) +
  geom_col(fill = P$greyF, width = 0.76) +
  geom_vline(xintercept = med, colour = P$red, linetype = "22", linewidth = 0.45) +
  annotate("text", x = med + 1.6, y = max(d$n_cases) * 1.02, hjust = 0, vjust = 1,
           label = sprintf("median %g terms\nrange %g–%g", med, min(d$n_terms), max(d$n_terms)),
           size = 2.45, colour = P$red, family = FONT, lineheight = 1.25) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.12))) +
  labs(x = NULL, y = "Cases") + theme_p1()

fig3 <- (stack_hdr("a", "Disease-category counts",
                   "Four MONDO-derived strata; immunological drawn at a higher rate.", p3a) |
         stack_hdr("b", "Annotation-overlap split",
                   "Whether a case's source publication is cited in phenotype.hpoa.", p3b)) /
        (stack_hdr("c", "Source-publication year",
                   "1988–2025, split at 2020 for the recency stratum.", p3c) |
         stack_hdr("d", "HPO terms per case",
                   "Phenotype-annotation depth across the cohort.", p3d))

save_fig("fig3_cohort_characterisation.png", fig3, w = 9.6, h = 6.9)

# =============================================================================
#  Figure 4 - candidate-list difficulty
# =============================================================================
s4 <- read.csv(need("fig4a_similarity.csv"), stringsAsFactors = FALSE)
s4$variant <- factor(s4$variant, levels = c("Random", "Hard"))
notes <- fromJSON(need("figure_notes.json"))

p4a <- ggplot(s4, aes(x = bma, fill = variant)) +
  geom_histogram(aes(y = after_stat(density)), bins = 64,
                 position = "identity", alpha = 0.92, colour = NA) +
  geom_vline(xintercept = notes$median_causal_bma, colour = P$red,
             linetype = "22", linewidth = 0.45) +
  scale_fill_manual(values = c(Random = P$greyF, Hard = P$orangeF)) +
  annotate("text", x = 0.20, y = 9.2, hjust = 0, vjust = 1,
           label = "Random distractors\nstandard variant",
           size = 2.55, colour = P$greyT, family = FONT, lineheight = 1.25, fontface = "bold") +
  annotate("text", x = 1.66, y = 2.30, hjust = 0, vjust = 1,
           label = "Phenotype-similar\nhard variant",
           size = 2.55, colour = P$orangeT, family = FONT, lineheight = 1.25, fontface = "bold") +
  annotate("text", x = notes$median_causal_bma + 0.12, y = 11.4, hjust = 0, vjust = 1,
           label = sprintf("causal gene\nmedian %.2f", notes$median_causal_bma),
           size = 2.45, colour = P$red, family = FONT, lineheight = 1.25) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05))) +
  coord_cartesian(xlim = c(0, 4.2)) +
  labs(x = "Case-to-gene similarity (Resnik BMA)", y = "Density") + theme_p1()

s4b <- read.csv(need("fig4b_separability.csv"), stringsAsFactors = FALSE)
s4b$variant <- factor(s4b$variant, levels = c("Random", "Hard"))
lim <- ceiling(max(s4b$causal, s4b$hardest))

p4b <- ggplot(s4b, aes(x = hardest, y = causal, colour = variant)) +
  geom_abline(slope = 1, intercept = 0, colour = P$muted, linetype = "22", linewidth = 0.4) +
  geom_point(size = 0.55, alpha = 0.32) +
  scale_colour_manual(values = c(Random = P$grey, Hard = P$orange)) +
  annotate("text", x = 0.12, y = lim - 0.05, hjust = 0, vjust = 1,
           label = sprintf("Random\ndistractor ties or wins\nin %.1f%% of cases", notes$ties_random_pct),
           size = 2.45, colour = P$greyT, family = FONT, lineheight = 1.3, fontface = "bold") +
  annotate("text", x = lim - 0.08, y = 0.36, hjust = 1, vjust = 0,
           label = sprintf("Hard\ndistractor ties or wins\nin %.1f%% of cases", notes$ties_hard_pct),
           size = 2.45, colour = P$orangeT, family = FONT, lineheight = 1.3, fontface = "bold") +
  annotate("text", x = lim - 0.42, y = lim - 0.36, hjust = 1, vjust = 0, angle = 45,
           label = "equal similarity", size = 2.25, colour = P$muted, family = FONT) +
  coord_fixed(xlim = c(0, lim), ylim = c(0, lim)) +
  labs(x = "Hardest distractor similarity (max BMA)", y = "Causal-gene similarity (BMA)") +
  theme_p1(grid_x = TRUE)

fig4 <- stack_hdr("a", "Distractor phenotypic similarity",
                  "Random distractors sit near zero; phenotype-similar ones approach the causal gene.", p4a) |
        stack_hdr("b", "Per-case separability",
                  "Points on or above the diagonal are cases where a distractor ties or wins.", p4b)

save_fig("fig4_hard_vs_random_separability.png", fig4, w = 10.2, h = 4.7)

cat("\nWritten to ", OUT_DIR, "\n", sep = "")
