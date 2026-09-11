# How we write

Nightcord Lab house style. It covers everything with words in it: docs, READMEs, commit
messages, issue text, code comments, reports, chat replies. NIG-93 is the reason this file
exists.

## The bar

Write like one person explaining something to one reader who is short on time.

If a sentence could sit unchanged in any other company's docs, it isn't saying anything.
Cut it or make it specific.

## The tells

These are what make text read as machine output. Cut them.

- **Tricolons.** "fast, reliable, and scalable." Three adjectives in a row is a drumbeat. Use
  one, or use a number.
- **The "not just X, it's Y" frame.** Also "more than a X — it's a Y." Nobody talks like
  that. Say the thing.
- **Em-dashes as default punctuation.** One or two a page is fine. One per sentence is a tic.
- **Sentence-initial scaffolding.** Moreover, Furthermore, Additionally, That said, It's worth
  noting that, In conclusion. Start the sentence instead.
- **Abstract nouns where a verb belongs.** utilize → use. facilitate → help. leverage → use.
  implement → build, write, add.
- **Stacked hedges.** "may potentially help to improve." Pick one.
- **Uniform paragraphs.** Every paragraph four sentences, every section three paragraphs. Let
  something run long because the idea needed it, and let the next thing be one line.
- **Bold on every key term.** It stops meaning anything. Bold the one thing per section a
  skimmer must not miss.
- **Headers over two-line sections.** That's a paragraph, not a section.
- **Emoji headers, "Let's dive in," "In today's landscape."** No.
- **A conclusion that restates the intro.** You already said it. Stop.
- **Perfect parallelism everywhere.** Real writing is lumpy.

## What to do instead

- **Vary sentence length on purpose.** A three-word sentence after a forty-word one. This
  single habit does more than everything else on this list.
- **Use contractions.** We're, don't, it's, won't.
- **Start with And, But, So.** Sometimes.
- **Be specific.** Name the file, the issue, the number, the date. "We lost two days to the
  nginx proxy in NIG-94" beats "we encountered challenges."
- **Have an opinion.** "This is the wrong tradeoff, here's why" is worth more than a balanced
  list of considerations.
- **Say what you don't know.** "I haven't tested this on the GPU box" is something the reader
  can act on.
- **Use parentheses for asides.** (We tried this in August. It didn't work.)
- **Write the first sentence last.** If you can't find the point, the paragraph hasn't got one.

## Code comments

- Comments say **why**. The code already says what.
- No banner dividers, no restating the function signature, no narration of the obvious.
  `// increment i` is noise.
- Match the file. A file full of lowercase fragments doesn't want full sentences with periods.
- If the explanation needs a paragraph, either the function is too big or it belongs in
  `docs/`.
- Delete stale comments. A wrong comment is worse than no comment.
- Most functions don't need one. Don't comment for coverage.

## Commit messages

Subject in the imperative, under ~70 characters, saying what changed — not that work
happened. Body explains why when why isn't obvious. No "This commit…".

Commit under your own agent identity, per the identity rule in your instructions. Never a
generic placeholder.

## Scope

**Behavior does not change.** This is prose, comments, and commit identity. No logic, no
config values, no API contracts, no test expectations. If a "humanizing" edit would change
what the code does, it's out of scope — stop and flag it.

**Don't rewrite what already reads fine.** The job is to find text carrying the tells above
and fix it. A doc that already sounds like a person wrote it is done; leave it alone. This is
what keeps the work from being a 25,000-line full-repo rewrite.

**Order of work.** Client-facing prose first (README, public docs, wiki). Then internal docs
and `CLAUDE.md`. Then inline comments last.

**Skip.** Vendored and generated trees (`node_modules`, `.venv`, `site-packages`, `.pytest_cache`),
third-party licenses, and old `CHANGELOG` entries — history stays as it happened.

**Excluded: AI Portal.** Anything belonging to the AI Portal project stays as it is.

**Required disclosure wins.** Where a contract, license, or regulation requires attribution
or an AI-use disclosure, it stays. Style never overrides a legal or contractual obligation.
If you hit one, flag it rather than deciding alone.

## Before you commit

1. Would a person say this out loud this way? If not, rewrite it.
2. Any tell from the list above still in there?
3. Did I change any behavior? If yes, revert that part.
4. Does the surrounding code keep its own voice?
