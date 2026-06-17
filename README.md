## Upload documents to the RagFlow knowledge base

[RagFlow](https://github.com/infiniflow/ragflow) supports document parsing, chunking, and retrieval for LLM-based information extraction, but its default upload interface is inefficient for large-scale paper processing because files must be uploaded and parsed manually.

This work provides an automated paper-by-paper pipeline. For each paper, the script uploads it to the RagFlow knowledge base, starts parsing, performs retrieval-based parameter extraction using local LLMs deployed through Ollama, saves the results, and then removes the paper from the knowledge base before processing the next one. This design reduces manual intervention, avoids information mixing across papers, and improves reproducibility.


To run from source code, refer to the following steps:

### Use [miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install#power-shell) to create the env environment

```shell
conda create -n MatExtractBench python=3.10.13 -y
```

### Activate the environment

```shell
conda activate MatExtractBench
```

### Install dependencies

```shell
pip install -r requirements.txt
```

## Copy and configure [ragflows/configs.py](ragflows/configs.py)

For an explanation of the configuration file, refer to this: [issues #2](https://github.com/Samge0/ragflow-upload/issues/2)

```shell
cp ragflows/configs.demo.py ragflows/configs.py
```

### Upload documents

```shell
python ragflows/main.py
```

### FAQ

<details> <summary> Script execution prompts: ModuleNotFoundError: No module named 'ragflows' </summary>

> This problem is generally not encountered when executing in `vscode`/`pycharm` or other IDEs, but it may occur when executing directly in a terminal window.

Run

1. Main experiment: RagFlow retrieval-augmented extraction

Before execution, temporarily point `PYTHONPATH` to the current project directory.

Linux/macOS:

```bash
export PYTHONPATH=.
python ragflows/main.py
```

Windows CMD:

```shell
set PYTHONPATH=.
python ragflows/main.py
```

Windows PowerShell:

```shell
$env:PYTHONPATH = "."
python ragflows/main.py
```

This script uploads papers to the RagFlow knowledge base one by one, completes parsing, retrieval, parameter extraction, and result saving, and automatically clears the current paper after extraction before processing the next paper.

2. Comparative experiment

pip install pymupdf
Nanozyme dataset:

```bash
python nanozyme_extractor.py  pdf
```

Perovskite dataset:

```bash
python gaitaikuang.py pdf2
```

Among them, the `pdf` folder stores nanozyme papers, and the `pdf2` folder stores perovskite papers. The scripts directly read the corresponding PDF papers and perform parameter extraction.

</details>

Datasets:
The dataset is available upon request. Please contact the author by email if you need access to it.
