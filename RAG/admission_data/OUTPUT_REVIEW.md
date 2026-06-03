## Output Review

Review of the current clean data package for backend, product, and AI/RAG use.
Source website: `https://collegedunia.com/`

## Current Scope
- Reviewed school-page list: `1421` schools
- Countries: `16`
- Main countries: `usa`, `canada`, `germany`, `uk`, `australia`

## Country Summary
- `usa`: `933` schools
- `canada`: `113` schools
- `germany`: `100` schools
- `uk`: `79` schools
- `australia`: `44` schools
- `malaysia`: `23` schools
- `uae`: `20` schools
- `sweden`: `21` schools
- `new-zealand`: `13` schools
- `ireland`: `19` schools
- `netherlands`: `19` schools
- `france`: `15` schools
- `italy`: `14` schools
- `hong-kong`: `12` schools
- `singapore`: `9` schools
- `switzerland`: `1` school

## Final Data Files
- [`data/clean/programs/programs.csv`](/Users/mollymac/Desktop/ioffer/admission_data/data/clean/programs/programs.csv)
  Main one-row-per-program dataset.
- [`data/clean/admission_pages/admission_pages.csv`](/Users/mollymac/Desktop/ioffer/admission_data/data/clean/admission_pages/admission_pages.csv)
  School-level admission details from `/admission` pages.
- [`data/clean/school_pages/school_pages.csv`](/Users/mollymac/Desktop/ioffer/admission_data/data/clean/school_pages/school_pages.csv)
  School-page layer for school overview, highlights, and curated school summaries.

## Coverage Summary
- Program rows: `82,111`
- Schools with program output: `1,418`
- Admission fact rows: `54,767`
- Schools with cleaned admission output: `1,421`
- Fact rows in school-page layer: `48,335`
- Schools represented in school-page layer: `1,421`

## Program Quality
- Average programs per school: `57.91`
- Schools with `10+` programs: `1,232`
- Schools with `20+` programs: `1,073`
- Schools with `50+` programs: `623`
- Schools with `100+` programs: `228`

Assessment:
- `programs.csv` is the strongest dataset in the project.
- This is already good enough to support program search, consultant workflows, and RAG answers focused on program choice.

## Admission Quality
Admission facts are useful, but weaker than programs.

School coverage:
- Schools with admission facts: `1,421`

Field coverage:
- Schools with tuition: `1,064`
- Schools with exam requirement: `1,040`
- Schools with deadline: `713`
- Schools with scholarship: `398`
- Schools with acceptance rate: `284`

Assessment:
- Good for school-level admission guidance.
- Not every school has a strong Collegedunia `/admission` page.
- Lower-traffic schools often have thin or weak admission content.

## School Homepage Layer
`school_pages.csv` should be treated as the school-page context layer.

Current state:
- Useful for school overview, key highlights, rankings, tuition context, scholarship mentions, and curator-edited school summaries.
- Some lower-value or thin pages were intentionally left unresolved rather than forcing bad extractions.

Assessment:
- Useful for school context and homepage identity.
- Not as strong as `programs.csv` for detailed retrieval.
- Not as reliable as `admission_pages.csv` for school-level deadlines or requirements.

## Backend Guidance
Recommended primary keys:
- `school_id`
- `school_num_id`
- school homepage URL

Recommended backend model:
- `schools`
  Use the reviewed school-page/program package plus the raw crawl inventory when needed.
- `programs`
  Use `programs.csv` as the main searchable table.
- `school_admissions`
  Use `admission_pages.csv` as the school-level admissions table.
- `school_pages`
  Use `school_pages.csv` only as supplemental context.

Recommended retrieval priority:
1. `programs.csv`
2. `admission_pages.csv`
3. `school_pages.csv`
4. reviewed school identity input when needed

## Product Guidance
Best user-facing use cases right now:
- find programs by degree level
- compare tuition across programs
- answer duration and entry requirement questions
- answer school-level admission questions when available

Good product framing:
- strong program coverage
- useful school-level admission support
- uneven scholarship / acceptance-rate coverage

Do not oversell:
- full school-homepage richness for every school
- full admission coverage for every school
- perfect scholarship depth for every school

## Known Limits
- Some admission pages contain light program-like snippets.
- Some schools have weak or nearly empty `/admission` pages on Collegedunia.
- Scholarship coverage is meaningful but not comprehensive.
- `school_pages.csv` is not equally rich for every school.

## Submission Readiness
This package is ready for a strong v1 submission if the product goal is:
- school consultant agent
- program discovery
- admission support
- RAG over school + program + admission content
