"""Genre profiles: how deep to research and how to write for each target format.

A profile controls both halves of the pipeline. Research depth (sub-questions, rounds, source budget) is
scaled to what the format can use: a LinkedIn post cites two sources, a paper needs dozens.
"""
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

Genre = Literal["paper", "blog", "linkedin"]
GENRES: tuple[Genre, ...] = ("paper", "blog", "linkedin")


@dataclass(frozen=True)
class GenreProfile:
    name: Genre
    label: str
    # Research
    sub_questions: tuple[int, int]
    queries_per_question: int
    results_per_query: int
    max_rounds: int
    max_sources: int
    # Writing
    target_words: tuple[int, int]
    max_figures: int
    sectioned: bool
    citation_style: Literal["numbered", "links"]
    references_heading: str
    guide: str


PAPER_GUIDE = """\
You are writing a rigorous academic-style paper (survey / position / technical analysis), the kind a
reviewer at a good venue would accept as well-argued and well-sourced.

Structure (adapt section titles to the topic; keep this order):
- Title, then an **Abstract** (150-250 words: context, gap, what this paper does, key findings, implication).
- 1. Introduction: motivation, problem statement, explicit list of contributions, roadmap.
- 2. Background and Related Work: define terms precisely; group prior work by approach and compare.
- 3-5. Core analysis sections: the substance. Taxonomies, mechanisms, quantitative comparisons, trade-offs.
  Use tables to compare approaches across consistent dimensions. Use numbered equations only when they add rigor.
- Discussion: implications, open problems, threats to validity / limitations of the evidence.
- Conclusion: answer the research questions directly; future work.

Voice and rigor:
- Formal, precise, third person. Every non-trivial factual claim carries a citation.
- Report numbers with their conditions (dataset, setup, date). Distinguish measured results from vendor claims.
- Hedge proportionally to evidence ("suggests", "reported", "in the authors' benchmark"). Never overstate.
- Compare, do not just list: for every pair of approaches say where each wins and why.
- Number figures and tables ("Figure 1", "Table 1") and refer to them in the text.
"""

BLOG_GUIDE = """\
You are writing an expert technical blog post (Medium / dev.to / company engineering blog quality) for
practitioners with 1-5 years of experience who want to understand *and apply* the topic.

Structure:
- A specific, benefit-driven title. An opening hook (a concrete problem, number or scenario, 2-4 sentences).
- **TL;DR** box: 3-5 bullets with the key takeaways.
- Body sections with descriptive H2 headings that read as a story: why it matters, how it works
  (mechanism, with a diagram when architecture is involved), how to use it (steps, code or config when the
  evidence supports it), trade-offs and pitfalls, when not to use it.
- A comparison table when two or more options are discussed.
- Conclusion with concrete next steps. Then references.

Voice:
- Confident, clear, conversational but precise. Second person is fine. Short paragraphs (2-4 sentences).
- Explain the "why" behind every "how". Use one concrete example per abstract idea.
- Cite facts inline. Prefer official docs and primary sources; flag anything speculative.
- No filler intros ("In today's fast-paced world"), no generic conclusions.
"""

LINKEDIN_GUIDE = """\
You are writing a LinkedIn post for technical professionals. It must be worth stopping the scroll for:
one sharp insight backed by research, not a summary of everything found.

Structure:
- Title line: one emoji + a title that names the technical keyword.
- 1-2 sentence context, then why it matters (the problem or the shift).
- 3-5 sections, each "emoji + keyword heading", with short paragraphs or bullets in the form
  "**keyword**: explanation".
- Close with a takeaway or a question that invites discussion, then 1-3 source links, then 3-5 hashtags.

Voice:
- Humble, confident, educational. No hype, no self-promotion, no clickbait.
- One idea per sentence. Plain punctuation. No emoji inside sentences.
- Concrete numbers from the research beat adjectives.
- Length: about 1,300-2,200 characters per language section.
"""

PROFILES: dict[Genre, GenreProfile] = {
    "paper": GenreProfile(
        name="paper", label="논문", sub_questions=(6, 8), queries_per_question=3, results_per_query=6,
        max_rounds=3, max_sources=60, target_words=(5000, 8000), max_figures=3, sectioned=True,
        citation_style="numbered", references_heading="References", guide=PAPER_GUIDE,
    ),
    "blog": GenreProfile(
        name="blog", label="블로그", sub_questions=(4, 6), queries_per_question=2, results_per_query=6,
        max_rounds=2, max_sources=40, target_words=(2200, 3800), max_figures=2, sectioned=True,
        citation_style="numbered", references_heading="References", guide=BLOG_GUIDE,
    ),
    "linkedin": GenreProfile(
        name="linkedin", label="LinkedIn", sub_questions=(2, 3), queries_per_question=2, results_per_query=5,
        max_rounds=1, max_sources=16, target_words=(250, 450), max_figures=1, sectioned=False,
        citation_style="links", references_heading="", guide=LINKEDIN_GUIDE,
    ),
}


def _external_style_guide(genre: Genre) -> str | None:
    """The owner's own style guides (Claude Code skills) take precedence over the built-in voice notes."""
    if genre != "linkedin":
        return None
    path = os.getenv("LINKEDIN_STYLE_GUIDE_PATH") or str(
        Path.home() / ".claude/skills/linkedin-writer/references/style-guide.md"
    )
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def get_profile(genre: str) -> GenreProfile:
    if genre not in PROFILES:
        raise ValueError(f"Unknown research genre '{genre}'. Use one of {', '.join(GENRES)}.")
    return PROFILES[genre]  # type: ignore[index]


def style_guide(genre: Genre) -> str:
    profile = get_profile(genre)
    external = _external_style_guide(genre)
    if external:
        return f"{profile.guide}\n<author-style-guide>\n{external}\n</author-style-guide>"
    return profile.guide
