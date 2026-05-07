# Supported Python Packages

Pure Python packages are installed from pip and validated by
functional tests. They are split across two requirements files.

> Packages listed without a version are unpinned and install the latest
> compatible release at build time. To pin all versions, edit the
> requirements files directly.
>
> **Note:** C extension packages (NumPy, cffi, cymem, reportlab) have
> been temporarily removed. Packages with optional C accelerators
> (MarkupSafe, charset-normalizer, PyYAML, msgpack, wrapt) are included
> and use their pure Python fallback.

## Base Packages

Source: [`requirements/site-packages-base.txt`](../requirements/site-packages-base.txt)

### Core utilities, typing, networking, data, NLP ecosystem support

| Package            | Version |
| ------------------ | ------- |
| attrs              | 23.2.0  |
| filelock           | 3.20.0  |
| immutabledict      | —       |
| ordered-set        | 4.1.0   |
| packaging          | 23.2    |
| schedule           | 1.2.2   |
| setuptools         | 75.8.0  |
| tenacity           | —       |
| toolz              | 0.12.1  |
| tqdm               | —       |
| wheel              | 0.45.1  |
| annotated-types    | 0.7.0   |
| iniconfig          | 2.3.0   |
| ply                | 3.11    |
| pyparsing          | 3.1.1   |
| typing-extensions  | 4.15.0  |
| typing-inspection  | 0.4.2   |
| certifi            | —       |
| charset-normalizer | 3.4.4   |
| cloudpathlib       | 0.23.0  |
| fsspec             | —       |
| idna               | 3.11    |
| markdown           | —       |
| markdown-it-py     | 4.0.0   |
| MarkupSafe         | 2.1.5   |
| mdurl              | 0.1.2   |
| pygments           | —       |
| srt                | 3.5.3   |
| striprtf           | 0.0.20  |
| tabulate           | 0.8.10  |
| absl-py            | 2.3.1   |
| flatbuffers        | —       |
| gast               | 0.6.0   |
| namex              | 0.1.0   |
| opt-einsum         | 3.4.0   |
| mpmath             | 1.3.0   |
| networkx           | 3.4.2   |
| pytz               | 2024.1  |
| tzdata             | 2024.1  |
| click              | 8.3.0   |
| lazy-loader        | 0.4     |
| langcodes          | 3.5.0   |
| shellingham        | 1.5.4   |
| six                | 1.16.0  |
| termcolor          | —       |
| chess              | 1.9.2   |
| click-plugins      | 1.1.1.2 |
| cligj              | 0.7.2   |
| et-xmlfile         | 2.0.0   |
| pycparser          | 2.23    |
| spacy-legacy       | 3.0.12  |
| spacy-loggers      | 1.0.5   |
| wasabi             | 1.1.3   |
| hypothesis         | 6.152.4 |
| sortedcontainers   | 2.4.0   |
| cycler             | 0.12.1  |
| entrypoints        | 0.4     |
| fpdf               | 1.7.2   |
| joblib             | 1.3.2   |
| pluggy             | 1.6.0   |

## Extra Packages

Source: [`requirements/site-packages-extra.txt`](../requirements/site-packages-extra.txt)

### Web, serialisation, templating, scientific, spreadsheet

| Package          | Version |
| ---------------- | ------- |
| beautifulsoup4   | —       |
| chardet          | 5.2.0   |
| flask            | —       |
| html5lib         | —       |
| itsdangerous     | —       |
| requests         | —       |
| soupsieve        | —       |
| urllib3          | —       |
| webencodings     | —       |
| werkzeug         | —       |
| dataclasses-json | —       |
| defusedxml       | —       |
| isodate          | —       |
| jmespath         | —       |
| jsonpatch        | —       |
| jsonpointer      | —       |
| marshmallow      | —       |
| msgpack          | —       |
| pyyaml           | —       |
| docutils         | —       |
| fonttools        | 4.49.0  |
| Jinja2           | —       |
| pandoc           | 2.4     |
| pylatex          | 1.4.2   |
| PyPDF2           | 3.0.1   |
| pypdf            | —       |
| google-pasta     | 0.2.0   |
| nltk             | —       |
| python-dateutil  | 2.8.2   |
| sympy            | 1.12    |
| textblob         | —       |
| openpyxl         | 3.1.2   |
| plotly           | 5.20.0  |
| xlrd             | 2.0.1   |
| xlsxwriter       | —       |
| python-pptx      | 1.0.2   |
| blinker          | —       |
| catalogue        | 2.0.10  |
| colorama         | —       |
| decorator        | —       |
| more-itertools   | —       |
| mypy_extensions  | —       |
| pyaes            | —       |
| platformdirs     | —       |
| python-dotenv    | —       |
| rich             | —       |
| smart-open       | 7.5.0   |
| threadpoolctl    | 3.3.0   |
| tomli            | —       |
| typing_inspect   | —       |
| wrapt            | 2.0.1   |
| plumbum          | 1.9.0   |

### Locale and ISO data

| Package   | Version |
| --------- | ------- |
| pycountry | 26.2.16 |
