# quick n dirty setup

if for any reason you want to use following notebooks
(these are primarily just for hacky implementation / data research),
do the following

## environment setup

I personally use uv for all of my python project setup, but use pip if preferred

### for uv

(assuming you installed uv already via a package manager)  

run `uv sync` to initialize a .venv with the pinned enviroment and packages

### for pip

create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # on windows: .venv\Scripts\activate
pip install -e .
```

## register .venv as ipykernel

### with uv

uv handles the environment for you, just run:

```bash
uv run python -m ipykernel install --user --name nana_nalu_notebooks --display-name 'Python (Nana Nalu Notebooks)'
```

### with pip

activate your venv first, then install the kernel:

```bash
source .venv/bin/activate  # on windows: .venv\Scripts\activate
python -m ipykernel install --user --name nana_nalu_notebooks --display-name 'Python (Nana Nalu Notebooks)'
```

## running jupyter

### with uv

no need to activate anything, uv manages the environment:

```bash
uv run jupyter lab
```

### with pip

activate the venv first:

```bash
source .venv/bin/activate  # on windows: .venv\Scripts\activate
jupyter lab
```
