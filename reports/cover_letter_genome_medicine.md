# Cover letter — Genome Medicine submission

*Render as PDF on Universidad Europea letterhead (or a plain
letterhead with UE address block); submit via the Genome Medicine
portal at the "cover letter" step. Replace bracketed placeholders
before submission.*

---

**Johanna Angulo**
PhD Candidate
Universidad Europea, Madrid, Spain
johanna.angulo@gmail.com
[phone number]

[Date of submission]

**The Editor-in-Chief**
*Genome Medicine*
BMC, Springer Nature
genomemedicine@biomedcentral.com

---

**Subject:** Submission of original Research Article — *"Literature-only
multi-agent retrieval-augmented LLM gene prioritisation for rare
disease: development, annotation-overlap-deconfounded evaluation, and
frontier-LLM ablation on 1,047 cases"*

---

Dear Editor,

I am pleased to submit the enclosed original research article for
consideration as a **Research Article** in *Genome Medicine*. The
manuscript reports the development and rigorous evaluation of
**geno_agent**, a literature-only, locally-deployable multi-agent
retrieval-augmented LLM system for rare-disease gene prioritisation,
benchmarked against the curated reference tools **Exomiser** and
**LIRICAL** on a stratified cohort of 1,047 cases drawn from the
GA4GH Phenopacket Store v0.1.26 release.

**Fit with the journal's scope.** *Genome Medicine* explicitly covers
computational and translational genomics, methods for the diagnosis
and management of human disease, and emerging applications of large
language models in clinical genetics. Our contribution lies at the
intersection of three of the journal's priority themes —
(i) rare-disease genomics, (ii) computational phenotype-driven
prioritisation, and (iii) clinically-grounded evaluation of LLM
systems in medicine — and we believe it will be of broad interest to
the journal's clinical-genetics and computational-genomics readership.

**Principal scientific contributions.**

1. **A methodological deconfounding result of immediate relevance to
   the field.** We show that the apparent dominance of LIRICAL on
   standard rare-disease benchmarks (top-1 = 0.924 on the full
   cohort) is largely an artefact of annotation-overlap between the
   benchmark's source publications and LIRICAL's curated
   `phenotype.hpoa` table. On the **annotation-overlap-absent fair-
   comparison cohort (n = 282)**, LIRICAL collapses to 0.777 and
   **geno_agent becomes the top-ranked system at 0.858**, beating
   LIRICAL by +0.082 (★) and Exomiser by +0.078 (★) — both
   statistically significant under paired bootstrap with McNemar.
   To our knowledge this is the first fully-deconfounded,
   paired-bootstrap, 1,047-case comparison of literature-only versus
   curated rare-disease prioritisation systems.

2. **Recency robustness as a clinical-deployment property.** On cases
   whose source publications appeared after 2020, Exomiser's top-1
   drops **37 percentage points** while geno_agent's advantage is
   2.7× larger on this recent-publication subset — a structurally
   relevant gap as the rare-disease publication cadence accelerates.

3. **Faithfulness as a deployable clinical-triage signal.**
   Independent GPT-4o-judged RAGAS and DeepEval evaluations show a
   **33–39 percentage-point gap in top-1 correctness** between high-
   and low-grounding cases, supporting an audit-traceable deployment
   pattern in which low-faithfulness predictions are automatically
   routed to clinician review.

4. **LLM-family robustness.** Replaying the LEA prompts against three
   frontier LLMs (Qwen3-32B, Claude Sonnet 4.6, DeepSeek-V3) on an
   n = 300 sub-sample converges within 2.4 percentage points on the
   fair cohort, indicating the headline result is not an artefact of
   the production model choice.

5. **All-local deployment** on a single workstation, with no cloud
   LLM API at inference time — addressing institutional PHI-safety
   constraints that preclude cloud-based agentic systems for rare-
   disease consultation.

**Timeliness.** With the recent publication of DeepRare (Zhao W.
*et al.*, *Nature*, 2026), the field is rapidly converging on
agentic-LLM rare-disease diagnosis. Our manuscript contributes the
complementary literature-only, locally-deployable axis of this
landscape together with the deconfounding methodology that we believe
should become standard for any benchmark in this area going forward.

