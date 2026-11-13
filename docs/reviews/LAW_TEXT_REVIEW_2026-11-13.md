# The law's own words: how the texts were read and checked (2026-11-13)

**What this is.** The record behind `backend/apps/library/baseline/provisions/`: where each
text was read, what a script was allowed to do to it, every check that was run and what each
one found. D-142 is the decision; the format and each source's reuse terms are in the
baseline README, "The law's own words".

**Result.** 3,327 provisions in 24 files (3,222 at first, 105 more with the corrections of section 10) give 1,816 of the baseline's 1,894 obligations the
text of the sections, articles and paragraphs they cite: 1,189 in English (688 from EU acts,
501 from the guidelines of EBA, ESMA and EIOPA), 789 in Swedish, 488 in Finnish, 427 in
Danish and 329 in Norwegian, each national text with an English translation and the Danish,
Norwegian and Finnish ones with Swedish beside it (for Finland the authority's own). 78
obligations have no text yet, each with its reason in the file's `withoutProvision`
(section 6).

No text was typed, tidied or shortened by a person or a model. Every emitted text is
compared byte for byte with the extraction or the reviewed translation batch it came from
(6,499 of 6,499 texts identical at the last run), and `check_baseline.py` holds every file
to the format.

## 1. Sources

| Source | Read as | Units read | Provisions in the files |
|---|---|---|---|
| Sweden, statutes and ordinances, `riksdagen.se` | the page's HTML; the government's `rkrattsbaser.gov.se` as second witness | 406 | 406 |
| Sweden, Finansinspektionen's regulations (FFFS), `fi.se` | PDF | 383 | 383 |
| Denmark, `retsinformation.dk` | the official XML | 474 | 427 |
| Norway, Lovdata | the open data packages under NLOD 2.0, never the site's pages | 329 | 329 |
| Finland, Finlex | open data (Akoma Ntoso), the Finnish and the Swedish expression | 328 | 327 |
| Finland, Finanssivalvonta's regulations and guidelines | PDF, Finnish and Swedish | 161 | 161 |
| EU acts, EUR-Lex | HTML: the consolidated version in force where one exists, else the Official Journal text | 695 | 688 |
| EBA, ESMA, EIOPA guidelines | PDF | 505 | 501 |

The difference between the two columns is section 6: 47 Danish sections amended since the
text Retsinformation publishes, one Finnish section whose official Swedish text is not
published yet, seven EU articles whose duty the baseline records under another act, and
four units of EBA/GL/2015/18 whose published wording includes an amendment that does not
apply yet.

## 2. What a script may do to a text

The text is what the source publishes. A script may decode entities, turn non-breaking and
repeated spaces into one space, strip the ends, and nothing else, with these rules, each
found necessary by a check below:

- **A paragraph of the source is a paragraph of the text.** One blank line between
  paragraphs; every list item on its own line with its own marker; a line break the source
  prints inside a paragraph stays (three stand in the middle of a sentence, in SFS 2015:70
  3 § and BEK 1443/2025 § 15, because the official markup has them there).
- **Whitespace between words is never lost**, also across an inline element.
- **A footnote's mark stays where it is printed**, as a superscript, and the footnote's text
  follows the unit's last paragraph. A footnote whose mark sits on the section's number or
  title, outside the body, is kept out of the text (one Norwegian section).
- **The publisher's own markers stay in place and are recorded**: a repealed subsection,
  the amending act a Swedish section ends with, Finlex's note that a part enters into force
  later.
- **A word the source breaks over two lines is written whole**, decided by evidence and
  never by a model's sense of the language: the joined form or the hyphenated form must
  occur unbroken elsewhere in the official texts (18 places in 16 Swedish sections; in the
  PDF sources each join is listed on its unit). A hyphen followed by a space inside one line is kept as
  printed (section 7).
- **A table is never flattened into running text**: a section holding one is not emitted.
- **The wording in force today.** EU acts are read from the consolidated version in force;
  a Danish section a later act amended, where Retsinformation has not consolidated it, is
  held back; a Swedish or Finnish section printed in two wordings gives the one in force. A
  part that a coming act adds, which Finlex prints in the consolidated section with its own
  note, stays in place with that note directly after it (five Finnish sections, entering
  into force between 20 November 2026 and 16 April 2027).

Each source is read by two parsers written separately; a unit is kept only where both give
the same characters. A PDF is read by two libraries (pypdf, pdfminer.six) under the same
rule.

## 3. Web sources: the checks, in order

Every check is a reader who did not write the extraction, finds the section in the cached
official document by its own means, and compares the whole text. A reported difference goes
to a second reader, and a confirmed one is repaired at the rule and the source re-run.

| Check | What was read | Found |
|---|---|---|
| 1. Sample | 50 units of each of the five web sources | Four kinds of fault: paragraphs of one section joined, a space lost between two words across an inline element, a footnote's mark dropped or its text woven into the sentence, the publisher's marker of a repealed part unrecorded. Repair 1, which also found 47 Danish sections amended by a later act that Retsinformation has not consolidated, and sections of two Swedish acts printed without their marker |
| 2. After repair 1 | every unit the repair touched and a fresh sample: 42 Swedish, 51 Danish, 46 Norwegian, 46 Finnish, 156 EU | Sweden, Denmark, Norway, Finland clean. EU: articles had been read as adopted although a later consolidated version is in force; every such act was read again from the version in force, and the text of 76 articles differed |
| 3 and 4. EU again | 175, then 18 units | Clean at the last |
| 5. Translators' doubts | every oddity a translator or second reader noted in an original (35 batches), each settled against the official document: printed so, or an extraction fault | Swedish words left broken at a line wrap, one Swedish table flattened, a Norwegian footnote without its mark, Finnish items that enter into force later dropped without trace. Three Danish places and one Finnish are printed so. Repair 2 |
| 6. After repair 2 | every changed unit and a fresh sample: 30 Swedish, 10 Norwegian, 19 Finnish, 10 Danish | 69 of 69 identical |
| 7. The duty reading (section 5) | every provision, beside its obligation | One Swedish section ran on into the next (SFS 2018:1219 4 kap. 8 §: the page prints "9§" with no marker). Repair 3: the rule now cuts at such a paragraph, confirmed by the second source, over all 7,535 sections of the 60 acts (six places, two of them in cited sections) |
| 8. After repair 3 | the changed unit and seven more | 8 of 8 identical |

## 4. PDF sources

### 4.1 Finansinspektionen (383 units) and Finanssivalvonta (161 units)

1. Two libraries read every unit; both must agree character for character.
2. Line-end hyphens decided by evidence; a word no evidence settles is listed on its unit.
3. A reader compared every unit with the text of its pages, read by its own program.
4. A reader compared every unit with a **picture of the printed page**, which does not
   depend on the PDF's text layer at all.

Result: no difference in either source at the last pass.

### 4.2 EBA, ESMA and EIOPA guidelines (505 units of 27 documents)

Steps 1 and 2 as above. The readers of the page pictures then went through the 471 units
the first extraction gave, and a second reader confirmed 16 differences: one paragraph that
ended before its list (EBA/GL/2020/06 paragraph 158, whose list sits under italic labels),
one point that kept its own number and one unit that held two points (EBA/GL/2015/18), one
false paragraph break at a page break (EBA/GL/2018/05), and wrong heading paths. So none of
it was taken. The extraction was repaired at the rule (among others: an italic label inside
a paragraph belongs to it; a guideline cited whole resolves to its points; a document
printed with its changes showing, ESMA/2016/1478, is read as amended, struck words out and
inserted words in), which made 505 units, and every one was read again:

- against the text of its pages, by a reader with its own program: 505 of 505 identical;
- against a picture of its printed page, each report settled by a second reader: every
  text, every boundary and every nearest heading as printed.

108 units still carry an incomplete `headingPath`, the chain of outer headings (a Title or
a parent section left out). The files hold a unit's text, its reference and its nearest
heading, never that path, so nothing shown depends on it; it must not be used until it is
repaired. 22 units the two readings could not agree on, or that hold a list label or a
character the PDF does not carry as text, are not in the files, and their nine obligations
say so.

## 5. Translations

A glossary per language pair, a translator per batch, a second reader on every batch
("must", never "shall"; nothing added, nothing dropped; the original's paragraphs and
lines). Then:

| Check | Found |
|---|---|
| Numbers: every number of the original must be in the translation, by program | The flagged translations went to a third reader: 17 corrected (mostly the title of an act cut short, in one case a short name expanded), the rest innocent (a date written with the month's name) |
| After each repair of an original | A translation is used only if it was read against the original as it stands. 16 Swedish re-read unchanged; 8 corrected and read by a second reader (new Finnish parts translated, a Norwegian footnote and a Swedish run-on section removed) |
| Shape, by program | 14 translations had joined two lines the original keeps apart; the line breaks were restored and a program proved that nothing but whitespace changed |
| Remarks of the duty readers | Five texts corrected in four provisions (a missing full stop the Danish original itself lacks, "notification" for "anmälan", a third-party provider narrowed to one kind, a list item that did not parse), one left as it was |

Skatteverket's own English for "kontrolluppgift" is "income statement", which the
translations follow; our summaries say "control statement". Left for the owner
(`docs/TODO_FOR_alex.md`).

## 6. Obligations with no text yet (78)

| Reason, as the file states it | Obligations |
|---|---|
| Danish section amended since the text Retsinformation publishes for the act | 41 |
| The baseline records the duty under an amending act; the article is in the act it amends | 9 |
| A guideline's paragraph holds a list label, a character or a table the PDF does not carry as text | 9 |
| The provision holds a formula or a table the source does not publish as plain text | 7 |
| The section could not be cut from the official text with certainty | 4 |
| Cited from two published versions whose wording differs | 3 |
| The cited section is not in the official consolidated text | 2 |
| The citation names a part that is not a numbered section | 1 |
| The authority's own Swedish text of the wording in force is not published yet | 1 |
| The published guideline already includes an amendment that does not apply yet | 1 |

Four more obligations show only part of what they cite, because one cited provision is held
back and the others are not: `obl-dk-forsdist-fair-dealing`,
`obl-dk-skatopsparbek-pool-information`, `obl-dk-skatopsparbek-depot-placement` and
`obl-eu-eba-gl-pog-target-market`. The citation on the obligation names what is missing.

## 7. Kept as printed

A misprint of the authority is not ours to mend. Each was confirmed in the official file's
own characters:

- "kreditværdigheds- vurderingen", "Finans- tilsynet" and "§§ 25- 29" (BEK 1443/2025 §§ 17
  and 28, BEK 1016/2023 § 22), and "ETA- valtiossa" (laki 1021/2012 2 §): a hyphen and a
  space inside one line.
- BEK 1016/2023 § 1 stk. 3 lacks the full stop between two sentences. The translations have
  it.
- Article 92 of Regulation (EU) No 575/2013 carries three invisible direction marks and a
  Greek middle dot inside a formula, as EUR-Lex publishes it.
- §§ 7-3-17 and 7-3-24 of the Norwegian tax administration regulation hold the same words.
- "1§ 2 mom." without a space, in the Swedish text of a Finnish decree.

## 8. The duty reading

Before the files were committed, every obligation with text (1,816) was read beside the
provisions cited under it: does the text carry the duty the summary describes? A second
reader then tried to show that it does for every case the first reader doubted. 1,641
carry it. 175 stood, none overturned:

- **9 contradict the law's words** (a deadline, an actor or a condition stated differently
  in the summary).
- **14 cite only the Norwegian clause that makes an EU regulation Norwegian law**; the
  duty's own words are in the EU article the citation names, which the library holds under
  the EU act.
- **152 are carried in part**: a material element of the summary comes from a provision
  that is not cited. 82 of them are Norwegian sanctions regulations that incorporate an EU
  regulation by reference.

The law texts are not in question in any of them. Each is a correction to propose for the
obligation, through the proposal door: `docs/reviews/law-text-2026-11-13/duty-reading.json`
lists every one with the words at issue and what to do.

By program, over the 2,917 pairs of a provision of a law and an obligation that names it:
the obligation's own citation names the provision's section in every pair. The guidelines
are cited more loosely (a whole section, a range of points), so their 504 pairs were read
by the duty readers instead.

## 9. Where the tooling is

The fetchers, parsers, checkers, the converter that wrote the files, the reviewed
translation batches and the cached official documents are not in this repository. They were
copied on 2026-11-13 to `C:\Users\Alex\projects\grc-law-tooling` on the owner's machine,
with a README (`docs/TODO_FOR_alex.md`). Every text names the page it was read from in
`source`, so any one of them can be checked against the authority without the tooling.

## 10. The corrections (2026-11-13, D-144)

The owner said to correct the 175 findings of section 8 ("go ahead and fix it, u dont need
my approval to get things right"). The door gained what a correction needs: a new version of
an obligation may replace its title, its citation and the provisions it cites, with before
and after in the audit row. The corrections are `backend/apps/library/baseline/corrections/`,
one file per tranche, filed by the baseline agent and approved in the queue.

| | |
|---|---|
| Corrections | 168: 158 findings and 10 that say "income statement", Skatteverket's own English for kontrolluppgift |
| New provisions | 105, made by the same tooling from the same official documents, two readings agreeing; 58 of them the EU regulations' articles as the Norwegian sanctions regulations print them in their annexes, 2 GDPR articles as personopplysningsloven prints them |
| Left as they are | 17, below |

Five groups (Norwegian sanctions, other Norwegian law, Swedish, Danish and Finnish, EU) each
decided their findings from the law text: a summary that said something the law does not is
rewritten; an element from a section not cited is cited, its text extracted where the library
lacked it; an element from another act is named in words, since the door ties a provision only
to duties of its own instrument. Translations of new texts were written sense for sense and
read by a second reader, numbers cross-checked by program. Then an independent reader per
group tried to prove each correction and each new text wrong, re-cutting the texts with
scripts of its own: 11 of 273 were (an EEA derogation left out, a CRS exception too wide, a
Danish consumer scope dropped, a Finnish narrowing from 20 November 2026 not named, a Russia
reporting duty without its limits, the Guinea title too wide, an ESMA date resting on a list
rather than the law, five Norwegian source lines without a date), and all were corrected.

Left as they are, each for the reason given: the eleven Norwegian duties under the DORA,
crypto-assets, PRIIPs, SFDR and securities trading acts, which do not print the EU text (each
summary was checked against the EU article it names); `obl-no-vpsf-account-register-details`
(its responsibility is in another act, which the summary names);
`obl-dk-skatopsparbek-depot-placement` and `obl-dk-skatopsparbek-pool-information` (the
sections holding the missing elements were amended without a consolidated text; both
summaries already state the amended rules); `obl-eu-emir-clearing-threshold` (the summary
names Regulation (EU) 2024/2987, whose Article 5 bears it out).

Two repairs of existing texts came with it: 29 Swedish source lines that read "amended up to
." now say "text as issued, no amendment recorded", and § 5 of BEK 1557/2024 lost the chapter
heading that BEK 1637/2024 repealed. Wordings that change on a known day (20 November 2026, 11
and 30 January 2027) are listed in `docs/TODO_FOR_alex.md`; nothing files them yet.
