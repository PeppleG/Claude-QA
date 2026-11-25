# Compliance and Verification Summary: GET307 Group 8 TSP Report

Kept separate from the academic report, as requested.

## Document facts (checked in the exported PDF)
| Item | Result |
|---|---|
| Main report page count | **10 pages** (pages 1 to 10, references included) |
| Appendix page count | 10 pages (pages 11 to 20) |
| Page size and layout | A4 portrait, single column, 2.54 cm margins, page numbers bottom centre |
| Fonts | Times New Roman: body and all table text 11 pt, title 16 pt bold, headings 12 pt / 11 pt bold |
| Abstract | 215 words |
| References | 14 (APA 7, alphabetical, hanging indent); every entry is cited and every citation has an entry |
| Figures | 4 in main report, 3 in appendix (A.1 to A.3) |
| Tables | 5 in main report, 9 in appendix (A.1 to A.9); all editable Word tables |
| Equations | 10 numbered, editable Word (OMML) equations |
| Seven discussion questions | All answered (Sections 7.1 to 7.7), plus 7.8 interpretation |
| Em dashes | None |

## Notebook verification
- Every code cell and saved output in TSP_Group_8.ipynb was inspected.
- The notebook code was re-executed unmodified. It reproduced **exactly** all quick-test values, all 50 final distances (best, mean, SD, median and worst to 6 decimal places), the Friedman and Wilcoxon/Holm outputs, the threshold table and all 30 sensitivity means.
- Run-level tables (A.4, A.5, A.7) and all figures were regenerated from these reproduced data, which match the recorded outputs.
- Verified: 20,000 evaluations in each of 50 runs (1,000,000 total); 90 sensitivity runs at 2,000 evaluations (180,000 total); seeds 10, 101 to 110 and 301 to 303; nearest-neighbour baseline 583.160 and threshold 699.792; sample SD (ddof = 1); 10 pairwise tests with correct Holm correction; *xi* unused in ACO.

## Unresolved or corrected numerical discrepancies
1. **Runtimes (corrected in the report).** The brief's runtimes (ACO 23.04 s, GA 2.66 s, SA 0.59 s, TS 0.58 s, PSO 0.58 s) appear only in the markdown of notebook cell 42. The recorded output of cell 32 gives **ACO 98.98 s, GA 10.32 s, SA 3.23 s, TS 3.39 s, PSO 3.50 s**, consistent with the 1,194.23 s total in cell 41. The report uses the recorded values, so the ACO/TS ratio is **about 29×, not 40×**. The brief's numbers look like a run on a faster machine (our re-execution gave ACO 18.22 s, TS 0.54 s). **The group should confirm which run they intend to report.**
2. Cell 42's "Question 3" table is labelled as sensitivity but contains final-comparison values. It was not used.
3. The TS docstring says it remembers complete routes, but the code stores the swapped city pair. The report describes the actual behaviour.
4. Evidence map: the threshold results are in cell 39 (not 34) and the runtimes in cells 32 and 41 (not 39). The correct cells are cited.

## Missing environment information
- The commercial processor model name was not recorded (only "Intel64 Family 6 Model 142 Stepping 12"). The notebook front-end (Jupyter or Colab) was not recorded either; the metadata mentions Colab, but the OS output shows Windows 11.

## Items requiring the group's action before submission
- **Duplicate member attribution:** Idris-Muhammed-Lawal is listed for both GA and ACO, giving only 4 unique names for a group described as having 5. This is flagged in Table A.1 and not altered. The notebook spells the name "Idris Muhammed-Lawal".
- **AI-assistance disclosure:** notebook cell 29 requires disclosure of AI-assisted debugging. A placeholder is in Appendix A.1. This report itself was drafted with AI assistance, so disclose that in line with your course policy.
- **References:** bibliographic details were checked against publisher, IEEE, JMLR, PubMed and library records via web search. Direct DOI resolution was blocked in the drafting environment. Two DOIs (Friedman 1937 via a Wikipedia citation; Wilcoxon 1945, 10.2307/3001968) were not confirmed from a primary record, so check them on doi.org before submission.
- Open the .docx in Microsoft Word once and confirm the pagination. The PDF was produced with LibreOffice, so Word may reflow slightly; the main report has about a third of a page of slack on page 10.

## Submission readiness
The content and formatting are complete. The report is **not fully submission-ready** until the group confirms the runtime source, the membership/ACO attribution and the AI-use disclosure.
