# Chinese Correlation Spine — and the Received Numbers audit

**A standalone instrument for dating Indian history by correlation with
precisely dated Chinese records — and the audit campaigns built on it,
published as the "Received Numbers" manuscript.**

Manuscript: https://github.com/atharva-chourey-lab/received-numbers

India's early chronology is famously soft: Sanskrit texts rarely date
themselves, and traditional dates can float by centuries. China, by contrast,
dated everything it touched — translation colophons give the year (sometimes
the day), catalogues fix what existed by when, pilgrims file timestamped
eyewitness reports, and dynastic annals log embassies by reign year. The Spine
collects those Chinese-dated anchors into one queryable database and turns
them into constraints on Indian dates.

## What is here

- `spine.py` — the instrument: loads the anchor database
  (`data/anchors.json`, `data/anchors.csv`, `data/eras.json`), and queries
  correlations and date constraints. `data/build_data.py` rebuilds the anchor
  database from its sources. `tests/test_spine.py` is the test suite.
- `nalanda/` — the Nalanda audit: the famous "10,000 students" figure traced
  bearer-by-bearer (`NALANDA-STATS.md`, `numbers.csv`). The attribution itself
  was settled by Beal's translations (1884/1911); the audit documents that
  modern textbooks still miscredit Xuanzang directly.
- `campaign/`, `campaign2/` — two audit campaigns applying the same
  bearer-tracing method (after Rekdal 2014, Sutton 2010, Greenberg 2009) to a
  defined set of received historical figures: 37 cases in total, each graded
  with its correction record (`CORRECTIONS.md`, `CORRECTIONS2.md`) under
  pre-registrations (`CAMPAIGN-PREREG.md`, `CAMPAIGN2-PREREG.md`).
- `bodhidharma/`, `medicine/`, `thomas/`, `malabar-mosque/` — further
  correlation case files built on the Spine.
- `exports/panel.csv` — an exported panel view of the anchors.

## How to run

```bash
python3 spine.py            # CLI / query entry point — see spine.py header
python3 -m pytest tests/    # test suite (needs pytest)
python3 data/build_data.py  # rebuild the anchor database
```

Pure Python 3, standard library only for the core instrument.

## Status

Working research instrument, in active use by the lab. The anchor data are
historical facts drawn from published translations and catalogues, named per
anchor in the data files.

## Authorship and licence

**Author:** Atharva Chourey, Atharva Chourey Lab (independent research lab)

The Atharva Chourey Lab is a human–AI collaboration: Atharva Chourey works with
Lapis (Muse), an AI research partner. All results are framed as the
collaboration's.

Code in this repository is released under the **MIT License** (see `LICENSE`).
The associated manuscripts are published separately under CC BY 4.0 — the code
licence and the paper licence are deliberately different.
