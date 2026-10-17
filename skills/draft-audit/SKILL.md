---
name: draft-audit
description: "Audit a finished draft for internal consistency, source integrity, and machine-sounding register before it is submitted or sent. Use when the user asks to review, check, proofread, fact-check, sanity-check, or \"have a look through\" any substantial document: academic papers, group deliverables, reports, memos, decks. Also use when they paste someone else's comments on a draft and want them adjudicated. Do NOT use for drafting or rewriting from scratch, or for building a class summary (master-takeaways)."
---

# Draft Audit

Auditing a finished document. The job is to find what is wrong, rank it by what it costs, and be right about it. Not to rewrite, and not to be impressive.

---

## Before commenting on anything

Read the whole artifact first, including the parts that are not prose:

- The body text
- Every figure and image (open them, do not infer from the caption)
- Every table, including appendix tables and any data table
- The appendices, especially any process log or methodology note
- The brief, template, rubric or assignment spec if one exists
- Any sibling files in the folder: prior versions, handoff notes, checklists

Half the real findings live in the gap between two of these, not inside any one of them.

---

## The four checks

### 1. Internal consistency

This is where the highest-value findings come from. Work through it mechanically.

- **Every number appears more than once.** Find every mention of each figure, in prose, figures, tables, appendices and sibling files, and confirm they agree. Disagreement between a table and the sentence describing it is the single most common defect.
- **Count, do not trust the prose.** If the text says "only four of thirteen," open the figure and count. Enumerations in prose drift when the figure is edited.
- **Do the arithmetic.** If a total is broken into components, add them. State the gap if they do not sum, and check whether the gap is the source's or the author's.
- **Figures against text.** Does the figure show what the surrounding text claims it shows? Does a claim about "the only X" survive looking at the figure?
- **Cross-references.** Does "Section 5.3" point at what it says it does? After any renumbering, re-check every internal reference.
- **Contents page against reality.** Section numbers, and page numbers if they are hardcoded. Any edit to the body invalidates hardcoded page numbers.
- **Body against appendix.** A process log or methodology note that documents a decision the body no longer follows is a serious inconsistency, because it is self-inflicted evidence.
- **Terminology and locale.** A term defined one way and used another. British versus American spelling, especially where a category label disagrees with the body around it.
- **Stated rules against actual practice.** If the document states a rule about itself ("every figure traces to a source below", "we give a range where sources disagree", "no shortened links"), test the rule against the document. Documents that publish their own standards are graded against them.

### 2. Sources

For every entry in the bibliography or reference list:

- Does the URL resolve? Fetch it.
- Does the source actually support the claim cited to it, including the specific number, date and framing?
- Is it cited anywhere in the body, or is it an orphan?
- Are the citation details right: volume, pages, dates, official titles, and the source's own internal numbering (an author's numbered framework must use the author's numbers, not renumbered ones)
- Does any source named in a table or figure lack a bibliography entry?
- Is any link a bare homepage where a deep link to the actual document is possible?

On orphans: recommend attaching each to the sentence it already supports, not deleting it. An uncited source doing intellectual work in the argument is an attribution gap, not surplus.

### 3. Register

Count, do not assert. Numbers make the finding actionable and stop it reading as taste.

- **Punchline rate.** Proportion of paragraphs ending on a short sentence that restates rather than advances. Above roughly a quarter reads as machine-written. Test: read only the last sentence of each paragraph in a section and see whether it scans as a list of aphorisms.
- **Connective tics.** Count "rather than", "not X but Y", "it is not A, it is B".
- **Self-grading sentences.** Sentences telling the reader the document has been rigorous rather than being rigorous. The test is whether the sentence admits a cost or advertises a virtue. Admissions stay; advertisements go.
- **Repetition.** Findings stated three or four times in near-identical words across summary, body and conclusion.

### 4. Requirements

Against the brief, template or house rules: every required element present, formatting rules met (page numbering, filename protocol, length limits, citation style), and the grading weights noted, so that recommendations can be ranked by what they actually cost.

---

## Rules of engagement

These matter more than the checklist.

**Verify before flagging.** Never assert a factual or sourcing error on the strength of a search summary, a snippet, or memory. Fetch the primary source and read the relevant passage. A search summary paraphrasing an article is not the article, and it will sometimes say the opposite. If a source cannot be fetched, report the check as unresolved rather than guessing.

**Retract loudly.** If a later check contradicts an earlier flag, lead the next response with the retraction, state what the source actually says, and withdraw the item. Never let a wrong flag quietly disappear, and never leave it standing.

**Correct your own overstatements.** Do not characterise the size or thinness of a section without opening it. If you already did, open it and say plainly that you were wrong.

**Separate confirmed from suspected.** Say which findings were verified against a source and which are judgment.

**Rank by severity and cost.** Lead with what is most likely to be noticed and cheapest to fix. Give a suggested order of work and say where to stop if time is short.

**Always include what not to change.** Tie it to what the work is actually judged on. Cutting is not automatically improvement, and a reviewer who only subtracts is not doing the job.

**Do not edit unless asked.** When asked: back up the original first, make only the changes agreed, verify every edit site for orphaned punctuation and broken sentences, and re-render to confirm nothing shifted downstream. Report what moved.

**Do not pad.** If a check comes back clean, say so in one line and move on.

---

## Output shape

- One line on the headline finding
- Findings in severity order, each with the evidence that supports it rather than the assertion alone
- Explicit separation of confirmed from suspected
- A short "do not change" list
- A suggested order of work with a stopping point
- A Sources section listing anything fetched live

Give exact locations. "Section 4.2, third paragraph, the sentence beginning X" is usable; "the stablecoin section" is not.

