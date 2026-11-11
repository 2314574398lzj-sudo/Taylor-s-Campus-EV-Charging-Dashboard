# Deploying the dashboard to Streamlit Community Cloud (free public URL)

You only need this if the exam asks for a **live link** (usually it does not:
the PDF + code files are the submission). The full walkthrough is about ten
minutes.

## 1. Create the GitHub repository

1. Go to <https://github.com/new>.
2. Repository name: `ITS72604_FE` (any name works), visibility **Public**
   (Streamlit Cloud needs public, or a private repo connected to your account).
3. Do **not** add a README (you already have one).

## 2. Upload exactly these files

Upload the contents of this `code/` folder, keeping the structure:

```
app.py
data_pipeline.py
visualisations.py
visualisation_panels.py
section_a_q1_numpy_pandas.py
section_a_q2_functional_pipeline.py
section_a_q3_visual_charts.py
requirements.txt
README.md
.streamlit/config.toml
assets/cleaned_energy_sales_data.csv
assets/ev_campus_dataset.csv
assets/sales_data.csv
```

`assets/figures/` and `outputs/` are optional on the web (they are only needed
to reproduce the report), but uploading them does no harm.

GitHub web upload: open the repo → **Add file → Upload files** → drag the files
→ **Commit changes**. The `.streamlit` folder must be uploaded as a folder
(create it with "Add file → Create new file" and type `.streamlit/config.toml`
if the drag-and-drop skips dot-folders).

## 3. Deploy on Streamlit Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**.
3. Repository: `ThisIsMialy/ITS72604_FE` (or whatever you named it).
   Branch: `main`. Main file path: `app.py`.
4. **Deploy**. The first build takes 2–4 minutes.

You get a URL such as `https://its72604-fe-xxxx.streamlit.app` — that is the
link to put in the report (and in MyTimes if a live demo is requested).

## 4. If the build fails

* **`ModuleNotFoundError`** — a library is missing from `requirements.txt`.
* **`FileNotFoundError: assets/cleaned_energy_sales_data.csv`** — the CSV was
  not uploaded, or `assets/` is not next to `app.py`. The app rebuilds it from
  `assets/ev_campus_dataset.csv` if the raw file is present.
* **Wrong Python version** — add a `runtime.txt` containing `python-3.12`.

## 5. Keep it alive

Free apps sleep after a few days of inactivity; the first visit after that takes
about 30 seconds to wake. Open the link once before submitting.