**Methodological rigour and reporting.** The manuscript is reported
per the **TRIPOD-LLM** guideline (Gallifant *et al.*, *Nature
Medicine*, 2025); a 39-item compliance checklist is supplied as
Supplementary Table 1, with 38 of 39 applicable items fully addressed
in the manuscript prose. The full evaluation pipeline — deterministic
seeds, pinned ontology versions, UUID5 chunk identifiers, paired-
bootstrap 95 % confidence intervals, and McNemar significance tests —
is publicly available at `github.com/Jangulo7/geno_agent` under an
open licence, with bit-perfect reproducibility verified across re-
runs (top-1 flip rate ≤ 1 / 1,047 on Cell S).

**Standard submission declarations.**

- *Originality.* This manuscript has not been published elsewhere and
  is not under simultaneous consideration by any other journal.
- *Authorship.* All listed authors have read and approved the
  submitted version, contributed to its preparation per the CRediT
  statement included in the Declarations section, and consent to its
  publication.
- *Ethics.* The study used only de-identified, previously-published
  phenotypic data from the GA4GH Phenopacket Store public release;
  no new patient data were collected and no identifiable patient
  information was processed at any stage. A confirmation letter from
  the Universidad Europea Research Ethics Committee confirming that
  this work is exempt from prospective ethics-committee review is
  provided as Supplementary File 2.
- *Funding.* No external grant funding supported this work. All
  computational infrastructure and the modest evaluation-time cloud
  API spend (~$120 total, for the GPT-4o judges and the OpenRouter
  LLM-family ablation) were borne by the first author.
- *Competing interests.* The authors declare no competing financial
  or non-financial interests.
- *Data and code availability.* All source code, per-case evaluation
  sidecars (n = 1,047 + n = 300 ablation), aggregated paired-Δ JSONs,
  TRIPOD-LLM compliance materials, and the rendered tables and
  figures are publicly hosted at `github.com/Jangulo7/geno_agent`. A
  Zenodo deposition of the frozen 4.2-million-chunk Qdrant index used
  for the reported evaluation will be referenced by DOI in the
  Declarations at the proof stage.

**Suggested reviewers** (none has been involved in this work; please
verify the editorial office's reviewer-selection policy):

1. **[Reviewer 1]** — *expertise:* Exomiser, phenotype-driven
   prioritisation; *rationale:* leading authority on the principal
   curated comparator. *Suggested candidate, pending confirmation:*
   Damian Smedley group, Queen Mary University of London.

2. **[Reviewer 2]** — *expertise:* TRIPOD-LLM, LLM evaluation in
   clinical settings; *rationale:* lead author of the reporting
   guideline against which the manuscript is verified. *Suggested
   candidate, pending confirmation:* Jacob Gallifant, Massachusetts
   Institute of Technology / Beth Israel Deaconess.

3. **[Reviewer 3]** — *expertise:* machine learning for biomedicine,
   knowledge-graph-augmented systems; *rationale:* methodological
   peer for the multi-agent RAG architecture. *Suggested candidate,
   pending confirmation:* Marinka Zitnik, Harvard Medical School.

4. **[Reviewer 4]** — *expertise:* practising clinical geneticist
   with rare-disease diagnostic-odyssey experience; *rationale:*
   evaluates the clinical-deployment claims. *Candidate to be
   suggested by the UE PhD supervisor.*

**Suggested non-reviewers / conflicts of interest.** [To be completed
by the corresponding author if any specific exclusions apply.]

I look forward to the reviewers' comments and to the opportunity to
contribute this work to *Genome Medicine*. Please direct any
correspondence regarding this submission to me at the address above.

Yours sincerely,

[Handwritten signature]

**Johanna Angulo**
PhD Candidate, Universidad Europea
Madrid, Spain
On behalf of all authors

---

*Cover letter — 2026-05-24. To be rendered as PDF on Universidad
Europea letterhead and uploaded at the Genome Medicine portal's
"cover letter" step. Length: ~750 words; ~1.5 pages at standard PDF
margins.*
