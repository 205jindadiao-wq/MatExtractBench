## 上传文档到RagFlow知识库
[RagFlow](https://github.com/infiniflow/ragflow)是一个基于 LLM 的问答系统，能够快速构建智能问答平台。然而，RagFlow 默认的知识库上传界面存在一定局限性：每次只能上传有限数量的文件，并且上传后通常需要手动启动解析流程。当需要处理大量材料领域论文时，手动分批上传、解析和管理文档会显得较为繁琐，也容易增加人工操作成本。

为了简化这一过程，我编写了一个自动化脚本，用于遍历指定目录中的材料领域论文，并按照逐篇处理的方式完成知识库构建与参数抽取。具体而言，系统首先将一篇论文上传至 RagFlow 知识库，并立即启动解析流程，对论文内容进行切块和检索索引构建；随后，调用通过 Ollama 部署的本地大模型，根据预设参数字段从该论文中提取所需信息，并将抽取结果保存，用于后续结果对比和性能评估。

为避免不同论文之间的信息混杂，在完成当前论文的参数抽取后，系统会自动将该论文从 RagFlow 知识库中删除，并继续读取下一篇论文，重复执行“上传—解析—检索—抽取—保存—清空”的流程。通过这种逐篇迭代的方式，可以保证每次抽取仅基于当前论文内容，减少知识库污染，同时显著降低人工干预，提高大规模材料文献参数抽取任务的自动化程度和可复现性。



如果需要以源码方式运行，可参考下面几个步骤：

### 使用[miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install#power-shell)创建env环境
```shell
conda create -n MatExtractBench python=3.10.13 -y
```

### 激活环境
```shell
conda activate MatExtractBench
```

### 安装依赖
```shell
pip install -r requirements.txt
```

## 复制并配置[ragflows/configs.py](ragflows/configs.py)
关于配置文件的说明可参考这个：[issues #2](https://github.com/Samge0/ragflow-upload/issues/2)
```shell
cp ragflows/configs.demo.py ragflows/configs.py
```

### 上传文档
```shell
python ragflows/main.py
```

### 常见问题
<details> <summary> 执行脚本提示: ModuleNotFoundError: No module named 'ragflows' </summary>

> 一般在`vscode`/`pycharm`或者其他IDE中执行时不会遇到这个问题，但如果直接在终端窗口中执行时可能会遇到。

 Run

 1. 主实验：RagFlow 检索增强抽取

执行前需将 `PYTHONPATH` 临时指向当前项目目录。

Linux/macOS：

```bash
export PYTHONPATH=.
python ragflows/main.py
```

Windows CMD：

```shell
set PYTHONPATH=.
python ragflows/main.py
```

Windows PowerShell：

```shell
$env:PYTHONPATH = "."
python ragflows/main.py
```

该脚本会逐篇上传论文至 RagFlow 知识库，完成解析、检索、参数抽取、结果保存，并在抽取完成后自动清空当前论文，再处理下一篇论文。

 2. 对比实验

pip install pymupdf
纳米酶数据集：

```bash
python nanozyme_extractor.py  pdf
```

钙钛矿数据集：

```bash
python gaitaikuang.py pdf2
```

其中，`pdf` 文件夹存放纳米酶论文，`pdf2` 文件夹存放钙钛矿论文。脚本会直接读取对应 PDF 文献并进行参数抽取。

</details>

Datasets:
The dataset is available upon request. Please contact the author by email if you need access to it.





