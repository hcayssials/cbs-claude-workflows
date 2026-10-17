---
name: master-takeaways
description: Create or update a "Master Takeaways_[Class Name].md" summary for one of the user's MBA classes, built from the materials in that class's folder (lecture transcripts, slides, syllabus, cases). Use whenever the user asks to summarize a class, build or refresh a class summary, fold new lecture transcripts or slides into a summary, prep a study document for finals, or says "update the takeaways for X", "add this week's transcripts to X" or "make a master doc for X". Do NOT use for individual assignments, essays or exam cheat sheets.
---

# Master Takeaways: one living summary doc per class

## Purpose

Each class gets exactly one Markdown file, `Master Takeaways_[Class Name].md`, in that
class's folder. It is a teaching document, not a filing cabinet: someone who never took
the class should be able to read it and understand the ideas. It is also a living
document. Classes accumulate material (above all, lecture transcripts), so the doc must
be easy to update incrementally and easy to scan during finals.

When a class has only slides and a syllabus, use the same structure at whatever depth the
sources support, and say so plainly in the Coverage section rather than padding.

**One current version.** Update the doc in place. Never leave `_v2`, `_Update` or dated
copies beside it; if the user wants the old one kept, move it into an `Archive/` subfolder.

## Where the material is

If the folder was set up with `coursework` (see the coursework-sync skill), expect:

- `Transcripts/S07 Transcript.txt`: plain text, one file per recorded class. These exist
  only to be read by you, so their size in tokens is what matters. Read them all before
  writing, and if a whole course won't fit, summarise session by session first.
- `Canvas_Assignments.md`: every assignment description.
- `Readings/S03 ….pdf`: readings, prefixed with the session they're assigned to.
- The professor's own folders (slides, cases, syllabus).

## Source priority

Ground every claim in course materials. When sources conflict, prefer the higher-ranked one:

1. **Lecture transcripts**: the professor's actual framing, examples and emphasis. This
   is what lifts the doc from "textbook summary" to "what this class actually taught".
2. **The user's own study guides and notes**: already-distilled course content.
3. **Syllabus / course-at-a-glance**: the course arc, session topics, stated objectives.
4. **Lecture slides and session notes**: concept coverage, formulas, examples.
5. **Cases, problem sets, worked solutions**: raw material for worked examples.

Don't invent content the materials can't support. A thin class gets a shorter doc with
honest gaps, not filler.

## Document structure

Use these exact top-level headers in this order for every class, so docs stay comparable
across classes. The subsections within them can vary.

```markdown
# Master Takeaways — [Class Name]

> **Course:** [code, professor, term, format] · **Last updated:** [date] · **Coverage:** [one line, e.g. "syllabus + slides; no transcripts yet"]

## 1. What This Class Is About
## 2. The Big Ideas
## 3. Concepts, Explained
## 4. Cases & Applications
## 5. Exams & Assignments (brief)
## 6. Coverage, Gaps & Update Log
```

**1. What This Class Is About**: 2–4 paragraphs covering the question the course answers,
how it's structured (cases, lecture or hands-on) and the arc from first session to last.
A stranger should be oriented in one minute.

**2. The Big Ideas**: the 3–7 frameworks or themes the professor keeps returning to,
each with a short bold name and a plain-language paragraph. This is the finals-week skim
target: reading only this section should recover the spine of the course.

**3. Concepts, Explained**: the body. Organise by module or session cluster, following
how the class actually ran (check the syllabus). For each concept:
- Explain it **from scratch, in plain language**. Introduce jargon only after the idea is
  clear, then give the technical term in parentheses.
- Include a **worked example** wherever the concept is quantitative or mechanical: real
  numbers, step by step, ideally from a class exercise, case or problem set.
- Where the professor frames something distinctively (visible in transcripts), keep that
  framing. It's what makes the doc about *this class* rather than a textbook.

**4. Cases & Applications**: each case in 2–5 sentences: the decision it posed, the
takeaway, and which Big Idea it illustrates. For non-case classes, use this section for
projects instead. If a class has neither, write "Not applicable — lecture/problem-set course."

**5. Exams & Assignments (brief)**: a few sentences on what the assessments covered
*conceptually*. No deadlines, no grading breakdowns, no logistics.

**6. Coverage, Gaps & Update Log**:
- **Sources used:** the actual files this version drew on.
- **Known gaps:** what's missing and what would improve it.
- **Update log:** one line per revision: `YYYY-MM-DD — added S05–S07 transcripts; rewrote §3.2.`

## Updating incrementally

0. **Check what file names mean before trusting them.** Recordings are sometimes numbered
   by class *day*, not course session (one day can cover two sessions), and a recording
   can be split into parts where one part is a break or a mic left running. Map each
   transcript to course sessions against the syllabus or calendar, and label the doc by
   *course* session so it lines up with slides.
1. Read the new material and identify which sections it touches. Transcripts mostly deepen
   §2 and §3 and sharpen §4.
2. Edit in place, revising the affected subsections. Never append a "new stuff" section:
   the doc should always read as one coherent pass.
3. Keep anything the new source doesn't contradict. Where the transcript shows the
   professor emphasised something differently from the slides, follow the transcript.
4. Update **Last updated** and **Coverage** in the header, and add an Update Log line.
5. If the class was flagged as thin, check whether the gap note in §6 can be softened.

## Style rules

- Plain language first: "the slowest step sets the pace of the whole process", then
  name the term (bottleneck).
- Worked examples use concrete numbers, show the arithmetic and name their source
  ("from the Aroma case: …").
- Prose over bullet walls in §1–§3; bullets are fine in §4–§6.
- Keep formulas minimal, each followed by a sentence saying what it *means*.
- Length: a transcript-rich class runs 3,000–6,000 words, a slides-only class 1,500–3,000.
  Don't pad thin classes.
- Never include grades, scores or personal performance data.
- **Off-the-record sessions stay off the record.** If a course says guest sessions are
  confidential, don't attribute statements to named guests in anything meant to be shared.
