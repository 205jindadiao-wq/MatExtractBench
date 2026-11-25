# MatExtractBench

MatExtractBench is a benchmark designed to evaluate large language models on entity-conditioned document-level parameter extraction from materials science literature, covering two representative domains: nanozymes and perovskite solar cells (PSCs).

This work develops an automated parameter extraction framework based on [RAGFlow](https://github.com/infiniflow/ragflow) and [Ollama](https://github.com/ollama/ollama), integrating document parsing, retrieval-augmented generation, structured parameter extraction, and result saving.

To prevent cross-document information interference, each paper is processed independently and removed from the knowledge base after extraction. This workflow reduces manual intervention and improves the reproducibility of large-scale materials parameter extraction experiments.

To run from source code, follow the steps below.

## Installation

### Create a Conda environment

Use [Miniconda](https://docs.anaconda.com/miniconda/) to create the environment:

```bash
conda create -n MatExtractBench python=3.10.13 -y
```

### Activate the environment

```bash
conda activate MatExtractBench
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Configuration

Before running the experiments, ensure that RAGFlow and Ollama are installed and running.

Copy and configure `ragflows/configs.py`:

```bash
cp ragflows/configs.demo.py ragflows/configs.py
```

For Windows CMD:

```cmd
copy ragflows\configs.demo.py ragflows\configs.py
```

Modify the configuration file according to the local RAGFlow service, model settings, and dataset paths.

## Run Experiments

### 1. Main Experiment: Retrieval-Augmented Extraction

Before execution, set `PYTHONPATH` to the current project directory.

**Linux/macOS:**

```bash
export PYTHONPATH=.
python ragflows/main.py
```

**Windows CMD:**

```cmd
set PYTHONPATH=.
python ragflows/main.py
```

**Windows PowerShell:**

```powershell
$env:PYTHONPATH = "."
python ragflows/main.py
```

The script automatically processes papers through the following workflow:

```
Uploading → Parsing → Retrieval → Extraction → Saving → Clearing
```

Each document is removed from the knowledge base before the next document is processed to maintain document-level isolation during evaluation.

<details>
<summary>Troubleshooting: ModuleNotFoundError: No module named 'ragflows'</summary>

This error may occur when executing scripts directly in a terminal. Ensure that the current working directory is the project root and that `PYTHONPATH` is configured correctly using the commands above.

</details>

### 2. Comparative Experiment: Direct Parameter Extraction

Install PyMuPDF:

```bash
pip install pymupdf
```

**Nanozyme dataset:**

```bash
python nanozyme_extractor.py pdf
```

**Perovskite solar cell dataset:**

```bash
python gaitaikuang.py pdf2
```

The `pdf` directory contains nanozyme papers, while the `pdf2` directory contains perovskite solar cell papers. These scripts directly process the corresponding PDF documents and extract predefined material parameters without retrieval augmentation.

## Datasets

MatExtractBench covers two materials science domains:

- **Nanozymes:** Material composition, physicochemical properties, experimental conditions, and catalytic performance parameters.
- **Perovskite Solar Cells (PSCs):** Material composition, fabrication conditions, passivation strategies, and photovoltaic performance parameters.

The datasets are available upon reasonable request. Please contact the authors by email for access.
