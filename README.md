## Upload documents to the RagFlow knowledge base

[RagFlow](https://github.com/infiniflow/ragflow) is an LLM-based question-answering system that can quickly build an intelligent question-answering platform. However, the default knowledge-base upload interface of RagFlow has certain limitations: only a limited number of files can be uploaded each time, and the parsing process usually needs to be started manually after uploading. When processing a large number of materials-science papers, manually uploading, parsing, and managing documents in batches becomes cumbersome and may also increase the cost of manual operations.

To simplify this process, I wrote an automated script to traverse the materials-science papers in a specified directory and complete knowledge-base construction and parameter extraction in a paper-by-paper manner. Specifically, the system first uploads one paper to the RagFlow knowledge base and immediately starts the parsing process to perform chunking and build a retrieval index for the paper content; then, it calls the local large language model deployed through Ollama to extract the required information from the paper according to predefined parameter fields, and saves the extraction results for subsequent comparison and performance evaluation.

To avoid information mixing between different papers, after completing parameter extraction for the current paper, the system automatically deletes the paper from the RagFlow knowledge base and continues to read the next paper, repeatedly executing the workflow of “uploading—parsing—retrieval—extraction—saving—clearing”. Through this paper-by-paper iterative process, each extraction is guaranteed to be based only on the current paper content, reducing knowledge-base contamination while significantly lowering manual intervention and improving the automation and reproducibility of large-scale materials-literature parameter extraction tasks.

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
